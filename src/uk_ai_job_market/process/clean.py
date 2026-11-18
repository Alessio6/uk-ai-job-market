"""Clean the raw `jobs` table into `jobs_clean`.

Usage:
    uv run python -m uk_ai_job_market.process.clean

Every rule lives in a small pure function below so it can be unit-tested and adjusted.
THE RULES (tweak the constants, then re-run):

Salary
  * Pick a midpoint: (min+max)/2, or whichever one is present.
  * Annualise by magnitude, since Adzuna doesn't say what period a salary covers:
      < HOURLY_MAX (150)        -> hourly  x HOURS_PER_YEAR (1,650 = 7.5h x 220d)
      < DAILY_MAX (2,000)       -> daily   x WORKING_DAYS (220)
      < ANNUAL_MIN_RAW (10,000) -> ambiguous (could be monthly) -> dropped
      otherwise                 -> already annual
  * Annual values outside [SALARY_FLOOR, SALARY_CEILING] (15k-400k) are dropped as implausible.
  * salary_is_predicted is kept; `salary_real` = has a salary AND it isn't an Adzuna estimate.

Region       Adzuna's area[1] (e.g. "London", "South East England"), grouped as London / Rest of UK.
Work mode    regex on title+description: remote > hybrid > on-site/unspecified.
Seniority    title keywords, checked from most senior down (see SENIORITY_RULES).
Role family  title keywords, first match wins (see ROLE_FAMILY_RULES).
Reposts      same normalised title+company+location within REPOST_WINDOW_DAYS of an earlier
             posting -> is_repost = TRUE (kept in the table, filtered out in analysis).
"""

from __future__ import annotations

import logging
import re

import duckdb
import pandas as pd

from uk_ai_job_market.config import DB_PATH

log = logging.getLogger(__name__)

# --- Salary ---------------------------------------------------------------------------
HOURLY_MAX = 150
DAILY_MAX = 2_000
ANNUAL_MIN_RAW = 10_000
WORKING_DAYS = 220
HOURS_PER_YEAR = 1_650
SALARY_FLOOR = 15_000
SALARY_CEILING = 400_000


def salary_midpoint(smin: float | None, smax: float | None) -> float | None:
    vals = [v for v in (smin, smax) if v is not None and not pd.isna(v) and v > 0]
    if not vals:
        return None
    return sum(vals) / len(vals)


