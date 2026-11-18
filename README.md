# UK AI Job Market Intelligence

An end-to-end project analysing the UK job market for AI, ML and data science roles. It collects job postings daily, analyses which skills, salaries and locations are in demand, trains models to predict salary band from job descriptions, and builds an LLM-powered assistant that matches a CV to relevant roles and highlights skill gaps. Each stage is measured: statistical analysis for the insights, benchmarked model comparisons for the ML, and a hand-labelled evaluation set for the assistant.

## Status
- [ ] Layer 1 – Data pipeline & market analysis *complete*
- [ ] Layer 2 – Salary/seniority prediction models & API *in progress*
- [ ] Layer 3 – LLM CV-to-job matching assistant with evals

## Questions this project answers
- Which skills appear most often in UK AI/ML/data job postings, and which are growing?
- Which skills are associated with higher salaries?
- How do London, the rest of the UK, and remote roles compare?

## Tech
Python · DuckDB · pandas · scikit-learn · PyTorch · MLflow · FastAPI · Docker

## Data
Job postings from the [Adzuna API](https://developer.adzuna.com/). Raw data is not redistributed in this repo.

## Pipeline
```
Adzuna API ──► data/raw/<timestamp>/*.json ──► DuckDB `jobs` (upsert, first/last seen)
           ──► `jobs_clean` (salary, region, remote, seniority, role family, reposts)
           ──► `job_skills` (regex skill extraction)  ──► notebooks / reports/figures
```

## Quick start
```powershell
uv sync                                              # Python 3.12 + dependencies
copy .env.example .env                               # then add your Adzuna app_id / app_key
uv run python -m uk_ai_job_market.pipeline           # fetch -> load -> clean -> skills
uv run pytest                                        # tests
```
Search terms live in `config/searches.yaml`, skill patterns in `config/skills.yaml`.
To collect daily on Windows: `powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1`.

## Limitations (so far)
- Single data source (Adzuna); search results include only the first ~500 characters of each description,
  so keyword-based skill rates are lower bounds.
- Many salaries are Adzuna estimates (`salary_is_predicted`); salary findings use only advertised salaries.
- Seniority, role family and remote status are derived from keyword rules, not ground truth.

## Use of AI tools
Built with help from Claude Code for implementation. Project design, experiment choices, evaluation and analysis are my own.
