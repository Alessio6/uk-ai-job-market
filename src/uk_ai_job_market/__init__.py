"""UK AI Job Market Intelligence."""


def main() -> None:
    """Console entry point (`uv run uk-ai-job-market`): runs the daily pipeline."""
    from uk_ai_job_market.pipeline import main as pipeline_main

    pipeline_main()
