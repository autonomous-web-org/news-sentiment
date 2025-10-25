"""
Creates MySQL tables and yearly date partitions on PythonAnywhere over an SSH tunnel.

Prereqs:
  pip install sshtunnel PyMySQL python-dotenv
"""

import sys
import os
import csv
import datetime as dt
from typing import Tuple, List
from datetime import datetime, timezone
from dotenv import load_dotenv
from contextlib import contextmanager
from sshtunnel import SSHTunnelForwarder
import pymysql
import re

load_dotenv()

# -----------------------------
# Configuration (edit these)
# -----------------------------
SSH_HOST = "ssh.pythonanywhere.com"      # or "ssh.eu.pythonanywhere.com"
SSH_USERNAME = "username"
SSH_PASSWORD = ""    # PythonAnywhere SSH/password auth

PA_DB_HOST = SSH_USERNAME + ".mysql.pythonanywhere-services.com"  # or *.eu.* for EU
PA_DB_USER = SSH_USERNAME
PA_DB_PASSWORD = "adf"
PA_DB_NAME = SSH_USERNAME+"$default"

# Partition years to create (inclusive range + MAXVALUE)
FIRST_YEAR = 2023
LAST_YEAR = dt.date.today().year + 3

# -----------------------------
# SQL DDL - Updated with separate ID for uniqueness
# -----------------------------
DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS exchanges (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      code VARCHAR(32) NOT NULL UNIQUE,
      name VARCHAR(255),
      timezone VARCHAR(64),
      currency VARCHAR(16)
    ) ENGINE=InnoDB;
    """,
    """
    CREATE TABLE IF NOT EXISTS tickers (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      exchange_id BIGINT NOT NULL,
      symbol VARCHAR(64) NOT NULL,
      name VARCHAR(255),
      isin VARCHAR(32),
      sector VARCHAR(128),
      currency VARCHAR(16),
      active BOOLEAN NOT NULL DEFAULT TRUE,
      first_trade_date DATE,
      last_updated DATETIME(3),
      UNIQUE KEY uq_exchange_symbol (exchange_id, symbol),
      INDEX idx_tickers_exchange (exchange_id)
    ) ENGINE=InnoDB;
    """,
    """
    CREATE TABLE IF NOT EXISTS ticker_sentiment_cursor (
      ticker_id BIGINT NOT NULL,
      last_updated DATETIME(3) NOT NULL,
      PRIMARY KEY (ticker_id)
    ) ENGINE=InnoDB;
    """,
    # Separate ID as PK, UNIQUE on (ticker_id, date) for business uniqueness
    """
    CREATE TABLE IF NOT EXISTS sentiment_daily (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      ticker_id BIGINT NOT NULL,
      date DATE NOT NULL,
      sentiment SMALLINT NOT NULL,
      last_updated DATETIME(3) NOT NULL,
      UNIQUE KEY uq_ticker_date (ticker_id, date),
      INDEX idx_ticker (ticker_id),
      INDEX idx_date (date)
    ) ENGINE=InnoDB;
    """
]

def partition_clause_for_years(first_year: int, last_year: int) -> str:
    """Generate partition clause for yearly date partitions."""
    parts = []
    for y in range(first_year, last_year + 1):
        cutoff = f"{y+1}-01-01"
        parts.append(f"  PARTITION p{y} VALUES LESS THAN ('{cutoff}')")
    parts.append("  PARTITION pmax VALUES LESS THAN (MAXVALUE)")
    return "PARTITION BY RANGE COLUMNS(date) (\n" + ",\n".join(parts) + "\n)"

# Updated ALTER statement for partitioning
ALTER_TO_PARTITION = f"""
ALTER TABLE sentiment_daily
{partition_clause_for_years(FIRST_YEAR, LAST_YEAR)};
"""

def rebuild_partitions_if_needed(cur):
    """Check if table is partitioned and create partitions if needed."""
    cur.execute("""
        SELECT PARTITION_NAME
        FROM INFORMATION_SCHEMA.PARTITIONS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'sentiment_daily'
        ORDER BY PARTITION_ORDINAL_POSITION
    """)
    rows = cur.fetchall()
    already_partitioned = len([r for r in rows if r[0] is not None]) > 1

    if not already_partitioned:
        cur.execute("SELECT COUNT(*) FROM sentiment_daily")
        count = cur.fetchone()[0]
        if count != 0:
            print("Warning: sentiment_daily table has data. Partitioning may fail.")
            return False
        try:
            cur.execute(ALTER_TO_PARTITION)
            print(f"Successfully partitioned sentiment_daily for years {FIRST_YEAR}-{LAST_YEAR}")
            return True
        except Exception as e:
            print(f"Failed to partition table: {e}")
            return False
    else:
        print("Table is already partitioned.")
        return True

@contextmanager
def mysql_conn_over_ssh():
    """Create MySQL connection over SSH tunnel to PythonAnywhere."""
    with SSHTunnelForwarder(
        (SSH_HOST, 22),
        ssh_username=SSH_USERNAME,
        ssh_password=SSH_PASSWORD,
        remote_bind_address=(PA_DB_HOST, 3306),
        set_keepalive=10.0
    ) as tunnel:
        local_port = tunnel.local_bind_port
        conn = pymysql.connect(
            host="127.0.0.1",
            port=local_port,
            user=PA_DB_USER,
            password=PA_DB_PASSWORD,
            database=PA_DB_NAME,
            charset="utf8mb4",
            autocommit=True,
            local_infile=True  # Enable for LOAD DATA LOCAL INFILE
        )
        try:
            yield conn
        finally:
            conn.close()

# ----------------------------- 
# Sanitizers for invisible chars
# -----------------------------
ZW_INVISIBLES = (
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\ufeff",  # BOM
    "\u2060",  # word joiner
)

def clean_invisibles(text: str) -> str:
    if not isinstance(text, str):
        return text
    for ch in ZW_INVISIBLES:
        text = text.replace(ch, "")
    return text

def parse_sentiment(raw: str) -> int:
    # Remove invisible chars, then keep only sign and digits
    s = clean_invisibles(raw).strip()
    s = re.sub(r"[^\+\-\d]", "", s)
    if not re.fullmatch(r"[+\-]?\d+", s):
        raise ValueError(f"not an int: {raw!r}")
    return int(s)

# --------------- DB helpers: get-or-create ---------------
def ensure_exchange(cur, code: str) -> int:
    """Get or create exchange and return ID."""
    cur.execute("SELECT id FROM exchanges WHERE code = %s", (code.lower(),))
    row = cur.fetchone()
    if row:
        return row[0] if isinstance(row, tuple) else row["id"]
    cur.execute("INSERT INTO exchanges (code) VALUES (%s)", (code.lower(),))
    return cur.lastrowid

def ensure_ticker(cur, exchange_id: int, symbol: str) -> int:
    """Get or create ticker and return ID."""
    cur.execute("""
        SELECT id FROM tickers
        WHERE exchange_id = %s AND symbol = %s
    """, (exchange_id, symbol.upper()))
    row = cur.fetchone()
    if row:
        return row[0] if isinstance(row, tuple) else row["id"]
    cur.execute("""
        INSERT INTO tickers (exchange_id, symbol, active, last_updated)
        VALUES (%s, %s, 1, NOW(3))
    """, (exchange_id, symbol.upper()))
    return cur.lastrowid

# --------------- CSV ingestion using executemany (recommended) ---------------
def load_csv_with_executemany(conn, ticker_id: int, csv_path: str, batch_size: int = 1000) -> int:
    """
    Reads date,sentiment CSV and upserts into sentiment_daily in batches.
    Uses INSERT ... ON DUPLICATE KEY UPDATE for idempotency on (ticker_id, date).
    Returns number of processed rows (attempted inserts/updates).
    """
    total_processed = 0

    upsert_sql = """
        INSERT INTO sentiment_daily (ticker_id, date, sentiment, last_updated)
        VALUES (%s, %s, %s, NOW(3))
        ON DUPLICATE KEY UPDATE
          sentiment = VALUES(sentiment),
          last_updated = VALUES(last_updated)
    """

    batch: List[Tuple[int, str, int]] = []

    # Use utf-8-sig to transparently consume a UTF-8 BOM if present
    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f, conn.cursor() as cur:
        rdr = csv.reader(f)
        header = next(rdr, None)  # Skip header row

        for row in rdr:
            if not row or len(row) < 2:
                continue

            d_raw, s_raw = row[0], row[1]
            d = clean_invisibles(d_raw).strip()
            s_clean = clean_invisibles(s_raw)

            if not d or not s_clean:
                continue

            try:
                # Validate date format (ISO format expected)
                datetime.strptime(d, "%Y-%m-%d")
                s_int = parse_sentiment(s_clean)

                # Optional: validate sentiment range if desired
                if -100 <= s_int <= 100:
                    batch.append((ticker_id, d, s_int))
                else:
                    print(f"Warning: Out-of-range sentiment {s_int} in {csv_path} ({d})")
            except ValueError as e:
                print(f"Warning: Skipping invalid row in {csv_path}: {row} - {e}")
                continue
            except Exception as e:
                print(f"Warning: Unexpected error processing row in {csv_path}: {row} - {e}")
                continue

            if len(batch) >= batch_size:
                try:
                    cur.executemany(upsert_sql, batch)
                    total_processed += len(batch)
                    batch.clear()
                except Exception as e:
                    print(f"Error inserting batch for {csv_path}: {e}")
                    break

        # Process remaining batch
        if batch:
            try:
                cur.executemany(upsert_sql, batch)
                total_processed += len(batch)
            except Exception as e:
                print(f"Error inserting final batch for {csv_path}: {e}")

    print(f"  Processed rows (inserts+updates attempted): {total_processed}")
    return total_processed

# --------------- Alternative: CSV ingestion via LOAD DATA LOCAL INFILE ---------------
def load_csv_with_load_data(conn, ticker_id: int, csv_path: str) -> int:
    """
    Fast path using LOAD DATA LOCAL INFILE directly into sentiment_daily.
    Strips zero-width spaces and BOM in SET clause, then casts to SIGNED.
    Returns approximate number of processed rows.
    """
    # Strip U+200B/U+200C/U+200D and UTF‑8 BOM bytes before CAST
    load_sql = f"""
    LOAD DATA LOCAL INFILE %s
    INTO TABLE sentiment_daily
    FIELDS TERMINATED BY ',' 
    OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\\n'
    IGNORE 1 LINES
    (@date_str, @sentiment_str)
    SET
      ticker_id = {int(ticker_id)},
      date = STR_TO_DATE(@date_str, '%Y-%m-%d'),
      sentiment = CAST(
        REPLACE(
          REPLACE(
            REPLACE(
              REPLACE(@sentiment_str, x'E2808B',''),  -- U+200B
            x'E2808C',''),                            -- U+200C
          x'E2808D',''),                              -- U+200D
        x'EFBBBF','')                                 -- BOM
        AS SIGNED
      ),
      last_updated = NOW(3)
    """

    try:
        with conn.cursor() as cur:
            cur.execute(load_sql, (os.path.abspath(csv_path),))
            processed = cur.rowcount or 0
            print(f"  LOAD DATA processed ~{processed} rows (inserts + updates)")
            return processed
    except Exception as e:
        print(f"LOAD DATA failed for {csv_path}: {e}")
        return 0

# --------------- Cursor updater from JSON ---------------
def update_cursor_from_json(conn, json_path: str, exchange_code: str) -> None:
    """
    Reads tickers_last_updated.json [{ticker, lastUpdated}] and updates ticker_sentiment_cursor.
    Also ensures exchange/tickers exist.
    """
    import json

    try:
        with open(json_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {json_path}: {e}")
        return

    if not isinstance(data, list):
        print(f"Warning: {json_path} is not a list of objects")
        return

    with conn.cursor() as cur:
        ex_id = ensure_exchange(cur, exchange_code)
        updated_count = 0

        for obj in data:
            ticker = clean_invisibles((obj.get("ticker") or obj.get("symbol") or "")).strip()
            ms = obj.get("lastUpdated") or obj.get("last_updated")

            if not ticker or ms is None:
                continue

            try:
                ms_int = int(ms)
            except (ValueError, TypeError):
                print(f"Warning: Invalid timestamp for ticker {ticker}: {ms}")
                continue

            tid = ensure_ticker(cur, ex_id, ticker)

            try:
                dt_utc = datetime.fromtimestamp(ms_int / 1000.0, tz=timezone.utc)
                dt_midnight = datetime(dt_utc.year, dt_utc.month, dt_utc.day, tzinfo=timezone.utc)

                cur.execute("""
                    INSERT INTO ticker_sentiment_cursor (ticker_id, last_updated)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE last_updated = VALUES(last_updated)
                """, (tid, dt_midnight))
                updated_count += 1
            except Exception as e:
                print(f"Error processing cursor for {ticker}: {e}")
                continue

        print(f"Updated sentiment cursors for {updated_count} tickers from {json_path}")

# --------------- High-level directory migrator ---------------
def migrate_data_dir(conn, data_root: str, use_load_data: bool = False) -> None:
    """
    Scans {data_root}/{exchange}/ for *.csv and tickers_last_updated.json and loads them.
    - Ensures exchange and tickers exist.
    - Loads CSVs into sentiment_daily.
    - Updates ticker_sentiment_cursor from JSON.
    """
    if not os.path.exists(data_root):
        print(f"Error: Data directory {data_root} does not exist")
        return

    exchange_count = 0
    total_csvs = 0
    total_rows = 0

    for exchange_code in sorted(os.listdir(data_root)):
        ex_dir = os.path.join(data_root, exchange_code)
        if not os.path.isdir(ex_dir):
            continue

        print(f"\nProcessing exchange: {exchange_code}")
        exchange_count += 1

        json_path = os.path.join(ex_dir, "tickers_last_updated.json")
        if os.path.isfile(json_path):
            print(f"  Updating cursors from {json_path}")
            update_cursor_from_json(conn, json_path, exchange_code)
        else:
            print(f"  No cursor JSON found at {json_path}")

        csv_files = [f for f in os.listdir(ex_dir) if f.lower().endswith(".csv")]
        csv_files.sort()

        if not csv_files:
            print(f"  No CSV files found in {ex_dir}")
            continue

        print(f"  Found {len(csv_files)} CSV files")
        total_csvs += len(csv_files)

        for name in csv_files:
            ticker = os.path.splitext(name)[0]
            csv_path = os.path.join(ex_dir, name)

            with conn.cursor() as cur:
                ex_id = ensure_exchange(cur, exchange_code)
                tid = ensure_ticker(cur, ex_id, ticker)
                print(f"  Processing {ticker} ({tid}) from {name}...")

            if use_load_data:
                processed = load_csv_with_load_data(conn, tid, csv_path)
            else:
                processed = load_csv_with_executemany(conn, tid, csv_path)

            total_rows += processed
            print(f"    -> Loaded {processed} rows")

    print(f"\n=== Migration Summary ===")
    print(f"Exchanges processed: {exchange_count}")
    print(f"CSV files processed: {total_csvs}")
    print(f"Total rows processed: {total_rows}")
    if use_load_data:
        print("Note: LOAD DATA counts are approximate (inserts + updates)")

# --------------- Main execution ---------------
def main():
    """Main execution function."""
    print("Starting database migration...")
    print(f"Target: {PA_DB_NAME} on PythonAnywhere")
    print(f"Data directory: ./data")
    print(f"Years to partition: {FIRST_YEAR}-{LAST_YEAR}")
    print("-" * 50)

    try:
        with mysql_conn_over_ssh() as conn:
            cur = conn.cursor()

            # Create tables (if not exists)
            print("Creating/ensuring database schema...")
            for i, ddl in enumerate(DDL_STATEMENTS, 1):
                try:
                    print(f"  Executing DDL {i}/{len(DDL_STATEMENTS)}...")
                    cur.execute(ddl)
                    print(f"    ✓ {ddl.splitlines()[0].strip()}")
                except Exception as e:
                    print(f"    ! DDL {i} warning: {e}")

            # Set up partitioning
            print("\nSetting up table partitioning...")
            partition_success = rebuild_partitions_if_needed(cur)

            if partition_success:
                cur.execute("""
                    SELECT PARTITION_NAME, TABLE_ROWS 
                    FROM INFORMATION_SCHEMA.PARTITIONS 
                    WHERE TABLE_SCHEMA = DATABASE() 
                      AND TABLE_NAME = 'sentiment_daily'
                    ORDER BY PARTITION_ORDINAL_POSITION
                """)
                partitions = cur.fetchall()
                print(f"  Partitions created: {len(partitions)}")
                for part in partitions[:5]:
                    print(f"    {part[0]}: {part[1] or 0} rows")
                if len(partitions) > 5:
                    print(f"    ... and {len(partitions) - 5} more")

            # Migrate data files
            print("\n" + "="*50)
            print("Starting data migration...")
            data_root = "./data"
            use_load_data = False  # Set to True for faster loading (less validation)

            if use_load_data:
                print("Using LOAD DATA LOCAL INFILE (fast, less validation)")
            else:
                print("Using executemany (safer, more validation)")

            migrate_data_dir(conn, data_root, use_load_data=use_load_data)

            # Final verification
            print("\nVerifying final data counts...")
            cur.execute("""
                SELECT 
                    t.symbol,
                    COUNT(s.id) as row_count,
                    MIN(s.date) as first_date,
                    MAX(s.date) as last_date
                FROM tickers t
                LEFT JOIN sentiment_daily s ON t.id = s.ticker_id
                WHERE t.active = 1
                GROUP BY t.id, t.symbol
                ORDER BY row_count DESC
                LIMIT 10
            """)
            results = cur.fetchall()

            if results:
                print("\nTop 10 tickers by row count:")
                for row in results:
                    print(f"  {row[0]}: {row[1]} rows ({row[2]} to {row[3]})")

            print("\n" + "="*50)
            print("Migration completed successfully!")
            print("To verify all data:")
            print("SELECT COUNT(*) FROM sentiment_daily;")
            print("SELECT COUNT(DISTINCT ticker_id) FROM sentiment_daily;")

    except KeyboardInterrupt:
        print("\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError during migration: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
