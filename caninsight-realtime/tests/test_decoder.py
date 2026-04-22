from __future__ import annotations

from core.decoder import decode_can_message, decode_signals, payload_hex_to_bytes


def test_payload_hex_to_bytes_has_8_bytes() -> None:
    data = payload_hex_to_bytes("0E FE 18 00 76 00 00 00")
    assert isinstance(data, bytes)
    assert len(data) == 8


def test_decode_signals_with_basic_config() -> None:
    payload = payload_hex_to_bytes("0E FE 18 00 76 00 00 00")
    config = {
        "rpm": {"bytes": [0, 1], "scale": 0.25},
        "throttle_pct": {"bytes": [2], "scale": 100 / 255, "round": 2},
        "speed_kph": {"bytes": [3]},
        "engine_temp_c": {"bytes": [4], "offset": -40},
    }

    out = decode_signals(payload, config)
    assert out["rpm"] == 959.5
    assert out["speed_kph"] == 0.0
    assert out["engine_temp_c"] == 78.0


def test_decode_can_message_shape() -> None:
    msg = {
        "timestamp": "2026-04-22T10:00:00+00:00",
        "can_id": "0x100",
        "payload": "0E FE 18 00 76 00 00 00",
    }
    config = {"rpm": {"bytes": [0, 1], "scale": 0.25}}
    decoded = decode_can_message(msg, config)

    assert decoded["timestamp"] == msg["timestamp"]
    assert decoded["can_id"] == msg["can_id"]
    assert "signals" in decoded
    assert "rpm" in decoded["signals"]
