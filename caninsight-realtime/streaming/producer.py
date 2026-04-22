from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from queue import Queue
from threading import Event
from typing import Dict


@dataclass
class ProducerConfig:
    can_id: str = "0x100"
    hz: float = 8.0
    seed: int = 42


class CANFrameProducer:
    """Continuously simulates CAN frames and pushes them into a queue."""

    def __init__(self, queue: Queue, stop_event: Event, config: ProducerConfig | None = None) -> None:
        self.queue = queue
        self.stop_event = stop_event
        self.config = config or ProducerConfig()
        self.rng = random.Random(self.config.seed)

        self._rpm = 850.0
        self._speed = 8.0
        self._throttle = 12.0
        self._brake = 0.0
        self._temp = 72.0
        self._load = 18.0
        self._fuel = 78.0

    def _inject_events(self) -> None:
        # Rare event injections to exercise detectors under streaming conditions.
        if self.rng.random() < 0.02:
            self._throttle = min(100.0, self._throttle + self.rng.uniform(35, 55))
        if self.rng.random() < 0.015:
            self._brake = min(100.0, self._brake + self.rng.uniform(40, 70))
            self._speed = max(0.0, self._speed - self.rng.uniform(8, 20))
        if self.rng.random() < 0.01:
            self._temp = min(125.0, self._temp + self.rng.uniform(10, 24))

    def _step_dynamics(self) -> None:
        throttle_noise = self.rng.uniform(-7, 7)
        brake_decay = self.rng.uniform(5, 15)

        self._throttle = min(100.0, max(0.0, self._throttle + throttle_noise))
        self._brake = max(0.0, self._brake - brake_decay)

        speed_delta = (self._throttle * 0.07) - (self._brake * 0.16) + self.rng.uniform(-1.6, 1.6)
        self._speed = min(180.0, max(0.0, self._speed + speed_delta))

        target_rpm = 700 + self._speed * 42 + self._throttle * 28
        self._rpm += (target_rpm - self._rpm) * 0.35 + self.rng.uniform(-120, 120)
        self._rpm = min(6500.0, max(650.0, self._rpm))

        cooling = max(0.0, (self._speed / 180.0) * 1.5)
        heating = (self._rpm / 6000.0) * 2.8 + (self._throttle / 100.0) * 1.2
        self._temp += heating - cooling + self.rng.uniform(-0.6, 0.6)
        self._temp = min(125.0, max(60.0, self._temp))

        self._load = min(100.0, max(0.0, self._throttle * 0.8 + self._rpm / 120.0 + self.rng.uniform(-5, 5)))
        self._fuel = max(0.0, self._fuel - 0.0025 * max(0.0, self._rpm / 1000.0))

        self._inject_events()

    @staticmethod
    def _clamp_uint8(value: float) -> int:
        return max(0, min(255, int(round(value))))

    def _encode_payload(self) -> str:
        rpm_raw = int(round(self._rpm / 0.25))
        rpm_raw = max(0, min(65535, rpm_raw))

        payload = [
            (rpm_raw >> 8) & 0xFF,
            rpm_raw & 0xFF,
            self._clamp_uint8(self._throttle / 100.0 * 255),
            self._clamp_uint8(self._speed),
            self._clamp_uint8(self._temp + 40),
            self._clamp_uint8(self._brake / 100.0 * 255),
            self._clamp_uint8(self._load / 100.0 * 255),
            self._clamp_uint8(self._fuel / 100.0 * 255),
        ]
        return " ".join(f"{byte:02X}" for byte in payload)

    def next_message(self) -> Dict[str, str]:
        self._step_dynamics()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "can_id": self.config.can_id,
            "payload": self._encode_payload(),
        }

    def run(self) -> None:
        sleep_s = 1.0 / max(0.5, self.config.hz)
        while not self.stop_event.is_set():
            msg = self.next_message()
            try:
                self.queue.put(msg, timeout=0.2)
            except Exception:
                pass
            time.sleep(sleep_s)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone CAN frame producer preview")
    parser.add_argument("--hz", type=float, default=8.0, help="Frames per second")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--count", type=int, default=15, help="How many messages to print")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queue: Queue = Queue(maxsize=200)
    stop_event = Event()
    producer = CANFrameProducer(queue, stop_event, ProducerConfig(hz=args.hz, seed=args.seed))

    for _ in range(args.count):
        print(producer.next_message())


if __name__ == "__main__":
    main()
