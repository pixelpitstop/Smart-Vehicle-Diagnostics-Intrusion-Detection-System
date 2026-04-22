from __future__ import annotations

from typing import Any, Dict, List

from core.state import StateStore


def _alert(timestamp: str, severity: str, category: str, message: str, source: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "timestamp": timestamp,
        "severity": severity,
        "category": category,
        "source": source,
        "message": message,
        "details": details or {},
    }


def detect_rule_anomalies(signals: Dict[str, float], state: StateStore, timestamp: str) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    temp = float(signals.get("engine_temp_c", 0.0))
    rpm = float(signals.get("rpm", 0.0))
    brake = float(signals.get("brake_pct", 0.0))
    throttle = float(signals.get("throttle_pct", 0.0))

    prev = state.previous() or {}
    prev_rpm = float(prev.get("rpm", rpm))
    prev_brake = float(prev.get("brake_pct", brake))
    prev_throttle = float(prev.get("throttle_pct", throttle))

    if temp >= 112:
        alerts.append(
            _alert(
                timestamp,
                severity="high",
                category="overheating",
                source="rules",
                message=f"Engine temperature critical at {temp:.1f} C",
                details={"engine_temp_c": temp},
            )
        )
    elif temp >= 100:
        alerts.append(
            _alert(
                timestamp,
                severity="medium",
                category="overheating",
                source="rules",
                message=f"Engine temperature elevated at {temp:.1f} C",
                details={"engine_temp_c": temp},
            )
        )

    rpm_delta = rpm - prev_rpm
    if abs(rpm_delta) >= 1200:
        alerts.append(
            _alert(
                timestamp,
                severity="medium",
                category="rpm_spike",
                source="rules",
                message=f"Abrupt RPM change detected ({rpm_delta:+.0f})",
                details={"rpm": rpm, "delta": rpm_delta},
            )
        )

    brake_delta = brake - prev_brake
    if brake >= 75 and brake_delta >= 25:
        alerts.append(
            _alert(
                timestamp,
                severity="high",
                category="harsh_braking",
                source="rules",
                message=f"Harsh braking event (brake {brake:.1f}%)",
                details={"brake_pct": brake, "delta": brake_delta},
            )
        )

    throttle_delta = throttle - prev_throttle
    if throttle >= 80 and throttle_delta >= 35:
        alerts.append(
            _alert(
                timestamp,
                severity="medium",
                category="aggressive_acceleration",
                source="rules",
                message=f"Aggressive acceleration detected (throttle {throttle:.1f}%)",
                details={"throttle_pct": throttle, "delta": throttle_delta},
            )
        )

    return alerts
