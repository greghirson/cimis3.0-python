"""On-disk response cache backed by SQLite (stdlib only).

CIMIS historical weather data is immutable once the date range is fully in
the past, so those responses are cached indefinitely. Station metadata and
zip code lists change occasionally, so they are cached with a TTL.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

DEFAULT_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "cimis"


class ResponseCache:
    """A small key/value store for JSON API responses.

    Args:
        path: SQLite file path. Defaults to ``~/.cache/cimis/cache.sqlite``.
    """

    def __init__(self, path: Union[str, Path, None] = None):
        if path is None:
            path = DEFAULT_CACHE_DIR / "cache.sqlite"
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS responses (
                    key TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    params TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    fetched_at REAL NOT NULL
                )
                """
            )

    @staticmethod
    def make_key(endpoint: str, params: Mapping[str, str]) -> str:
        canonical = json.dumps([endpoint, sorted(params.items())], separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def get(self, key: str, max_age: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Cached payload for ``key``, or None if absent or older than ``max_age`` seconds."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, fetched_at FROM responses WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        payload, fetched_at = row
        if max_age is not None and (time.time() - fetched_at) > max_age:
            return None
        return json.loads(payload)

    def set(self, key: str, endpoint: str, params: Mapping[str, str], payload: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO responses (key, endpoint, params, payload, fetched_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, endpoint, json.dumps(dict(params)), json.dumps(payload), time.time()),
            )

    def clear(self, endpoint: Optional[str] = None) -> int:
        """Delete cached responses (optionally only for one endpoint). Returns rows deleted."""
        with self._lock, self._conn:
            if endpoint is None:
                cur = self._conn.execute("DELETE FROM responses")
            else:
                cur = self._conn.execute("DELETE FROM responses WHERE endpoint = ?", (endpoint,))
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
