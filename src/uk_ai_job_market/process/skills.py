"""Regex skill extraction into a long-format `job_skills` table, plus a labelling sample.

Usage:
    uv run python -m uk_ai_job_market.process.skills            # rebuild job_skills
    uv run python -m uk_ai_job_market.process.skills --sample 50 # write a CSV to hand-label

Patterns live in config/skills.yaml. Matching is case-insensitive on title + description
(use (?-i:...) inside a pattern for a case-sensitive part).

Evaluation idea: label the sampled CSV by hand (one column per skill, 1/0), then compare to
the regex output for per-skill precision/recall - later, do the same for an LLM extractor.
"""

from __future__ import annotations

import argparse
import logging
import re
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

from uk_ai_job_market.config import DB_PATH, LABELS_DIR, load_yaml

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def compiled_skills() -> dict[str, list[re.Pattern]]:
    cfg = load_yaml("skills")["skills"]
    return {skill: [re.compile(p, re.I) for p in pats] for skill, pats in cfg.items()}


def extract_skills(text: str | None, skills: dict[str, list[re.Pattern]] | None = None) -> list[str]:
    skills = skills if skills is not None else compiled_skills()
    t = text or ""
    return [s for s, pats in skills.items() if any(p.search(t) for p in pats)]


def build_job_skills(jobs: pd.DataFrame) -> pd.DataFrame:
    text = jobs["title"].fillna("") + "\n" + jobs["description"].fillna("")
    rows = [(job_id, skill) for job_id, t in zip(jobs["job_id"], text) for skill in extract_skills(t)]
    return pd.DataFrame(rows, columns=["job_id", "skill"])


def run(db_path: Path = DB_PATH) -> pd.DataFrame:
    con = duckdb.connect(str(db_path))
    jobs = con.execute("SELECT job_id, title, description FROM jobs").df()
    skills_df = build_job_skills(jobs)
    con.register("skills_df", skills_df)
    con.execute("CREATE OR REPLACE TABLE job_skills AS SELECT * FROM skills_df")
    top = con.execute("""
        SELECT skill, count(*) AS n,
               round(100.0 * count(*) / (SELECT count(*) FROM jobs), 1) AS pct
        FROM job_skills GROUP BY skill ORDER BY n DESC LIMIT 10
    """).df()
    con.close()
    log.info("job_skills rebuilt (%d rows). Top skills:\n%s", len(skills_df), top.to_string(index=False))
    return skills_df


def write_labelling_sample(n: int = 50, seed: int = 42, db_path: Path = DB_PATH) -> Path:
    """Sample n postings to CSV with an empty 0/1 column per skill for hand-labelling,
    plus the regex predictions in a separate file for later comparison."""
    con = duckdb.connect(str(db_path), read_only=True)
    sample = con.execute(
        "SELECT job_id, title, description FROM jobs USING SAMPLE reservoir(?) REPEATABLE (?)",
        [n, seed],
    ).df()
    con.close()
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    skills = list(compiled_skills())

    to_label = sample.copy()
    for s in skills:
        to_label[s] = ""
    out = LABELS_DIR / "skills_to_label.csv"
    to_label.to_csv(out, index=False)

    preds = sample[["job_id"]].copy()
    texts = sample["title"].fillna("") + "\n" + sample["description"].fillna("")
    found = [set(extract_skills(t)) for t in texts]
    for s in skills:
        preds[s] = [int(s in f) for f in found]
    preds.to_csv(LABELS_DIR / "skills_regex_predictions.csv", index=False)
    log.info("Wrote %s (fill each skill column with 1/0, save as skills_labelled.csv)", out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", type=int, default=None, help="write N postings to a labelling CSV")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.sample:
        write_labelling_sample(args.sample)
    else:
        run()


if __name__ == "__main__":
    main()
