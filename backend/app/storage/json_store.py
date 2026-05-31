from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4

from app.domain.models import utc_now


SCHEMA_VERSION = 1
COLLECTIONS = (
    "users",
    "categories",
    "tickets",
    "messages",
    "audit_logs",
    "sessions",
)

T = TypeVar("T")


class StorageError(RuntimeError):
    pass


class JsonFileStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.RLock()

    def read(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._read_unlocked())

    def transaction(self, mutator: Callable[[dict[str, Any]], T]) -> T:
        with self._lock:
            data = self._read_unlocked()
            result = mutator(data)
            data["meta"]["updated_at"] = utc_now()
            self._validate(data)
            try:
                self._atomic_write(data)
            except OSError as exc:
                raise StorageError("Could not persist JSON store") from exc
            return result

    def ensure_initialized(self) -> None:
        with self._lock:
            if self.path.exists():
                self._validate(self._load_json())
                return
            self._atomic_write(self._empty_store())

    def _read_unlocked(self) -> dict[str, Any]:
        self.ensure_initialized()
        data = self._load_json()
        self._validate(data)
        return data

    def _load_json(self) -> dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError as exc:
            raise StorageError("JSON store is malformed") from exc
        except OSError as exc:
            raise StorageError("Could not read JSON store") from exc
        if not isinstance(data, dict):
            raise StorageError("JSON store root must be an object")
        return data

    def _atomic_write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _empty_store(self) -> dict[str, Any]:
        now = utc_now()
        data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "meta": {"created_at": now, "updated_at": now},
        }
        for collection in COLLECTIONS:
            data[collection] = []
        return data

    def _validate(self, data: dict[str, Any]) -> None:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise StorageError("Unsupported JSON store schema version")
        meta = data.get("meta")
        if not isinstance(meta, dict):
            raise StorageError("JSON store meta must be an object")
        if not isinstance(meta.get("created_at"), str) or not isinstance(
            meta.get("updated_at"), str
        ):
            raise StorageError("JSON store meta timestamps are invalid")
        for collection in COLLECTIONS:
            if not isinstance(data.get(collection), list):
                raise StorageError(f"JSON store collection is invalid: {collection}")
