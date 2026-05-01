from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Mapping, Tuple


def _alert(
    timestamp: str,
    severity: str,
    category: str,
    message: str,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "timestamp": timestamp,
        "severity": severity,
        "category": category,
        "source": "security",
        "message": message,
        "details": details or {},
    }


class IntrusionDetector:
    """Lightweight CAN security heuristics for realtime stream monitoring."""

    def __init__(
        self,
        allowed_can_ids: set[str] | None = None,
        min_inter_arrival_ms: float = 10.0,
        max_same_payload_streak: int = 12,
        burst_window_seconds: float = 1.0,
        burst_threshold_per_can: int = 40,
    ) -> None:
        self.allowed_can_ids = allowed_can_ids or set()
        self.min_inter_arrival_ms = float(min_inter_arrival_ms)
        self.max_same_payload_streak = int(max_same_payload_streak)
        self.burst_window_seconds = float(burst_window_seconds)
        self.burst_threshold_per_can = int(burst_threshold_per_can)

        self._last_timestamp_by_can: Dict[str, datetime] = {}
        self._last_payload_by_can: Dict[str, str] = {}
        self._payload_streak_by_can: Dict[str, int] = {}
        self._window: Deque[Tuple[datetime, str]] = deque()

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "IntrusionDetector":
        cfg = dict(config or {})
        return cls(
            allowed_can_ids=set(str(x) for x in cfg.get("allowed_can_ids", [])),
            min_inter_arrival_ms=float(cfg.get("min_inter_arrival_ms", 10.0)),
            max_same_payload_streak=int(cfg.get("max_same_payload_streak", 12)),
            burst_window_seconds=float(cfg.get("burst_window_seconds", 1.0)),
            burst_threshold_per_can=int(cfg.get("burst_threshold_per_can", 40)),
        )

    def detect(self, message: Mapping[str, Any], timestamp: str) -> list[Dict[str, Any]]:
        alerts: list[Dict[str, Any]] = []

        can_id = str(message.get("can_id", ""))
        payload = str(message.get("payload", "")).strip()
        ts = self._parse_timestamp(timestamp)

        if self.allowed_can_ids and can_id not in self.allowed_can_ids:
            alerts.append(
                _alert(
                    timestamp,
                    "high",
                    "spoofed_can_id",
                    f"CAN ID {can_id} is outside the configured whitelist",
                    {"can_id": can_id},
                )
            )

        if not self._looks_like_payload(payload):
            alerts.append(
                _alert(
                    timestamp,
                    "high",
                    "protocol_violation",
                    "Malformed CAN payload (expected 8 bytes in hex)",
                    {"payload": payload},
                )
            )

        if ts is None:
            alerts.append(
                _alert(
                    timestamp,
                    "medium",
                    "timestamp_anomaly",
                    "Timestamp format is invalid for temporal analysis",
                    {"timestamp": timestamp},
                )
            )
            return alerts

        last_ts = self._last_timestamp_by_can.get(can_id)
        if last_ts is not None:
            delta_ms = (ts - last_ts).total_seconds() * 1000.0
            if delta_ms < self.min_inter_arrival_ms:
                alerts.append(
                    _alert(
                        timestamp,
                        "medium",
                        "high_rate_traffic",
                        f"Inter-arrival time {delta_ms:.2f} ms below configured minimum",
                        {"can_id": can_id, "delta_ms": round(delta_ms, 3)},
                    )
                )
        self._last_timestamp_by_can[can_id] = ts

        self._window.append((ts, can_id))
        self._trim_window(ts)
        burst_count = sum(1 for _, cid in self._window if cid == can_id)
        if burst_count == self.burst_threshold_per_can:
            alerts.append(
                _alert(
                    timestamp,
                    "medium",
                    "burst_traffic",
                    "CAN ID burst traffic exceeded configured threshold",
                    {
                        "can_id": can_id,
                        "window_seconds": self.burst_window_seconds,
                        "count": burst_count,
                    },
                )
            )

        prev_payload = self._last_payload_by_can.get(can_id)
        streak = self._payload_streak_by_can.get(can_id, 0)
        if payload == prev_payload:
            streak += 1
        else:
            streak = 1
        self._last_payload_by_can[can_id] = payload
        self._payload_streak_by_can[can_id] = streak

        if streak == self.max_same_payload_streak:
            alerts.append(
                _alert(
                    timestamp,
                    "medium",
                    "replay_suspected",
                    "Repeated identical payload pattern detected",
                    {"can_id": can_id, "streak": streak},
                )
            )

        return alerts

    def _trim_window(self, now: datetime) -> None:
        while self._window and (now - self._window[0][0]).total_seconds() > self.burst_window_seconds:
            self._window.popleft()

    @staticmethod
    def _parse_timestamp(ts: str) -> datetime | None:
        value = ts.strip()
        if not value:
            return None
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _looks_like_payload(payload: str) -> bool:
        normalized = payload.replace(" ", "")
        if len(normalized) != 16:
            return False
        try:
            bytes.fromhex(normalized)
            return True
        except ValueError:
            return False
