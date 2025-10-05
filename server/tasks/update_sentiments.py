"""
Daily sentiment backfill/append task for PythonAnywhere using MySQL.

Behavior:
- For each configured exchange code, load active tickers from DB.
- For each ticker, compute missing dates from the smaller of:
  (a) ticker_sentiment_cursor.last_updated (date) and
  (b) max(sentiment_daily.date) if any,
  then fill up to yesterday (UTC), skipping dates already present.
- For each missing day, call Gemini to classify sentiment.
- Upsert rows into sentiment_daily and advance ticker_sentiment_cursor.

Prereqs: pip install python-dotenv PyMySQL google-genai requests urllib3
"""

from dotenv import load_dotenv
import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone, date
from typing import Optional, List, Set, Dict, Tuple

import pymysql

# Optional: Google Gemini (new SDK)
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

# ----------------------------
# Env and logging
# ----------------------------
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

EXCHANGES = [e.strip().lower() for e in os.environ.get("EXCHANGES", "nasdaq,bse,nse,nyse").split(",") if e.strip()]
# MySQL (inside PythonAnywhere scheduled tasks, connect directly without SSH)
DB_HOST = os.environ.get("PA_DB_HOST")  # e.g., youruser.mysql.pythonanywhere-services.com
DB_USER = os.environ.get("PA_DB_USER")
DB_PASSWORD = os.environ.get("PA_DB_PASSWORD")
DB_NAME = os.environ.get("PA_DB_NAME")  # e.g., youruser$yourdbname

# Gemini settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if GEMINI_API_KEY and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY  # let genai.Client() auto-pick the key
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ENABLE_GOOGLE_SEARCH = os.environ.get("ENABLE_GOOGLE_SEARCH", "false").lower() in {"1", "true", "yes"}

# Safety limits
MAX_DAYS_PER_TICKER = int(os.environ.get("MAX_DAYS_PER_TICKER", "30"))  # cap per run

# ----------------------------
# Time helpers
# ----------------------------
def today_utc_date() -> date:
    return datetime.now(timezone.utc).date()

def ms_to_utc_date(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date()

# ----------------------------
# Gemini helpers (same prompts as before)
# ----------------------------
def resolve_model_name(name: str) -> str:
    return name.split("/", 1)[-1] if name.startswith("models/") else name

class _ModelShim:
    def __init__(self, client: "genai.Client", model_id: str, config: Optional["types.GenerateContentConfig"]):
        self._client = client
        self._model_id = model_id
        self._config = config
    def generate_content(self, contents: str):
        return self._client.models.generate_content(
            model=self._model_id,
            contents=contents,
            config=self._config,
        )

def init_gemini():
    if genai is None or types is None:
        raise RuntimeError("google-genai is not installed")
    client = genai.Client()
    model_id = resolve_model_name(GEMINI_MODEL)
    config = None
    if ENABLE_GOOGLE_SEARCH:
        search_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[search_tool])
    return _ModelShim(client, model_id, config)

def research_with_grounding(model, ticker: str, date_str: str) -> str:
    prompt = f"""
Summarize public news coverage for {ticker} on {date_str} (UTC) in 3-5 short bullet points
focused only on that day. Include only facts and high-level analyst actions.
"""
    resp = model.generate_content(prompt.strip())
    return (getattr(resp, "text", "") or "").strip()

def classify_without_tools(client: "genai.Client", model_id: str, context: str, ticker: str, date_str: str) -> int:
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.0,
    )
    prompt = f"""
Based only on the context below, classify the overall sentiment for {ticker} on {date_str} as:
0 = neutral, 1 = positive, 2 = negative.
Respond with a single JSON integer, no text.

Context:
{context}
"""
    resp = client.models.generate_content(model=model_id, contents=prompt.strip(), config=cfg)
    txt = (getattr(resp, "text", "") or "").strip()
    try:
        val = int(json.loads(txt))
    except Exception:
        raise RuntimeError(f"Structured classification failed: {txt!r}")
    if val not in (0, 1, 2):
        raise RuntimeError(f"Classification out of range: {val!r}")
    return val

def generate_sentiment(model_shim, ticker: str, date_str: str) -> int:
    summary = research_with_grounding(model_shim, ticker, date_str)
    client = model_shim._client
    model_id = model_shim._model_id
    return classify_without_tools(client, model_id, summary, ticker, date_str)

# ----------------------------
# DB helpers (PyMySQL)
# ----------------------------
def db_connect():
    # Autocommit to simplify upserts
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )

def get_exchange_ids(conn, exchange_codes: List[str]) -> Dict[str, int]:
    if not exchange_codes:
        return {}
    q = "SELECT id, code FROM exchanges WHERE LOWER(code) IN ({})".format(
        ",".join(["%s"] * len(exchange_codes))
    )
    with conn.cursor() as cur:
        cur.execute(q, [c.lower() for c in exchange_codes])
        rows = cur.fetchall()
    return {r["code"].lower(): r["id"] for r in rows}

def get_tickers_for_exchange(conn, exchange_id: int) -> List[Dict]:
    q = """
    SELECT id, symbol, active, first_trade_date
    FROM tickers
    WHERE exchange_id = %s AND active = 1
    ORDER BY symbol
    """
    with conn.cursor() as cur:
        cur.execute(q, (exchange_id,))
        return cur.fetchall()

