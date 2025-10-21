"""
Creates MySQL tables and yearly date partitions on PythonAnywhere over an SSH tunnel.

Prereqs:
  pip install sshtunnel PyMySQL
"""

import sys
import os
import csv
import datetime as dt
from typing import Optional, Tuple, List, Dict, Set
from datetime import datetime, timezone
from dotenv import load_dotenv
from contextlib import contextmanager
from sshtunnel import SSHTunnelForwarder
import pymysql


load_dotenv()

# -----------------------------
# Configuration (edit these)
# -----------------------------
SSH_HOST = "ssh.pythonanywhere.com"      # or "ssh.eu.pythonanywhere.com"
SSH_USERNAME = "username"
SSH_PASSWORD = ""    # PythonAnywhere SSH/password auth

PA_DB_HOST = SSH_USERNAME+".mysql.pythonanywhere-services.com"  # or *.eu.* for EU
PA_DB_USER = SSH_USERNAME
PA_DB_PASSWORD = ""
PA_DB_NAME = "username$default"

# Partition years to create (inclusive range + MAXVALUE)
FIRST_YEAR = 2019
LAST_YEAR = dt.date.today().year + 6

# -----------------------------
# SQL DDL
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
    # Create unpartitioned base first to allow ALTER to partitioning
    """
    CREATE TABLE IF NOT EXISTS sentiment_daily (
      ticker_id BIGINT NOT NULL,
      date DATE NOT NULL,
      sentiment SMALLINT NOT NULL,
      last_updated DATETIME(3) NOT NULL,
      PRIMARY KEY (ticker_id, date)
    ) ENGINE=InnoDB;
    """
]

def partition_clause_for_years(first_year: int, last_year: int) -> str:
    parts = []
    for y in range(first_year, last_year + 1):
        cutoff = f"{y+1}-01-01"
        parts.append(f"  PARTITION p{y} VALUES LESS THAN ('{cutoff}')")
    parts.append("  PARTITION pmax VALUES LESS THAN (MAXVALUE)")
    return "PARTITION BY RANGE COLUMNS(date) (\n" + ",\n".join(parts) + "\n)"

ALTER_TO_PARTITION = f"""
ALTER TABLE sentiment_daily
{partition_clause_for_years(FIRST_YEAR, LAST_YEAR)};
"""

def rebuild_partitions_if_needed(cur):
    # Check if partitioned already
    cur.execute("""
        SELECT PARTITION_NAME
        FROM INFORMATION_SCHEMA.PARTITIONS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'sentiment_daily'
        ORDER BY PARTITION_ORDINAL_POSITION
    """)
    rows = cur.fetchall()
    already_partitioned = any(r[0] is not None for r in rows)
    if not already_partitioned:
        # Must be empty to convert to partitioned
        cur.execute("SELECT COUNT(*) FROM sentiment_daily")
        count = cur.fetchone()[0]
        if count != 0:
            raise RuntimeError("sentiment_daily is not empty; cannot convert to partitioned table safely.")
        cur.execute(ALTER_TO_PARTITION)

@contextmanager
def mysql_conn_over_ssh():
    # SSH tunnel to PythonAnywhere, forwarding MySQL host:3306 to a local port
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
        )
        try:
            yield conn
        finally:
            conn.close()


# --------------- DB helpers: get-or-create ---------------

def ensure_exchange(cur, code: str) -> int:
    cur.execute("SELECT id FROM exchanges WHERE code = %s", (code.lower(),))
    row = cur.fetchone()
    if row:
        return row[0] if isinstance(row, tuple) else row["id"]
    cur.execute("INSERT INTO exchanges (code) VALUES (%s)", (code.lower(),))
    return cur.lastrowid

def ensure_ticker(cur, exchange_id: int, symbol: str) -> int:
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

# --------------- CSV ingestion (safe, portable) ---------------

def load_csv_with_executemany(conn, ticker_id: int, csv_path: str, batch_size: int = 1000) -> int:
    """
    Reads date,sentiment CSV and upserts into sentiment_daily in batches.
    Uses INSERT ... ON DUPLICATE KEY UPDATE for idempotency.
    """
    total = 0
    upsert_sql = """
        INSERT INTO sentiment_daily (ticker_id, date, sentiment, last_updated)
        VALUES (%s, %s, %s, NOW(3))
        ON DUPLICATE KEY UPDATE
          sentiment = VALUES(sentiment),
          last_updated = VALUES(last_updated)
    """
    batch: List[Tuple[int, str, int]] = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f, conn.cursor() as cur:
        rdr = csv.reader(f)
        header = next(rdr, None)
        # Expect header ["date","sentiment"]
        for row in rdr:
            if not row or len(row) < 2:
                continue
            d, s = row[0].strip(), row[1].strip()
            if not d:
                continue
            try:
                # Validate date format
                datetime.fromisoformat(d)
                s_int = int(s)
            except Exception:
                continue
            batch.append((ticker_id, d, s_int))
            if len(batch) >= batch_size:
                cur.executemany(upsert_sql, batch)
                total += len(batch)
                batch.clear()
        if batch:
            cur.executemany(upsert_sql, batch)
            total += len(batch)
    return total

