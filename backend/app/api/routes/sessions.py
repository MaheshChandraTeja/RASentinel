from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.actuator import Actuator
from app.models.session_run import SessionRun
from app.schemas.session_run import SessionRunCreate, SessionRunRead

router = APIRouter(tags=["sessions"])


@router.post(
    "/actuators/{actuator_id}/sessions",
    response_model=SessionRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    actuator_id: str,
    payload: SessionRunCreate,
    db: Session = Depends(get_db),
) -> SessionRun:
    actuator = db.get(Actuator, actuator_id)
    if actuator is None:
        raise HTTPException(status_code=404, detail="Actuator not found")

    data = payload.model_dump(exclude_none=True)
    session = SessionRun(actuator_id=actuator_id, **data)

    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/actuators/{actuator_id}/sessions", response_model=list[SessionRunRead])
def list_sessions_for_actuator(
    actuator_id: str,
    db: Session = Depends(get_db),
) -> list[SessionRun]:
    actuator = db.get(Actuator, actuator_id)
    if actuator is None:
        raise HTTPException(status_code=404, detail="Actuator not found")

    stmt = (
        select(SessionRun)
        .where(SessionRun.actuator_id == actuator_id)
        .order_by(SessionRun.started_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.get("/sessions/{session_id}", response_model=SessionRunRead)
def get_session(session_id: str, db: Session = Depends(get_db)) -> SessionRun:
    session = db.get(SessionRun, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session