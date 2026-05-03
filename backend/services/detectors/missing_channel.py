"""
Missing channel detector — flags a dead or unreadable monitored variable when ingest
still carries other telemetry (distinct from dropout, which fires on timing gaps).

Emits ``AnomalyType.MISSING_DATA`` after consecutive ``null`` samples for one channel while
(by default) at least one other monitored env field on the **same reading** is non-null.

State resets when the sensor recovers (non-null value) or ``reset()`` is called per stream.
"""

from __future__ import annotations

from typing import Literal, Optional

from enums import AlertSeverity, AnomalyType
from .base import AnomalyEvent, BaseDetector, Reading

VarTier = Literal["warning", "critical"]


class MissingChannelDetector(BaseDetector):
    def __init__(
        self,
        monitored_variables: list[str],
        *,
        consec_warning: int = 4,
        consec_critical: int = 8,
        require_peer_non_null: bool = True,
    ):
        self._vars = list(monitored_variables)
        self._warn_n = max(1, int(consec_warning))
        self._crit_n = max(self._warn_n + 1, int(consec_critical))
        self._require_peer = require_peer_non_null
        self._streak: dict[int, dict[str, int]] = {}
        self._tier_sent: dict[int, dict[str, Optional[VarTier]]] = {}

    def reset(self, stream_key: int) -> None:
        self._streak.pop(stream_key, None)
        self._tier_sent.pop(stream_key, None)

    def _ensure(self, stream_key: int) -> None:
        if stream_key not in self._streak:
            self._streak[stream_key] = {v: 0 for v in self._vars}
            self._tier_sent[stream_key] = {v: None for v in self._vars}

    @staticmethod
    def _snapshot(reading: Reading) -> dict[str, Optional[float | int]]:
        return {
            "temperature": reading.temperature,
            "humidity": reading.humidity,
            "light": reading.light,
        }

    def detect_reading(
        self,
        reading: Reading,
        buffer: object,
        session_id: int,
    ) -> list[AnomalyEvent]:
        events: list[AnomalyEvent] = []
        _ = buffer

        vals = self._snapshot(reading)
        self._ensure(session_id)

        for var in self._vars:
            value = vals.get(var)
            st = self._streak[session_id]
            tier = self._tier_sent[session_id]

            if value is not None:
                st[var] = 0
                tier[var] = None
                continue

            peer_alive = any(
                vals.get(o) is not None for o in self._vars if o != var
            )
            if self._require_peer and not peer_alive:
                st[var] = 0
                tier[var] = None
                continue

            st[var] = st[var] + 1
            streak = st[var]

            detail = {"consecutive_null": streak, "require_peer_signal": self._require_peer}

            if streak >= self._crit_n and tier[var] != "critical":
                tier[var] = "critical"
                events.append(
                    AnomalyEvent(
                        timestamp=reading.timestamp,
                        session_id=session_id,
                        variable=var,
                        anomaly_type=AnomalyType.MISSING_DATA,
                        severity=AlertSeverity.CRITICAL,
                        message=(
                            f"{var} missing ({streak} consecutive null readings): "
                            f"possible sensor unplugged or sustained read failures"
                        ),
                        detail={**detail, "tier": "critical"},
                    )
                )
            elif streak >= self._warn_n and tier[var] is None:
                tier[var] = "warning"
                events.append(
                    AnomalyEvent(
                        timestamp=reading.timestamp,
                        session_id=session_id,
                        variable=var,
                        anomaly_type=AnomalyType.MISSING_DATA,
                        severity=AlertSeverity.WARNING,
                        message=(
                            f"{var} missing ({streak} consecutive null readings): "
                            "check wiring, probe, or bus for this channel"
                        ),
                        detail={**detail, "tier": "warning"},
                    )
                )

        return events
