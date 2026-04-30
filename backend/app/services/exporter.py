from __future__ import annotations

import csv
import io
import json
from typing import Iterable

from app.models.session_run import SessionRun
from app.models.telemetry import TelemetrySample


TELEMETRY_EXPORT_COLUMNS = [
    "timestamp",
    "actuator_id",
    "session_id",
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
]


class TelemetryExporter:
    def session_to_csv(self, samples: Iterable[TelemetrySample]) -> bytes:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=TELEMETRY_EXPORT_COLUMNS)
        writer.writeheader()

        for sample in samples:
            writer.writerow(
                {
                    "timestamp": sample.timestamp.isoformat(),
                    "actuator_id": sample.actuator_id,
                    "session_id": sample.session_id,
                    "commanded_position": sample.commanded_position,
                    "actual_position": sample.actual_position,
                    "commanded_velocity": sample.commanded_velocity,
                    "actual_velocity": sample.actual_velocity,
                    "commanded_torque": sample.commanded_torque,
                    "estimated_torque": sample.estimated_torque,
                    "motor_current": sample.motor_current,
                    "temperature": sample.temperature,
                    "load_estimate": sample.load_estimate,
                    "control_latency_ms": sample.control_latency_ms,
                    "encoder_position": sample.encoder_position,
                    "error_position": sample.error_position,
                    "error_velocity": sample.error_velocity,
                    "fault_label": sample.fault_label.value,
                }
            )

        return output.getvalue().encode("utf-8")

    def session_to_json(self, session: SessionRun, samples: Iterable[TelemetrySample]) -> bytes:
        payload = {
            "session": {
                "id": session.id,
                "actuator_id": session.actuator_id,
                "name": session.name,
                "source": session.source,
                "notes": session.notes,
                "started_at": session.started_at.isoformat(),
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "sample_count": session.sample_count,
                "tags": session.tags,
            },
            "samples": [
                {
                    "timestamp": sample.timestamp.isoformat(),
                    "actuator_id": sample.actuator_id,
                    "session_id": sample.session_id,
                    "commanded_position": sample.commanded_position,
                    "actual_position": sample.actual_position,
                    "commanded_velocity": sample.commanded_velocity,
                    "actual_velocity": sample.actual_velocity,
                    "commanded_torque": sample.commanded_torque,
                    "estimated_torque": sample.estimated_torque,
                    "motor_current": sample.motor_current,
                    "temperature": sample.temperature,
                    "load_estimate": sample.load_estimate,
                    "control_latency_ms": sample.control_latency_ms,
                    "encoder_position": sample.encoder_position,
                    "error_position": sample.error_position,
                    "error_velocity": sample.error_velocity,
                    "fault_label": sample.fault_label.value,
                }
                for sample in samples
            ],
        }
        return json.dumps(payload, indent=2).encode("utf-8")


telemetry_exporter = TelemetryExporter()
