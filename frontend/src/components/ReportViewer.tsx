import type { AuditReportResponse } from "../types/domain";
import { formatDateTime, formatNumber, labelize } from "../utils/format";
import { EvidencePanel } from "./EvidencePanel";
import { MaintenanceRecommendation } from "./MaintenanceRecommendation";
import { SeverityBadge } from "./SeverityBadge";
import { TelemetryMultiChart } from "./TelemetryMultiChart";

interface ReportViewerProps {
  report: AuditReportResponse | null;
  htmlUrl?: string | null;
}

export function ReportViewer({ report, htmlUrl }: ReportViewerProps) {
  if (!report) {
    return (
      <section className="panel panel--soft report-empty">
        <h2>No report selected</h2>
        <p className="muted">Preview an existing diagnosis or generate a new audit report to review details here.</p>
      </section>
    );
  }

  const severityScore = Number(report.severity_and_confidence.severity_score ?? 0);
  const severityBand = String(report.severity_and_confidence.severity_band ?? "unknown");
  const confidenceScore = Number(report.severity_and_confidence.confidence_score ?? 0);

  return (
    <section className="report-viewer">
      <div className="report-hero-card">
        <div>
          <p className="eyebrow">Audit report</p>
          <h2>{report.title}</h2>
          <p className="muted">Generated {formatDateTime(report.generated_at)}</p>
        </div>
        <SeverityBadge band={severityBand} score={severityScore} />
      </div>

      <div className="report-meta-grid">
        <Meta label="Actuator" value={String(report.actuator_information.name ?? "Not available")} />
        <Meta label="Fault" value={labelize(String(report.detected_fault.fault_label ?? "unknown"))} />
        <Meta label="Confidence" value={formatNumber(confidenceScore * 100, 1) + "%"} />
        <Meta label="Diagnosis history" value={`${report.diagnosis_history_count} record(s)`} />
      </div>

      <MaintenanceRecommendation recommendation={report.recommended_action} />

      <section className="panel">
        <div className="panel-title-row">
          <div>
            <h2>Evidence signals</h2>
            <p className="muted">Primary signals supporting the diagnosis.</p>
          </div>
          {htmlUrl ? (
            <a className="ghost-link" href={htmlUrl} target="_blank" rel="noreferrer">
              Open HTML export
            </a>
          ) : null}
        </div>
        <EvidencePanel evidence={report.evidence_signals} />
      </section>

      <section className="panel">
        <div className="panel-title-row">
          <div>
            <h2>Drift timeline</h2>
            <p className="muted">Time-series evidence captured for the report.</p>
          </div>
        </div>
        <TelemetryMultiChart timeline={report.drift_timeline} compact />
      </section>

      <section className="panel">
        <h2>Technical notes</h2>
        <ul className="note-list">
          {report.technical_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </section>
    </section>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="meta-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
