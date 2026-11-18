"""Project paths and config loading. Everything else imports paths from here."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LABELS_DIR = DATA_DIR / "labels"
DB_PATH = PROCESSED_DIR / "jobs.duckdb"
FIGURES_DIR = ROOT / "reports" / "figures"


def load_yaml(name: str) -> dict[str, Any]:
    """Load config/<name>.yaml as a dict."""
    with open(CONFIG_DIR / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
