import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { ReportViewer } from "../components/ReportViewer";
import { SeverityBadge } from "../components/SeverityBadge";
import { api } from "../services/api";
import type { Actuator, AuditReportResponse, DiagnosisResult, ReportRecordRead, SessionRun } from "../types/domain";
import { formatDateTime, formatNumber, labelize } from "../utils/format";

export function ReportsPage() {
  const [actuators, setActuators] = useState<Actuator[]>([]);
  const [sessions, setSessions] = useState<SessionRun[]>([]);
  const [diagnoses, setDiagnoses] = useState<DiagnosisResult[]>([]);
  const [history, setHistory] = useState<ReportRecordRead[]>([]);
  const [actuatorId, setActuatorId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [diagnosisId, setDiagnosisId] = useState("");
  const [query, setQuery] = useState("");
  const [report, setReport] = useState<AuditReportResponse | null>(null);
  const [error, setError] = useState("");

  const htmlUrl = useMemo(() => diagnosisId ? api.getReportHtmlUrl(diagnosisId) : null, [diagnosisId]);

  async function loadHistory() {
    const payload = await api.listReportHistory({ actuatorId: actuatorId || undefined, query: query || undefined, limit: 80 });
    setHistory(payload.items);
  }

  useEffect(() => {
    void api.listActuators().then((payload) => {
      setActuators(payload);
      setActuatorId(payload[0]?.id ?? "");
    });
  }, []);

  useEffect(() => {
    if (!actuatorId) return;
    void Promise.all([api.listSessions(actuatorId), api.listReportHistory({ actuatorId, limit: 80 })]).then(([sessionPayload, historyPayload]) => {
      setSessions(sessionPayload);
      setHistory(historyPayload.items);
      setSessionId(sessionPayload[0]?.id ?? "");
    });
  }, [actuatorId]);

  useEffect(() => {
    if (!sessionId) {
      setDiagnoses([]);
      setDiagnosisId("");
      return;
    }
    void api.listDiagnoses(sessionId).then((payload) => {
      setDiagnoses(payload);
      setDiagnosisId(payload[0]?.id ?? "");
    });
  }, [sessionId]);

  async function previewReport() {
    if (!diagnosisId) return;
    setError("");
    try {
      setReport(await api.getAuditReport(diagnosisId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load report preview.");
    }
  }

  async function generateReport() {
    if (!diagnosisId) return;
    setError("");
    try {
      const payload = await api.generateAuditReport(diagnosisId);
      setReport(payload.audit_report);
      await loadHistory();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to generate report.");
    }
  }

  return (
    <main className="page-stack">
      <PageHeader
        eyebrow="Reports"
        title="Reports and audit history"
        description="Generate, preview, and search local diagnostic reports with actuator metadata, evidence, and maintenance recommendations."
        actions={<button onClick={generateReport} disabled={!diagnosisId}>Generate report</button>}
      />
      {error ? <div className="error-panel">{error}</div> : null}

      <section className="control-strip">
        <label className="form-field">Actuator<select value={actuatorId} onChange={(e) => setActuatorId(e.target.value)}>{actuators.map((actuator) => <option key={actuator.id} value={actuator.id}>{actuator.name}</option>)}</select></label>
        <label className="form-field">Session<select value={sessionId} onChange={(e) => setSessionId(e.target.value)}><option value="">No session</option>{sessions.map((session) => <option key={session.id} value={session.id}>{session.name}</option>)}</select></label>
        <label className="form-field">Diagnosis<select value={diagnosisId} onChange={(e) => setDiagnosisId(e.target.value)}><option value="">No diagnosis</option>{diagnoses.map((diagnosis) => <option key={diagnosis.id} value={diagnosis.id}>{labelize(diagnosis.fault_label)} · {formatNumber(diagnosis.severity_score, 1)}</option>)}</select></label>
        <button className="secondary-button" onClick={previewReport} disabled={!diagnosisId}>Preview</button>
      </section>

      <section className="reports-workspace-grid">
        <div className="panel reports-history-panel">
          <div className="panel-title-row">
            <div>
              <h2>Report history</h2>
              <p className="muted">Find saved reports for the selected actuator.</p>
            </div>
            <span>{history.length}</span>
          </div>
          <label className="form-field">Search<input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void loadHistory(); }} placeholder="Fault, severity, or report title" /></label>
          <button className="secondary-button full-width" onClick={() => void loadHistory()}>Search reports</button>
          <div className="list-stack report-history-list">
            {history.map((item) => (
              <button key={item.id} className="entity-row" onClick={() => { setDiagnosisId(item.diagnosis_id); void api.getAuditReport(item.diagnosis_id).then(setReport); }}>
                <strong>{item.title}</strong>
                <small>{formatDateTime(item.generated_at)}</small>
                <SeverityBadge band={item.severity_band} />
              </button>
            ))}
          </div>
        </div>

        <div className="panel panel--wide reports-preview-panel">
          <ReportViewer report={report} htmlUrl={htmlUrl} />
        </div>
      </section>
    </main>
  );
}
