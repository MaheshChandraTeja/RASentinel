from __future__ import annotations

import argparse
import math
import random
import time
from datetime import datetime, timezone
from typing import Any

import requests


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_json(url: str, payload: Any, *, timeout: int = 30) -> dict:
    response = requests.post(url, json=payload, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(
            f"POST {url} failed: {response.status_code}\n{response.text}"
        )
    if not response.text:
        return {}
    return response.json()


def create_live_session(
    api_base: str,
    actuator_id: str,
    session_name: str,
    sample_rate_hz: float,
    auto_extract_features: bool,
    diagnose_every_samples: int,
) -> str:
    payload = {
        "actuator_id": actuator_id,
        "session_name": session_name,
        "duplicate_strategy": "create_new",
        "controller_name": "Virtual actuator controller",
        "controller_type": "mock_servo_controller",
        "transport": "http_bridge",
        "endpoint": "local_mock_stream",
        "sample_rate_hint_hz": sample_rate_hz,
        "auto_extract_features": auto_extract_features,
        "auto_diagnose_every_n_samples": None,
        "min_diagnosis_samples": max(250, min(diagnose_every_samples, 1000)),
        "notes": "Mock real-time actuator stream used to validate the live hardware telemetry pipeline without physical hardware.",
        "tags": {
            "capture_mode": "mock_live_controller",
            "hardware_attached": False,
            "rasentinel_demo": True,
        },
        "connection_metadata": {
            "hardware_attached": False,
            "transport": "http_bridge",
            "generator": "scripts/mock_live_actuator_stream.py",
        },
    }
    data = post_json(f"{api_base}/live/sessions", payload)
    live_session_id = data.get("id") or data.get("live_session_id") or data.get("session_id")
    if not live_session_id:
        raise RuntimeError(f"Could not find live session id in response: {data}")
    return live_session_id


def generate_sample(
    index: int,
    elapsed_s: float,
    sample_rate_hz: float,
    fault_after_s: float,
    fault_mode: str,
    rng: random.Random,
) -> dict:
    commanded_position = 30.0 * math.sin(2.0 * math.pi * 0.20 * elapsed_s)
    commanded_velocity = (
        30.0 * 2.0 * math.pi * 0.20 * math.cos(2.0 * math.pi * 0.20 * elapsed_s)
    )

    fault_active = elapsed_s >= fault_after_s
    intensity = min(max((elapsed_s - fault_after_s) / 20.0, 0.0), 1.0)

    lag_samples = 1
    position_bias = 0.0
    velocity_loss = 0.0
    current_extra = 0.0
    temperature_extra = 0.0
    oscillation = 0.0
    encoder_noise = rng.gauss(0.0, 0.04)

    if fault_active:
        if fault_mode == "delayed_response":
            lag_samples = int(2 + 10 * intensity)
            position_bias = 0.25 + 1.5 * intensity
            velocity_loss = 0.04 + 0.16 * intensity
        elif fault_mode == "friction_increase":
            position_bias = 0.15 + 1.0 * intensity
            velocity_loss = 0.03 + 0.12 * intensity
            current_extra = 0.35 + 1.4 * intensity
            temperature_extra = 1.5 + 8.0 * intensity
        elif fault_mode == "overheating":
            current_extra = 0.2 + 0.8 * intensity
            temperature_extra = 4.0 + 20.0 * intensity
        elif fault_mode == "encoder_noise":
            encoder_noise += rng.gauss(0.0, 0.8 + 1.8 * intensity)
        elif fault_mode == "oscillation":
            oscillation = 1.2 * intensity * math.sin(2.0 * math.pi * 3.5 * elapsed_s)
            current_extra = 0.25 + 0.7 * intensity
        elif fault_mode == "load_imbalance":
            position_bias = 0.4 + 1.2 * intensity
            current_extra = 0.5 + 1.6 * intensity
            oscillation = 0.5 * intensity * math.sin(2.0 * math.pi * 1.4 * elapsed_s)

    delayed_t = max(elapsed_s - (lag_samples / sample_rate_hz), 0.0)
    delayed_command = 30.0 * math.sin(2.0 * math.pi * 0.20 * delayed_t)

    actual_position = delayed_command - position_bias + oscillation + rng.gauss(0.0, 0.08)
    actual_velocity = commanded_velocity * (1.0 - velocity_loss) + rng.gauss(0.0, 0.15)
    motor_current = 1.2 + abs(commanded_velocity) * 0.025 + current_extra + rng.gauss(0.0, 0.025)
    temperature = 34.0 + elapsed_s * 0.025 + temperature_extra + rng.gauss(0.0, 0.05)
    latency_ms = 12.0 + lag_samples * (1000.0 / sample_rate_hz)
    encoder_position = actual_position + encoder_noise

    if not fault_active:
        fault_label = "none"
    elif fault_mode == "delayed_response":
        fault_label = "response_delay"
    elif fault_mode == "friction_increase":
        fault_label = "friction_increase"
    elif fault_mode == "overheating":
        fault_label = "thermal_rise"
    elif fault_mode == "encoder_noise":
        fault_label = "encoder_inconsistency"
    elif fault_mode == "oscillation":
        fault_label = "oscillation"
    elif fault_mode == "load_imbalance":
        fault_label = "load_anomaly"
    else:
        fault_label = "unknown"

    return {
        "sequence_number": index,
        "controller_timestamp": now_iso(),
        "monotonic_ms": round(elapsed_s * 1000.0, 3),
        "timestamp": now_iso(),
        "commanded_position": round(commanded_position, 6),
        "actual_position": round(actual_position, 6),
        "commanded_velocity": round(commanded_velocity, 6),
        "actual_velocity": round(actual_velocity, 6),
        "commanded_torque": 1.2,
        "estimated_torque": round(1.2 + current_extra * 0.35, 6),
        "motor_current": round(max(motor_current, 0.0), 6),
        "temperature": round(temperature, 6),
        "load_estimate": round(0.35 + current_extra * 0.2, 6),
        "control_latency_ms": round(latency_ms, 6),
        "encoder_position": round(encoder_position, 6),
        "fault_label": fault_label,
    }


def send_samples(api_base: str, live_session_id: str, samples: list[dict]) -> None:
    url = f"{api_base}/live/sessions/{live_session_id}/samples"
    payload = {
        "samples": samples,
        "run_diagnosis": False,
        "smoothing_window": 5,
        "use_isolation_forest": True,
        "persist_diagnosis": True,
    }
    response = requests.post(url, json=payload, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Sample post failed: {response.status_code}\n{response.text}\n"
            f"First sample in failed batch: {samples[0] if samples else None}"
        )


def run_diagnosis(api_base: str, live_session_id: str) -> None:
    url = f"{api_base}/live/sessions/{live_session_id}/diagnose"
    response = requests.post(url, json={}, timeout=90)
    if response.status_code >= 400:
        print(f"Diagnosis request failed: {response.status_code} {response.text}")
        return
    payload = response.json()
    label = payload.get("fault_label") or payload.get("diagnosis", {}).get("fault_label")
    severity = payload.get("severity_score") or payload.get("diagnosis", {}).get("severity_score")
    print(f"Live diagnosis updated. Fault={label}, severity={severity}")


def stop_session(api_base: str, live_session_id: str) -> None:
    url = f"{api_base}/live/sessions/{live_session_id}/stop"
    response = requests.post(url, timeout=30)
    if response.status_code >= 400:
        print(f"Stop request failed: {response.status_code} {response.text}")
        return
    print("Live session stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock a real-time actuator controller stream into RASentinel.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--actuator-id", required=True)
    parser.add_argument("--session-name", default="Mock real-time actuator test")
    parser.add_argument("--sample-rate-hz", type=float, default=50.0)
    parser.add_argument("--duration-s", type=float, default=60.0)
    parser.add_argument("--fault-after-s", type=float, default=20.0)
    parser.add_argument(
        "--fault-mode",
        default="delayed_response",
        choices=["delayed_response", "friction_increase", "overheating", "encoder_noise", "oscillation", "load_imbalance"],
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--diagnose-every-samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--auto-extract-features",
        action="store_true",
        help="Enable rolling feature extraction on every batch. Default is off for stable mock streaming; diagnosis still extracts features periodically.",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    live_session_id = create_live_session(
        api_base=args.api_base,
        actuator_id=args.actuator_id,
        session_name=args.session_name,
        sample_rate_hz=args.sample_rate_hz,
        auto_extract_features=args.auto_extract_features,
        diagnose_every_samples=args.diagnose_every_samples,
    )

    print(f"Live session created: {live_session_id}")
    print(f"Streaming {args.duration_s:.1f}s at {args.sample_rate_hz:.1f} Hz")
    print(f"Fault mode: {args.fault_mode}, starts after {args.fault_after_s:.1f}s")
    print(f"Per-batch rolling feature extraction: {'enabled' if args.auto_extract_features else 'disabled'}")

    interval_s = 1.0 / args.sample_rate_hz
    started = time.monotonic()
    next_tick = started
    sent = 0
    batch: list[dict] = []

    try:
        while True:
            elapsed_s = time.monotonic() - started
            if elapsed_s >= args.duration_s:
                break

            sent += 1
            batch.append(
                generate_sample(
                    index=sent,
                    elapsed_s=elapsed_s,
                    sample_rate_hz=args.sample_rate_hz,
                    fault_after_s=args.fault_after_s,
                    fault_mode=args.fault_mode,
                    rng=rng,
                )
            )

            if len(batch) >= args.batch_size:
                send_samples(args.api_base, live_session_id, batch)
                print(f"Sent {sent} samples")
                batch.clear()
                if args.diagnose_every_samples > 0 and sent % args.diagnose_every_samples == 0:
                    run_diagnosis(args.api_base, live_session_id)

            next_tick += interval_s
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)

        if batch:
            send_samples(args.api_base, live_session_id, batch)
            print(f"Sent {sent} samples")

        run_diagnosis(args.api_base, live_session_id)
        stop_session(args.api_base, live_session_id)
        print("Mock real-time actuator test complete.")
        print(f"Total samples sent: {sent}")
        print(f"Live session ID: {live_session_id}")
    except KeyboardInterrupt:
        print("Interrupted. Stopping live session.")
        stop_session(args.api_base, live_session_id)
        raise


if __name__ == "__main__":
    main()
