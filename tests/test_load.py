import duckdb

from uk_ai_job_market.process import load


def test_upsert_dedupes_and_tracks_seen_dates(raw_dir, tmp_path):
    db = tmp_path / "jobs.duckdb"
    load.load(raw_dir=raw_dir, db_path=db)
    con = duckdb.connect(str(db))
    assert con.execute("SELECT count(*) FROM jobs").fetchone()[0] == 3

    terms, first, last, smin = con.execute(
        "SELECT search_terms, first_seen, last_seen, salary_min FROM jobs WHERE job_id = '1'"
    ).fetchone()
    assert terms == ["ai engineer", "machine learning engineer"]
    assert str(first).startswith("2026-11-10")
    assert str(last).startswith("2026-11-11")
    assert smin == 65000  # newest fetch wins for data fields
    con.close()


def test_incremental_load_skips_loaded_files_and_merges(raw_dir, tmp_path):
    db = tmp_path / "jobs.duckdb"
    run1 = raw_dir / "20261110T080000Z"
    later = raw_dir / "20261111T080000Z"
    # Load only the first run, then add the second and load again.
    hidden = tmp_path / "hidden"
    later.rename(hidden)
    load.load(raw_dir=raw_dir, db_path=db)
    hidden.rename(later)
    assert load.load(raw_dir=raw_dir, db_path=db) == 2  # only the new file's 2 jobs
    assert load.load(raw_dir=raw_dir, db_path=db) == 0  # nothing new

    con = duckdb.connect(str(db))
    first, last = con.execute("SELECT first_seen, last_seen FROM jobs WHERE job_id = '1'").fetchone()
    assert str(first).startswith("2026-11-10") and str(last).startswith("2026-11-11")
    assert con.execute("SELECT count(*) FROM jobs").fetchone()[0] == 3
    con.close()
    assert run1.exists()


def test_predicted_flag_parsed_as_bool(raw_dir, tmp_path):
    db = tmp_path / "jobs.duckdb"
    load.load(raw_dir=raw_dir, db_path=db)
    con = duckdb.connect(str(db))
    assert con.execute("SELECT bool_or(salary_is_predicted) FROM jobs").fetchone()[0] is False
    con.close()