def get_cursor_date(conn, ticker_id: int) -> Optional[date]:
    q = "SELECT last_updated FROM ticker_sentiment_cursor WHERE ticker_id = %s"
    with conn.cursor() as cur:
        cur.execute(q, (ticker_id,))
        row = cur.fetchone()
        if not row or not row["last_updated"]:
            return None
        # Interpret DATETIME as date
        return row["last_updated"].date()

def get_max_sentiment_date(conn, ticker_id: int) -> Optional[date]:
    q = "SELECT MAX(date) AS max_date FROM sentiment_daily WHERE ticker_id = %s"
    with conn.cursor() as cur:
        cur.execute(q, (ticker_id,))
        row = cur.fetchone()
        return row["max_date"] if row and row["max_date"] else None

def get_existing_dates(conn, ticker_id: int, start_d: date, end_d: date) -> Set[str]:
    if start_d > end_d:
        return set()
    q = """
    SELECT date
    FROM sentiment_daily
    WHERE ticker_id = %s AND date >= %s AND date <= %s
    """
    with conn.cursor() as cur:
        cur.execute(q, (ticker_id, start_d, end_d))
        return {r["date"].isoformat() for r in cur.fetchall()}

def compute_days_to_fill(base_date: date, today: date, existing_dates: Set[str]) -> List[date]:
    # Fill (base_date, yesterday]
    yesterday = today - timedelta(days=1)
    d = base_date + timedelta(days=1)
    out: List[date] = []
    while d <= yesterday and len(out) < MAX_DAYS_PER_TICKER:
        if d.isoformat() not in existing_dates:
            out.append(d)
        d += timedelta(days=1)
    return out

def upsert_sentiment_batch(conn, ticker_id: int, rows: List[Tuple[str, int]]):
    if not rows:
        return
    # MySQL idempotent upsert on composite PK (ticker_id, date)
    q = """
    INSERT INTO sentiment_daily (ticker_id, date, sentiment, last_updated)
    VALUES (%s, %s, %s, NOW(3))
    ON DUPLICATE KEY UPDATE
      sentiment = VALUES(sentiment),
      last_updated = VALUES(last_updated)
    """
    data = [(ticker_id, d, s) for (d, s) in rows]
    with conn.cursor() as cur:
        cur.executemany(q, data)

def upsert_cursor(conn, ticker_id: int, last_date: date):
    q = """
    INSERT INTO ticker_sentiment_cursor (ticker_id, last_updated)
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
      last_updated = VALUES(last_updated)
    """
    # Store as DATETIME end-of-day or NOW? Use midnight UTC for clarity.
    dt_value = datetime(last_date.year, last_date.month, last_date.day)
    with conn.cursor() as cur:
        cur.execute(q, (ticker_id, dt_value))

# ----------------------------
# Main
# ----------------------------
def main() -> int:
    # Validate env
    for k in ("PA_DB_HOST", "PA_DB_USER", "PA_DB_PASSWORD", "PA_DB_NAME"):
        if not os.environ.get(k):
            logging.error("Missing env var %s", k)
            return 2

    # Gemini init
    try:
        model = init_gemini()
    except Exception:
        logging.exception("Gemini init failed")
        return 3

    today = today_utc_date()

    try:
        conn = db_connect()
    except Exception:
        logging.exception("DB connection failed")
        return 4

    rc = 0
    try:
        ex_ids = get_exchange_ids(conn, EXCHANGES)
        if not ex_ids:
            logging.warning("No matching exchanges found: %s", ",".join(EXCHANGES))

        for ex_code, ex_id in ex_ids.items():
            tickers = get_tickers_for_exchange(conn, ex_id)
            logging.info("Exchange %s: %d active tickers", ex_code.upper(), len(tickers))

            for t in tickers:
                tid = t["id"]
                sym = t["symbol"]

                # Determine base date
                cdate = get_cursor_date(conn, tid)
                mdate = get_max_sentiment_date(conn, tid)
                if cdate and mdate:
                    base = min(cdate, mdate)
                else:
                    base = cdate or mdate or (today - timedelta(days=1))  # nothing yet -> start with yesterday

                # Identify missing dates
                existing = get_existing_dates(conn, tid, base + timedelta(days=1), today - timedelta(days=1))
                days = compute_days_to_fill(base, today, existing)
                if not days:
                    logging.info("No missing days for %s between %s..%s", sym.upper(), base.isoformat(), (today - timedelta(days=1)).isoformat())
                    continue

                # Generate and upsert
                new_rows: List[Tuple[str, int]] = []
                for d in days:
                    date_str = d.isoformat()
                    try:
                        s = generate_sentiment(model, sym.upper(), date_str)
                    except Exception as e:
                        logging.error("Classification failed for %s %s: %s", sym.upper(), date_str, e)
                        rc = rc or 5
                        break
                    new_rows.append((date_str, s))

                if not new_rows:
                    continue

                try:
                    upsert_sentiment_batch(conn, tid, new_rows)
                    upsert_cursor(conn, tid, days[-1])
                    logging.info("Upserted %d rows for %s through %s", len(new_rows), sym.upper(), days[-1].isoformat())
                except Exception:
                    logging.exception("DB upsert failed for %s", sym.upper())
                    rc = rc or 6

    finally:
        try:
            conn.close()
        except Exception:
            pass

    return rc

if __name__ == "__main__":
    sys.exit(main())