def salary_period(value: float | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    if value < HOURLY_MAX:
        return "hourly"
    if value < DAILY_MAX:
        return "daily"
    if value < ANNUAL_MIN_RAW:
        return "ambiguous"
    return "annual"


def annualise(value: float | None) -> float | None:
    """Convert a raw salary figure to annual GBP, or None if implausible/ambiguous."""
    period = salary_period(value)
    if period is None or period == "ambiguous":
        return None
    annual = {"hourly": value * HOURS_PER_YEAR, "daily": value * WORKING_DAYS, "annual": value}[period]
    if not (SALARY_FLOOR <= annual <= SALARY_CEILING):
        return None
    return float(annual)


# --- Region ---------------------------------------------------------------------------
def derive_region(area: list[str] | None) -> str:
    """Adzuna area is a hierarchy like ['UK', 'London', 'Central London']."""
    if area is None or len(area) < 2:
        return "Unknown"
    return str(area[1])


def region_group(region: str) -> str:
    if region == "London":
        return "London"
    if region == "Unknown":
        return "Unknown"
    return "Rest of UK"


# --- Work mode ------------------------------------------------------------------------
REMOTE_RE = re.compile(r"\b(fully[- ]remote|remote[- ]first|100% remote|work from home|wfh|remote)\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b|\b\d (?:days?|x) (?:a|per) week in (?:the )?office\b", re.I)


def work_mode(title: str | None, description: str | None) -> str:
    text = f"{title or ''} {description or ''}"
    # Hybrid checked first: "hybrid - 2 days remote" should be hybrid, not remote.
    if HYBRID_RE.search(text):
        return "hybrid"
    if REMOTE_RE.search(text):
        return "remote"
    return "onsite/unspecified"


# --- Seniority ------------------------------------------------------------------------
SENIORITY_RULES: list[tuple[str, str]] = [
    ("head", r"\b(head of|director|vp|vice president|chief)\b"),
    ("lead", r"\b(lead|principal|staff|architect|manager)\b"),
    ("senior", r"\b(senior|snr|sr\.?)\b"),
    ("junior", r"\b(junior|jnr|jr\.?|graduate|grad|intern(ship)?|entry[- ]level|trainee|apprentice|placement)\b"),
]
SENIORITY_ORDER = ["junior", "mid", "senior", "lead", "head"]


def derive_seniority(title: str | None) -> str:
    t = title or ""
    for level, pattern in SENIORITY_RULES:
        if re.search(pattern, t, re.I):
            return level
    return "mid"


# --- Role family ----------------------------------------------------------------------
ROLE_FAMILY_RULES: list[tuple[str, str]] = [
    ("research", r"\bresearch(er)?\b|\bapplied scien(tist|ce)\b|\bresearch scientist\b"),
    (
        "ai_llm_engineering",
        r"\b(llm|gen ?ai|generative|prompt|aiml|ai/ml)\b"
        r"|\bai\b[\w\s/&,-]*\b(engineer(ing)?|developer|automation|solutions?|architect)\b",
    ),
    ("ml_engineering", r"\b(machine learning|ml|mlops|ml ops|computer vision|nlp|deep learning)\b"),
    (
        "data_engineering",
        r"\b(data engineer(ing)?|analytics engineer|etl|data platform|big data|data architect)\b",
    ),
    ("data_science", r"\b(data scien(ce|tist)|decision scientist|quantitative analyst|statistician)\b"),
    ("data_analysis", r"\b(data analyst|bi analyst|business intelligence|insight analyst)\b"),
]


def derive_role_family(title: str | None) -> str:
    t = title or ""
    for family, pattern in ROLE_FAMILY_RULES:
        if re.search(pattern, t, re.I):
            return family
    return "other"


# --- Reposts --------------------------------------------------------------------------
REPOST_WINDOW_DAYS = 7


def _norm(s: pd.Series) -> pd.Series:
    return s.fillna("").str.lower().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()


def flag_reposts(df: pd.DataFrame, window_days: int = REPOST_WINDOW_DAYS) -> pd.Series:
    """True for postings that repeat an earlier (title, company, location) within window_days.
    Each posting is compared to the previous one in its group (so a chain of weekly reposts
    is all flagged except the first)."""
    key = _norm(df["title"]) + "|" + _norm(df["company"]) + "|" + _norm(df["location"])
    created = pd.to_datetime(df["created"])
    order = created.sort_values(kind="stable").index
    gap = created.loc[order].groupby(key.loc[order]).diff()
    is_repost = gap.notna() & (gap <= pd.Timedelta(days=window_days))
    return is_repost.reindex(df.index).fillna(False).astype(bool)


# --- Build the table ------------------------------------------------------------------
def clean_frame(jobs: pd.DataFrame) -> pd.DataFrame:
    df = jobs.copy()
    raw_mid = [salary_midpoint(a, b) for a, b in zip(df["salary_min"], df["salary_max"])]
    df["salary_period"] = [salary_period(v) for v in raw_mid]
    df["salary_annual"] = [annualise(v) for v in raw_mid]
    df["has_salary"] = df["salary_annual"].notna()
    df["salary_real"] = df["has_salary"] & ~df["salary_is_predicted"].fillna(False).astype(bool)
    df["region"] = [derive_region(a) for a in df["area"]]
    df["region_group"] = df["region"].map(region_group)
    df["work_mode"] = [work_mode(t, d) for t, d in zip(df["title"], df["description"])]
    df["seniority"] = df["title"].map(derive_seniority)
    df["role_family"] = df["title"].map(derive_role_family)
    df["is_repost"] = flag_reposts(df)
    df["created_week"] = pd.to_datetime(df["created"]).dt.to_period("W-SUN").dt.start_time
    df["salary_annual"] = df["salary_annual"].astype(float)  # None -> NaN for DuckDB DOUBLE
    return df


def run(db_path=DB_PATH) -> pd.DataFrame:
    con = duckdb.connect(str(db_path))
    jobs = con.execute("SELECT * FROM jobs").df()
    clean = clean_frame(jobs)
    con.register("clean_df", clean)
    con.execute("CREATE OR REPLACE TABLE jobs_clean AS SELECT * FROM clean_df")
    summary = con.execute("""
        SELECT count(*) AS jobs,
               sum(is_repost::INT) AS reposts,
               sum(has_salary::INT) AS with_salary,
               sum(salary_real::INT) AS with_real_salary
        FROM jobs_clean
    """).df()
    con.close()
    log.info("jobs_clean rebuilt:\n%s", summary.to_string(index=False))
    return clean


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()


if __name__ == "__main__":
    main()
