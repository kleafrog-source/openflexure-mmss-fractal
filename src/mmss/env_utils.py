"""
Helpers for loading project environment variables consistently.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_project_env() -> None:
    """
    Load `.env` first, then apply non-empty values from `.env.local`.

    Empty values in `.env.local` do not erase working values from `.env`.
    Existing process environment variables keep priority unless they are blank.
    """
    merged: dict[str, str] = {}

    for env_name in (".env", ".env.local"):
        env_path = PROJECT_ROOT / env_name
        if not env_path.exists():
            continue
        for key, value in dotenv_values(env_path).items():
            if value in (None, ""):
                continue
            merged[key] = value

    for key, value in merged.items():
        if os.environ.get(key, "") == "":
            os.environ[key] = value
