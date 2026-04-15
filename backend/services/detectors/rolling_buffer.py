"""
Fixed-size sliding window for sensor readings.

Stores the last N (timestamp, value) pairs for each variable independently.
Used by DriftDetector and NoiseDetector to access recent history.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime


class RollingBuffer:
    """
    Fixed-size sliding window that stores the last N (timestamp, value) pairs
    for each variable independently.  Uses collections.deque so that when the
    buffer is full, the oldest entry is automatically dropped on append.

    Example:
        buf = RollingBuffer(max_size=30)
        buf.add("temperature", now, 22.3)
        values = buf.get_values("temperature")   # [22.3]
    """

    def __init__(self, max_size: int):
        self._max_size = max_size
        # Separate deque per variable so they fill independently
        self._values: dict[str, deque[float]] = {}
        self._timestamps: dict[str, deque[datetime]] = {}

    def add(self, variable: str, timestamp: datetime, value: float) -> None:
        """Append a reading. If the buffer is full, the oldest entry is evicted."""
        if variable not in self._values:
            self._values[variable] = deque(maxlen=self._max_size)
            self._timestamps[variable] = deque(maxlen=self._max_size)
        self._values[variable].append(value)
        self._timestamps[variable].append(timestamp)

    def get_values(self, variable: str) -> list[float]:
        """Return all buffered values for a variable (oldest first)."""
        return list(self._values.get(variable, []))

    def get_timestamps(self, variable: str) -> list[datetime]:
        """Return all buffered timestamps for a variable (oldest first)."""
        return list(self._timestamps.get(variable, []))

    def size(self, variable: str) -> int:
        """How many readings are currently in the buffer for this variable."""
        return len(self._values.get(variable, []))

    def clear(self) -> None:
        """Wipe all variables. Used when a session ends."""
        self._values.clear()
        self._timestamps.clear()
