"""Run the whole Layer 1 pipeline: fetch -> load -> clean -> skills.

Usage:
    uv run python -m uk_ai_job_market.pipeline              # daily run
    uv run python -m uk_ai_job_market.pipeline --skip-fetch # rebuild from existing raw data
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime

from uk_ai_job_market.collect import fetch_jobs
from uk_ai_job_market.config import DATA_DIR
from uk_ai_job_market.process import clean, load, skills


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--reload", action="store_true", help="rebuild jobs table from all raw files")
    args = parser.parse_args()

    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / f"pipeline_{datetime.now():%Y%m}.log", encoding="utf-8"),
        ],
    )
    log = logging.getLogger("pipeline")
    try:
        if not args.skip_fetch:
            fetch_jobs.run()
        load.load(reload=args.reload)
        clean.run()
        skills.run()
        log.info("Pipeline finished OK")
    except Exception:
        log.exception("Pipeline failed")
        raise


if __name__ == "__main__":
    main()
