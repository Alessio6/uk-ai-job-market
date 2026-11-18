"""Load raw Adzuna JSON files into the DuckDB `jobs` table with upsert de-duplication.

Usage:
    uv run python -m uk_ai_job_market.process.load [--reload]

How duplicates are handled
--------------------------
* Within a batch: the same job_id found by several search terms (or several runs) is collapsed
  to one row; its search terms are merged and first/last seen are the min/max fetch time.
* Across batches: INSERT ... ON CONFLICT (job_id) DO UPDATE keeps the *earliest* first_seen,
  the *latest* last_seen, merges search_terms, and refreshes the other fields with the newest data.
* Each raw file is recorded in `loaded_files`, so daily runs only read new files.
  `--reload` drops everything and rebuilds from all raw files (raw data is the source of truth).
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from uk_ai_job_market.config import DB_PATH, RAW_DIR

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id              VARCHAR PRIMARY KEY,
    title               VARCHAR,
    company             VARCHAR,
    location            VARCHAR,
    area                VARCHAR[],      -- Adzuna hierarchy, e.g. [UK, London, Central London]
    latitude            DOUBLE,
    longitude           DOUBLE,
    category            VARCHAR,
    salary_min          DOUBLE,
    salary_max          DOUBLE,
    salary_is_predicted BOOLEAN,        -- Adzuna estimated the salary; analyse separately
    contract_type       VARCHAR,        -- permanent / contract
    contract_time       VARCHAR,        -- full_time / part_time
    description         VARCHAR,        -- truncated (~500 chars) in search results
    redirect_url        VARCHAR,
    created             TIMESTAMP,      -- posting date (UTC)
    search_terms        VARCHAR[],      -- every query that has returned this job
    first_seen          TIMESTAMP,
    last_seen           TIMESTAMP
);
CREATE TABLE IF NOT EXISTS loaded_files (
    path      VARCHAR PRIMARY KEY,
    loaded_at TIMESTAMP,
    n_rows    INTEGER
);
"""

UPSERT = """
INSERT INTO jobs BY NAME SELECT * FROM batch
ON CONFLICT (job_id) DO UPDATE SET
    title = excluded.title,
    company = excluded.company,
    location = excluded.location,
    area = excluded.area,
    latitude = excluded.latitude,
    longitude = excluded.longitude,
    category = excluded.category,
    salary_min = excluded.salary_min,
    salary_max = excluded.salary_max,
    salary_is_predicted = excluded.salary_is_predicted,
    contract_type = excluded.contract_type,
    contract_time = excluded.contract_time,
    description = excluded.description,
    redirect_url = excluded.redirect_url,
    created = excluded.created,
    search_terms = list_sort(list_distinct(list_concat(search_terms, excluded.search_terms))),
    first_seen = least(first_seen, excluded.first_seen),
    last_seen = greatest(last_seen, excluded.last_seen)
"""


def _to_bool(v) -> bool | None:
    if v is None:
        return None
    return str(v).strip() in ("1", "true", "True")


def _parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp.rstrip("Z"), "%Y%m%dT%H%M%S")


def read_raw_file(path: Path) -> list[dict]:
    """Flatten one raw file into row dicts. Supports both the wrapped format written by
    fetch_jobs ({search_term, fetched_at, results}) and a bare list of results."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        results = payload.get("results", [])
        term = payload.get("search_term") or path.stem.replace("_", " ")
        fetched_at = _parse_stamp(payload.get("fetched_at") or path.parent.name)
    else:
        results, term, fetched_at = payload, path.stem.replace("_", " "), _parse_stamp(path.parent.name)

    rows = []
    for r in results:
        loc = r.get("location") or {}
        rows.append(
            {
                "job_id": str(r["id"]),
                "title": r.get("title"),
                "company": (r.get("company") or {}).get("display_name"),
                "location": loc.get("display_name"),
                "area": loc.get("area") or [],
                "latitude": r.get("latitude"),
                "longitude": r.get("longitude"),
                "category": (r.get("category") or {}).get("label"),
                "salary_min": r.get("salary_min"),
                "salary_max": r.get("salary_max"),
                "salary_is_predicted": _to_bool(r.get("salary_is_predicted")),
                "contract_type": r.get("contract_type"),
                "contract_time": r.get("contract_time"),
                "description": r.get("description"),
                "redirect_url": r.get("redirect_url"),
                "created": r.get("created"),
                "search_term": term,
                "fetched_at": fetched_at,
            }
        )
    return rows


def build_batch(rows: list[dict]) -> pd.DataFrame:
    """Collapse rows to one per job_id (newest fetch wins for the data fields)."""
    df = pd.DataFrame(rows)
    df["created"] = pd.to_datetime(df["created"], utc=True, errors="coerce").dt.tz_localize(None)
    df["salary_min"] = pd.to_numeric(df["salary_min"], errors="coerce")
    df["salary_max"] = pd.to_numeric(df["salary_max"], errors="coerce")
    df = df.sort_values("fetched_at")
    agg = df.groupby("job_id").agg(
        search_terms=("search_term", lambda s: sorted(set(s))),
        first_seen=("fetched_at", "min"),
        last_seen=("fetched_at", "max"),
    )
    latest = df.drop_duplicates("job_id", keep="last").set_index("job_id")
    latest = latest.drop(columns=["search_term", "fetched_at"])
    return latest.join(agg).reset_index()


def connect(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA)
    return con


def load(raw_dir: Path = RAW_DIR, db_path: Path = DB_PATH, reload: bool = False) -> int:
    """Upsert all not-yet-loaded raw files. Returns the number of distinct jobs in the batch."""
    con = connect(db_path)
    if reload:
        con.execute("DELETE FROM jobs; DELETE FROM loaded_files;")

    done = {p for (p,) in con.execute("SELECT path FROM loaded_files").fetchall()}
    files = sorted(p for p in raw_dir.glob("*/*.json") if p.relative_to(raw_dir).as_posix() not in done)
    if not files:
        log.info("No new raw files to load.")
        con.close()
        return 0

    rows, file_counts = [], []
    for f in files:
        file_rows = read_raw_file(f)
        rows.extend(file_rows)
        file_counts.append((f.relative_to(raw_dir).as_posix(), len(file_rows)))

    n = 0
    if rows:
        batch = build_batch(rows)
        con.register("batch", batch)
        n = len(batch)
        con.execute("BEGIN")
        con.execute(UPSERT)
        con.executemany("INSERT INTO loaded_files VALUES (?, now()::TIMESTAMP, ?)", file_counts)
        con.execute("COMMIT")
    else:
        con.executemany("INSERT INTO loaded_files VALUES (?, now()::TIMESTAMP, ?)", file_counts)

    total = con.execute("SELECT count(*) FROM jobs").fetchone()[0]
    log.info("Loaded %d files, %d distinct jobs in batch; jobs table now has %d rows", len(files), n, total)
    con.close()
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reload", action="store_true", help="rebuild the jobs table from all raw files")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load(reload=args.reload)


if __name__ == "__main__":
    main()
