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
REPO_JSON_URL = os.environ.get("REPO_JSON_URL", "")
GH_OWNER = os.environ.get("GH_OWNER", "autonomous-web-org")
GH_REPO = os.environ.get("GH_REPO", "news-sentiment")
GH_BRANCH = os.environ.get("GH_BRANCH", "main")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Path of the tickers JSON inside the repo to advance after commits
TICKERS_JSON_PATH_IN_REPO = os.environ.get(
    "TICKERS_JSON_PATH_IN_REPO",
    "src/assets/data/tickers_last_updated.json",
)

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
def fetch_tickers_json(url: str) -> List[Dict[str, Any]]:
    if not url:
        raise RuntimeError("REPO_JSON_URL must be set")
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError("Tickers JSON must be a list of records")
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

def generate_sentiment(model, ticker: str, date_str: str) -> int:
    """
    Strict classification: returns ONLY one of {0,1,2}.
    On any parsing error or API error, raises RuntimeError (no fallback).
    """
    prompt = f"""
You are a financial news sentiment classifier.

Task:
- Consider major public news coverage for ticker "{ticker}" on {date_str} (UTC).
- Classify the overall daily sentiment as:
  0 = neutral, 1 = positive, 2 = negative.
- Respond with a single character: 0 or 1 or 2. No extra text.
"""
    try:
        resp = model.generate_content(prompt.strip())
        text = (getattr(resp, "text", "") or "").strip()
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}") from e

    if text not in {"0", "1", "2"}:
        raise RuntimeError(f"Invalid Gemini output for {ticker} {date_str}: {repr(text)}")

    return int(text)

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

# ----------------------------
# CSV helpers and batch upsert
# ----------------------------
def get_csv_existing_dates(ticker: str) -> Tuple[Set[str], Optional[datetime.date], Dict[str, Any]]:
    """
    Return:
      - set of YYYY-MM-DD strings present,
      - max date present (or None),
      - the metadata dict from Contents API (for reuse: sha, not_found)
    """
    path = f"webapp/src/assets/data/{ticker.lower()}.csv"
    meta = gh_get_content(path)
    if meta.get("not_found"):
        return set(), None, meta

    if "content" in meta and meta.get("encoding") == "base64":
        text = base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
    else:
        text = meta.get("content", "") or ""

    dates: Set[str] = set()
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith("date,"):
            continue
        d = ln.split(",", 1)[0].strip()
        if d:
            dates.add(d)
    max_date = max((datetime.fromisoformat(d).date() for d in dates), default=None)
    return dates, max_date, meta

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

def upsert_csv_batch(ticker: str, new_rows: List[Tuple[str, int]], meta: Dict[str, Any]) -> bool:
    """
    Append multiple rows to webapp/src/assets/data/{ticker}.csv in one commit.
    new_rows: list of (date_str, sentiment).
    Returns True if file content changed.
    """
    if not new_rows:
        return False

    path = f"webapp/src/assets/data/{ticker.lower()}.csv"
    header = "date,sentiment\n"

    if meta.get("not_found"):
        text = header + "".join(f"{d},{s}\n" for d, s in new_rows)
        gh_put_content(path, text, message=f"{ticker.upper()}: add {len(new_rows)} days through {new_rows[-1][0]}")
        logging.info("Created CSV for %s with %d new rows through %s", ticker.upper(), len(new_rows), new_rows[-1][0])
        return True

    # Decode existing
    if "content" in meta and meta.get("encoding") == "base64":
        text = base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
    else:
        text = meta.get("content", "") or ""

    lines = [ln if ln.endswith("\n") else ln + "\n" for ln in text.splitlines()]
    if not lines or not lines[0].startswith("date,sentiment"):
        lines = [header] + [ln for ln in lines if ln.strip()]

    # Build set to avoid duplicates
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
        logging.info("CSV for %s already had all %d rows; no commit", ticker.upper(), len(new_rows))
        return False

    gh_put_content(
        path,
        "".join(lines),
        message=f"{ticker.upper()}: add {appended} days through {new_rows[-1][0]}",
        sha=meta.get("sha"),
    )
    logging.info("Updated CSV for %s with %d rows through %s", ticker.upper(), appended, new_rows[-1][0])
    return True

