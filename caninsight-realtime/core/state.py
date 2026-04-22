from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Mapping


@dataclass
class StateStore:
    """Rolling in-memory state used by streaming detectors."""

    window_size: int = 120
    _history: Deque[Dict[str, float]] = field(default_factory=deque)

    def update(self, signals: Mapping[str, float]) -> None:
        self._history.append(dict(signals))
        while len(self._history) > self.window_size:
            self._history.popleft()

    def window(self) -> List[Dict[str, float]]:
        return list(self._history)

    def latest(self) -> Dict[str, float] | None:
        if not self._history:
            return None
        return self._history[-1]

    def previous(self) -> Dict[str, float] | None:
        if len(self._history) < 2:
            return None
        return self._history[-2]

    def series(self, key: str, include_latest: bool = True) -> List[float]:
        items = list(self._history)
        if not include_latest and items:
            items = items[:-1]

        return [float(row[key]) for row in items if key in row]

    def size(self) -> int:
        return len(self._history)
