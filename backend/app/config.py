from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
# In Docker, backend/ and frontend/ are both under /app/, so BACKEND_ROOT is already the project root.
# Locally, backend/ is a subdirectory, so we go one level up.
_PROJECT_PARENT = BACKEND_ROOT.parent
PROJECT_ROOT = BACKEND_ROOT if (BACKEND_ROOT / "frontend").exists() else _PROJECT_PARENT


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default.resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    project_root: Path
    backend_root: Path
    data_file_path: Path
    session_cookie_name: str
    session_cookie_secure: bool
    session_ttl_hours: int
    initial_admin_username: str
    initial_admin_email: str
    initial_admin_password: str

    @property
    def initial_admin_configured(self) -> bool:
        return all(
            [
                self.initial_admin_username.strip(),
                self.initial_admin_email.strip(),
                self.initial_admin_password,
            ]
        )


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "企业售后工单系统"),
        app_env=os.getenv("APP_ENV", "local"),
        project_root=PROJECT_ROOT,
        backend_root=BACKEND_ROOT,
        data_file_path=_path_from_env(
            "TICKET_DATA_FILE", BACKEND_ROOT / "data" / "store.json"
        ),
        session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "ticket_session"),
        session_cookie_secure=_bool_from_env("SESSION_COOKIE_SECURE", False),
        session_ttl_hours=int(os.getenv("SESSION_TTL_HOURS", "8")),
        initial_admin_username=os.getenv("INITIAL_ADMIN_USERNAME", ""),
        initial_admin_email=os.getenv("INITIAL_ADMIN_EMAIL", ""),
        initial_admin_password=os.getenv("INITIAL_ADMIN_PASSWORD", ""),
    )
