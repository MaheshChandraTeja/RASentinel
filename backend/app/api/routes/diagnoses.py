from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.diagnosis import DiagnosisResult
from app.models.session_run import SessionRun
from app.schemas.diagnosis import DiagnosisCreate, DiagnosisRead, severity_band_from_score

router = APIRouter(prefix="/sessions/{session_id}/diagnoses", tags=["diagnoses"])


@router.post("", response_model=DiagnosisRead, status_code=status.HTTP_201_CREATED)
def create_diagnosis(
    session_id: str,
    payload: DiagnosisCreate,
    db: Session = Depends(get_db),
) -> DiagnosisResult:
    session = db.get(SessionRun, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    data = payload.model_dump(exclude_none=True)
    if data.get("severity_band") is None:
        data["severity_band"] = severity_band_from_score(data["severity_score"])

    diagnosis = DiagnosisResult(
        session_id=session.id,
        actuator_id=session.actuator_id,
        **data,
    )

    db.add(diagnosis)
    db.commit()
    db.refresh(diagnosis)
    return diagnosis


@router.get("", response_model=list[DiagnosisRead])
def list_diagnoses(
    session_id: str,
    db: Session = Depends(get_db),
) -> list[DiagnosisResult]:
    session = db.get(SessionRun, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(DiagnosisResult)
        .where(DiagnosisResult.session_id == session_id)
        .order_by(DiagnosisResult.diagnosis_time.desc())
    )
    return list(db.scalars(stmt).all())


@router.get("/latest", response_model=DiagnosisRead)
def get_latest_diagnosis(
    session_id: str,
    db: Session = Depends(get_db),
) -> DiagnosisResult:
    session = db.get(SessionRun, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(DiagnosisResult)
        .where(DiagnosisResult.session_id == session_id)
        .order_by(DiagnosisResult.diagnosis_time.desc())
        .limit(1)
    )

    diagnosis = db.scalars(stmt).first()
    if diagnosis is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    return diagnosis