import { type FormEvent, useEffect, useMemo, useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { TelemetryMultiChart } from "../components/TelemetryMultiChart";
import { api } from "../services/api";
import type { Actuator, LiveControllerTransport, LiveSessionRead, TelemetrySample } from "../types/domain";
import { formatDateTime, formatInteger, formatNumber, sentenceLabel } from "../utils/format";

const transports: LiveControllerTransport[] = ["http_bridge", "serial", "ros2", "can", "modbus", "opc_ua", "plc", "custom"];

export function LiveTelemetryPage() {
  const [actuators, setActuators] = useState<Actuator[]>([]);
  const [liveSessions, setLiveSessions] = useState<LiveSessionRead[]>([]);
  const [selectedLiveId, setSelectedLiveId] = useState("");
  const [recentSamples, setRecentSamples] = useState<TelemetrySample[]>([]);
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [pollingEnabled, setPollingEnabled] = useState(true);

  const [form, setForm] = useState({
    actuatorId: "",
    sessionName: "Real actuator live run",
    controllerName: "Serial actuator controller",
    controllerType: "embedded_controller",
    transport: "serial" as LiveControllerTransport,
    endpoint: "COM5",
    sampleRateHz: 50,
    minDiagnosisSamples: 250,
    autoDiagnoseEvery: 0
  });

  const selectedLiveSession = useMemo(
    () => liveSessions.find((session) => session.id === selectedLiveId) ?? null,
    [liveSessions, selectedLiveId]
  );

  async function loadActuators() {
    const payload = await api.listActuators();
    setActuators(payload);
    setForm((current) => ({ ...current, actuatorId: current.actuatorId || payload[0]?.id || "" }));
  }

  async function loadLiveSessions(preferredId?: string) {
    const payload = await api.listLiveSessions({ limit: 100 });
    setLiveSessions(payload.items);
    if (preferredId) {
      setSelectedLiveId(preferredId);
    } else if (!selectedLiveId && payload.items.length > 0) {
      setSelectedLiveId(payload.items[0].id);
    }
  }

  async function loadRecentSamples(liveSessionId: string) {
    if (!liveSessionId) {
      setRecentSamples([]);
      return;
    }
    const payload = await api.getRecentLiveTelemetry(liveSessionId, 500);
    setRecentSamples(payload.samples);
  }

  async function refreshSelected() {
    if (!selectedLiveId) return;
    const session = await api.getLiveSession(selectedLiveId);
    setLiveSessions((current) => {
      const exists = current.some((item) => item.id === session.id);
      return exists
        ? current.map((item) => (item.id === session.id ? session : item))
        : [session, ...current];
    });
    await loadRecentSamples(selectedLiveId);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsBusy(true);

    try {
      const liveSession = await api.startLiveSession({
        actuator_id: form.actuatorId,
        session_name: form.sessionName,
        duplicate_strategy: "create_new",
        controller_name: form.controllerName,
        controller_type: form.controllerType,
        transport: form.transport,
        endpoint: form.endpoint || null,
        sample_rate_hint_hz: form.sampleRateHz,
        min_diagnosis_samples: form.minDiagnosisSamples,
        auto_extract_features: true,
        auto_diagnose_every_n_samples: form.autoDiagnoseEvery > 0 ? form.autoDiagnoseEvery : null,
        tags: { created_from: "live_telemetry_page" },
        connection_metadata: {
          endpoint: form.endpoint,
          bridge: "external controller bridge"
        }
      });
      await loadLiveSessions(liveSession.id);
      await loadRecentSamples(liveSession.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start live telemetry session.");
    } finally {
      setIsBusy(false);
    }
  }

  async function stopSelected() {
    if (!selectedLiveId) return;
    setError("");
    try {
      const stopped = await api.stopLiveSession(selectedLiveId);
      setLiveSessions((current) => current.map((item) => (item.id === stopped.id ? stopped : item)));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not stop live telemetry session.");
    }
  }

  async function runDiagnosis() {
    if (!selectedLiveId) return;
    setError("");
    try {
      await api.runLiveDiagnosis(selectedLiveId);
      await refreshSelected();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not run live diagnosis.");
    }
  }

  useEffect(() => {
    void Promise.all([loadActuators(), loadLiveSessions()]);
  }, []);

  useEffect(() => {
    void loadRecentSamples(selectedLiveId);
  }, [selectedLiveId]);

  useEffect(() => {
    if (!pollingEnabled || !selectedLiveId) return;
    const timer = window.setInterval(() => {
      void refreshSelected();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [pollingEnabled, selectedLiveId]);

  const latest = selectedLiveSession?.latest_metrics ?? {};

  return (
    <main className="page-stack live-page">
      <PageHeader
        eyebrow="Live telemetry"
        title="Controller telemetry workspace"
        description="Monitor read-only actuator telemetry streams, review incoming samples, and run diagnostics on live capture sessions."
        actions={
          <button className="secondary-button" onClick={() => setPollingEnabled((current) => !current)}>
            {pollingEnabled ? "Pause refresh" : "Resume refresh"}
          </button>
        }
      />

      {error ? <div className="error-panel">{error}</div> : null}

      <section className="split-layout">
        <form className="panel form-stack" onSubmit={submit}>
          <div className="panel-title-row">
            <div>
              <h2>Start live capture</h2>
              <p>Create a capture session for telemetry from a controller, hardware adapter, or test stream.</p>
            </div>
          </div>

          <label className="form-field">
            Actuator
            <select value={form.actuatorId} onChange={(event) => setForm({ ...form, actuatorId: event.target.value })} required>
              <option value="">Select actuator</option>
              {actuators.map((actuator) => (
                <option key={actuator.id} value={actuator.id}>{actuator.name}</option>
              ))}
            </select>
          </label>

          <label className="form-field">
            Session name
            <input value={form.sessionName} onChange={(event) => setForm({ ...form, sessionName: event.target.value })} required />
          </label>

          <label className="form-field">
            Controller name
            <input value={form.controllerName} onChange={(event) => setForm({ ...form, controllerName: event.target.value })} required />
          </label>

          <div className="form-grid">
            <label className="form-field">
Controller profile
              <input value={form.controllerType} onChange={(event) => setForm({ ...form, controllerType: event.target.value })} />
            </label>

            <label className="form-field">
              Transport
              <select value={form.transport} onChange={(event) => setForm({ ...form, transport: event.target.value as LiveControllerTransport })}>
                {transports.map((transport) => (
                  <option key={transport} value={transport}>{sentenceLabel(transport)}</option>
                ))}
              </select>
            </label>

            <label className="form-field">
              Connection endpoint
              <input value={form.endpoint} onChange={(event) => setForm({ ...form, endpoint: event.target.value })} placeholder="Controller port, topic, or source name" />
            </label>

            <label className="form-field">
Expected sample rate
              <input type="number" value={form.sampleRateHz} min={0.1} step={0.1} onChange={(event) => setForm({ ...form, sampleRateHz: Number(event.target.value) })} />
            </label>

            <label className="form-field">
Minimum analysis samples
              <input type="number" value={form.minDiagnosisSamples} min={25} onChange={(event) => setForm({ ...form, minDiagnosisSamples: Number(event.target.value) })} />
            </label>

            <label className="form-field">
Automatic diagnosis interval
              <input type="number" value={form.autoDiagnoseEvery} min={0} onChange={(event) => setForm({ ...form, autoDiagnoseEvery: Number(event.target.value) })} />
              <span className="field-help">Use 0 to run diagnostics manually.</span>
            </label>
          </div>

          <button type="submit" disabled={isBusy || !form.actuatorId}>Start live session</button>
        </form>

        <section className="panel panel--wide">
          <div className="panel-title-row">
            <div>
              <h2>Capture sessions</h2>
              <p>Select a session to review incoming telemetry and diagnostic status.</p>
            </div>
            <span>{liveSessions.length}</span>
          </div>

          {liveSessions.length === 0 ? (
            <EmptyState title="No live sessions" message="Start a capture session to receive samples from a controller, integration adapter, or validation stream." />
          ) : (
            <div className="list-stack live-session-list">
              {liveSessions.map((session) => (
                <button
                  key={session.id}
                  className={session.id === selectedLiveId ? "entity-row entity-row--active" : "entity-row"}
                  onClick={() => setSelectedLiveId(session.id)}
                  type="button"
                >
                  <strong>{session.controller_name}</strong>
                  <small>{sentenceLabel(String(session.transport))} · {formatInteger(session.sample_count)} samples · {sentenceLabel(String(session.status))}</small>
                </button>
              ))}
            </div>
          )}
        </section>
      </section>

      <section className="live-kpi-grid">
        <div className="kpi-card panel">
          <span>Samples received</span>
          <strong>{formatInteger(selectedLiveSession?.sample_count ?? 0)}</strong>
          <small>{selectedLiveSession ? `${formatInteger(selectedLiveSession.batch_count)} batches` : "No session selected"}</small>
        </div>
        <div className="kpi-card panel">
          <span>Position error</span>
          <strong>{formatNumber(typeof latest.position_error === "number" ? latest.position_error : null, 3)}</strong>
          <small>Latest command tracking error</small>
        </div>
        <div className="kpi-card panel">
          <span>Motor current</span>
          <strong>{formatNumber(typeof latest.motor_current === "number" ? latest.motor_current : null, 2)} A</strong>
          <small>Latest controller reading</small>
        </div>
        <div className="kpi-card panel">
          <span>Temperature</span>
          <strong>{formatNumber(typeof latest.temperature === "number" ? latest.temperature : null, 1)} °C</strong>
          <small>Latest temperature reading</small>
        </div>
      </section>

      <section className="live-monitor-grid">
        <div className="panel form-stack live-control-panel">
          <div className="panel-title-row">
            <div>
              <h2>Session controls</h2>
              <p>Manage the selected capture session and run diagnostics when enough telemetry has arrived.</p>
            </div>
          </div>

          <div className="connection-summary-grid">
            <div className="connection-summary-item">
              <span>Status</span>
              <strong>{selectedLiveSession ? sentenceLabel(String(selectedLiveSession.status)) : "No session selected"}</strong>
            </div>
            <div className="connection-summary-item">
              <span>Transport</span>
              <strong>{selectedLiveSession ? sentenceLabel(String(selectedLiveSession.transport)) : "Not connected"}</strong>
            </div>
            <div className="connection-summary-item">
              <span>Endpoint</span>
              <strong>{selectedLiveSession?.endpoint || "Not provided"}</strong>
            </div>
            <div className="connection-summary-item">
              <span>Last sample</span>
              <strong>{formatDateTime(selectedLiveSession?.last_seen_at)}</strong>
            </div>
          </div>

          <div className="form-grid live-action-grid">
            <button type="button" className="secondary-button" onClick={() => void refreshSelected()} disabled={!selectedLiveId}>Refresh now</button>
            <button type="button" className="secondary-button" onClick={() => void runDiagnosis()} disabled={!selectedLiveId}>Run diagnosis</button>
            <button type="button" className="secondary-button" onClick={() => void stopSelected()} disabled={!selectedLiveId || selectedLiveSession?.status === "stopped"}>Stop session</button>
          </div>

          {selectedLiveSession?.last_error ? (
            <div className="error-panel compact-error">{selectedLiveSession.last_error}</div>
          ) : null}
        </div>

        <div className="panel panel--wide live-chart-panel">
          <div className="panel-title-row">
            <div>
              <h2>Live telemetry window</h2>
              <p>Recent samples are plotted as a rolling diagnostic view for the selected capture session.</p>
            </div>
            <span>{formatInteger(recentSamples.length)}</span>
          </div>
          <TelemetryMultiChart samples={recentSamples} compact />
        </div>
      </section>
    </main>
  );
}
