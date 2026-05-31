from pathlib import Path

from app.config import get_settings


def test_default_settings_point_to_backend_data_file() -> None:
    settings = get_settings()

    assert settings.session_cookie_name == "ticket_session"
    assert settings.session_ttl_hours == 8
    assert settings.data_file_path == Path("data/store.json").resolve()
