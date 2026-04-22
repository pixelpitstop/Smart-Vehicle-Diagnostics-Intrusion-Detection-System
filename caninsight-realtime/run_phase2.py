from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DASHBOARD_APP = PROJECT_ROOT / "dashboard" / "app.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CANInsight Phase 2 stream + dashboard")
    parser.add_argument("--hz", type=float, default=8.0, help="Producer frequency")
    parser.add_argument("--window", type=int, default=120, help="Rolling window size")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port")
    parser.add_argument("--disable-ml", action="store_true", help="Disable IsolationForest detector")
    parser.add_argument("--reset-log", action="store_true", help="Reset stream log on startup")
    return parser.parse_args()


def _consumer_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "streaming.consumer",
        "--hz",
        str(args.hz),
        "--window",
        str(args.window),
    ]
    if args.disable_ml:
        cmd.append("--disable-ml")
    if args.reset_log:
        cmd.append("--reset-log")
    return cmd


def _dashboard_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(DASHBOARD_APP),
        "--server.headless",
        "true",
        "--server.port",
        str(args.port),
    ]


def _spawn_process(cmd: list[str], name: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    process = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env)
    print(f"[phase2] started {name} (pid={process.pid})")
    return process


def _terminate(proc: subprocess.Popen, name: str) -> None:
    if proc.poll() is not None:
        return

    print(f"[phase2] stopping {name}...")
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> None:
    args = parse_args()

    consumer = _spawn_process(_consumer_command(args), "consumer")
    dashboard = _spawn_process(_dashboard_command(args), "dashboard")

    print(f"[phase2] dashboard url: http://localhost:{args.port}")
    print("[phase2] press Ctrl+C to stop both services")

    try:
        while True:
            if consumer.poll() is not None:
                raise RuntimeError("consumer process exited unexpectedly")
            if dashboard.poll() is not None:
                raise RuntimeError("dashboard process exited unexpectedly")
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print(f"[phase2] error: {exc}")
    finally:
        _terminate(dashboard, "dashboard")
        _terminate(consumer, "consumer")


if __name__ == "__main__":
    # Ensure child processes handle Ctrl+C cleanly when launched interactively.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    main()
