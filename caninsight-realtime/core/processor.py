from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Mapping

from core.decoder import decode_can_message, load_signal_config
from core.state import StateStore
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
    ) -> None:
        self.signal_config = load_signal_config(config_path)
        self.state = StateStore(window_size=window_size)
        self.event_log_path = Path(event_log_path)
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = Lock()
        if not self.event_log_path.exists():
            self.event_log_path.write_text("", encoding="utf-8")

        self.ml_detector = IsolationForestDetector(enabled=ml_enabled)

    def process_message(self, message: Mapping[str, Any]) -> Dict[str, Any]:
        decoded = decode_can_message(message, self.signal_config)
        signals = decoded["signals"]
        timestamp = str(decoded.get("timestamp"))

        self.state.update(signals)

        alerts = []
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
