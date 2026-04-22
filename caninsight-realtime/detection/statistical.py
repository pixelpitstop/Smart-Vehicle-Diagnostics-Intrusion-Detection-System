from __future__ import annotations

import statistics
from typing import Any, Dict, List

from core.state import StateStore


def _alert(timestamp: str, severity: str, category: str, message: str, details: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "timestamp": timestamp,
        "severity": severity,
        "category": category,
        "source": "statistical",
        "message": message,
        "details": details,
    }


def detect_statistical_anomalies(
    signals: Dict[str, float],
    state: StateStore,
    timestamp: str,
    z_threshold: float = 2.8,
    min_samples: int = 25,
) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    monitored_keys = ["rpm", "speed_kph", "engine_temp_c", "brake_pct", "throttle_pct"]

    for key in monitored_keys:
        baseline = state.series(key, include_latest=False)
        if len(baseline) < min_samples:
            continue

        value = float(signals.get(key, 0.0))
        mean = statistics.fmean(baseline)
        std = statistics.pstdev(baseline)
        if std < 1e-6:
            continue

        z_score = (value - mean) / std
        if abs(z_score) >= z_threshold:
            severity = "high" if abs(z_score) >= 4.0 else "medium"
            alerts.append(
                _alert(
                    timestamp=timestamp,
                    severity=severity,
                    category="zscore_anomaly",
                    message=f"{key} deviates from rolling baseline (z={z_score:.2f})",
                    details={
                        "signal": key,
                        "value": round(value, 3),
                        "rolling_mean": round(mean, 3),
                        "rolling_std": round(std, 3),
                        "z_score": round(z_score, 3),
                    },
                )
            )

    return alerts
