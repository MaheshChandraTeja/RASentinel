from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.init_db import init_db  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.release_benchmark import BenchmarkConfig, ReleaseBenchmarkRunner  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RASentinel release readiness benchmark.")
    parser.add_argument("--sample-count", type=int, default=1000)
    parser.add_argument("--sample-rate-hz", type=float, default=50.0)
    parser.add_argument("--healthy-trials", type=int, default=5)
    parser.add_argument("--fault-intensity", type=float, default=0.72)
    parser.add_argument("--seed", type=int, default=20260429)
    parser.add_argument("--no-isolation-forest", action="store_true")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "benchmarks" / "latest-benchmark.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    init_db()
    config = BenchmarkConfig(
        sample_count=args.sample_count,
        sample_rate_hz=args.sample_rate_hz,
        healthy_trials=args.healthy_trials,
        fault_intensity=args.fault_intensity,
        seed=args.seed,
        use_isolation_forest=not args.no_isolation_forest,
    )

    runner = ReleaseBenchmarkRunner()
    with SessionLocal() as db:
        result = runner.run(db, config)

    args.output.write_text(result.to_json(), encoding="utf-8")
    print(result.to_json())
    print(f"\nSaved benchmark result to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
