from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPOSITORY_ROOT / ".env")


def database_path() -> Path:
    configured_path = os.getenv("DATABASE_PATH", "data/trialguard.db")
    path = Path(configured_path)
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    return path


def app_host() -> str:
    return os.getenv("APP_HOST", "127.0.0.1")


def app_port() -> int:
    return int(os.getenv("APP_PORT", "8000"))


def seed_demo_data_enabled() -> bool:
    return os.getenv("SEED_DEMO_DATA", "false").lower() == "true"