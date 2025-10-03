
from dotenv import load_dotenv
import os
import sys
import json
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Optional (recommended): pip install google-generativeai
# Ensure this library is installed in the PythonAnywhere virtualenv used by the scheduled task.
try:
    import google.generativeai as genai
except ImportError:
    genai = None


load_dotenv()


# ----------------------------
# Configuration via env vars
# ----------------------------
REPO_JSON_URL = os.environ.get(
    "REPO_JSON_URL",
    # Default to the provided tickers JSON
    "",
)
print(REPO_JSON_URL, "REPO_JSON_URL")

# GitHub repo info where CSVs live
GH_OWNER = os.environ.get("GH_OWNER", "autonomous-web-org")
GH_REPO = os.environ.get("GH_REPO", "news-sentiment")
GH_BRANCH = os.environ.get("GH_BRANCH", "main")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Path of the tickers JSON inside the repo if updating it (optional but recommended)
# The raw URL above points at src/assets/data/tickers_last_updated.json
TICKERS_JSON_PATH_IN_REPO = os.environ.get(
    "TICKERS_JSON_PATH_IN_REPO",
    "src/assets/data/tickers_last_updated.json",
)

# Gemini settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")  # Free-tier friendly

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
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError("Tickers JSON must be a list")
    return data


# ----------------------------
# Gemini sentiment generation
# ----------------------------
def init_gemini():
    if genai is None:
        raise RuntimeError("google-generativeai is not installed in this environment")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY must be set")
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(GEMINI_MODEL)

def list_models_supporting_generate_content() -> list[str]:
    """
    Uses existing init_gemini() to ensure google.generativeai is configured,
    then returns model names that support generateContent.
    """
    names: list[str] = []
    for m in genai.list_models():
        # Handle both historical and newer field names
        methods = set(getattr(m, "supported_generation_methods", [])) | set(getattr(m, "supported_actions", []))
        if "generateContent" in methods:
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
        text = (resp.text or "").strip()
    except Exception as e:
        # Surface the failure to caller; do not guess
        raise RuntimeError(f"Gemini API error: {e}") from e

    if text not in {"0", "1", "2"}:
        # Strict mode: invalid output => hard fail
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
# CSV read/append logic
# ----------------------------
def upsert_csv_for_ticker(ticker: str, date_str: str, sentiment: int):
    """
    Append a row "YYYY-MM-DD,<sentiment>" to webapp/src/assets/data/{ticker}.csv
    If file does not exist, create with header "date,sentiment".
    Avoid duplicate date rows
    """
    path = f"webapp/src/assets/data/{ticker.lower()}.csv"
    existing = gh_get_content(path)
    header = "date,sentiment\n"
    rows: List[str] = []

    if existing.get("not_found"):
        # New file
        rows = [header, f"{date_str},{sentiment}\n"]
        gh_put_content(
            path,
            "".join(rows),
            message=f"{ticker.upper()}: add sentiment for {date_str}",
        )
        logging.info("Created CSV for %s with %s", ticker.upper(), date_str)
        return

    # Existing file: decode and append if missing
    if "content" in existing and existing.get("encoding") == "base64":
        text = base64.b64decode(existing["content"]).decode("utf-8", errors="replace")
    else:
        # Some responses might be served raw due to preview headers/configs
        text = existing.get("content", "")
        if not text:
            # Fallback: treat as empty if unexpected
            text = ""

    # Normalize lines
    if not text.startswith("date,sentiment"):
        # Insert header if missing
        lines = [header] + [ln if ln.endswith("\n") else ln + "\n" for ln in text.splitlines() if ln.strip()]
    else:
        lines = [ln if ln.endswith("\n") else ln + "\n" for ln in text.splitlines()]

    # Avoid duplicate date rows
    date_exists = any(ln.split(",")[0] == date_str for ln in lines if ln and not ln.startswith("date,"))
    if not date_exists:
        lines.append(f"{date_str},{sentiment}\n")
    else:
        logging.info("CSV for %s already has %s; skipping append", ticker.upper(), date_str)

    gh_put_content(
        path,
        "".join(lines),
        message=f"{ticker.upper()}: update sentiment for {date_str}",
        sha=existing.get("sha"),
    )
    logging.info("Updated CSV for %s with %s", ticker.upper(), date_str)


# ----------------------------
# Optional: update tickers_last_updated.json
# ----------------------------
def update_tickers_json(target_date_by_ticker: Dict[str, datetime.date]):
    """
    Move each ticker's lastUpdated to the processed target date (ms since epoch).
    """
    # Fetch current file via Contents API
    meta = gh_get_content(TICKERS_JSON_PATH_IN_REPO)
    if meta.get("not_found"):
        logging.warning("tickers_last_updated.json not found in repo path; skipping JSON update")
        return

    if "content" in meta and meta.get("encoding") == "base64":
        text = base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
    else:
        text = meta.get("content", "")

    try:
        data = json.loads(text)
    except Exception:
        logging.exception("Failed to parse existing tickers_last_updated.json; skipping")
        return

    if not isinstance(data, list):
        logging.warning("tickers_last_updated.json is not a list; skipping update")
        return

    # Build fast lookup
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

    # Initialize Gemini once
    try:
        model = init_gemini()
        # print(list_models_supporting_generate_content())
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

        last_date = ms_to_utc_date(ms)
        delta_days = (today - last_date).days

        if delta_days >= 2:
            target_date = last_date + timedelta(days=1)
            date_str = target_date.isoformat()

            # STRICT: if Gemini cannot produce a valid label, end the task immediately
            try:
                sentiment = generate_sentiment(model, str(ticker).upper(), date_str)
            except RuntimeError as e:
                logging.error("Stopping run: %s", e)
                return 5  # non-zero exit so scheduler shows failure

            try:
                upsert_csv_for_ticker(str(ticker), date_str, sentiment)
                processed_dates[str(ticker)] = target_date
            except Exception:
                logging.exception("Failed to update CSV for %s", ticker)
                return 6  # also stop, to avoid partial/ambiguous state
        else:
            logging.info("Skipping %s; lastUpdated=%s (delta %d days)", ticker, last_date.isoformat(), delta_days)

    if processed_dates:
        try:
            update_tickers_json(processed_dates)
        except Exception:
            logging.exception("Failed to update tickers_last_updated.json; continuing")
            return 7  # fail hard if preferred

    return 0


if __name__ == "__main__":
    sys.exit(main())
