import json
import time
import threading
from pathlib import Path
from typing import Any, Dict, Optional

PLUGIN_DATA_ROOT = Path("data/plugins")


class PluginData:
    def __init__(self, plugin_id: str, filename: str = "data.json"):
        self._path = PLUGIN_DATA_ROOT / plugin_id / filename
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {}
        self._dirty: bool = False
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._cache = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def get(self, key: str, default=None):
        with self._lock:
            return self._cache.get(key, default)

    def set(self, key: str, value):
        with self._lock:
            self._cache[key] = value
            self._save()

    def delete(self, key: str):
        with self._lock:
            self._cache.pop(key, None)
            self._save()

    def all(self) -> dict:
        with self._lock:
            return dict(self._cache)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._save()

    def update(self, data: dict):
        with self._lock:
            self._cache.update(data)
            self._save()


class PluginDataManager:
    def __init__(self):
        self._stores: Dict[str, PluginData] = {}

    def get_store(self, plugin_id: str, filename: str = "data.json") -> PluginData:
        key = f"{plugin_id}/{filename}"
        if key not in self._stores:
            self._stores[key] = PluginData(plugin_id, filename)
        return self._stores[key]

    def close_all(self):
        self._stores.clear()
