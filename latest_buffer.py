from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class BufferSnapshot(Generic[T]):
    value: Optional[T]
    updated_at: float
    received_count: int
    overwrite_count: int
    age_s: Optional[float]


class LatestValueBuffer(Generic[T]):
    """Thread-safe single-slot buffer.

    The previous value is intentionally overwritten whenever a newer sample
    arrives. This keeps UI latency bounded and prevents memory growth.
    """

    def __init__(self, name: str):
        self.name = name
        self._lock = threading.Lock()
        self._value: Optional[T] = None
        self._updated_at = 0.0
        self._received_count = 0
        self._overwrite_count = 0

    def set(self, value: T) -> None:
        now = time.monotonic()
        with self._lock:
            if self._value is not None:
                self._overwrite_count += 1
            self._value = value
            self._updated_at = now
            self._received_count += 1

    def get(self, copy_value: bool = False) -> Optional[T]:
        with self._lock:
            if copy_value:
                return copy.deepcopy(self._value)
            return self._value

    def snapshot(self, copy_value: bool = False) -> BufferSnapshot[T]:
        now = time.monotonic()
        with self._lock:
            value = copy.deepcopy(self._value) if copy_value else self._value
            age_s = None if self._updated_at <= 0 else now - self._updated_at
            return BufferSnapshot(
                value=value,
                updated_at=self._updated_at,
                received_count=self._received_count,
                overwrite_count=self._overwrite_count,
                age_s=age_s,
            )

    def clear(self) -> None:
        with self._lock:
            self._value = None
            self._updated_at = 0.0
            self._received_count = 0
            self._overwrite_count = 0
