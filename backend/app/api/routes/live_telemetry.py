from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.diagnostics import DiagnosisRunResponse
from app.schemas.live_telemetry import (
    LiveDiagnosisRequest,
    LiveRecentTelemetryResponse,
    LiveSessionListResponse,
    LiveSessionRead,
    LiveSessionStartRequest,
    LiveTelemetryBatchRequest,
    LiveTelemetryBatchResponse,
)
from app.services.live_telemetry import LiveTelemetryError, live_telemetry_service

router = APIRouter(prefix="/live", tags=["live-telemetry"])


@router.post("/sessions", response_model=LiveSessionRead, status_code=status.HTTP_201_CREATED)
def start_live_session(
    payload: LiveSessionStartRequest,
    db: Session = Depends(get_db),
) -> LiveSessionRead:
    try:
        return live_telemetry_service.start_session(db, payload)
    except LiveTelemetryError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc


@router.get("/sessions", response_model=LiveSessionListResponse)
def list_live_sessions(
    actuator_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=250),
    db: Session = Depends(get_db),
) -> LiveSessionListResponse:
    return live_telemetry_service.list_sessions(
        db,
        actuator_id=actuator_id,
        status=status_filter,
        limit=limit,
    )


@router.get("/sessions/{live_session_id}", response_model=LiveSessionRead)
def get_live_session(
    live_session_id: str,
    db: Session = Depends(get_db),
) -> LiveSessionRead:
    try:
        return live_telemetry_service.get_session(db, live_session_id)
    except LiveTelemetryError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc


@router.post("/sessions/{live_session_id}/samples", response_model=LiveTelemetryBatchResponse)
def ingest_live_samples(
    live_session_id: str,
    payload: LiveTelemetryBatchRequest,
    db: Session = Depends(get_db),
) -> LiveTelemetryBatchResponse:
    try:
        return live_telemetry_service.ingest_batch(
            db,
            live_session_id=live_session_id,
            payload=payload,
        )
    except LiveTelemetryError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc


@router.post("/sessions/{live_session_id}/diagnose", response_model=DiagnosisRunResponse, status_code=status.HTTP_201_CREATED)
def diagnose_live_session(
    live_session_id: str,
    payload: LiveDiagnosisRequest | None = None,
    db: Session = Depends(get_db),
) -> DiagnosisRunResponse:
    try:
        return live_telemetry_service.run_diagnosis(
            db,
            live_session_id=live_session_id,
            payload=payload or LiveDiagnosisRequest(),
        )
    except LiveTelemetryError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc


@router.post("/sessions/{live_session_id}/stop", response_model=LiveSessionRead)
def stop_live_session(
    live_session_id: str,
    db: Session = Depends(get_db),
) -> LiveSessionRead:
    try:
        return live_telemetry_service.stop_session(db, live_session_id)
    except LiveTelemetryError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc


@router.get("/sessions/{live_session_id}/telemetry/recent", response_model=LiveRecentTelemetryResponse)
def get_recent_live_telemetry(
    live_session_id: str,
    limit: int = Query(default=500, ge=1, le=10_000),
    db: Session = Depends(get_db),
) -> LiveRecentTelemetryResponse:
    try:
        return live_telemetry_service.recent_telemetry(
            db,
            live_session_id=live_session_id,
            limit=limit,
        )
    except LiveTelemetryError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
