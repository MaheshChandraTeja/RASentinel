from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.simulator import ActuatorSimulationConfig, SimulationFaultProfile  # noqa: E402
from app.services.simulator import simulator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate RASentinel sample telemetry datasets.")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data" / "samples")
    parser.add_argument("--sample-count", type=int, default=1000)
    parser.add_argument("--sample-rate-hz", type=float, default=50.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    duration_s = args.sample_count / args.sample_rate_hz

    datasets = [
        ("rasentinel_healthy_1000", SimulationFaultProfile.HEALTHY, 42, 0.0),
        ("rasentinel_delayed_response_1000", SimulationFaultProfile.DELAYED_RESPONSE, 43, 0.85),
        ("rasentinel_friction_increase_1000", SimulationFaultProfile.FRICTION_INCREASE, 44, 0.80),
        ("rasentinel_control_instability_1000", SimulationFaultProfile.OSCILLATION_CONTROL_INSTABILITY, 45, 0.80),
    ]

    for stem, profile, seed, intensity in datasets:
        config = ActuatorSimulationConfig(
            fault_profile=profile,
            seed=seed,
            sample_rate_hz=args.sample_rate_hz,
            duration_s=duration_s,
            fault_intensity=intensity,
        )
        generated = simulator.generate(config)
        csv_path = args.output_dir / f"{stem}.csv"
        json_path = args.output_dir / f"{stem}.json"
        csv_path.write_text(simulator.export_csv(generated), encoding="utf-8")
        json_path.write_text(simulator.export_json(generated), encoding="utf-8")
        print(f"Generated {csv_path}")
        print(f"Generated {json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
