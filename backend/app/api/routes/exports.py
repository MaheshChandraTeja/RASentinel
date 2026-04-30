from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.session_run import SessionRun
from app.models.telemetry import TelemetrySample
from app.services.exporter import telemetry_exporter

router = APIRouter(prefix="/sessions/{session_id}/exports", tags=["exports"])


def load_session_and_samples(session_id: str, db: Session) -> tuple[SessionRun, list[TelemetrySample]]:
    session = db.get(SessionRun, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    samples = list(
        db.scalars(
            select(TelemetrySample)
            .where(TelemetrySample.session_id == session_id)
            .order_by(TelemetrySample.timestamp.asc(), TelemetrySample.id.asc())
        ).all()
    )
    return session, samples


@router.get("/csv")
def export_session_csv(session_id: str, db: Session = Depends(get_db)) -> Response:
    session, samples = load_session_and_samples(session_id, db)
    content = telemetry_exporter.session_to_csv(samples)
    safe_name = session.name.lower().replace(" ", "-")[:80]
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={safe_name}-telemetry.csv"},
    )


@router.get("/json")
def export_session_json(session_id: str, db: Session = Depends(get_db)) -> Response:
    session, samples = load_session_and_samples(session_id, db)
    content = telemetry_exporter.session_to_json(session, samples)
    safe_name = session.name.lower().replace(" ", "-")[:80]
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={safe_name}-telemetry.json"},
    )
