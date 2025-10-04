from dotenv import load_dotenv
import os
import sys
import json
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# New SDK
# pip install -U google-genai python-dotenv requests urllib3
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

load_dotenv()

# ----------------------------
# Configuration via env vars
# ----------------------------
DATA_PATH = os.environ.get("DATA_PATH", "webapp/src/assets/data").rstrip("/")
EXCHANGES = [e.strip().lower() for e in os.environ.get("EXCHANGES", "nasdaq,bse,nse,nyse").split(",") if e.strip()]
GH_OWNER = os.environ.get("GH_OWNER", "autonomous-web-org")
GH_REPO = os.environ.get("GH_REPO", "news-sentiment")
GH_BRANCH = os.environ.get("GH_BRANCH", "main")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
# Gemini settings
# The new SDK reads GOOGLE_API_KEY by default; keep compatibility with GEMINI_API_KEY.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if GEMINI_API_KEY and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY  # let genai.Client() auto-pick the key
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")  # prefer 2.5 flash
ENABLE_GOOGLE_SEARCH = os.environ.get("ENABLE_GOOGLE_SEARCH", "false").lower() in {"1", "true", "yes"}  # optional grounding

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ----------------------------
# HTTP session with retries
# ----------------------------
def make_session() -> requests.Session:
    retry = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "PUT"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s = requests.Session()
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

SESSION = make_session()

# ----------------------------
# Helpers: time and parsing
# ----------------------------
def ms_to_utc_date(ms: int) -> datetime.date:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date()

def date_to_ms_utc(d: datetime.date) -> int:
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def today_utc_date() -> datetime.date:
    return datetime.now(timezone.utc).date()

# ----------------------------
# Fetch tickers JSON (raw)
# ----------------------------
def load_exchange_tickers(exchange: str) -> list[dict]:
    data, _meta = gh_get_json(path_tickers_json(exchange))
    if data is None:
        # If absent, treat as empty list
        return []
    if not isinstance(data, list):
        raise RuntimeError(f"{path_tickers_json(exchange)} must be a list of records")
    return data

# ----------------------------
# Gemini via new SDK (google-genai)
# ----------------------------
def resolve_model_name(name: str) -> str:
    # Accept 'models/gemini-2.5-flash' or 'gemini-2.5-flash'
    return name.split("/", 1)[-1] if name.startswith("models/") else name

class _ModelShim:
    """
    Wraps the new genai.Client to maintain the old model.generate_content(...) call pattern.
    """
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
    """
    Initialize google-genai client and return a shim with generate_content to keep the existing callsite unchanged.
    Optionally enables Google Search grounding if ENABLE_GOOGLE_SEARCH is true.
    """
    if genai is None or types is None:
        raise RuntimeError("google-genai is not installed in this environment")
    # genai.Client() reads GOOGLE_API_KEY by default
    client = genai.Client()  # Developer API client; set GOOGLE_GENAI_USE_VERTEXAI for Vertex if needed
    model_id = resolve_model_name(GEMINI_MODEL)

    config = None
    if ENABLE_GOOGLE_SEARCH:
        # Enable Google Search grounding tool
        # See: https://ai.google.dev/gemini-api/docs/google-search
        search_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[search_tool])

    return _ModelShim(client, model_id, config)

def list_models_supporting_generate_content() -> list[str]:
    """
    Uses the new google-genai client to list models that support generateContent.
    """
    if genai is None:
        raise RuntimeError("google-genai is not installed in this environment")
    client = genai.Client()
    names: list[str] = []
    for m in client.models.list():
        actions = set(getattr(m, "supported_actions", []) or [])
        if "generateContent" in actions:
            # Return full name as listed (often prefixed with 'models/')
            names.append(getattr(m, "name", ""))
    return names

def research_with_grounding(model, ticker: str, date_str: str) -> str:
    """
    Returns a concise grounded summary of news for the ticker/date.
    Uses the same model shim but with Google Search enabled in init_gemini.
    """
    prompt = f"""
Summarize public news coverage for {ticker} on {date_str} (UTC) in 3-5 short bullet points
focused only on that day. Include only facts and high-level analyst actions.
"""
    resp = model.generate_content(prompt.strip())
    return (getattr(resp, "text", "") or "").strip()

def classify_without_tools(client: "genai.Client", model_id: str, context: str, ticker: str, date_str: str) -> int:
    """
    Second call: turn OFF grounding/tools and enforce structured output (single int).
    """
    cfg = types.GenerateContentConfig(
        # Force strict JSON integer output
        response_mime_type="application/json",
        # response_schema=types.Schema(type=types.Type.INT),
        # Optional: reduce creativity
        temperature=0.0,
    )
    prompt = f"""
Based only on the context below, classify the overall sentiment for {ticker} on {date_str} as:
0 = neutral, 1 = positive, 2 = negative.
Respond with a single JSON integer, no text.

Context:
{context}
"""
    # New direct client call without tools
    resp = client.models.generate_content(
        model=model_id,
        contents=prompt.strip(),
        config=cfg,
    )
    txt = (getattr(resp, "text", "") or "").strip()
    try:
        val = int(json.loads(txt))
    except Exception:
        raise RuntimeError(f"Structured classification failed: {txt!r}")
    if val not in (0, 1, 2):
        raise RuntimeError(f"Classification out of range: {val!r}")
    return val

