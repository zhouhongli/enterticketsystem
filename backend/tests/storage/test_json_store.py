import json

import pytest

from app.storage.json_store import JsonFileStore, StorageError


def test_missing_store_file_is_initialized_with_versioned_shape(tmp_path) -> None:
    store_path = tmp_path / "store.json"
    store = JsonFileStore(store_path)

    data = store.read()

    assert store_path.exists()
    assert data["schema_version"] == 1
    assert set(data) == {
        "schema_version",
        "meta",
        "users",
        "categories",
        "tickets",
        "messages",
        "audit_logs",
        "sessions",
    }
    assert data["users"] == []


def test_transaction_atomically_persists_changes(tmp_path) -> None:
    store = JsonFileStore(tmp_path / "store.json")

    def add_user(data: dict) -> str:
        data["users"].append({"id": "user-1"})
        return "done"

    result = store.transaction(add_user)

    assert result == "done"
    assert store.read()["users"] == [{"id": "user-1"}]


def test_failed_atomic_write_keeps_previous_store_content(tmp_path) -> None:
    class BrokenStore(JsonFileStore):
        def _atomic_write(self, data: dict) -> None:
            raise OSError("disk is full")

    store_path = tmp_path / "store.json"
    JsonFileStore(store_path).transaction(
        lambda data: data["users"].append({"id": "user-1"})
    )
    before = json.loads(store_path.read_text(encoding="utf-8"))

    broken = BrokenStore(store_path)
    with pytest.raises(StorageError):
        broken.transaction(lambda data: data["users"].append({"id": "user-2"}))

    after = json.loads(store_path.read_text(encoding="utf-8"))
    assert after == before
