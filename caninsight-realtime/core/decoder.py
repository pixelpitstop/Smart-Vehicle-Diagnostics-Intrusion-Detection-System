from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping


def load_signal_config(config_path: str | Path) -> Dict[str, Dict[str, Any]]:
    """Load and validate signal extraction config."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Signal config not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Signal config must be a JSON object")

    for name, spec in data.items():
        if "bytes" not in spec or not isinstance(spec["bytes"], list):
            raise ValueError(f"Signal '{name}' must define a 'bytes' list")

    return data


def payload_hex_to_bytes(payload_hex: str) -> bytes:
    """Convert a CAN payload string like '0E FE 18 00 76 00 00 00' to bytes."""
    normalized = payload_hex.replace(" ", "").strip()
    if len(normalized) != 16:
        raise ValueError("CAN payload must contain exactly 8 bytes (16 hex chars)")
    return bytes.fromhex(normalized)


def _extract_raw_value(data_bytes: bytes, byte_positions: List[int], byte_order: str, signed: bool) -> int:
    if any(pos < 0 or pos >= len(data_bytes) for pos in byte_positions):
        raise IndexError("Signal byte index is out of range for payload")

    raw_slice = bytes(data_bytes[pos] for pos in byte_positions)
    return int.from_bytes(raw_slice, byteorder=byte_order, signed=signed)


def decode_signals(data_bytes: bytes, signal_config: Mapping[str, Mapping[str, Any]]) -> Dict[str, float]:
    """Decode all configured signals from a payload."""
    decoded: Dict[str, float] = {}

    for signal_name, spec in signal_config.items():
        byte_positions = spec["bytes"]
        byte_order = spec.get("byte_order", "big")
        signed = bool(spec.get("signed", False))
        scale = float(spec.get("scale", 1.0))
        offset = float(spec.get("offset", 0.0))
        round_digits = spec.get("round")

        raw_value = _extract_raw_value(data_bytes, byte_positions, byte_order=byte_order, signed=signed)
        value = raw_value * scale + offset

        if "clip" in spec and isinstance(spec["clip"], list) and len(spec["clip"]) == 2:
            low, high = spec["clip"]
            value = max(float(low), min(float(high), value))

        if isinstance(round_digits, int):
            value = round(value, round_digits)

        decoded[signal_name] = value

    return decoded


def decode_can_message(message: Mapping[str, Any], signal_config: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Decode one CAN-style message into engineering signals."""
    payload_hex = str(message.get("payload", ""))
    payload_bytes = payload_hex_to_bytes(payload_hex)
    signals = decode_signals(payload_bytes, signal_config)

    return {
        "timestamp": message.get("timestamp"),
        "can_id": message.get("can_id"),
        "payload": payload_hex,
        "signals": signals,
    }
