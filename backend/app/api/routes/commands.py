from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.command import CommandSignal
from app.models.session_run import SessionRun
from app.schemas.command import CommandSignalCreate, CommandSignalRead

router = APIRouter(prefix="/sessions/{session_id}/commands", tags=["commands"])


@router.post("", response_model=CommandSignalRead, status_code=status.HTTP_201_CREATED)
def create_command_signal(
    session_id: str,
    payload: CommandSignalCreate,
    db: Session = Depends(get_db),
) -> CommandSignal:
    session = db.get(SessionRun, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    command = CommandSignal(
        session_id=session.id,
        actuator_id=session.actuator_id,
        **payload.model_dump(exclude_none=True),
    )

    db.add(command)
    db.commit()
    db.refresh(command)
    return command


@router.get("", response_model=list[CommandSignalRead])
def list_command_signals(
    session_id: str,
    db: Session = Depends(get_db),
) -> list[CommandSignal]:
    session = db.get(SessionRun, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(CommandSignal)
        .where(CommandSignal.session_id == session_id)
        .order_by(CommandSignal.timestamp.asc(), CommandSignal.id.asc())
    )
    return list(db.scalars(stmt).all())