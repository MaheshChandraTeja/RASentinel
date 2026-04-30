from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.diagnostics import DiagnosticReportResponse
from app.schemas.reports import AuditReportResponse, ReportGenerationResponse, ReportHistoryResponse, ReportRecordRead
from app.services.diagnostics_engine import DiagnosticsEngine, DiagnosticsError
from app.services.reporting_service import ReportingError, ReportingService

router = APIRouter(prefix="/reports", tags=["reports"])
diagnostics_engine = DiagnosticsEngine()
reporting_service = ReportingService(diagnostics_engine=diagnostics_engine)


@router.get("/history", response_model=ReportHistoryResponse)
def list_report_history(
    actuator_id: str | None = None,
    query: str | None = None,
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReportHistoryResponse:
    return reporting_service.list_history(
        db,
        actuator_id=actuator_id,
        query=query,
        limit=limit,
        offset=offset,
    )


@router.get("/history/{record_id}", response_model=ReportRecordRead)
def get_report_history_record(record_id: str, db: Session = Depends(get_db)) -> ReportRecordRead:
    try:
        return reporting_service.get_record(db, record_id=record_id)
    except ReportingError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc


@router.get("/{diagnosis_id}", response_model=DiagnosticReportResponse)
def get_diagnostic_report(
    diagnosis_id: str,
    db: Session = Depends(get_db),
) -> DiagnosticReportResponse:
    try:
        return diagnostics_engine.build_report(db, diagnosis_id=diagnosis_id)
    except DiagnosticsError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc


@router.get("/{diagnosis_id}/audit", response_model=AuditReportResponse)
def get_audit_report(
    diagnosis_id: str,
    persist: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> AuditReportResponse:
    try:
        return reporting_service.build_audit_report(
            db,
            diagnosis_id=diagnosis_id,
            persist_record=persist,
        )
    except ReportingError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc


@router.post("/{diagnosis_id}/audit", response_model=ReportGenerationResponse)
def generate_and_store_audit_report(
    diagnosis_id: str,
    db: Session = Depends(get_db),
) -> ReportGenerationResponse:
    try:
        audit_report = reporting_service.build_audit_report(
            db,
            diagnosis_id=diagnosis_id,
            persist_record=False,
        )
        html_payload = reporting_service.render_html(audit_report)
        record = reporting_service.persist_html_report(
            db,
            audit_report=audit_report,
            html_payload=html_payload,
        )
        audit_report.report_record_id = record.id
        return ReportGenerationResponse(
            record=ReportRecordRead.model_validate(record),
            audit_report=audit_report,
        )
    except ReportingError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc


@router.get("/{diagnosis_id}/html", response_class=HTMLResponse)
def get_diagnostic_report_html(
    diagnosis_id: str,
    persist: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        html_payload, _record = reporting_service.generate_html_report(
            db,
            diagnosis_id=diagnosis_id,
            persist_record=persist,
        )
        return HTMLResponse(
            content=html_payload,
            headers={"Content-Disposition": f"inline; filename=rasentinel-diagnosis-{diagnosis_id}.html"},
        )
    except ReportingError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc


@router.get("/{diagnosis_id}/markdown")
def get_diagnostic_report_markdown(
    diagnosis_id: str,
    db: Session = Depends(get_db),
) -> Response:
    try:
        report = diagnostics_engine.build_report(db, diagnosis_id=diagnosis_id)
        markdown = diagnostics_engine.render_markdown_report(report)
        return Response(
            content=markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=rasentinel-diagnosis-{diagnosis_id}.md"},
        )
    except DiagnosticsError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
