from __future__ import annotations

import json
import time
from pathlib import Path

from core.processor import StreamProcessor
from streaming.producer import CANFrameProducer, ProducerConfig
from queue import Queue
from threading import Event


def _write_signal_config(path: Path) -> None:
    cfg = {
        "rpm": {"bytes": [0, 1], "scale": 0.25},
        "throttle_pct": {"bytes": [2], "scale": 100 / 255, "round": 2},
        "speed_kph": {"bytes": [3], "scale": 1.0},
        "engine_temp_c": {"bytes": [4], "offset": -40},
        "brake_pct": {"bytes": [5], "scale": 100 / 255, "round": 2},
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")


def _write_security_config(path: Path) -> None:
    cfg = {
        "allowed_can_ids": ["0x100"],
        "min_inter_arrival_ms": 10.0,
        "max_same_payload_streak": 3,
        "burst_window_seconds": 1.0,
        "burst_threshold_per_can": 999,
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")


def test_integration_end_to_end_happy_path(tmp_path: Path) -> None:
    """Test full producer -> processor -> JSONL pipeline in happy path."""
    config_path = tmp_path / "signals.json"
    security_path = tmp_path / "security.json"
    log_path = tmp_path / "events.jsonl"
    _write_signal_config(config_path)
    _write_security_config(security_path)

    processor = StreamProcessor(
        config_path=config_path,
        event_log_path=log_path,
        window_size=20,
        ml_enabled=False,
        security_config_path=security_path,
    )

    producer = CANFrameProducer(
        queue=Queue(maxsize=100),
        stop_event=Event(),
        config=ProducerConfig(hz=10, seed=42),
    )

    # Simulate 5 messages through processor
    for _ in range(5):
        msg = producer.next_message()
        event = processor.process_message(msg)
        assert "signals" in event
        assert "risk_level" in event
        assert "alerts" in event

    # Verify JSONL was written correctly
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5

    # Verify all events parse and have expected structure
    for line in lines:
        parsed = json.loads(line)
        assert parsed["can_id"] == "0x100"
        assert "signals" in parsed
        assert "risk_level" in parsed


def test_integration_failure_mode_spoofed_can_id(tmp_path: Path) -> None:
    """Test detection of spoofed CAN ID (whitelist violation)."""
    config_path = tmp_path / "signals.json"
    security_path = tmp_path / "security.json"
    log_path = tmp_path / "events.jsonl"
    _write_signal_config(config_path)
    _write_security_config(security_path)

    processor = StreamProcessor(
        config_path=config_path,
        event_log_path=log_path,
        window_size=20,
        ml_enabled=False,
        security_config_path=security_path,
    )

    # Inject a spoofed CAN message with unauthorized ID
    spoofed_message = {
        "timestamp": "2026-05-01T10:00:00+00:00",
        "can_id": "0x999",
        "payload": "0E FE 18 00 76 00 00 00",
    }

    event = processor.process_message(spoofed_message)

    # Verify alert was raised
    alert_categories = {a["category"] for a in event.get("alerts", [])}
    assert "spoofed_can_id" in alert_categories

    # Verify risk level reflects the threat (high severity alert scores 3, triggering medium risk)
    assert event["risk_level"] == "medium"

    # Verify event was logged
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["can_id"] == "0x999"
    assert len(parsed["alerts"]) > 0


def test_integration_failure_mode_replay_attack(tmp_path: Path) -> None:
    """Test detection of replay-like attacks (identical payload streaks)."""
    config_path = tmp_path / "signals.json"
    security_path = tmp_path / "security.json"
    log_path = tmp_path / "events.jsonl"
    _write_signal_config(config_path)
    _write_security_config(security_path)

    processor = StreamProcessor(
        config_path=config_path,
        event_log_path=log_path,
        window_size=20,
        ml_enabled=False,
        security_config_path=security_path,
    )

    # Send 3 identical payloads in rapid succession (replay-like pattern)
    identical_payload = "0E FE 18 00 76 00 00 00"
    for i in range(3):
        msg = {
            "timestamp": f"2026-05-01T10:00:00.{i:03d}000+00:00",
            "can_id": "0x100",
            "payload": identical_payload,
        }
        event = processor.process_message(msg)

        # Third message should trigger replay_suspected alert
        if i == 2:
            alert_categories = {a["category"] for a in event.get("alerts", [])}
            assert "replay_suspected" in alert_categories

    # Verify all events logged
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_integration_failure_mode_protocol_violation(tmp_path: Path) -> None:
    """Test detection of malformed/invalid CAN payloads (protocol violations)."""
    config_path = tmp_path / "signals.json"
    security_path = tmp_path / "security.json"
    log_path = tmp_path / "events.jsonl"
    _write_signal_config(config_path)
    _write_security_config(security_path)

    processor = StreamProcessor(
        config_path=config_path,
        event_log_path=log_path,
        window_size=20,
        ml_enabled=False,
        security_config_path=security_path,
    )

    # Send malformed payload (not 8 bytes)
    malformed_message = {
        "timestamp": "2026-05-01T10:00:00+00:00",
        "can_id": "0x100",
        "payload": "FF FF",  # Too short
    }

    event = processor.process_message(malformed_message)

    # Verify both security and decode alerts
    alert_categories = {a["category"] for a in event.get("alerts", [])}
    assert "protocol_violation" in alert_categories

    # Verify system didn't crash and logged the event
    assert event["signals"] == {}
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
