import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any

import requests
import serial


def create_session(
    api_base: str,
    actuator_id: str,
    session_name: str,
    source: str,
) -> str:
    response = requests.post(
        f"{api_base}/actuators/{actuator_id}/sessions",
        json={
            "name": session_name,
            "source": source,
            "tags": {
                "capture_mode": "live_serial",
                "created_by": "RASentinel serial bridge",
            },
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["id"]


def post_batch(api_base: str, session_id: str, samples: list[dict[str, Any]]) -> None:
    if not samples:
        return

    response = requests.post(
        f"{api_base}/sessions/{session_id}/telemetry",
        json={"samples": samples},
        timeout=30,
    )
    response.raise_for_status()


def normalize_sample(raw: dict[str, Any]) -> dict[str, Any]:
    sample = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commanded_position": raw.get("commanded_position"),
        "actual_position": raw.get("actual_position"),
        "commanded_velocity": raw.get("commanded_velocity"),
        "actual_velocity": raw.get("actual_velocity"),
        "commanded_torque": raw.get("commanded_torque"),
        "estimated_torque": raw.get("estimated_torque"),
        "motor_current": raw.get("motor_current"),
        "temperature": raw.get("temperature"),
        "load_estimate": raw.get("load_estimate"),
        "control_latency_ms": raw.get("control_latency_ms"),
        "encoder_position": raw.get("encoder_position"),
        "fault_label": raw.get("fault_label", "none"),
    }

    return {key: value for key, value in sample.items() if value is not None}


def run_capture() -> None:
    parser = argparse.ArgumentParser(description="Capture live actuator telemetry into RASentinel.")
    parser.add_argument("--port", required=True, help="Serial port, for example COM5")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--actuator-id", required=True)
    parser.add_argument("--session-name", default="Live actuator capture")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--duration-s", type=float, default=20.0)
    args = parser.parse_args()

    session_id = create_session(
        api_base=args.api_base,
        actuator_id=args.actuator_id,
        session_name=args.session_name,
        source=f"serial:{args.port}",
    )

    print(f"Created RASentinel session: {session_id}")

    samples: list[dict[str, Any]] = []
    started_at = time.monotonic()
    total_imported = 0

    with serial.Serial(args.port, args.baud, timeout=1) as ser:
        print(f"Listening on {args.port} at {args.baud} baud...")

        while True:
            if time.monotonic() - started_at >= args.duration_s:
                break

            line = ser.readline().decode("utf-8", errors="replace").strip()

            if not line:
                continue

            try:
                raw = json.loads(line)
                sample = normalize_sample(raw)
                samples.append(sample)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON: {line}", file=sys.stderr)
                continue

            if len(samples) >= args.batch_size:
                post_batch(args.api_base, session_id, samples)
                total_imported += len(samples)
                print(f"Imported {total_imported} samples")
                samples.clear()

    if samples:
        post_batch(args.api_base, session_id, samples)
        total_imported += len(samples)

    print(f"Capture complete. Imported {total_imported} samples.")
    print(f"Session ID: {session_id}")


if __name__ == "__main__":
    run_capture()