def generate_sentiment(model_shim, ticker: str, date_str: str) -> int:
    # Step 1: grounded research (uses tools if enabled in init_gemini)
    summary = research_with_grounding(model_shim, ticker, date_str)

    # Step 2: strict labeling without tools using the raw client
    # Access underlying client/model from the shim:
    client = model_shim._client
    model_id = model_shim._model_id
    return classify_without_tools(client, model_id, summary, ticker, date_str)

# ----------------------------
# GitHub Contents API helpers
# ----------------------------

def gh_headers():
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN must be set for GitHub updates")
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

def path_tickers_json(exchange: str) -> str:
    return f"{DATA_PATH}/{exchange}/tickers_last_updated.json"

def path_ticker_data(exchange: str, ticker: str) -> str:
    return f"{DATA_PATH}/{exchange}/{ticker.lower()}.csv"

# 2) Path helpers
def path_tickers_json(exchange: str) -> str:
    return f"{DATA_PATH}/{exchange}/tickers_last_updated.json"

def path_ticker_csv(exchange: str, ticker: str) -> str:
    return f"{DATA_PATH}/{exchange}/{ticker.lower()}.csv"

# 3) GitHub JSON loader for tickers_last_updated.json
def gh_get_json(path: str):
    meta = gh_get_content(path)
    if meta.get("not_found"):
        return None, meta
    if "content" in meta and meta.get("encoding") == "base64":
        text = base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
    else:
        text = meta.get("content", "") or ""
    return json.loads(text), meta

def load_exchange_tickers(exchange: str) -> list[dict]:
    data, _meta = gh_get_json(path_tickers_json(exchange))
    if data is None:
        return []
    if not isinstance(data, list):
        raise RuntimeError(f"{path_tickers_json(exchange)} must be a list of objects")
    return data

# 4) CSV helpers (exchange-aware)
def get_csv_existing_dates(exchange: str, ticker: str):
    p = path_ticker_csv(exchange, ticker)
    meta = gh_get_content(p)
    if meta.get("not_found"):
        return set(), None, meta
    if "content" in meta and meta.get("encoding") == "base64":
        text = base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
    else:
        text = meta.get("content", "") or ""
    dates: set[str] = set()
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith("date,"):
            continue
        d = ln.split(",", 1)[0].strip()
        if d:
            dates.add(d)
    max_date = max((datetime.fromisoformat(d).date() for d in dates), default=None)
    return dates, max_date, meta


def gh_get_content(path: str) -> Dict[str, Any]:
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"
    resp = SESSION.get(url, headers=gh_headers(), params={"ref": GH_BRANCH}, timeout=30)
    if resp.status_code == 404:
        return {"not_found": True}
    resp.raise_for_status()
    return resp.json()

