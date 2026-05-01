#!/usr/bin/env python
"""Lightweight performance benchmark for CANInsight streaming pipeline."""

from __future__ import annotations

import json
import time
from pathlib import Path
from queue import Queue
from threading import Event

from core.processor import StreamProcessor
from streaming.producer import CANFrameProducer, ProducerConfig


def benchmark_throughput(num_messages: int = 1000) -> dict:
    """Measure events/sec throughput and per-event latency."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Write minimal config
        config_path = tmp_path / "signals.json"
        security_path = tmp_path / "security.json"
        log_path = tmp_path / "events.jsonl"

        config_path.write_text(
            json.dumps({
                "rpm": {"bytes": [0, 1], "scale": 0.25},
                "speed_kph": {"bytes": [3]},
                "engine_temp_c": {"bytes": [4], "offset": -40},
            })
        )
        security_path.write_text(json.dumps({
            "allowed_can_ids": ["0x100"],
            "min_inter_arrival_ms": 10.0,
            "max_same_payload_streak": 12,
            "burst_window_seconds": 1.0,
            "burst_threshold_per_can": 40,
        }))

        processor = StreamProcessor(
            config_path=config_path,
            event_log_path=log_path,
            window_size=120,
            ml_enabled=False,
            security_config_path=security_path,
        )

        producer = CANFrameProducer(
            queue=Queue(maxsize=5000),
            stop_event=Event(),
            config=ProducerConfig(hz=100, seed=42),
        )

        latencies = []
        start = time.perf_counter()

        for i in range(num_messages):
            msg = producer.next_message()
            msg_start = time.perf_counter()
            event = processor.process_message(msg)
            msg_end = time.perf_counter()
            latencies.append((msg_end - msg_start) * 1000.0)

        end = time.perf_counter()
        elapsed = end - start

        # Compute statistics
        latencies_sorted = sorted(latencies)
        avg_latency_ms = sum(latencies) / len(latencies)
        p50_latency_ms = latencies_sorted[len(latencies_sorted) // 2]
        p95_latency_ms = latencies_sorted[int(0.95 * len(latencies_sorted))]
        p99_latency_ms = latencies_sorted[int(0.99 * len(latencies_sorted))]
        max_latency_ms = max(latencies)

        throughput_eps = num_messages / elapsed

        return {
            "num_messages": num_messages,
            "total_time_sec": round(elapsed, 3),
            "throughput_events_per_sec": round(throughput_eps, 1),
            "avg_latency_ms": round(avg_latency_ms, 3),
            "p50_latency_ms": round(p50_latency_ms, 3),
            "p95_latency_ms": round(p95_latency_ms, 3),
            "p99_latency_ms": round(p99_latency_ms, 3),
            "max_latency_ms": round(max_latency_ms, 3),
        }


if __name__ == "__main__":
    print("CANInsight Performance Benchmark")
    print("=" * 50)
    results = benchmark_throughput(num_messages=1000)
    print(json.dumps(results, indent=2))
