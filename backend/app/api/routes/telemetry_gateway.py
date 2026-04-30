from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.imports import DuplicateSessionStrategy, ImportSourceFormat, TelemetryImportResponse
from app.schemas.simulator import SimulationImportRequest, SimulationImportResponse
from app.services.simulator import simulator
from app.services.telemetry_importer import TelemetryImportError, telemetry_importer

router = APIRouter(prefix="/telemetry", tags=["telemetry-gateway"])


@router.post("/simulate", response_model=SimulationImportResponse)
def simulate_and_import_telemetry(
    payload: SimulationImportRequest,
    db: Session = Depends(get_db),
) -> SimulationImportResponse:
    generated = simulator.generate(payload.config)
    summary = simulator.summarize(generated.samples)

    try:
        import_result = telemetry_importer.persist_samples(
            db,
            actuator_id=payload.actuator_id,
            session_name=payload.session_name,
            source_format=ImportSourceFormat.SYNTHETIC,
            samples=generated.samples,
            duplicate_strategy=payload.duplicate_strategy,
            source_name="rasentinel-simulator",
            source="synthetic_gateway",
            notes=payload.notes,
            tags={
                **payload.tags,
                "simulator_fault_profile": payload.config.fault_profile.value,
                "simulator_seed": payload.config.seed,
            },
            metadata={
                "simulation": generated.metadata.model_dump(mode="json"),
                "summary": summary,
                "gateway_route": "/telemetry/simulate",
            },
        )
    except TelemetryImportError as exc:
        raise HTTPException(
            status_code=409 if "already exists" in exc.message else 422,
            detail={"message": exc.message, "errors": [issue.model_dump() for issue in exc.issues]},
        ) from exc

    return SimulationImportResponse(
        **import_result.model_dump(),
        metadata=generated.metadata,
    )


@router.post("/import", response_model=TelemetryImportResponse)
async def import_telemetry_file(
    file: UploadFile = File(...),
    actuator_id: str = Form(...),
    session_name: str | None = Form(None),
    file_format: str | None = Form(None),
    duplicate_strategy: DuplicateSessionStrategy = Form(DuplicateSessionStrategy.REJECT),
    source: str = Form("telemetry_gateway_upload"),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
) -> TelemetryImportResponse:
    filename = (file.filename or "").lower()
    resolved_format = (file_format or "").lower().strip()
    if not resolved_format:
        if filename.endswith(".csv"):
            resolved_format = "csv"
        elif filename.endswith(".json"):
            resolved_format = "json"

    try:
        if resolved_format == "csv":
            if not session_name:
                raise TelemetryImportError(
                    "session_name is required for CSV imports through /telemetry/import.",
                    [],
                )
            samples = telemetry_importer.parse_csv_upload(file)
            return telemetry_importer.persist_samples(
                db,
                actuator_id=actuator_id,
                session_name=session_name,
                source_format=ImportSourceFormat.CSV,
                samples=samples,
                duplicate_strategy=duplicate_strategy,
                source_name=file.filename,
                source=source,
                notes=notes,
                tags={"gateway_route": "/telemetry/import"},
                metadata={"filename": file.filename, "content_type": file.content_type},
            )

        if resolved_format == "json":
            samples, metadata = await telemetry_importer.parse_json_upload(file)
            resolved_session_name = session_name or str(metadata.get("session_name") or "Imported JSON telemetry")
            return telemetry_importer.persist_samples(
                db,
                actuator_id=actuator_id,
                session_name=resolved_session_name,
                source_format=ImportSourceFormat.JSON,
                samples=samples,
                duplicate_strategy=duplicate_strategy,
                source_name=file.filename,
                source=source,
                notes=notes,
                tags={"gateway_route": "/telemetry/import"},
                metadata={
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "payload_metadata": metadata,
                },
            )

        raise TelemetryImportError(
            "Unsupported telemetry file format. Use CSV or JSON, or pass file_format=csv/json.",
            [],
        )
    except TelemetryImportError as exc:
        raise HTTPException(
            status_code=409 if "already exists" in exc.message else 422,
            detail={"message": exc.message, "errors": [issue.model_dump() for issue in exc.issues]},
        ) from exc
