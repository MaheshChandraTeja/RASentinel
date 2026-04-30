from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.actuator import Actuator
from app.models.import_job import ImportJob
from app.models.session_run import SessionRun
from app.models.telemetry import TelemetrySample
from app.schemas.imports import (
    DuplicateSessionStrategy,
    ImportSourceFormat,
    ImportValidationIssue,
    TelemetryImportResponse,
)
from app.schemas.telemetry import TelemetrySampleCreate


class TelemetryImportError(Exception):
    def __init__(self, message: str, issues: list[ImportValidationIssue] | None = None):
        super().__init__(message)
        self.message = message
        self.issues = issues or []


class DuplicateSessionError(TelemetryImportError):
    pass


ALLOWED_TELEMETRY_FIELDS = set(TelemetrySampleCreate.model_fields.keys())
MEASUREMENT_FIELDS = {
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
}


class TelemetryImporter:
    def parse_csv_upload(self, file: UploadFile, max_rows: int = 250_000) -> list[TelemetrySampleCreate]:
        filename = file.filename or "telemetry.csv"
        if not filename.lower().endswith(".csv"):
            raise TelemetryImportError(
                "CSV import expects a .csv file.",
                [ImportValidationIssue(row=None, field="file", message="File extension must be .csv")],
            )

        issues: list[ImportValidationIssue] = []
        samples: list[TelemetrySampleCreate] = []

        file.file.seek(0)
        wrapper = io.TextIOWrapper(file.file, encoding="utf-8-sig", newline="")
        try:
            reader = csv.DictReader(wrapper)
            if not reader.fieldnames:
                raise TelemetryImportError(
                    "CSV file is empty or missing headers.",
                    [ImportValidationIssue(row=None, field="headers", message="CSV headers are required")],
                )

            normalized_headers = [self._normalize_header(header) for header in reader.fieldnames]
            unknown_headers = sorted(set(normalized_headers) - ALLOWED_TELEMETRY_FIELDS)
            if unknown_headers:
                raise TelemetryImportError(
                    "CSV contains unsupported telemetry columns.",
                    [
                        ImportValidationIssue(
                            row=None,
                            field=header,
                            message=f"Unsupported column '{header}'",
                        )
                        for header in unknown_headers
                    ],
                )

            for row_number, row in enumerate(reader, start=2):
                if len(samples) >= max_rows:
                    issues.append(
                        ImportValidationIssue(
                            row=row_number,
                            field=None,
                            message=f"Maximum import size of {max_rows} rows exceeded",
                        )
                    )
                    break

                normalized = {
                    self._normalize_header(key): self._normalize_value(value)
                    for key, value in row.items()
                    if key is not None
                }
                sample = self._validate_sample(normalized, row_number, issues)
                if sample is not None:
                    samples.append(sample)

                if len(issues) >= 100:
                    break
        finally:
            try:
                wrapper.detach()
            except Exception:
                pass

        if issues:
            raise TelemetryImportError("Telemetry CSV validation failed.", issues)

        if not samples:
            raise TelemetryImportError(
                "CSV did not contain any valid telemetry rows.",
                [ImportValidationIssue(row=None, field="rows", message="No valid rows found")],
            )

        return samples

    async def parse_json_upload(self, file: UploadFile, max_rows: int = 250_000) -> tuple[list[TelemetrySampleCreate], dict]:
        filename = file.filename or "telemetry.json"
        if not filename.lower().endswith(".json"):
            raise TelemetryImportError(
                "JSON import expects a .json file.",
                [ImportValidationIssue(row=None, field="file", message="File extension must be .json")],
            )

        raw = await file.read()
        if len(raw) > 150 * 1024 * 1024:
            raise TelemetryImportError(
                "JSON file is too large for this importer.",
                [ImportValidationIssue(row=None, field="file", message="Maximum JSON file size is 150 MB")],
            )

        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise TelemetryImportError(
                "Invalid JSON file.",
                [ImportValidationIssue(row=exc.lineno, field=None, message=exc.msg)],
            ) from exc

        metadata: dict[str, Any] = {}
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("samples") or payload.get("telemetry")
            metadata = {key: value for key, value in payload.items() if key not in {"samples", "telemetry"}}
        else:
            raise TelemetryImportError(
                "JSON root must be an array or an object containing 'samples'.",
                [ImportValidationIssue(row=None, field="root", message="Expected array or object")],
            )

        if not isinstance(rows, list):
            raise TelemetryImportError(
                "JSON telemetry payload must be a list.",
                [ImportValidationIssue(row=None, field="samples", message="Expected a list of samples")],
            )

        if len(rows) > max_rows:
            raise TelemetryImportError(
                "JSON contains too many telemetry samples.",
                [ImportValidationIssue(row=None, field="samples", message=f"Maximum import size is {max_rows}")],
            )

        issues: list[ImportValidationIssue] = []
        samples: list[TelemetrySampleCreate] = []

        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                issues.append(ImportValidationIssue(row=index, field=None, message="Each sample must be an object"))
                continue

            unknown = sorted(set(row.keys()) - ALLOWED_TELEMETRY_FIELDS)
            if unknown:
                issues.append(
                    ImportValidationIssue(row=index, field=unknown[0], message=f"Unsupported field '{unknown[0]}'")
                )
                continue

            sample = self._validate_sample(row, index, issues)
            if sample is not None:
                samples.append(sample)

            if len(issues) >= 100:
                break

        if issues:
            raise TelemetryImportError("Telemetry JSON validation failed.", issues)

        if not samples:
            raise TelemetryImportError(
                "JSON did not contain any valid telemetry rows.",
                [ImportValidationIssue(row=None, field="samples", message="No valid samples found")],
            )

        return samples, metadata

    def persist_samples(
        self,
        db: Session,
        *,
        actuator_id: str,
        session_name: str,
        source_format: ImportSourceFormat,
        samples: list[TelemetrySampleCreate],
        duplicate_strategy: DuplicateSessionStrategy,
        source_name: str | None = None,
        source: str = "import",
        notes: str | None = None,
        tags: dict | None = None,
        metadata: dict | None = None,
    ) -> TelemetryImportResponse:
        actuator = db.get(Actuator, actuator_id)
        if actuator is None:
            raise TelemetryImportError(
                "Actuator not found.",
                [ImportValidationIssue(row=None, field="actuator_id", message="Actuator does not exist")],
            )

        session = self._create_session_with_duplicate_strategy(
            db,
            actuator_id=actuator_id,
            session_name=session_name,
            source=source,
            notes=notes,
            tags=tags or {},
            duplicate_strategy=duplicate_strategy,
        )

        telemetry_models = [
            TelemetrySample(session_id=session.id, actuator_id=actuator_id, **sample.model_dump(exclude_none=True))
            for sample in samples
        ]

        db.add_all(telemetry_models)
        session.sample_count = len(telemetry_models)
        db.add(session)

        import_job = ImportJob(
            actuator_id=actuator_id,
            session_id=session.id,
            source_format=source_format.value,
            source_name=source_name,
            duplicate_strategy=duplicate_strategy.value,
            status="completed",
            rows_received=len(samples),
            rows_imported=len(samples),
            rows_failed=0,
            errors=[],
            metadata_json=metadata or {},
        )
        db.add(import_job)
        db.commit()
        db.refresh(session)
        db.refresh(import_job)

        return TelemetryImportResponse(
            import_job_id=import_job.id,
            actuator_id=actuator_id,
            session_id=session.id,
            session_name=session.name,
            source_format=source_format,
            duplicate_strategy=duplicate_strategy,
            rows_received=import_job.rows_received,
            rows_imported=import_job.rows_imported,
            rows_failed=import_job.rows_failed,
            status=import_job.status,
            errors=[],
            created_at=import_job.created_at,
        )

    def _create_session_with_duplicate_strategy(
        self,
        db: Session,
        *,
        actuator_id: str,
        session_name: str,
        source: str,
        notes: str | None,
        tags: dict,
        duplicate_strategy: DuplicateSessionStrategy,
    ) -> SessionRun:
        existing_sessions = list(
            db.scalars(
                select(SessionRun).where(
                    SessionRun.actuator_id == actuator_id,
                    SessionRun.name == session_name,
                )
            ).all()
        )

        if existing_sessions and duplicate_strategy == DuplicateSessionStrategy.REJECT:
            raise DuplicateSessionError(
                "A session with this name already exists for the actuator.",
                [
                    ImportValidationIssue(
                        row=None,
                        field="session_name",
                        message="Use duplicate_strategy=create_new or replace",
                    )
                ],
            )

        if existing_sessions and duplicate_strategy == DuplicateSessionStrategy.REPLACE:
            for existing in existing_sessions:
                db.delete(existing)
            db.flush()

        final_name = session_name
        if existing_sessions and duplicate_strategy == DuplicateSessionStrategy.CREATE_NEW:
            suffix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            final_name = f"{session_name} ({suffix})"

        session = SessionRun(actuator_id=actuator_id, name=final_name, source=source, notes=notes, tags=tags)
        db.add(session)
        db.flush()
        return session

    def _validate_sample(
        self,
        row: dict[str, Any],
        row_number: int,
        issues: list[ImportValidationIssue],
    ) -> TelemetrySampleCreate | None:
        if not any(row.get(field) not in {None, ""} for field in MEASUREMENT_FIELDS):
            issues.append(
                ImportValidationIssue(
                    row=row_number,
                    field=None,
                    message="At least one telemetry measurement field is required",
                )
            )
            return None

        try:
            return TelemetrySampleCreate.model_validate(row)
        except ValidationError as exc:
            for error in exc.errors():
                field = ".".join(str(part) for part in error.get("loc", [])) or None
                issues.append(
                    ImportValidationIssue(
                        row=row_number,
                        field=field,
                        message=str(error.get("msg", "Invalid value")),
                    )
                )
            return None

    def _normalize_header(self, header: str) -> str:
        return header.strip().lower().replace(" ", "_").replace("-", "_")

    def _normalize_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                return None
            return stripped
        return value


telemetry_importer = TelemetryImporter()