# ----------------------------
# Advance tickers_last_updated.json
# ----------------------------
def update_tickers_json(target_date_by_ticker: Dict[str, datetime.date]):
    """
    Move each ticker's lastUpdated to the processed target date (ms since epoch).
    """
    meta = gh_get_content(TICKERS_JSON_PATH_IN_REPO)
    if meta.get("not_found"):
        logging.warning("tickers_last_updated.json not found in repo path; skipping JSON update")
        return

    if "content" in meta and meta.get("encoding") == "base64":
        text = base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
    else:
        text = meta.get("content", "") or ""

    try:
        data = json.loads(text)
    except Exception:
        logging.exception("Failed to parse existing tickers_last_updated.json; skipping")
        return

    if not isinstance(data, list):
        logging.warning("tickers_last_updated.json is not a list; skipping update")
        return

    by_ticker = {str(item.get("ticker") or item.get("symbol")).lower(): item for item in data if isinstance(item, dict)}

    changed = False
    for tk, d in target_date_by_ticker.items():
        key = tk.lower()
        if key in by_ticker:
            by_ticker[key]["lastUpdated"] = date_to_ms_utc(d)
            changed = True

    if not changed:
        logging.info("No changes to tickers_last_updated.json")
        return

    new_text = json.dumps(data, ensure_ascii=False, indent=2)
    gh_put_content(
        TICKERS_JSON_PATH_IN_REPO,
        new_text,
        message="Update lastUpdated for processed tickers",
        sha=meta.get("sha"),
    )
    logging.info("Updated tickers_last_updated.json")

# ----------------------------
# Main workflow
# ----------------------------
def main() -> int:
    try:
        tickers = fetch_tickers_json(REPO_JSON_URL)
    except Exception:
        logging.exception("Failed to load tickers JSON")
        return 4

    # Initialize Gemini once (new SDK via shim)
    try:
        model = init_gemini()
    except Exception:
        logging.exception("Gemini init failed")
        return 3

    today = today_utc_date()
    processed_dates: Dict[str, datetime.date] = {}

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

        last_json_date = ms_to_utc_date(ms)

        # Determine all missing days up to yesterday, skipping any already in CSV
        try:
            csv_dates, csv_max_date, meta = get_csv_existing_dates(str(ticker))
        except Exception:
            logging.exception("Failed to read CSV for %s", ticker)
            return 6

        days = compute_days_to_fill(last_json_date, today, csv_dates, csv_max_date)
        if not days:
            logging.info("No missing days for %s between %s and %s",
                         ticker, last_json_date.isoformat(), (today - timedelta(days=1)).isoformat())
            continue

        # STRICT: generate all sentiments first; abort on any failure (no fallback)
        try:
            new_rows: List[Tuple[str, int]] = []
            for d in days:
                date_str = d.isoformat()
                s = generate_sentiment(model, str(ticker).upper(), date_str)
                new_rows.append((date_str, s))
        except RuntimeError as e:
            logging.error("Stopping run: %s", e)
            return 5

        # Write once per ticker; only advance JSON if something changed
        try:
            changed = upsert_csv_batch(str(ticker), new_rows, meta)
            if changed:
                processed_dates[str(ticker)] = days[-1]
        except Exception:
            logging.exception("Failed to batch-update CSV for %s", ticker)
            return 6

    if processed_dates:
        try:
            update_tickers_json(processed_dates)
        except Exception:
            logging.exception("Failed to update tickers_last_updated.json")
            return 7

    return 0

if __name__ == "__main__":
    sys.exit(main())
