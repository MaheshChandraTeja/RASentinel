from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.baseline import HealthyBaseline
from app.schemas.baseline import (
    BaselineCreateRequest,
    BaselineRead,
    DriftDetectionRequest,
    DriftDetectionResponse,
)
from app.services.drift_detection import BaselineDriftDetector, DriftDetectionError

router = APIRouter(tags=["baselines", "drift"])
detector = BaselineDriftDetector()


@router.post(
    "/actuators/{actuator_id}/baselines/from-session",
    response_model=BaselineRead,
    status_code=status.HTTP_201_CREATED,
)
def create_baseline_from_session(
    actuator_id: str,
    payload: BaselineCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        return detector.create_baseline_from_session(
            db,
            actuator_id=actuator_id,
            session_id=payload.session_id,
            name=payload.name,
            notes=payload.notes,
            smoothing_window=payload.smoothing_window,
            activate=payload.activate,
        )
    except DriftDetectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/actuators/{actuator_id}/baselines", response_model=list[BaselineRead])
def list_baselines(
    actuator_id: str,
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    stmt = select(HealthyBaseline).where(HealthyBaseline.actuator_id == actuator_id)
    if active_only:
        stmt = stmt.where(HealthyBaseline.is_active.is_(True))
    stmt = stmt.order_by(HealthyBaseline.created_at.desc())
    return list(db.scalars(stmt).all())


@router.get("/baselines/{baseline_id}", response_model=BaselineRead)
def get_baseline(baseline_id: str, db: Session = Depends(get_db)):
    baseline = db.get(HealthyBaseline, baseline_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return baseline


@router.post("/sessions/{session_id}/drift/analyze", response_model=DriftDetectionResponse)
def analyze_session_drift(
    session_id: str,
    payload: DriftDetectionRequest,
    db: Session = Depends(get_db),
):
    try:
        return detector.analyze_session(
            db,
            session_id=session_id,
            baseline_id=payload.baseline_id,
            smoothing_window=payload.smoothing_window,
            persist_diagnosis=payload.persist_diagnosis,
        )
    except DriftDetectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
