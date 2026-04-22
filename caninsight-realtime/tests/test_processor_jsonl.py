from __future__ import annotations

import json
from pathlib import Path

from core.processor import StreamProcessor


def _write_signal_config(path: Path) -> None:
    cfg = {
        "rpm": {"bytes": [0, 1], "scale": 0.25},
        "throttle_pct": {"bytes": [2], "scale": 100 / 255, "round": 2},
        "speed_kph": {"bytes": [3], "scale": 1.0},
        "engine_temp_c": {"bytes": [4], "offset": -40},
        "brake_pct": {"bytes": [5], "scale": 100 / 255, "round": 2},
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")


def test_processor_writes_jsonl_line(tmp_path: Path) -> None:
    config_path = tmp_path / "signals.json"
    log_path = tmp_path / "events.jsonl"
    _write_signal_config(config_path)

    processor = StreamProcessor(
        config_path=config_path,
        event_log_path=log_path,
        window_size=20,
        ml_enabled=False,
    )

    message = {
        "timestamp": "2026-04-22T10:00:00+00:00",
        "can_id": "0x100",
        "payload": "0E FE 18 00 76 00 00 00",
    }

    event = processor.process_message(message)
    assert "signals" in event
    assert log_path.exists()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["can_id"] == "0x100"
    assert "risk_level" in parsed
