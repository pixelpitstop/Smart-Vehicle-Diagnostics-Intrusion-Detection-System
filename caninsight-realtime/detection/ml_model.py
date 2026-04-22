from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from core.state import StateStore

try:
    from sklearn.ensemble import IsolationForest
except Exception:  # pragma: no cover - optional dependency at runtime
    IsolationForest = None


@dataclass
class IsolationForestDetector:
    """Optional ML detector for multivariate anomalies in streaming telemetry."""

    enabled: bool = True
    contamination: float = 0.02
    min_train_samples: int = 80
    retrain_interval: int = 20

    def __post_init__(self) -> None:
        self.enabled = self.enabled and IsolationForest is not None
        self.model = None
        self._samples_since_train = 0

    @staticmethod
    def _feature_vector(signals: Dict[str, float]) -> List[float]:
        return [
            float(signals.get("rpm", 0.0)),
            float(signals.get("speed_kph", 0.0)),
            float(signals.get("engine_temp_c", 0.0)),
            float(signals.get("throttle_pct", 0.0)),
            float(signals.get("brake_pct", 0.0)),
        ]

    def _train(self, state: StateStore) -> None:
        if not self.enabled:
            return

        rows = state.window()
        if len(rows) < self.min_train_samples:
            return

        matrix = [self._feature_vector(row) for row in rows]
        self.model = IsolationForest(contamination=self.contamination, random_state=42)
        self.model.fit(matrix)
        self._samples_since_train = 0

    def detect(self, signals: Dict[str, float], state: StateStore, timestamp: str) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        self._samples_since_train += 1
        if self.model is None:
            self._train(state)
            return []

        if self._samples_since_train >= self.retrain_interval:
            self._train(state)

        vector = [self._feature_vector(signals)]
        prediction = int(self.model.predict(vector)[0])
        if prediction == 1:
            return []

        score = float(self.model.score_samples(vector)[0])
        return [
            {
                "timestamp": timestamp,
                "severity": "medium",
                "category": "ml_anomaly",
                "source": "ml",
                "message": "IsolationForest flagged a multivariate anomaly",
                "details": {"score": round(score, 6)},
            }
        ]
