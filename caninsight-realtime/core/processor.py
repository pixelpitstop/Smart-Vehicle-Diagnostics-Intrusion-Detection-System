from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Mapping

from core.decoder import decode_can_message, load_signal_config
from core.state import StateStore
from detection.intrusion import IntrusionDetector
from detection.ml_model import IsolationForestDetector
from detection.rules import detect_rule_anomalies
from detection.statistical import detect_statistical_anomalies


class StreamProcessor:
    """Per-message realtime processor: decode -> state -> detect -> insight."""

    def __init__(
        self,
        config_path: str | Path,
        event_log_path: str | Path,
        window_size: int = 120,
        ml_enabled: bool = True,
        security_config_path: str | Path | None = None,
    ) -> None:
        self.signal_config = load_signal_config(config_path)
        self.state = StateStore(window_size=window_size)
        self.event_log_path = Path(event_log_path)
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = Lock()
        if not self.event_log_path.exists():
            self.event_log_path.write_text("", encoding="utf-8")

        self.ml_detector = IsolationForestDetector(enabled=ml_enabled)

        if security_config_path is None:
            candidate = Path(config_path).parent / "security.json"
            security_config_path = candidate if candidate.exists() else None
        self.intrusion_detector = IntrusionDetector.from_config(self._load_security_config(security_config_path))

    def process_message(self, message: Mapping[str, Any]) -> Dict[str, Any]:
        raw_timestamp = str(message.get("timestamp"))
        alerts = self.intrusion_detector.detect(message, raw_timestamp)

        try:
            decoded = decode_can_message(message, self.signal_config)
        except Exception as exc:
            alerts.append(
                self._alert(
                    raw_timestamp,
                    "high",
                    "protocol_violation",
                    f"Message decode failed: {type(exc).__name__}",
                    "security",
                    {"error": str(exc)},
                )
            )
            risk_level = self._risk_level(alerts)
            event = {
                "timestamp": raw_timestamp,
                "can_id": message.get("can_id"),
                "payload": message.get("payload"),
                "signals": {},
                "alerts": alerts,
                "risk_level": risk_level,
            }
            self._append_event(event)
            return event

        signals = decoded["signals"]
        timestamp = str(decoded.get("timestamp"))

        self.state.update(signals)

        alerts.extend(detect_rule_anomalies(signals, self.state, timestamp))
        alerts.extend(detect_statistical_anomalies(signals, self.state, timestamp))
        alerts.extend(self.ml_detector.detect(signals, self.state, timestamp))

        risk_level = self._risk_level(alerts)

        event = {
            "timestamp": timestamp,
            "can_id": decoded.get("can_id"),
            "payload": decoded.get("payload"),
            "signals": signals,
            "alerts": alerts,
            "risk_level": risk_level,
        }

        self._append_event(event)
        return event

    @staticmethod
    def _risk_level(alerts: list[dict[str, Any]]) -> str:
        if not alerts:
            return "low"

        weights = {"low": 1, "medium": 2, "high": 3}
        score = sum(weights.get(alert.get("severity", "low"), 1) for alert in alerts)

        if score >= 6:
            return "high"
        if score >= 3:
            return "medium"
        return "low"

    def _append_event(self, event: Dict[str, Any]) -> None:
        event_line = json.dumps(event, separators=(",", ":")) + "\n"
        with self._write_lock:
            with self.event_log_path.open("a", encoding="utf-8") as fp:
                fp.write(event_line)

    @staticmethod
    def _alert(
        timestamp: str,
        severity: str,
        category: str,
        message: str,
        source: str,
        details: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return {
            "timestamp": timestamp,
            "severity": severity,
            "category": category,
            "source": source,
            "message": message,
            "details": details or {},
        }

    @staticmethod
    def _load_security_config(path: str | Path | None) -> Dict[str, Any]:
        if path is None:
            return {}

        cfg_path = Path(path)
        if not cfg_path.exists():
            return {}

        try:
            payload = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

        return payload if isinstance(payload, dict) else {}
