from __future__ import annotations

from app.config import Settings, get_settings
from app.repositories.json_repository import JsonRepository
from app.security.passwords import PasswordService
from app.services.admin_initializer import AdminInitializer, AdminInitResult
from app.storage.json_store import JsonFileStore


def initialize_application(settings: Settings | None = None) -> AdminInitResult:
    resolved_settings = settings or get_settings()
    store = JsonFileStore(resolved_settings.data_file_path)
    store.ensure_initialized()
    repository = JsonRepository(store)
    return AdminInitializer(repository, PasswordService()).initialize_if_needed(
        resolved_settings
    )
