# Runs the daily Layer 1 pipeline. Called by Windows Task Scheduler (see register_task.ps1).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
uv run python -m uk_ai_job_market.pipeline
exit $LASTEXITCODE
