import { useEffect, useState } from "react";

import { EvidencePanel } from "../components/EvidencePanel";
import { MaintenanceRecommendation } from "../components/MaintenanceRecommendation";
import { PageHeader } from "../components/PageHeader";
import { SeverityBadge } from "../components/SeverityBadge";
import { TelemetryMultiChart } from "../components/TelemetryMultiChart";
import { api } from "../services/api";
import type { Actuator, BaselineRead, DiagnosisRunResponse, SessionRun, TelemetrySample } from "../types/domain";
import { formatInteger, labelize } from "../utils/format";

export function DiagnosticsPage() {
  const [actuators, setActuators] = useState<Actuator[]>([]);
  const [sessions, setSessions] = useState<SessionRun[]>([]);
  const [baselines, setBaselines] = useState<BaselineRead[]>([]);
  const [samples, setSamples] = useState<TelemetrySample[]>([]);
  const [actuatorId, setActuatorId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [result, setResult] = useState<DiagnosisRunResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void api.listActuators().then((payload) => {
      setActuators(payload);
      setActuatorId(payload[0]?.id ?? "");
    });
  }, []);

  useEffect(() => {
    if (!actuatorId) return;
    void Promise.all([api.listSessions(actuatorId), api.listBaselines(actuatorId)]).then(([sessionPayload, baselinePayload]) => {
      setSessions(sessionPayload);
      setBaselines(baselinePayload);
      setSessionId(sessionPayload[0]?.id ?? "");
      setBaselineId(baselinePayload.find((item) => item.is_active)?.id ?? "");
    });
  }, [actuatorId]);

  useEffect(() => {
    if (!sessionId) {
      setSamples([]);
      return;
    }
    void api.listTelemetry(sessionId).then(setSamples);
  }, [sessionId]);

  async function runDiagnosis() {
    if (!sessionId) return;
    setError("");
    try {
      const payload = await api.runDiagnosis(sessionId, baselineId || undefined);
      setResult(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Diagnosis failed.");
    }
  }

  async function createBaseline() {
    if (!actuatorId || !sessionId) return;
    setError("");
    try {
      const baseline = await api.createBaseline({ actuatorId, sessionId, name: `Healthy baseline ${new Date().toLocaleString()}` });
      setBaselines((current) => [baseline, ...current]);
      setBaselineId(baseline.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Baseline creation failed.");
    }
  }

  const classification = result?.classification;

  return (
    <main className="page-stack">
      <PageHeader
        eyebrow="Diagnostics"
        title="Fault classification workspace"
        description="Run diagnostics, compare against a healthy baseline, and review the signals behind each fault classification."
        actions={<button onClick={runDiagnosis} disabled={!sessionId}>Run diagnosis</button>}
      />
      {error ? <div className="error-panel">{error}</div> : null}

      <section className="control-strip">
        <label className="form-field">Actuator<select value={actuatorId} onChange={(e) => setActuatorId(e.target.value)}>{actuators.map((actuator) => <option key={actuator.id} value={actuator.id}>{actuator.name}</option>)}</select></label>
        <label className="form-field">Session<select value={sessionId} onChange={(e) => setSessionId(e.target.value)}><option value="">No session</option>{sessions.map((session) => <option key={session.id} value={session.id}>{session.name} · {formatInteger(session.sample_count)}</option>)}</select></label>
        <label className="form-field">Baseline<select value={baselineId} onChange={(e) => setBaselineId(e.target.value)}><option value="">No baseline selected</option>{baselines.map((baseline) => <option key={baseline.id} value={baseline.id}>{baseline.name}</option>)}</select></label>
        <button className="secondary-button" onClick={createBaseline} disabled={!sessionId}>Create baseline</button>
      </section>

      {classification ? (
        <section className="diagnosis-hero panel">
          <div>
            <p className="eyebrow">Detected fault</p>
            <h2>{labelize(classification.fault_label)}</h2>
            <p>{classification.summary}</p>
          </div>
          <SeverityBadge band={classification.severity_band} score={classification.severity_score} />
        </section>
      ) : null}

      <section className="diagnostics-workspace-grid">
        <div className="panel panel--wide telemetry-evidence-panel">
          <div className="panel-title-row">
            <div>
              <h2>Telemetry evidence</h2>
              <p className="muted">Command tracking, error, current, temperature, and latency trends used for diagnostics.</p>
            </div>
          </div>
          <TelemetryMultiChart samples={samples} compact />
        </div>
        <div className="panel fault-evidence-panel">
          <div className="panel-title-row"><h2>Fault evidence</h2></div>
          <EvidencePanel evidence={classification?.evidence ?? []} />
        </div>
      </section>

      <MaintenanceRecommendation recommendation={classification?.recommendation ?? result?.diagnosis?.recommendation} />
    </main>
  );
}
