#!/usr/bin/env python3
"""
Creates MySQL tables and yearly date partitions on PythonAnywhere over an SSH tunnel.

Prereqs:
  pip install sshtunnel PyMySQL
"""

import datetime as dt
import sys
from contextlib import contextmanager

from sshtunnel import SSHTunnelForwarder
import pymysql

# -----------------------------
# Configuration (edit these)
# -----------------------------
SSH_HOST = "ssh.pythonanywhere.com"      # or "ssh.eu.pythonanywhere.com"
SSH_USERNAME = "your_pa_username"
SSH_PASSWORD = "your_pa_ssh_password"    # PythonAnywhere SSH/password auth

PA_DB_HOST = "your_pa_username.mysql.pythonanywhere-services.com"  # or *.eu.* for EU
PA_DB_USER = "your_pa_db_username"
PA_DB_PASSWORD = "your_pa_db_password"
PA_DB_NAME = "your_pa_username$yourdbname"

# Partition years to create (inclusive range + MAXVALUE)
FIRST_YEAR = 2020
LAST_YEAR = dt.date.today().year + 2

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

def main():
    try:
        with mysql_conn_over_ssh() as conn:
            cur = conn.cursor()
            for ddl in DDL_STATEMENTS:
                cur.execute(ddl)
            rebuild_partitions_if_needed(cur)
            print("Schema created and partitions ensured.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
