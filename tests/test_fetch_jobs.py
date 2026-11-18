import json
from unittest.mock import MagicMock

import pytest

from tests.conftest import make_result
from uk_ai_job_market.collect import fetch_jobs


def fake_response(results):
    resp = MagicMock()
    resp.json.return_value = {"results": results, "count": 999}
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_paginates_until_short_page():
    session = MagicMock()
    session.get.side_effect = [
        fake_response([make_result(i) for i in range(2)]),  # full page (results_per_page=2)
        fake_response([make_result(10)]),  # short page -> stop
        fake_response([make_result(99)]),  # must not be requested
    ]
    jobs = fetch_jobs.fetch("ml engineer", "id", "key", session, max_pages=5, results_per_page=2, sleep_seconds=0)
    assert [j["id"] for j in jobs] == ["0", "1", "10"]
    assert session.get.call_count == 2
    first_call = session.get.call_args_list[0]
    assert first_call.args[0].endswith("/search/1")
    assert first_call.kwargs["params"]["what"] == "ml engineer"


def test_fetch_stops_on_empty_page():
    session = MagicMock()
    session.get.side_effect = [fake_response([])]
    assert fetch_jobs.fetch("x", "id", "key", session, sleep_seconds=0) == []


def test_run_writes_wrapped_raw_files(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_jobs, "get_credentials", lambda: ("id", "key"))
    monkeypatch.setattr(fetch_jobs, "fetch", lambda term, *a, **k: [make_result(1)])
    out = fetch_jobs.run(terms=["AI engineer"], max_pages=1, out_root=tmp_path)
    payload = json.loads((out / "ai_engineer.json").read_text())
    assert payload["search_term"] == "AI engineer"
    assert payload["results"][0]["id"] == "1"


def test_missing_credentials_exit(monkeypatch):
    monkeypatch.setattr(fetch_jobs, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ADZUNA_APP_ID", "replace_me")
    monkeypatch.setenv("ADZUNA_APP_KEY", "replace_me")
    with pytest.raises(SystemExit):
        fetch_jobs.get_credentials()
