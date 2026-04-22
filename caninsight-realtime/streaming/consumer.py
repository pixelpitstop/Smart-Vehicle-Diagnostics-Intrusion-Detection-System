from __future__ import annotations

import argparse
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from core.processor import StreamProcessor
from streaming.producer import CANFrameProducer, ProducerConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = PROJECT_ROOT / ".runtime" / "stream_events.jsonl"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "signals.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run realtime CANInsight producer+consumer")
    parser.add_argument("--hz", type=float, default=8.0, help="Producer frequency")
    parser.add_argument("--window", type=int, default=120, help="Rolling state window size")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--max-events", type=int, default=0, help="Optional stop after N events")
    parser.add_argument("--disable-ml", action="store_true", help="Disable optional IsolationForest detector")
    parser.add_argument(
        "--log-file",
        type=str,
        default=str(DEFAULT_LOG_PATH),
        help="Path to processed stream event log",
    )
    parser.add_argument(
        "--reset-log",
        action="store_true",
        help="Reset log file to [] before starting",
    )
    return parser.parse_args()


def reset_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def main() -> None:
    args = parse_args()

    log_path = Path(args.log_file)
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path

    if args.reset_log:
        reset_log(log_path)

    queue: Queue = Queue(maxsize=5000)
    stop_event = Event()

    producer = CANFrameProducer(
        queue=queue,
        stop_event=stop_event,
        config=ProducerConfig(hz=args.hz, seed=args.seed),
    )

    processor = StreamProcessor(
        config_path=DEFAULT_CONFIG_PATH,
        event_log_path=log_path,
        window_size=args.window,
        ml_enabled=not args.disable_ml,
    )

    producer_thread = Thread(target=producer.run, daemon=True)
    producer_thread.start()

    processed = 0
    print("Streaming started. Press Ctrl+C to stop.")

    try:
        while True:
            try:
                message = queue.get(timeout=1.0)
            except Empty:
                continue

            event = processor.process_message(message)
            processed += 1

            # Print a compact heartbeat line with latest state and alert count.
            signals = event["signals"]
            line = {
                "count": processed,
                "timestamp": event["timestamp"],
                "speed_kph": round(float(signals.get("speed_kph", 0.0)), 1),
                "rpm": round(float(signals.get("rpm", 0.0)), 1),
                "engine_temp_c": round(float(signals.get("engine_temp_c", 0.0)), 1),
                "alerts": len(event["alerts"]),
                "risk": event["risk_level"],
            }
            print(json.dumps(line))

            if args.max_events and processed >= args.max_events:
                break

    except KeyboardInterrupt:
        print("Stopping stream...")
    finally:
        stop_event.set()
        producer_thread.join(timeout=2.0)


if __name__ == "__main__":
    main()
