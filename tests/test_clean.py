import pandas as pd
import pytest

from uk_ai_job_market.process import clean


@pytest.mark.parametrize(
    "smin,smax,expected",
    [
        (60000, 80000, 70000),
        (60000, None, 60000),
        (None, None, None),
        (0, 50000, 50000),
    ],
)
def test_salary_midpoint(smin, smax, expected):
    assert clean.salary_midpoint(smin, smax) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (70000, 70000),  # annual
        (500, 500 * 220),  # day rate
        (50, 50 * 1650),  # hourly
        (5000, None),  # ambiguous (monthly?) -> dropped
        (12000, None),  # annual but under the 15k floor
        (900000, None),  # implausibly high
        (None, None),
    ],
)
def test_annualise(value, expected):
    assert clean.annualise(value) == expected


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Senior Machine Learning Engineer", "senior"),
        ("Lead Data Scientist", "lead"),
        ("Principal AI Engineer", "lead"),
        ("Head of Data Science", "head"),
        ("Graduate Data Engineer", "junior"),
        ("Machine Learning Intern", "junior"),
        ("Data Scientist", "mid"),
        ("Sr. Data Engineer", "senior"),
    ],
)
def test_seniority(title, expected):
    assert clean.derive_seniority(title) == expected


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Machine Learning Engineer", "ml_engineering"),
        ("MLOps Engineer", "ml_engineering"),
        ("Senior LLM Engineer", "ai_llm_engineering"),
        ("AI Engineer", "ai_llm_engineering"),
        ("Data Scientist", "data_science"),
        ("Data Engineer", "data_engineering"),
        ("Research Scientist, Machine Learning", "research"),
        ("Data Analyst", "data_analysis"),
        ("AI Solutions Engineer, Microsoft Tech Stack", "ai_llm_engineering"),
        ("AI Engineering Manager", "ai_llm_engineering"),
        ("Manager - AIML Developer", "ai_llm_engineering"),
        ("Data Engineering Manager", "data_engineering"),
        ("Sr. Applied Science Manager", "research"),
        ("Senior Software Engineer - Build AI Tools (Python, GoLang)", "other"),
        ("Chef", "other"),
    ],
)
def test_role_family(title, expected):
    assert clean.derive_role_family(title) == expected


@pytest.mark.parametrize(
    "title,desc,expected",
    [
        ("ML Engineer (Remote)", "", "remote"),
        ("ML Engineer", "Hybrid, 2 days a week in office", "hybrid"),
        ("ML Engineer", "Hybrid with remote flexibility", "hybrid"),
        ("ML Engineer", "Based in our Leeds office", "onsite/unspecified"),
    ],
)
def test_work_mode(title, desc, expected):
    assert clean.work_mode(title, desc) == expected


def test_region():
    assert clean.derive_region(["UK", "London", "Central London"]) == "London"
    assert clean.derive_region(["UK"]) == "Unknown"
    assert clean.region_group("Scotland") == "Rest of UK"


def test_flag_reposts():
    df = pd.DataFrame(
        {
            "title": ["ML Engineer", "ML Engineer", "ml engineer", "ML Engineer", "Data Scientist"],
            "company": ["Acme"] * 5,
            "location": ["London"] * 5,
            "created": pd.to_datetime(["2026-11-01", "2026-11-04", "2026-11-09", "2026-12-01", "2026-11-02"]),
        }
    )
    assert clean.flag_reposts(df).tolist() == [False, True, True, False, False]


def test_clean_frame_end_to_end(raw_dir, tmp_path):
    from uk_ai_job_market.process import load

    db = tmp_path / "jobs.duckdb"
    load.load(raw_dir=raw_dir, db_path=db)
    out = clean.run(db_path=db).set_index("job_id")
    assert out.loc["2", "seniority"] == "senior"
    assert out.loc["3", "region_group"] == "Rest of UK"
    assert out.loc["1", "salary_annual"] == pytest.approx(72500)
    assert bool(out.loc["1", "salary_real"]) is True
