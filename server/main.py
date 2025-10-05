import os
from flask import Flask, request, Response, abort
import pymysql

# Environment variables:
#   PA_DB_HOST=youruser.mysql.pythonanywhere-services.com
#   PA_DB_USER=youruser
#   PA_DB_PASSWORD=your_db_password
#   PA_DB_NAME=youruser$yourdbname

DB_HOST = os.environ.get("PA_DB_HOST")
DB_USER = os.environ.get("PA_DB_USER")
DB_PASSWORD = os.environ.get("PA_DB_PASSWORD")
DB_NAME = os.environ.get("PA_DB_NAME")

app = Flask(__name__)


def get_conn():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )

def resolve_ticker_id(conn, exchange_code: str, symbol: str):
    sql = """
      SELECT t.id
      FROM tickers t
      JOIN exchanges e ON e.id = t.exchange_id
      WHERE LOWER(e.code) = %s AND UPPER(t.symbol) = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (exchange_code.lower(), symbol.upper()))
        row = cur.fetchone()
        return row["id"] if row else None

@app.get("/sentiment")
def get_sentiment():
    exchange = (request.args.get("exchange") or "").strip()
    ticker = (request.args.get("ticker") or "").strip()
    if not exchange or not ticker:
        return Response("missing exchange or ticker\n", status=400, mimetype="text/plain")

    conn = get_conn()
    try:
        # Ensure socket is healthy; reconnect transparently if needed
        conn.ping(reconnect=True)

        tid = resolve_ticker_id(conn, exchange, ticker)
        if not tid:
            return Response("", status=404, mimetype="text/plain")

        sql = """
          SELECT date, sentiment
          FROM sentiment_daily
          WHERE ticker_id = %s
          ORDER BY date ASC
        """
        lines = []
        with conn.cursor() as cur:
            cur.execute(sql, (tid,))
            for row in cur.fetchall():
                lines.append(f"{row['date'].isoformat()}|{int(row['sentiment'])}")
        body = "\n".join(lines) + ("\n" if lines else "")
        return Response(body, mimetype="text/plain")
    finally:
        try:
            conn.close()
        except Exception:
            pass
            

# For local testing only;expose `app` as WSGI entrypoint.
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