# --------------- Optional: CSV ingestion via LOAD DATA LOCAL INFILE ---------------

def load_csv_with_load_data(conn, ticker_id: int, csv_path: str) -> int:
    """
    Fast path using LOAD DATA LOCAL INFILE directly into sentiment_daily.
    Requires local_infile=True on the PyMySQL connection and server-side allowance.
    """
    # MySQL counts affected rows differently on ON DUPLICATE; use ROW_COUNT() heuristic after the load if needed.
    # Path must be quoted, and LOCAL requires enabling in both client and server.
    q = f"""
    LOAD DATA LOCAL INFILE %s
    INTO TABLE sentiment_daily
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 LINES
    (@date_str, @sentiment)
    SET
      ticker_id = {int(ticker_id)},
      date = STR_TO_DATE(@date_str, '%Y-%m-%d'),
      sentiment = @sentiment,
      last_updated = NOW(3)
    """
    with conn.cursor() as cur:
        cur.execute(q, (csv_path,))
        # Affected rows semantics: 1 per insert, 2 per update; exact inserted vs updated split is not provided.
        # Return cursor.rowcount as a proxy for processed input lines.
        return cur.rowcount or 0

# --------------- Cursor updater from JSON ---------------

def update_cursor_from_json(conn, json_path: str, exchange_code: str):
    """
    Reads tickers_last_updated.json [{ticker, lastUpdated}] and updates ticker_sentiment_cursor.
    Also ensures exchange/tickers exist.
    """
    import json
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"{json_path} is not a list of objects")

    with conn.cursor() as cur:
        ex_id = ensure_exchange(cur, exchange_code)
        for obj in data:
            ticker = (obj.get("ticker") or obj.get("symbol") or "").strip()
            ms = obj.get("lastUpdated") or obj.get("last_updated")
            if not ticker or ms is None:
                continue
            try:
                ms_int = int(ms)
            except Exception:
                continue
            # Ensure ticker exists
            tid = ensure_ticker(cur, ex_id, ticker)
            # Store the cursor as the UTC date at midnight
            dt_utc = datetime.fromtimestamp(ms_int / 1000.0, tz=timezone.utc)
            dt_midnight = datetime(dt_utc.year, dt_utc.month, dt_utc.day)
            cur.execute("""
                INSERT INTO ticker_sentiment_cursor (ticker_id, last_updated)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE last_updated = VALUES(last_updated)
            """, (tid, dt_midnight))

# --------------- High-level directory migrator ---------------

def migrate_data_dir(conn, data_root: str, use_load_data: bool = False) -> None:
    """
    Scans {data_root}/{exchange}/ for *.csv and tickers_last_updated.json and loads them.
    - Ensures exchange and tickers exist.
    - Loads CSVs into sentiment_daily.
    - Updates ticker_sentiment_cursor from JSON.
    """
    for exchange_code in sorted(os.listdir(data_root)):
        ex_dir = os.path.join(data_root, exchange_code)
        if not os.path.isdir(ex_dir):
            continue
        # First update cursor from JSON if present
        json_path = os.path.join(ex_dir, "tickers_last_updated.json")
        if os.path.isfile(json_path):
            update_cursor_from_json(conn, json_path, exchange_code)

        # Then ingest all CSVs
        for name in sorted(os.listdir(ex_dir)):
            if not name.lower().endswith(".csv"):
                continue
            ticker = os.path.splitext(name)[0]
            csv_path = os.path.join(ex_dir, name)
            with conn.cursor() as cur:
                ex_id = ensure_exchange(cur, exchange_code)
                tid = ensure_ticker(cur, ex_id, ticker)
            if use_load_data:
                # Ensure the connection was created with local_infile=True
                processed = load_csv_with_load_data(conn, tid, csv_path)
            else:
                processed = load_csv_with_executemany(conn, tid, csv_path)
            print(f"[{exchange_code}] {ticker}: loaded ~{processed} rows from {name}")


def main():
    try:
        with mysql_conn_over_ssh() as conn:
            # Ensure schema exists (already in your script)
            cur = conn.cursor()
            # for ddl in DDL_STATEMENTS:
            #     cur.execute(ddl)
            # rebuild_partitions_if_needed(cur)

            # Migrate files under ./data/{exchange}/
            data_root = "./data"
            migrate_data_dir(conn, data_root, use_load_data=False)  # set True to use LOAD DATA LOCAL
            print("Migration complete.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