def gh_put_content(
    path: str,
    content_text: str,
    message: str,
    sha: Optional[str] = None,
) -> Dict[str, Any]:
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"
    payload: Dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content_text.encode("utf-8")).decode("ascii"),
        "branch": GH_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    resp = SESSION.put(url, headers=gh_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

def compute_days_to_fill(last_json_date: datetime.date, today: datetime.date, csv_dates: Set[str], csv_max_date: Optional[datetime.date]) -> List[datetime.date]:
    """
    From base = min(last_json_date, csv_max_date or last_json_date),
    return all missing dates in (base, yesterday], skipping dates already in CSV.
    """
    base = last_json_date if csv_max_date is None else min(last_json_date, csv_max_date)
    out: List[datetime.date] = []
    d = base + timedelta(days=1)
    while d < today:
        if d.isoformat() not in csv_dates:
            out.append(d)
        d += timedelta(days=1)
    return out

def upsert_csv_batch(exchange: str, ticker: str, new_rows: list[tuple[str, int]], meta: dict) -> bool:
    if not new_rows:
        return False
    p = path_ticker_csv(exchange, ticker)
    header = "date,sentiment\n"
    if meta.get("not_found"):
        text = header + "".join(f"{d},{s}\n" for d, s in new_rows)
        gh_put_content(p, text, message=f"{exchange.upper()} {ticker.upper()}: add {len(new_rows)} days through {new_rows[-1][0]}")
        logging.info("Created CSV for %s/%s with %d rows through %s", exchange.upper(), ticker.upper(), len(new_rows), new_rows[-1][0])
        return True

    # decode
    if "content" in meta and meta.get("encoding") == "base64":
        text = base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
    else:
        text = meta.get("content", "") or ""
    lines = [ln if ln.endswith("\n") else ln + "\n" for ln in text.splitlines()]
    if not lines or not lines[0].startswith("date,sentiment"):
        lines = [header] + [ln for ln in lines if ln.strip()]

    present = set()
    for ln in lines:
        if ln.startswith("date,") or not ln.strip():
            continue
        present.add(ln.split(",", 1)[0])

    appended = 0
    for d, s in new_rows:
        if d not in present:
            lines.append(f"{d},{s}\n")
            appended += 1

    if appended == 0:
        logging.info("CSV for %s/%s already had all %d rows; no commit", exchange.upper(), ticker.upper(), len(new_rows))
        return False

    gh_put_content(
        p,
        "".join(lines),
        message=f"{exchange.upper()} {ticker.upper()}: add {appended} days through {new_rows[-1][0]}",
        sha=meta.get("sha"),
    )
    logging.info("Updated CSV for %s/%s with %d rows through %s", exchange.upper(), ticker.upper(), appended, new_rows[-1][0])
    return True

# 5) Per-exchange tickers_last_updated.json updater
def update_exchange_tickers_json(exchange: str, target_date_by_ticker: dict[str, datetime.date]):
    p = path_tickers_json(exchange)
    meta = gh_get_content(p)
    if meta.get("not_found"):
        logging.warning("tickers_last_updated.json not found for %s; skipping", exchange.upper())
        return
    if "content" in meta and meta.get("encoding") == "base64":
        text = base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
    else:
        text = meta.get("content", "") or ""
    data = json.loads(text)
    if not isinstance(data, list):
        logging.warning("%s is not a list; skipping", p)
        return
    by_ticker = {str(obj.get("ticker") or obj.get("symbol")).lower(): obj for obj in data if isinstance(obj, dict)}
    changed = False
    for tk, d in target_date_by_ticker.items():
        key = tk.lower()
        if key in by_ticker:
            by_ticker[key]["lastUpdated"] = date_to_ms_utc(d)
            changed = True
    if not changed:
        logging.info("No changes to %s", p)
        return
    gh_put_content(p, json.dumps(data, ensure_ascii=False, indent=2), message=f"Update lastUpdated for {exchange.upper()}", sha=meta.get("sha"))

# 6) Main: iterate exchanges and tickers
def main() -> int:
    # init model
    try:
        model = init_gemini()
    except Exception:
        logging.exception("Gemini init failed")
        return 3

    today = today_utc_date()
    overall_rc = 0

    for exchange in EXCHANGES:
        try:
            tickers = load_exchange_tickers(exchange)
        except Exception:
            logging.exception("Failed to load tickers for %s", exchange.upper())
            overall_rc = overall_rc or 4
            continue

        processed_dates: dict[str, datetime.date] = {}

        for item in tickers:
            if not isinstance(item, dict):
                continue
            ticker = item.get("ticker") or item.get("symbol")
            last_updated = item.get("lastUpdated") or item.get("last_updated")
            if not ticker or last_updated is None:
                continue
            try:
                ms = int(last_updated)
            except Exception:
                continue
            last_date = ms_to_utc_date(ms)

            try:
                csv_dates, csv_max_date, meta = get_csv_existing_dates(exchange, str(ticker))
            except Exception:
                logging.exception("Failed reading CSV for %s/%s", exchange.upper(), ticker)
                overall_rc = overall_rc or 6
                continue

            days = compute_days_to_fill(last_date, today, csv_dates, csv_max_date)
            if not days:
                logging.info("No missing days for %s/%s between %s and %s", exchange.upper(), ticker, last_date.isoformat(), (today - timedelta(days=1)).isoformat())
                continue

            try:
                new_rows: list[tuple[str, int]] = []
                for d in days:
                    date_str = d.isoformat()
                    s = generate_sentiment(model, str(ticker).upper(), date_str)
                    new_rows.append((date_str, s))
            except RuntimeError as e:
                logging.error("Stopping %s/%s: %s", exchange.upper(), ticker, e)
                overall_rc = overall_rc or 5
                continue

            try:
                changed = upsert_csv_batch(exchange, str(ticker), new_rows, meta)
                if changed:
                    processed_dates[str(ticker)] = days[-1]
            except Exception:
                logging.exception("Failed to update CSV for %s/%s", exchange.upper(), ticker)
                overall_rc = overall_rc or 6
                continue

        if processed_dates:
            try:
                update_exchange_tickers_json(exchange, processed_dates)
            except Exception:
                logging.exception("Failed to update tickers_last_updated.json for %s", exchange.upper())
                overall_rc = overall_rc or 7

    return overall_rc

if __name__ == "__main__":
    sys.exit(main())
