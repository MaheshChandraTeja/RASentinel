from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.imports import DuplicateSessionStrategy, ImportSourceFormat, TelemetryImportResponse
from app.services.telemetry_importer import TelemetryImportError, telemetry_importer

router = APIRouter(prefix="/actuators/{actuator_id}/imports", tags=["imports"])


def parse_tags_json(tags_json: str | None) -> dict:
    if not tags_json:
        return {}

    try:
        parsed = json.loads(tags_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "tags_json must be valid JSON.",
                "errors": [{"row": None, "field": "tags_json", "message": exc.msg}],
            },
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "tags_json must decode to an object.",
                "errors": [{"row": None, "field": "tags_json", "message": "Expected JSON object"}],
            },
        )

    return parsed


def import_error_to_http(exc: TelemetryImportError) -> HTTPException:
    return HTTPException(
        status_code=409 if "already exists" in exc.message else 422,
        detail={
            "message": exc.message,
            "errors": [issue.model_dump() for issue in exc.issues],
        },
    )


@router.post("/csv", response_model=TelemetryImportResponse)
def import_csv_telemetry(
    actuator_id: str,
    file: UploadFile = File(...),
    session_name: str = Form(...),
    duplicate_strategy: DuplicateSessionStrategy = Form(DuplicateSessionStrategy.REJECT),
    source: str = Form("csv_upload"),
    notes: str | None = Form(None),
    tags_json: str | None = Form(None),
    db: Session = Depends(get_db),
) -> TelemetryImportResponse:
    try:
        tags = parse_tags_json(tags_json)
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
            tags=tags,
            metadata={"filename": file.filename, "content_type": file.content_type},
        )
    except TelemetryImportError as exc:
        raise import_error_to_http(exc) from exc


@router.post("/json", response_model=TelemetryImportResponse)
async def import_json_telemetry(
    actuator_id: str,
    file: UploadFile = File(...),
    session_name: str | None = Form(None),
    duplicate_strategy: DuplicateSessionStrategy = Form(DuplicateSessionStrategy.REJECT),
    source: str = Form("json_upload"),
    notes: str | None = Form(None),
    tags_json: str | None = Form(None),
    db: Session = Depends(get_db),
) -> TelemetryImportResponse:
    try:
        tags = parse_tags_json(tags_json)
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
            tags=tags,
            metadata={
                "filename": file.filename,
                "content_type": file.content_type,
                "payload_metadata": metadata,
            },
        )
    except TelemetryImportError as exc:
        raise import_error_to_http(exc) from exc
