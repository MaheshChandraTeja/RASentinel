import { useEffect, useMemo, useState } from "react";

import { api } from "../services/api";
import type {
  ActuatorHealthTimelineResponse,
  BaselineRead,
  DiagnosisRunResponse,
  DiagnosticReportResponse
} from "../types/domain";

interface DiagnosticsPanelProps {
  actuatorId: string;
  sessionId: string;
  onDiagnosisComplete: () => Promise<void> | void;
}

export function DiagnosticsPanel({ actuatorId, sessionId, onDiagnosisComplete }: DiagnosticsPanelProps) {
  const [baselines, setBaselines] = useState<BaselineRead[]>([]);
  const [selectedBaselineId, setSelectedBaselineId] = useState<string>("");
  const [diagnosis, setDiagnosis] = useState<DiagnosisRunResponse | null>(null);
  const [timeline, setTimeline] = useState<ActuatorHealthTimelineResponse | null>(null);
  const [report, setReport] = useState<DiagnosticReportResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const reportMarkdownUrl = useMemo(() => {
    if (!diagnosis?.diagnosis_id) return "";
    return `http://127.0.0.1:8000/api/v1/reports/${diagnosis.diagnosis_id}/markdown`;
  }, [diagnosis?.diagnosis_id]);

  async function loadBaselines() {
    if (!actuatorId) {
      setBaselines([]);
      setSelectedBaselineId("");
      return;
    }

    const payload = await api.listBaselines(actuatorId);
    setBaselines(payload);
    const active = payload.find((item) => item.is_active) ?? payload[0];
    setSelectedBaselineId(active?.id ?? "");
  }

  async function loadTimeline() {
    if (!actuatorId) {
      setTimeline(null);
      return;
    }
    setTimeline(await api.getActuatorHealthTimeline(actuatorId));
  }

  async function runDiagnosis() {
    if (!sessionId) return;

    setBusy(true);
    setError("");
    setReport(null);

    try {
      const payload = await api.runDiagnosis(sessionId, selectedBaselineId || undefined);
      setDiagnosis(payload);

      if (payload.diagnosis_id) {
        setReport(await api.getDiagnosticReport(payload.diagnosis_id));
      }

      await loadTimeline();
      await onDiagnosisComplete();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Diagnosis failed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadBaselines();
    void loadTimeline();
  }, [actuatorId]);

  return (
    <section className="module-panel diagnostics-panel">
      <div className="module-panel-header">
        <div>
          <p className="eyebrow compact">Module 6 + 7</p>
          <h2>Fault classification & diagnostics API</h2>
          <p>
            Classifies likely actuator faults using extracted features, anomaly scoring, baseline drift evidence, confidence, and maintenance guidance.
          </p>
        </div>

        <button onClick={runDiagnosis} disabled={!sessionId || busy}>
          {busy ? "Running diagnosis..." : "Run diagnosis"}
        </button>
      </div>

      {error ? <div className="error-panel">{error}</div> : null}

      <div className="diagnostics-grid">
        <div className="mini-panel">
          <label>
            Healthy baseline
            <select value={selectedBaselineId} onChange={(event) => setSelectedBaselineId(event.target.value)}>
              <option value="">No baseline, classifier-only</option>
              {baselines.map((baseline) => (
                <option key={baseline.id} value={baseline.id}>
                  {baseline.name} · quality {baseline.baseline_quality_score.toFixed(1)}
                </option>
              ))}
            </select>
          </label>

          <div className="help-text">
            Baseline improves drift evidence. Without it, RASentinel still classifies from raw extracted features,
            and can also run with extracted feature evidence when a baseline is not available.
          </div>
        </div>

        <div className="mini-panel">
          <h3>Latest classification</h3>
          {diagnosis ? (
            <div className="diagnosis-summary">
              <strong>{diagnosis.classification.fault_label.replaceAll("_", " ")}</strong>
              <span>Severity {diagnosis.classification.severity_score.toFixed(1)} / 100</span>
              <span>Confidence {(diagnosis.classification.confidence_score * 100).toFixed(1)}%</span>
              <span>Model {diagnosis.classification.model_used}</span>
            </div>
          ) : (
            <p className="muted">No diagnosis has been run yet.</p>
          )}
        </div>
      </div>

      {diagnosis ? (
        <div className="diagnostics-result">
          <div>
            <h3>Fault explanation</h3>
            <p>{diagnosis.classification.summary}</p>
            <p className="recommendation">{diagnosis.classification.recommendation}</p>
          </div>

          <div className="evidence-list">
            {diagnosis.classification.evidence.slice(0, 6).map((item) => (
              <div className="evidence-card" key={`${item.signal}-${item.score}`}>
                <strong>{item.signal.replaceAll("_", " ")}</strong>
                <span>score {item.score.toFixed(1)}</span>
                <p>{item.message}</p>
              </div>
            ))}
          </div>

          {diagnosis.diagnosis_id ? (
            <div className="report-actions">
              <a href={`http://127.0.0.1:8000/api/v1/reports/${diagnosis.diagnosis_id}`} target="_blank" rel="noreferrer">
                Open JSON report
              </a>
              <a href={reportMarkdownUrl} target="_blank" rel="noreferrer">
                Download Markdown report
              </a>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="diagnostics-grid">
        <div className="mini-panel">
          <h3>Health timeline</h3>
          {timeline?.points.length ? (
            <div className="timeline-list">
              {timeline.points.slice(-6).reverse().map((point) => (
                <div className="timeline-item" key={`${point.timestamp}-${point.diagnosis_id ?? point.feature_set_id}`}>
                  <strong>{point.severity_band}</strong>
                  <span>{new Date(point.timestamp).toLocaleString()}</span>
                  <p>{point.summary}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No health timeline points are available yet.</p>
          )}
        </div>

        <div className="mini-panel">
          <h3>Report snapshot</h3>
          {report ? (
            <div className="report-snapshot">
              <span>Diagnosis: {report.diagnosis.fault_label}</span>
              <span>Severity: {report.diagnosis.severity_score.toFixed(1)}</span>
              <span>Action: {report.maintenance_action}</span>
            </div>
          ) : (
            <p className="muted">Run a diagnosis to generate a report snapshot.</p>
          )}
        </div>
      </div>
    </section>
  );
}
