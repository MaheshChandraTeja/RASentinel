from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.init_db import init_db  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.actuator import Actuator  # noqa: E402
from app.models.enums import ActuatorType  # noqa: E402
from app.schemas.diagnostics import DiagnosisRunRequest  # noqa: E402
from app.schemas.imports import DuplicateSessionStrategy, ImportSourceFormat  # noqa: E402
from app.schemas.simulator import ActuatorSimulationConfig, SimulationFaultProfile  # noqa: E402
from app.services.diagnostics_engine import DiagnosticsEngine  # noqa: E402
from app.services.drift_detection import BaselineDriftDetector  # noqa: E402
from app.services.reporting_service import ReportingService  # noqa: E402
from app.services.simulator import simulator  # noqa: E402
from app.services.telemetry_importer import telemetry_importer  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the final RASentinel demo flow locally.")
    parser.add_argument("--fault-profile", default="delayed_response")
    parser.add_argument("--sample-count", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "demo" / "latest-demo-flow.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    init_db()

    profile = SimulationFaultProfile(args.fault_profile)
    duration_s = args.sample_count / 50.0

    with SessionLocal() as db:
        actuator = Actuator(
            name=f"RASentinel Demo Actuator {uuid4().hex[:6]}",
            actuator_type=ActuatorType.SERVO,
            manufacturer="RASentinel Lab",
            model_number="RS-DEMO-01",
            location="Final demo flow",
            rated_torque_nm=12.5,
            rated_current_a=4.2,
            rated_voltage_v=24.0,
        )
        db.add(actuator)
        db.commit()
        db.refresh(actuator)

        healthy = simulator.generate(
            ActuatorSimulationConfig(
                fault_profile=SimulationFaultProfile.HEALTHY,
                seed=9001,
                duration_s=duration_s,
                sample_rate_hz=50,
                fault_intensity=0,
            )
        )
        healthy_import = telemetry_importer.persist_samples(
            db,
            actuator_id=actuator.id,
            session_name="Demo healthy baseline",
            source_format=ImportSourceFormat.SYNTHETIC,
            samples=healthy.samples,
            duplicate_strategy=DuplicateSessionStrategy.CREATE_NEW,
            source="demo_flow",
            source_name="demo_healthy",
            tags={"demo": True, "profile": "healthy"},
            metadata={},
        )

        detector = BaselineDriftDetector()
        baseline = detector.create_baseline_from_session(
            db,
            actuator_id=actuator.id,
            session_id=healthy_import.session_id,
            name="Demo healthy baseline",
            notes="Created by scripts/run_demo_flow.py",
            smoothing_window=5,
            activate=True,
        )

        faulty = simulator.generate(
            ActuatorSimulationConfig(
                fault_profile=profile,
                seed=9002,
                duration_s=duration_s,
                sample_rate_hz=50,
                fault_intensity=0.82,
            )
        )
        faulty_import = telemetry_importer.persist_samples(
            db,
            actuator_id=actuator.id,
            session_name=f"Demo {profile.value} fault",
            source_format=ImportSourceFormat.SYNTHETIC,
            samples=faulty.samples,
            duplicate_strategy=DuplicateSessionStrategy.CREATE_NEW,
            source="demo_flow",
            source_name=f"demo_{profile.value}",
            tags={"demo": True, "profile": profile.value},
            metadata={},
        )

        diagnostics = DiagnosticsEngine(drift_detector=detector)
        diagnosis = diagnostics.run_diagnosis(
            db,
            session_id=faulty_import.session_id,
            payload=DiagnosisRunRequest(
                baseline_id=baseline.id,
                smoothing_window=5,
                persist=True,
                use_isolation_forest=True,
            ),
        )

        report_service = ReportingService()
        audit_report = report_service.build_audit_report(
            db,
            diagnosis_id=diagnosis.diagnosis_id,
            persist_record=False,
        )
        html_payload = report_service.render_html(audit_report)
        record = report_service.persist_html_report(
            db,
            audit_report=audit_report,
            html_payload=html_payload,
        )

        result = {
            "actuator_id": actuator.id,
            "healthy_session_id": healthy_import.session_id,
            "faulty_session_id": faulty_import.session_id,
            "baseline_id": baseline.id,
            "diagnosis_id": diagnosis.diagnosis_id,
            "fault_label": diagnosis.classification.fault_label.value,
            "severity_score": diagnosis.classification.severity_score,
            "confidence_score": diagnosis.classification.confidence_score,
            "report_html_path": record.file_path,
            "report_url": f"/api/v1/reports/{diagnosis.diagnosis_id}/html",
        }

    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nSaved demo flow result to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
