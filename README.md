# UK AI Job Market Intelligence

An end-to-end project analysing the UK job market for AI, ML and data science roles. It collects job postings daily, analyses which skills, salaries and locations are in demand, trains models to predict salary band from job descriptions, and builds an LLM-powered assistant that matches a CV to relevant roles and highlights skill gaps. Each stage is measured: statistical analysis for the insights, benchmarked model comparisons for the ML, and a hand-labelled evaluation set for the assistant.

## Status
- [ ] Layer 1 – Data pipeline & market analysis *(in progress)*
- [ ] Layer 2 – Salary/seniority prediction models & API
- [ ] Layer 3 – LLM CV-to-job matching assistant with evals

## Questions this project answers
- Which skills appear most often in UK AI/ML/data job postings, and which are growing?
- Which skills are associated with higher salaries?
- How do London, the rest of the UK, and remote roles compare?

## Tech
Python · DuckDB · pandas · scikit-learn · PyTorch · MLflow · FastAPI · Docker

## Data
Job postings from the [Adzuna API](https://developer.adzuna.com/). Raw data is not redistributed in this repo.

## Use of AI tools
Built with help from Claude Code for implementation. Project design, experiment choices, evaluation and analysis are my own.
