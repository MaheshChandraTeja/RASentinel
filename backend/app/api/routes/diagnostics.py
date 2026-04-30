from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.diagnosis import DiagnosisRead
from app.schemas.diagnostics import (
    ActuatorHealthTimelineResponse,
    DiagnosisRunRequest,
    DiagnosisRunResponse,
)
from app.services.diagnostics_engine import DiagnosticsEngine, DiagnosticsError

router = APIRouter(tags=["diagnostics"])
engine = DiagnosticsEngine()


@router.post(
    "/diagnostics/run/{session_id}",
    response_model=DiagnosisRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_diagnosis(
    session_id: str,
    payload: DiagnosisRunRequest | None = None,
    db: Session = Depends(get_db),
) -> DiagnosisRunResponse:
    try:
        return engine.run_diagnosis(
            db,
            session_id=session_id,
            payload=payload or DiagnosisRunRequest(),
        )
    except DiagnosticsError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc


@router.get("/diagnostics/{diagnosis_id}", response_model=DiagnosisRead)
def get_diagnosis(
    diagnosis_id: str,
    db: Session = Depends(get_db),
):
    try:
        return engine.get_diagnosis(db, diagnosis_id=diagnosis_id)
    except DiagnosticsError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc


@router.get("/actuators/{actuator_id}/health", response_model=ActuatorHealthTimelineResponse)
def get_actuator_health_timeline(
    actuator_id: str,
    db: Session = Depends(get_db),
) -> ActuatorHealthTimelineResponse:
    try:
        return engine.get_health_timeline(db, actuator_id=actuator_id)
    except DiagnosticsError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
