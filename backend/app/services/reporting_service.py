from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.actuator import Actuator
from app.models.diagnosis import DiagnosisResult
from app.models.report_record import ReportRecord
from app.models.session_run import SessionRun
from app.models.telemetry import TelemetrySample
from app.schemas.diagnostics import DiagnosticReportResponse
from app.schemas.reports import (
    AuditReportResponse,
    DriftTimelinePoint,
    EvidenceSignal,
    ReportGenerationResponse,
    ReportHistoryResponse,
    ReportRecordRead,
)
from app.services.diagnostics_engine import DiagnosticsEngine, DiagnosticsError

REPORT_ENGINE_VERSION = "reports-audit-1.0.0"


class ReportingError(ValueError):
    pass


class ReportingService:
    def __init__(self, diagnostics_engine: DiagnosticsEngine | None = None) -> None:
        self.diagnostics_engine = diagnostics_engine or DiagnosticsEngine()

    def build_audit_report(
        self,
        db: Session,
        *,
        diagnosis_id: str,
        persist_record: bool = False,
    ) -> AuditReportResponse:
        base_report = self._build_base_report(db, diagnosis_id=diagnosis_id)
        diagnosis = base_report.diagnosis
        evidence = self._extract_evidence(base_report)
        timeline = self._build_drift_timeline(db, session_id=diagnosis.session_id)
        history_count = self._diagnosis_history_count(db, actuator_id=diagnosis.actuator_id)

        title = f"RASentinel Diagnostic Report - {base_report.actuator.get('name', 'Actuator')}"
        notes = self._technical_notes(base_report)

        audit_report = AuditReportResponse(
            diagnosis_id=diagnosis.id,
            generated_at=datetime.now(timezone.utc),
            title=title,
            actuator_information=base_report.actuator,
            telemetry_session_summary=base_report.session,
            detected_fault={
                "fault_label": diagnosis.fault_label.value,
                "summary": diagnosis.summary,
                "diagnosis_time": diagnosis.diagnosis_time.isoformat(),
            },
            severity_and_confidence={
                "severity_score": diagnosis.severity_score,
                "severity_band": diagnosis.severity_band.value,
                "confidence_score": diagnosis.confidence_score,
                "health_status": base_report.actuator.get("health_status"),
            },
            evidence_signals=evidence,
            drift_timeline=timeline,
            recommended_action=base_report.maintenance_action,
            technical_notes=notes,
            diagnosis_history_count=history_count,
            report_record_id=None,
            html_url=f"/api/v1/reports/{diagnosis.id}/html",
        )

        if persist_record:
            record = self.persist_html_report(db, audit_report=audit_report)
            audit_report.report_record_id = record.id

        return audit_report

    def generate_html_report(
        self,
        db: Session,
        *,
        diagnosis_id: str,
        persist_record: bool = True,
    ) -> tuple[str, ReportRecord | None]:
        audit_report = self.build_audit_report(db, diagnosis_id=diagnosis_id, persist_record=False)
        html_payload = self.render_html(audit_report)
        record = None
        if persist_record:
            record = self.persist_html_report(db, audit_report=audit_report, html_payload=html_payload)
        return html_payload, record

    def persist_html_report(
        self,
        db: Session,
        *,
        audit_report: AuditReportResponse,
        html_payload: str | None = None,
    ) -> ReportRecord:
        if html_payload is None:
            html_payload = self.render_html(audit_report)

        diagnosis_id = audit_report.diagnosis_id
        content_hash = hashlib.sha256(html_payload.encode("utf-8")).hexdigest()
        diagnosis = self.diagnostics_engine.get_diagnosis(db, diagnosis_id=diagnosis_id)

        existing_stmt = (
            select(ReportRecord)
            .where(
                ReportRecord.diagnosis_id == diagnosis_id,
                ReportRecord.report_format == "html",
                ReportRecord.content_hash == content_hash,
            )
            .order_by(ReportRecord.generated_at.desc())
            .limit(1)
        )
        existing = db.scalars(existing_stmt).first()
        if existing is not None:
            return existing

        reports_dir = self._reports_dir()
        safe_name = f"rasentinel-report-{diagnosis_id}-{content_hash[:12]}.html"
        path = reports_dir / safe_name
        path.write_text(html_payload, encoding="utf-8")

        searchable = self._searchable_text(audit_report)
        record = ReportRecord(
            diagnosis_id=diagnosis.id,
            actuator_id=diagnosis.actuator_id,
            session_id=diagnosis.session_id,
            title=audit_report.title,
            report_format="html",
            file_path=str(path),
            content_hash=content_hash,
            fault_label=diagnosis.fault_label.value,
            severity_band=diagnosis.severity_band.value,
            summary=diagnosis.summary[:1400],
            searchable_text=searchable,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def list_history(
        self,
        db: Session,
        *,
        actuator_id: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReportHistoryResponse:
        limit = max(1, min(limit, 250))
        offset = max(0, offset)

        conditions = []
        if actuator_id:
            conditions.append(ReportRecord.actuator_id == actuator_id)
        if query:
            like_query = f"%{query.strip()}%"
            conditions.append(
                or_(
                    ReportRecord.title.ilike(like_query),
                    ReportRecord.summary.ilike(like_query),
                    ReportRecord.searchable_text.ilike(like_query),
                    ReportRecord.fault_label.ilike(like_query),
                    ReportRecord.severity_band.ilike(like_query),
                )
            )

        stmt = select(ReportRecord)
        count_stmt = select(func.count(ReportRecord.id))
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        stmt = stmt.order_by(ReportRecord.generated_at.desc()).offset(offset).limit(limit)
        items = list(db.scalars(stmt).all())
        total = int(db.scalar(count_stmt) or 0)
        return ReportHistoryResponse(
            items=[ReportRecordRead.model_validate(item) for item in items],
            total=total,
            query=query,
        )

    def get_record(self, db: Session, *, record_id: str) -> ReportRecordRead:
        record = db.get(ReportRecord, record_id)
        if record is None:
            raise ReportingError("Report record not found")
        return ReportRecordRead.model_validate(record)

    def render_html(self, report: AuditReportResponse) -> str:
        payload_json = html.escape(report.model_dump_json(indent=2))
        evidence_rows = "".join(
            f"""
            <tr>
              <td>{html.escape(item.signal)}</td>
              <td>{item.score:.1f}</td>
              <td>{self._fmt(item.observed)}</td>
              <td>{self._fmt(item.expected)}</td>
              <td>{html.escape(item.message)}</td>
            </tr>
            """
            for item in report.evidence_signals
        ) or "<tr><td colspan='5'>No detailed evidence signals were recorded.</td></tr>"

        timeline_rows = "".join(
            f"""
            <tr>
              <td>{html.escape(point.timestamp.isoformat())}</td>
              <td>{self._fmt(point.position_error)}</td>
              <td>{self._fmt(point.velocity_error)}</td>
              <td>{self._fmt(point.motor_current)}</td>
              <td>{self._fmt(point.temperature)}</td>
              <td>{self._fmt(point.latency_ms)}</td>
            </tr>
            """
            for point in report.drift_timeline[:250]
        ) or "<tr><td colspan='6'>No telemetry timeline samples were available.</td></tr>"

        severity = report.severity_and_confidence
        actuator = report.actuator_information
        session = report.telemetry_session_summary
        fault = report.detected_fault

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(report.title)}</title>
  <style>
    :root {{ font-family: Inter, Segoe UI, Arial, sans-serif; color: #172033; background: #f5f7fb; }}
    body {{ margin: 0; padding: 32px; }}
    .report {{ max-width: 1100px; margin: 0 auto; background: white; border-radius: 24px; padding: 36px; box-shadow: 0 24px 80px rgba(20,30,50,.12); }}
    h1 {{ margin: 0; font-size: 34px; }}
    h2 {{ margin-top: 34px; border-bottom: 1px solid #e7ebf3; padding-bottom: 10px; }}
    .muted {{ color: #68738a; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 22px; }}
    .card {{ border: 1px solid #e6ebf4; border-radius: 18px; padding: 18px; background: #fbfcff; }}
    .label {{ color: #68738a; font-size: 12px; text-transform: uppercase; letter-spacing: .12em; }}
    .value {{ font-size: 26px; font-weight: 800; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border-bottom: 1px solid #e7ebf3; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f7f9fe; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: #5b667c; }}
    pre {{ white-space: pre-wrap; background: #0c1220; color: #dce7ff; padding: 18px; border-radius: 18px; overflow: auto; }}
    .badge {{ display: inline-block; padding: 8px 12px; border-radius: 999px; background: #edf2ff; font-weight: 800; }}
    @media print {{ body {{ background: white; padding: 0; }} .report {{ box-shadow: none; border-radius: 0; }} }}
  </style>
</head>
<body>
  <article class="report">
    <p class="label">RASentinel Audit Report</p>
    <h1>{html.escape(report.title)}</h1>
    <p class="muted">Generated {html.escape(report.generated_at.isoformat())} · Engine {REPORT_ENGINE_VERSION}</p>

    <section class="grid">
      <div class="card"><div class="label">Fault</div><div class="value">{html.escape(str(fault.get('fault_label')))}</div></div>
      <div class="card"><div class="label">Severity</div><div class="value">{self._fmt(severity.get('severity_score'))}/100</div><span class="badge">{html.escape(str(severity.get('severity_band')))}</span></div>
      <div class="card"><div class="label">Confidence</div><div class="value">{self._fmt(severity.get('confidence_score'))}</div></div>
    </section>

    <h2>Actuator Information</h2>
    <table>
      <tr><th>Name</th><td>{html.escape(str(actuator.get('name')))}</td></tr>
      <tr><th>Type</th><td>{html.escape(str(actuator.get('actuator_type')))}</td></tr>
      <tr><th>Location</th><td>{html.escape(str(actuator.get('location') or 'N/A'))}</td></tr>
      <tr><th>Manufacturer</th><td>{html.escape(str(actuator.get('manufacturer') or 'N/A'))}</td></tr>
      <tr><th>Model</th><td>{html.escape(str(actuator.get('model_number') or 'N/A'))}</td></tr>
    </table>

    <h2>Telemetry Session Summary</h2>
    <table>
      <tr><th>Session</th><td>{html.escape(str(session.get('name')))}</td></tr>
      <tr><th>Source</th><td>{html.escape(str(session.get('source')))}</td></tr>
      <tr><th>Samples</th><td>{html.escape(str(session.get('sample_count')))}</td></tr>
      <tr><th>Started</th><td>{html.escape(str(session.get('started_at')))}</td></tr>
    </table>

    <h2>Detected Fault</h2>
    <p>{html.escape(str(fault.get('summary')))}</p>

    <h2>Evidence Signals</h2>
    <table>
      <thead><tr><th>Signal</th><th>Score</th><th>Observed</th><th>Expected</th><th>Explanation</th></tr></thead>
      <tbody>{evidence_rows}</tbody>
    </table>

    <h2>Drift Timeline</h2>
    <table>
      <thead><tr><th>Timestamp</th><th>Position Error</th><th>Velocity Error</th><th>Current</th><th>Temperature</th><th>Latency</th></tr></thead>
      <tbody>{timeline_rows}</tbody>
    </table>

    <h2>Recommended Action</h2>
    <p>{html.escape(report.recommended_action)}</p>

    <h2>Technical Notes</h2>
    <ul>{''.join(f'<li>{html.escape(note)}</li>' for note in report.technical_notes)}</ul>

    <h2>Machine-Readable Payload</h2>
    <pre>{payload_json}</pre>
  </article>
</body>
</html>"""

    def _build_base_report(self, db: Session, *, diagnosis_id: str) -> DiagnosticReportResponse:
        try:
            return self.diagnostics_engine.build_report(db, diagnosis_id=diagnosis_id)
        except DiagnosticsError as exc:
            raise ReportingError(str(exc)) from exc

    def _extract_evidence(self, report: DiagnosticReportResponse) -> list[EvidenceSignal]:
        classification = report.classification or {}
        raw_items = classification.get("evidence", []) if isinstance(classification, dict) else []
        items: list[EvidenceSignal] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                items.append(EvidenceSignal.model_validate(raw))
            except Exception:
                items.append(
                    EvidenceSignal(
                        signal=str(raw.get("signal", "unknown")),
                        score=float(raw.get("score", 0.0) or 0.0),
                        observed=self._float_or_none(raw.get("observed")),
                        expected=self._float_or_none(raw.get("expected")),
                        message=str(raw.get("message", "Evidence item could not be fully normalized.")),
                        recommendation=raw.get("recommendation"),
                    )
                )
        return items[:40]

    def _build_drift_timeline(self, db: Session, *, session_id: str) -> list[DriftTimelinePoint]:
        stmt = (
            select(TelemetrySample)
            .where(TelemetrySample.session_id == session_id)
            .order_by(TelemetrySample.timestamp.asc(), TelemetrySample.id.asc())
        )
        samples = list(db.scalars(stmt).all())
        if not samples:
            return []

        stride = max(1, len(samples) // 500)
        timeline = []
        for sample in samples[::stride]:
            timeline.append(
                DriftTimelinePoint(
                    timestamp=sample.timestamp,
                    position_error=sample.error_position,
                    velocity_error=sample.error_velocity,
                    motor_current=sample.motor_current,
                    temperature=sample.temperature,
                    latency_ms=sample.control_latency_ms,
                    fault_label=sample.fault_label.value if hasattr(sample.fault_label, "value") else sample.fault_label,
                )
            )
        return timeline

    def _diagnosis_history_count(self, db: Session, *, actuator_id: str) -> int:
        return int(db.scalar(select(func.count(DiagnosisResult.id)).where(DiagnosisResult.actuator_id == actuator_id)) or 0)

    def _technical_notes(self, report: DiagnosticReportResponse) -> list[str]:
        audit = report.audit or {}
        session = report.session or {}
        features = report.features or {}
        notes = [
            f"Report engine version: {REPORT_ENGINE_VERSION}.",
            f"Diagnostics engine version: {audit.get('engine_version', 'unknown')}.",
            f"Classifier version: {audit.get('classifier_version', 'unknown')}.",
            f"Signal processing version: {audit.get('signal_processing_version', 'unknown')}.",
            f"Telemetry sample count: {session.get('sample_count', 'unknown')}.",
        ]
        if features.get("algorithm_version"):
            notes.append(f"Feature extraction algorithm: {features.get('algorithm_version')}.")
        if report.baseline:
            notes.append(f"Baseline used: {report.baseline.get('name')} ({report.baseline.get('id')}).")
        else:
            notes.append("No healthy baseline was attached to this diagnosis; classification evidence is feature-based.")
        return notes

    def _searchable_text(self, report: AuditReportResponse) -> str:
        parts = [
            report.title,
            json.dumps(report.actuator_information, default=str),
            json.dumps(report.telemetry_session_summary, default=str),
            json.dumps(report.detected_fault, default=str),
            report.recommended_action,
            " ".join(item.message for item in report.evidence_signals),
            " ".join(report.technical_notes),
        ]
        return "\n".join(parts)[:20000]

    def _reports_dir(self) -> Path:
        settings = get_settings()
        path = settings.data_dir / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _fmt(self, value: Any) -> str:
        number = self._float_or_none(value)
        if number is None:
            return "N/A"
        return f"{number:.4g}"

    def _float_or_none(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
