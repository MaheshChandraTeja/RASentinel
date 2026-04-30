from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

import requests
import serial

STOP_REQUESTED = False

ALIASES = {
    "cmd_pos": "commanded_position",
    "commanded_pos": "commanded_position",
    "pos_cmd": "commanded_position",
    "act_pos": "actual_position",
    "actual_pos": "actual_position",
    "pos": "actual_position",
    "cmd_vel": "commanded_velocity",
    "commanded_vel": "commanded_velocity",
    "act_vel": "actual_velocity",
    "actual_vel": "actual_velocity",
    "current_a": "motor_current",
    "current": "motor_current",
    "temp_c": "temperature",
    "temperature_c": "temperature",
    "latency_ms": "control_latency_ms",
    "encoder": "encoder_position",
    "encoder_pos": "encoder_position",
    "seq": "sequence_number",
}

TELEMETRY_FIELDS = {
    "sequence_number",
    "controller_timestamp",
    "monotonic_ms",
    "timestamp",
    "commanded_position",
    "actual_position",
    "commanded_velocity",
    "actual_velocity",
    "commanded_torque",
    "estimated_torque",
    "motor_current",
    "temperature",
    "load_estimate",
    "control_latency_ms",
    "encoder_position",
    "error_position",
    "error_velocity",
    "fault_label",
}


def handle_stop(signum: int, frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    response = requests.request(method, url, timeout=30, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {url} failed: {response.status_code} {response.text}")
    return response.json()


def start_live_session(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "actuator_id": args.actuator_id,
        "session_name": args.session_name,
        "duplicate_strategy": args.duplicate_strategy,
        "controller_name": args.controller_name,
        "controller_type": args.controller_type,
        "transport": "serial",
        "endpoint": args.port,
        "sample_rate_hint_hz": args.sample_rate_hz,
        "min_diagnosis_samples": args.min_diagnosis_samples,
        "auto_extract_features": True,
        "auto_diagnose_every_n_samples": args.auto_diagnose_every_n_samples,
        "connection_metadata": {
            "port": args.port,
            "baud": args.baud,
            "bridge": "scripts/live_serial_bridge.py",
        },
    }
    return request_json("POST", f"{args.api_base}/live/sessions", json=payload)


def stop_live_session(api_base: str, live_session_id: str) -> None:
    try:
        request_json("POST", f"{api_base}/live/sessions/{live_session_id}/stop")
    except Exception as exc:
        print(f"Warning: failed to stop live session cleanly: {exc}", file=sys.stderr)


def normalize_sample(raw: dict[str, Any], fallback_sequence: int) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        resolved = ALIASES.get(key, key)
        if resolved in TELEMETRY_FIELDS:
            normalized[resolved] = value

    normalized.setdefault("sequence_number", fallback_sequence)
    normalized.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    return normalized


def post_batch(args: argparse.Namespace, live_session_id: str, batch: list[dict[str, Any]], *, run_diagnosis: bool) -> dict[str, Any]:
    return request_json(
        "POST",
        f"{args.api_base}/live/sessions/{live_session_id}/samples",
        json={
            "samples": batch,
            "run_diagnosis": run_diagnosis,
            "smoothing_window": args.smoothing_window,
            "use_isolation_forest": not args.disable_isolation_forest,
            "persist_diagnosis": True,
        },
    )


def run() -> None:
    parser = argparse.ArgumentParser(description="Stream serial actuator telemetry into RASentinel live ingestion.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--actuator-id", required=True)
    parser.add_argument("--session-name", default="Live actuator capture")
    parser.add_argument("--duplicate-strategy", choices=["reject", "create_new", "replace"], default="create_new")
    parser.add_argument("--controller-name", default="Serial actuator controller")
    parser.add_argument("--controller-type", default="embedded_controller")
    parser.add_argument("--port", required=True, help="Serial port, for example COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--sample-rate-hz", type=float, default=50)
    parser.add_argument("--duration-s", type=float, default=0, help="0 means run until Ctrl+C")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--smoothing-window", type=int, default=5)
    parser.add_argument("--min-diagnosis-samples", type=int, default=250)
    parser.add_argument("--diagnose-every", type=int, default=0, help="Client-side diagnosis interval in imported samples. 0 disables.")
    parser.add_argument("--auto-diagnose-every-n-samples", type=int, default=None)
    parser.add_argument("--disable-isolation-forest", action="store_true")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    live_session = start_live_session(args)
    live_session_id = live_session["id"]
    session_id = live_session["session_id"]
    print(f"Started live RASentinel session: {live_session_id}")
    print(f"Telemetry session: {session_id}")

    batch: list[dict[str, Any]] = []
    imported_total = 0
    fallback_sequence = 0
    started = time.monotonic()

    try:
        with serial.Serial(args.port, args.baud, timeout=1) as ser:
            print(f"Listening on {args.port} at {args.baud} baud")
            while not STOP_REQUESTED:
                if args.duration_s > 0 and time.monotonic() - started >= args.duration_s:
                    break

                line = ser.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    print(f"Skipping invalid JSON line: {line}", file=sys.stderr)
                    continue

                if not isinstance(raw, dict):
                    print(f"Skipping non-object JSON line: {line}", file=sys.stderr)
                    continue

                fallback_sequence += 1
                batch.append(normalize_sample(raw, fallback_sequence))

                if len(batch) >= args.batch_size:
                    run_diagnosis = bool(args.diagnose_every and (imported_total + len(batch)) // args.diagnose_every > imported_total // args.diagnose_every)
                    result = post_batch(args, live_session_id, batch, run_diagnosis=run_diagnosis)
                    imported_total += result["rows_imported"]
                    latest = result.get("latest_metrics", {})
                    print(
                        f"Imported {imported_total} samples | "
                        f"pos_err={latest.get('position_error')} | "
                        f"current={latest.get('motor_current')} | "
                        f"temp={latest.get('temperature')}"
                    )
                    batch.clear()

        if batch:
            result = post_batch(args, live_session_id, batch, run_diagnosis=False)
            imported_total += result["rows_imported"]
            batch.clear()

    finally:
        stop_live_session(args.api_base, live_session_id)
        print(f"Capture finished. Imported {imported_total} samples.")
        print(f"RASentinel live session: {live_session_id}")
        print(f"RASentinel telemetry session: {session_id}")


if __name__ == "__main__":
    run()
