from dataclasses import replace
from datetime import timedelta

from app.config import Settings
from app.domain.enums import UserRole, UserStatus
from app.domain.models import utc_now
from app.repositories.json_repository import JsonRepository
from app.security.passwords import PasswordService
from app.security.sessions import SessionService, hash_session_token
from app.services.admin_initializer import AdminInitializer, AdminInitStatus
from app.storage.json_store import JsonFileStore


def make_settings(tmp_path, **overrides) -> Settings:
    settings = Settings(
        app_name="test",
        app_env="test",
        project_root=tmp_path,
        backend_root=tmp_path,
        data_file_path=tmp_path / "store.json",
        session_cookie_name="ticket_session",
        session_cookie_secure=False,
        session_ttl_hours=8,
        initial_admin_username="admin01",
        initial_admin_email="admin01@example.com",
        initial_admin_password="StrongPassword123",
    )
    return replace(settings, **overrides)


def make_repo(tmp_path) -> JsonRepository:
    return JsonRepository(JsonFileStore(tmp_path / "store.json"))


def test_password_hash_uses_argon2id_and_verifies() -> None:
    service = PasswordService()

    password_hash = service.hash_password("StrongPassword123")

    assert password_hash.startswith("$argon2id$")
    assert "StrongPassword123" not in password_hash
    assert service.verify_password("StrongPassword123", password_hash)
    assert not service.verify_password("wrong", password_hash)


def test_session_service_persists_only_token_hash_and_authenticates(tmp_path) -> None:
    repo = make_repo(tmp_path)
    user = repo.add_user(
        username="customer01",
        email="customer01@example.com",
        password_hash="hash",
        role=UserRole.CUSTOMER,
    )
    service = SessionService(repo, ttl_hours=8)

    created = service.create_session(user["id"])
    store_data = repo.store.read()

    assert created.raw_token
    assert created.raw_token not in str(store_data)
    assert store_data["sessions"][0]["token_hash"] == hash_session_token(
        created.raw_token
    )
    assert service.authenticate(created.raw_token)["id"] == user["id"]


def test_session_authentication_rejects_revoked_expired_or_disabled_users(tmp_path) -> None:
    repo = make_repo(tmp_path)
    user = repo.add_user(
        username="customer01",
        email="customer01@example.com",
        password_hash="hash",
        role=UserRole.CUSTOMER,
    )
    service = SessionService(repo, ttl_hours=8)

    revoked = service.create_session(user["id"])
    service.revoke_session(revoked.raw_token)
    assert service.authenticate(revoked.raw_token) is None

    expired = service.create_session(
        user["id"], now=utc_now(offset=timedelta(hours=-9))
    )
    assert service.authenticate(expired.raw_token) is None

    active = service.create_session(user["id"])
    repo.update_user_status(user["id"], UserStatus.DISABLED)
    assert service.authenticate(active.raw_token) is None


def test_admin_initializer_creates_first_admin_once(tmp_path) -> None:
    repo = make_repo(tmp_path)
    settings = make_settings(tmp_path)
    initializer = AdminInitializer(repo, PasswordService())

    first = initializer.initialize_if_needed(settings)
    second = initializer.initialize_if_needed(settings)
    admins = [user for user in repo.list_users() if user["role"] == "admin"]

    assert first.status == AdminInitStatus.CREATED
    assert second.status == AdminInitStatus.ALREADY_EXISTS
    assert len(admins) == 1
    assert admins[0]["username"] == "admin01"
    assert admins[0]["role"] == "admin"
    assert admins[0]["status"] == "active"
    assert admins[0]["password_hash"].startswith("$argon2id$")


def test_admin_initializer_does_not_create_admin_without_complete_config(tmp_path) -> None:
    repo = make_repo(tmp_path)
    settings = make_settings(tmp_path, initial_admin_password="")
    initializer = AdminInitializer(repo, PasswordService())

    result = initializer.initialize_if_needed(settings)

    assert result.status == AdminInitStatus.MISSING_CONFIG
    assert repo.list_users() == []
