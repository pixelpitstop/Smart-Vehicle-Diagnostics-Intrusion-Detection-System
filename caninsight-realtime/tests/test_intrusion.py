from __future__ import annotations

from detection.intrusion import IntrusionDetector


def test_unknown_can_id_triggers_spoof_alert() -> None:
    detector = IntrusionDetector.from_config({"allowed_can_ids": ["0x100"]})
    msg = {
        "timestamp": "2026-05-01T10:00:00+00:00",
        "can_id": "0x999",
        "payload": "0E FE 18 00 76 00 00 00",
    }
    alerts = detector.detect(msg, str(msg["timestamp"]))
    categories = {a["category"] for a in alerts}
    assert "spoofed_can_id" in categories


def test_replay_pattern_triggers_alert() -> None:
    detector = IntrusionDetector.from_config(
        {
            "allowed_can_ids": ["0x100"],
            "max_same_payload_streak": 3,
            "burst_threshold_per_can": 999,
        }
    )
    msg1 = {
        "timestamp": "2026-05-01T10:00:00+00:00",
        "can_id": "0x100",
        "payload": "0E FE 18 00 76 00 00 00",
    }
    msg2 = {
        "timestamp": "2026-05-01T10:00:00.125000+00:00",
        "can_id": "0x100",
        "payload": "0E FE 18 00 76 00 00 00",
    }
    msg3 = {
        "timestamp": "2026-05-01T10:00:00.250000+00:00",
        "can_id": "0x100",
        "payload": "0E FE 18 00 76 00 00 00",
    }

    detector.detect(msg1, str(msg1["timestamp"]))
    detector.detect(msg2, str(msg2["timestamp"]))
    alerts = detector.detect(msg3, str(msg3["timestamp"]))

    categories = {a["category"] for a in alerts}
    assert "replay_suspected" in categories


def test_high_rate_triggers_alert() -> None:
    detector = IntrusionDetector.from_config(
        {
            "allowed_can_ids": ["0x100"],
            "min_inter_arrival_ms": 10.0,
            "burst_threshold_per_can": 999,
        }
    )
    msg1 = {
        "timestamp": "2026-05-01T10:00:00+00:00",
        "can_id": "0x100",
        "payload": "0E FE 18 00 76 00 00 00",
    }
    msg2 = {
        "timestamp": "2026-05-01T10:00:00.001000+00:00",
        "can_id": "0x100",
        "payload": "0E FE 18 00 76 00 00 01",
    }

    detector.detect(msg1, str(msg1["timestamp"]))
    alerts = detector.detect(msg2, str(msg2["timestamp"]))

    categories = {a["category"] for a in alerts}
    assert "high_rate_traffic" in categories
