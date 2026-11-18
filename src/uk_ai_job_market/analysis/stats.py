"""Statistics helpers for the analysis notebook: bootstrap medians, salary premiums, shares."""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_N = 30  # don't report a group statistic below this sample size


def bootstrap_median_ci(
    values, n_boot: int = 5_000, ci: float = 0.95, seed: int | None = 0
) -> tuple[float, float, float]:
    """Median and percentile-bootstrap CI. Returns (median, lower, upper); NaNs if empty."""
    x = np.asarray(pd.Series(values).dropna(), dtype=float)
    if x.size == 0:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(x, size=(n_boot, x.size), replace=True), axis=1)
    alpha = (1 - ci) / 2
    return (float(np.median(x)), float(np.quantile(meds, alpha)), float(np.quantile(meds, 1 - alpha)))


def median_by_group(
    df: pd.DataFrame,
    group: str | list[str],
    value: str = "salary_annual",
    min_n: int = MIN_N,
    **boot_kwargs,
) -> pd.DataFrame:
    """Median + bootstrap CI + n per group; groups with n < min_n are dropped."""
    rows = []
    for key, g in df.groupby(group, observed=True):
        vals = g[value].dropna()
        if len(vals) < min_n:
            continue
        med, lo, hi = bootstrap_median_ci(vals, **boot_kwargs)
        key = key if isinstance(key, tuple) else (key,)
        rows.append((*key, len(vals), med, lo, hi))
    cols = ([group] if isinstance(group, str) else list(group)) + ["n", "median", "ci_low", "ci_high"]
    return pd.DataFrame(rows, columns=cols).sort_values("median", ascending=False, ignore_index=True)


def skill_salary_premium(
    jobs: pd.DataFrame,
    job_skills: pd.DataFrame,
    value: str = "salary_annual",
    within: str | None = "seniority",
    min_n: int = MIN_N,
    n_boot: int = 2_000,
    seed: int = 0,
) -> pd.DataFrame:
    """Median salary with vs without each skill, and the difference with a bootstrap CI.

    If `within` is given (default: seniority), the premium is computed inside each stratum and
    averaged weighted by the number of postings with the skill - a simple way to stop
    'senior roles mention X' masquerading as 'X pays more'. This is still correlation only.
    """
    jobs = jobs.dropna(subset=[value])
    rng = np.random.default_rng(seed)
    strata = [("all", jobs)] if within is None else list(jobs.groupby(within, observed=True))
    out = []
    for skill in job_skills["skill"].unique():
        ids = set(job_skills.loc[job_skills["skill"] == skill, "job_id"])
        diffs, weights, boot = [], [], []
        n_with_total = n_without_total = 0
        for _, s in strata:
            has = s["job_id"].isin(ids)
            a, b = s.loc[has, value].to_numpy(), s.loc[~has, value].to_numpy()
            if len(a) < 10 or len(b) < 10:
                continue
            diffs.append(np.median(a) - np.median(b))
            weights.append(len(a))
            boot.append(
                np.median(rng.choice(a, (n_boot, len(a))), axis=1) - np.median(rng.choice(b, (n_boot, len(b))), axis=1)
            )
            n_with_total += len(a)
            n_without_total += len(b)
        if n_with_total < min_n:
            continue
        w = np.array(weights) / sum(weights)
        premium = float(np.dot(w, diffs))
        boot_premium = np.average(np.vstack(boot), axis=0, weights=w)
        out.append(
            {
                "skill": skill,
                "n_with": n_with_total,
                "n_without": n_without_total,
                "premium": premium,
                "ci_low": float(np.quantile(boot_premium, 0.025)),
                "ci_high": float(np.quantile(boot_premium, 0.975)),
            }
        )
    return pd.DataFrame(out).sort_values("premium", ascending=False, ignore_index=True)


def share(df: pd.DataFrame, col: str, by: str | None = None) -> pd.DataFrame:
    """Share (%) of postings in each category of `col`, optionally within groups of `by`."""
    if by is None:
        s = df[col].value_counts()
        return pd.DataFrame({"n": s, "pct": 100 * s / s.sum()}).reset_index()
    counts = df.groupby([by, col], observed=True).size().rename("n").reset_index()
    counts["pct"] = 100 * counts["n"] / counts.groupby(by)["n"].transform("sum")
    return counts
