import json

import pytest


def make_result(
    job_id,
    title="Machine Learning Engineer",
    company="Acme",
    area=None,
    salary_min=60000,
    salary_max=80000,
    predicted="0",
    created="2026-11-10T09:00:00Z",
    description="We use Python, PyTorch and AWS. Hybrid working.",
):
    return {
        "id": str(job_id),
        "title": title,
        "company": {"display_name": company},
        "location": {"display_name": "London", "area": area or ["UK", "London", "Central London"]},
        "category": {"label": "IT Jobs"},
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_is_predicted": predicted,
        "contract_type": "permanent",
        "contract_time": "full_time",
        "description": description,
        "redirect_url": f"https://example.com/{job_id}",
        "created": created,
        "latitude": 51.5,
        "longitude": -0.1,
    }


@pytest.fixture
def raw_dir(tmp_path):
    """Two fetch runs: job 1 appears in both runs and under two search terms."""
    root = tmp_path / "raw"
    run1 = root / "20261110T080000Z"
    run2 = root / "20261111T080000Z"
    run1.mkdir(parents=True)
    run2.mkdir(parents=True)

    def write(folder, term, results):
        slug = term.replace(" ", "_")
        payload = {"search_term": term, "fetched_at": folder.name, "results": results}
        (folder / f"{slug}.json").write_text(json.dumps(payload))

    write(run1, "machine learning engineer", [make_result(1), make_result(2, title="Senior Data Scientist")])
    write(run1, "ai engineer", [make_result(1)])
    write(
        run2,
        "machine learning engineer",
        [
            make_result(1, salary_min=65000),
            make_result(3, title="Graduate Data Engineer", area=["UK", "Scotland", "Edinburgh"]),
        ],
    )
    return root
