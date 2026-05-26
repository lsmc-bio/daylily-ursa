"""Small process-local cache helpers for Ursa GUI aggregates."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    loaded_at: float
    expires_at: float


class GuiPayloadCache:
    def __init__(self, *, ttl_seconds: int = 600) -> None:
        if int(ttl_seconds) < 1:
            raise ValueError("GUI payload cache ttl_seconds must be >= 1")
        self.ttl_seconds = int(ttl_seconds)
        self._condition = threading.Condition(threading.RLock())
        self._entries: dict[str, CacheEntry] = {}
        self._refreshing: set[str] = set()
        self._errors: dict[str, str] = {}
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def get(
        self,
        key: str,
        builder: Callable[[], Any],
        *,
        force_refresh: bool = False,
    ) -> Any:
        now = time.time()
        with self._condition:
            entry = self._entries.get(key)
            if not force_refresh and entry is not None and entry.expires_at > now:
                return entry.value
            if not force_refresh and entry is not None:
                self._trigger_refresh_locked(key, builder)
                return entry.value
            while key in self._refreshing:
                self._condition.wait(timeout=self.ttl_seconds)
                entry = self._entries.get(key)
                if not force_refresh and entry is not None and entry.expires_at > time.time():
                    return entry.value
                if key not in self._refreshing:
                    break
            self._refreshing.add(key)
        try:
            value = builder()
        except Exception as exc:
            with self._condition:
                self._errors[key] = str(exc)
                self._refreshing.discard(key)
                self._condition.notify_all()
            raise
        with self._condition:
            loaded_at = time.time()
            self._entries[key] = CacheEntry(
                value=value,
                loaded_at=loaded_at,
                expires_at=loaded_at + self.ttl_seconds,
            )
            self._errors.pop(key, None)
            self._refreshing.discard(key)
            self._condition.notify_all()
        return value

    def trigger_refresh(self, key: str, builder: Callable[[], Any]) -> dict[str, Any]:
        with self._condition:
            self._trigger_refresh_locked(key, builder)
            return self.status(key)

    def status(self, key: str) -> dict[str, Any]:
        now = time.time()
        with self._condition:
            entry = self._entries.get(key)
            refreshing = key in self._refreshing
            last_error = self._errors.get(key)
        if entry is None:
            state = "warming" if refreshing else ("error" if last_error else "empty")
            stale = False
            loaded_at = None
            expires_at = None
        else:
            stale = entry.expires_at <= now
            state = "refreshing" if refreshing else ("stale" if stale else "ready")
            loaded_at = entry.loaded_at
            expires_at = entry.expires_at
        return {
            "state": state,
            "stale": stale,
            "refreshing": refreshing,
            "loaded_at_epoch": loaded_at,
            "expires_at_epoch": expires_at,
            "ttl_seconds": self.ttl_seconds,
            "last_error": last_error,
        }

    def start_periodic(
        self,
        *,
        key: str,
        builder: Callable[[], Any],
        interval_seconds: int,
        thread_name: str,
    ) -> None:
        interval = int(interval_seconds)
        if interval < 1:
            raise ValueError("GUI payload cache interval_seconds must be >= 1")
        thread = threading.Thread(
            target=self._periodic_loop,
            args=(key, builder, interval),
            daemon=True,
            name=thread_name,
        )
        self._threads.append(thread)
        thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        for thread in list(self._threads):
            if thread.is_alive():
                thread.join(timeout=2)

    def _trigger_refresh_locked(self, key: str, builder: Callable[[], Any]) -> None:
        if key in self._refreshing:
            return
        self._refreshing.add(key)
        thread = threading.Thread(
            target=self._refresh_worker,
            args=(key, builder),
            daemon=True,
            name=f"ursa-gui-cache-{key}",
        )
        thread.start()

    def _periodic_loop(self, key: str, builder: Callable[[], Any], interval_seconds: int) -> None:
        self.trigger_refresh(key, builder)
        while not self._stop_event.wait(interval_seconds):
            self.trigger_refresh(key, builder)

    def _refresh_worker(self, key: str, builder: Callable[[], Any]) -> None:
        try:
            value = builder()
        except Exception as exc:
            with self._condition:
                self._errors[key] = str(exc)
                self._refreshing.discard(key)
                self._condition.notify_all()
            return
        with self._condition:
            loaded_at = time.time()
            self._entries[key] = CacheEntry(
                value=value,
                loaded_at=loaded_at,
                expires_at=loaded_at + self.ttl_seconds,
            )
            self._errors.pop(key, None)
            self._refreshing.discard(key)
            self._condition.notify_all()
