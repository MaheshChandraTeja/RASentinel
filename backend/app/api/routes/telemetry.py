from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.actuator import Actuator
from app.models.session_run import SessionRun
from app.models.telemetry import TelemetrySample
from app.schemas.telemetry import TelemetryBulkCreate, TelemetrySampleRead

router = APIRouter(tags=["telemetry"])


@router.post(
    "/sessions/{session_id}/telemetry",
    response_model=list[TelemetrySampleRead],
    status_code=status.HTTP_201_CREATED,
)
def add_telemetry_samples(
    session_id: str,
    payload: TelemetryBulkCreate,
    db: Session = Depends(get_db),
) -> list[TelemetrySample]:
    session = db.get(SessionRun, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    samples: list[TelemetrySample] = []

    for sample_payload in payload.samples:
        sample_data = sample_payload.model_dump(exclude_none=True)
        sample = TelemetrySample(session_id=session.id, actuator_id=session.actuator_id, **sample_data)
        samples.append(sample)

    db.add_all(samples)
    session.sample_count += len(samples)
    db.add(session)
    db.commit()

    for sample in samples:
        db.refresh(sample)

    return samples


@router.get("/sessions/{session_id}/telemetry", response_model=list[TelemetrySampleRead])
def list_telemetry_samples(
    session_id: str,
    limit: int = Query(default=500, ge=1, le=10_000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[TelemetrySample]:
    session = db.get(SessionRun, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(TelemetrySample)
        .where(TelemetrySample.session_id == session_id)
        .order_by(TelemetrySample.timestamp.asc(), TelemetrySample.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


@router.get("/actuators/{actuator_id}/telemetry", response_model=list[TelemetrySampleRead])
def list_telemetry_for_actuator(
    actuator_id: str,
    session_id: str | None = None,
    limit: int = Query(default=1_000, ge=1, le=25_000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[TelemetrySample]:
    actuator = db.get(Actuator, actuator_id)
    if actuator is None:
        raise HTTPException(status_code=404, detail="Actuator not found")

    stmt = select(TelemetrySample).where(TelemetrySample.actuator_id == actuator_id)
    if session_id:
        stmt = stmt.where(TelemetrySample.session_id == session_id)

    stmt = stmt.order_by(TelemetrySample.timestamp.asc(), TelemetrySample.id.asc()).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())
