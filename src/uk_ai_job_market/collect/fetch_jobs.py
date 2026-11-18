"""Fetch UK job postings from the Adzuna search API and save the raw JSON.

Usage:
    uv run python -m uk_ai_job_market.collect.fetch_jobs [--max-pages N] [--terms "data scientist" ...]

Output: data/raw/<UTC timestamp>/<search_term>.json  (a list of raw Adzuna result dicts)
Raw responses are saved untouched so cleaning can be re-run without hitting the API again.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from uk_ai_job_market.config import RAW_DIR, ROOT, load_yaml

log = logging.getLogger(__name__)

BASE_URL = "https://api.adzuna.com/v1/api/jobs/gb/search/{page}"


def get_credentials() -> tuple[str, str]:
    load_dotenv(ROOT / ".env")
    app_id = os.environ.get("ADZUNA_APP_ID", "")
    app_key = os.environ.get("ADZUNA_APP_KEY", "")
    if not app_id or not app_key or "replace_me" in (app_id, app_key):
        raise SystemExit(
            "Adzuna credentials missing. Copy .env.example to .env and fill in ADZUNA_APP_ID and ADZUNA_APP_KEY."
        )
    return app_id, app_key


def make_session(total_retries: int = 5) -> requests.Session:
    """Session that retries on connection errors, 429 and 5xx with exponential backoff."""
    retry = Retry(
        total=total_retries,
        backoff_factor=2,  # 2s, 4s, 8s, ...
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch(
    query: str,
    app_id: str,
    app_key: str,
    session: requests.Session,
    max_pages: int = 10,
    results_per_page: int = 50,
    sleep_seconds: float = 1.5,
) -> list[dict]:
    """Fetch up to max_pages pages of results for one search term."""
    results: list[dict] = []
    for page in range(1, max_pages + 1):
        resp = session.get(
            BASE_URL.format(page=page),
            params={
                "app_id": app_id,
                "app_key": app_key,
                "what": query,
                "results_per_page": results_per_page,
                "content-type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("results", [])
        if not batch:
            break
        results.extend(batch)
        log.debug("%s page %d: %d results (total count %s)", query, page, len(batch), payload.get("count"))
        if len(batch) < results_per_page:
            break  # last page
        time.sleep(sleep_seconds)
    return results


def slugify(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")


def run(terms: list[str] | None = None, max_pages: int | None = None, out_root: Path = RAW_DIR) -> Path:
    """Fetch all configured search terms into a new timestamped raw folder. Returns that folder."""
    cfg = load_yaml("searches")
    terms = terms or cfg["searches"]
    max_pages = max_pages or cfg.get("max_pages", 10)
    app_id, app_key = get_credentials()
    session = make_session()

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = out_root / stamp
    out.mkdir(parents=True, exist_ok=True)

    for term in terms:
        try:
            jobs = fetch(
                term,
                app_id,
                app_key,
                session,
                max_pages=max_pages,
                results_per_page=cfg.get("results_per_page", 50),
                sleep_seconds=cfg.get("sleep_seconds", 1.5),
            )
        except requests.HTTPError as e:
            # One failing term shouldn't lose the others; log and carry on.
            log.error("%s: failed with %s", term, e)
            continue
        payload = {"search_term": term, "fetched_at": stamp, "results": jobs}
        (out / f"{slugify(term)}.json").write_text(json.dumps(payload), encoding="utf-8")
        log.info("%s: %d postings", term, len(jobs))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-pages", type=int, default=None, help="override max_pages from config")
    parser.add_argument("--terms", nargs="*", default=None, help="override search terms from config")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = run(terms=args.terms, max_pages=args.max_pages)
    print(f"Saved raw data to {out}")


if __name__ == "__main__":
    main()
