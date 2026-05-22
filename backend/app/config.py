from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_REPO_ROOT / "backend" / ".env")


def demo_mode_enabled() -> bool:
    return os.getenv("ALPHALENS_DEMO_MODE", "0") == "1"


def demo_filings_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "demo_filings"
