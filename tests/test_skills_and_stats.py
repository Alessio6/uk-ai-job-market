import numpy as np
import pandas as pd
import pytest

from uk_ai_job_market.analysis import stats
from uk_ai_job_market.process.skills import extract_skills


@pytest.mark.parametrize(
    "text,present,absent",
    [
        ("Python and SQL with PyTorch on AWS", {"python", "sql", "pytorch", "aws"}, {"java"}),
        ("Experience with JavaScript", set(), {"java"}),
        ("Build RAG pipelines with LLMs and LangChain", {"rag", "llm", "langchain"}, set()),
        ("Strong R and tidyverse skills", {"r"}, set()),
        ("R&D team working on forecasting", set(), {"r"}),
        ("Deploy with Docker and k8s", {"docker", "kubernetes"}, set()),
        ("We do drag and drop", set(), {"rag"}),
    ],
)
def test_extract_skills(text, present, absent):
    found = set(extract_skills(text))
    assert present <= found
    assert not (absent & found)


def test_extract_skills_empty():
    assert extract_skills(None) == []


def test_bootstrap_median_ci_brackets_median():
    rng = np.random.default_rng(1)
    x = rng.normal(60000, 10000, 500)
    med, lo, hi = stats.bootstrap_median_ci(x, n_boot=1000)
    assert lo < med < hi
    assert hi - lo < 5000


def test_median_by_group_drops_small_groups():
    df = pd.DataFrame({"g": ["a"] * 40 + ["b"] * 5, "salary_annual": np.arange(45) * 1000.0})
    out = stats.median_by_group(df, "g", n_boot=200)
    assert out["g"].tolist() == ["a"]
    assert out.loc[0, "n"] == 40


def test_skill_premium_controls_for_seniority():
    # Skill X only appears in senior jobs; within each level it has no effect on pay.
    rng = np.random.default_rng(0)
    rows = []
    for i in range(400):
        senior = i % 2 == 0
        rows.append(
            {
                "job_id": str(i),
                "seniority": "senior" if senior else "mid",
                "salary_annual": rng.normal(90000 if senior else 55000, 5000),
                "has_x": senior and rng.random() < 0.5,
            }
        )
    jobs = pd.DataFrame(rows)
    job_skills = pd.DataFrame({"job_id": jobs.loc[jobs.has_x, "job_id"], "skill": "x"})
    # Senior-only skill: no within-stratum comparison in 'mid', compare inside 'senior' only.
    adjusted = stats.skill_salary_premium(jobs, job_skills, within="seniority", n_boot=300)
    naive = stats.skill_salary_premium(jobs, job_skills, within=None, n_boot=300)
    assert naive.loc[0, "premium"] > 20000  # naive: looks like a big premium
    assert abs(adjusted.loc[0, "premium"]) < 3000  # adjusted: ~no premium


def test_share():
    df = pd.DataFrame({"a": ["x", "x", "y", "y"], "b": ["p", "q", "p", "p"]})
    s = stats.share(df, "b", by="a").set_index(["a", "b"])
    assert s.loc[("y", "p"), "pct"] == 100
