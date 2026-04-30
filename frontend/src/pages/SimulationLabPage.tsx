import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { TelemetryMultiChart } from "../components/TelemetryMultiChart";
import { api, defaultSimulationConfig } from "../services/api";
import type { Actuator, DuplicateSessionStrategy, SimulationConfig, SimulationImportResponse, SimulationFaultProfile, TelemetrySample } from "../types/domain";
import { formatInteger, labelize } from "../utils/format";

const faultProfiles: SimulationFaultProfile[] = [
  "healthy",
  "friction_increase",
  "backlash",
  "encoder_noise",
  "motor_weakening",
  "overheating",
  "delayed_response",
  "load_imbalance",
  "oscillation_control_instability",
  "current_spike_anomaly"
];

export function SimulationLabPage() {
  const [actuators, setActuators] = useState<Actuator[]>([]);
  const [actuatorId, setActuatorId] = useState("");
  const [sessionName, setSessionName] = useState("Synthetic actuator run");
  const [duplicateStrategy, setDuplicateStrategy] = useState<DuplicateSessionStrategy>("create_new");
  const [config, setConfig] = useState<SimulationConfig>(defaultSimulationConfig);
  const [result, setResult] = useState<SimulationImportResponse | null>(null);
  const [samples, setSamples] = useState<TelemetrySample[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void api.listActuators().then((payload) => {
      setActuators(payload);
      setActuatorId(payload[0]?.id ?? "");
    });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!actuatorId) return;
    setError("");
    setResult(null);
    setSamples([]);
    try {
      const payload = await api.simulateTelemetryGateway({ actuator_id: actuatorId, session_name: sessionName, duplicate_strategy: duplicateStrategy, config });
      setResult(payload);
      const telemetry = await api.listTelemetry(payload.session_id);
      setSamples(telemetry);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Simulation failed.");
    }
  }

  function updateNumber<K extends keyof SimulationConfig>(key: K, value: number) {
    setConfig((current) => ({ ...current, [key]: value }));
  }

  return (
    <main className="page-stack">
      <PageHeader
        eyebrow="Simulation"
        title="Generate deterministic actuator telemetry"
        description="Create healthy or faulty actuator sessions with reproducible seeds for demos, tests, and diagnostic validation."
      />
      {error ? <div className="error-panel">{error}</div> : null}

      <section className="split-layout">
        <form className="panel form-stack" onSubmit={submit}>
          <div className="panel-title-row">
            <div>
              <h2>Simulation setup</h2>
              <p className="muted">Configure the actuator, fault profile, sample rate, and run duration.</p>
            </div>
          </div>
          <label className="form-field">Actuator<select value={actuatorId} onChange={(e) => setActuatorId(e.target.value)} required>{actuators.map((actuator) => <option key={actuator.id} value={actuator.id}>{actuator.name}</option>)}</select></label>
          <label className="form-field">Session name<input value={sessionName} onChange={(e) => setSessionName(e.target.value)} required /></label>
          <label className="form-field">Fault profile<select value={config.fault_profile} onChange={(e) => setConfig({ ...config, fault_profile: e.target.value as SimulationFaultProfile })}>{faultProfiles.map((profile) => <option key={profile} value={profile}>{labelize(profile)}</option>)}</select></label>
          <label className="form-field">Duplicate handling<select value={duplicateStrategy} onChange={(e) => setDuplicateStrategy(e.target.value as DuplicateSessionStrategy)}><option value="reject">Reject duplicate</option><option value="create_new">Create new session</option><option value="replace">Replace existing session</option></select></label>
          <div className="form-grid">
            <label className="form-field">Seed<input type="number" value={config.seed ?? 0} onChange={(e) => updateNumber("seed", Number(e.target.value))} /></label>
            <label className="form-field">Sample rate Hz<input type="number" value={config.sample_rate_hz} onChange={(e) => updateNumber("sample_rate_hz", Number(e.target.value))} /></label>
            <label className="form-field">Duration seconds<input type="number" value={config.duration_s} onChange={(e) => updateNumber("duration_s", Number(e.target.value))} /></label>
            <label className="form-field">Fault intensity<input type="number" step="0.05" min="0" max="1" value={config.fault_intensity} onChange={(e) => updateNumber("fault_intensity", Number(e.target.value))} /></label>
          </div>
          <button type="submit" disabled={!actuatorId}>Generate and import</button>
        </form>

        <section className="panel panel--wide">
          <div className="panel-title-row">
            <div>
              <h2>Generated telemetry</h2>
              <p className="muted">The generated session is imported immediately and shown below.</p>
            </div>
            {result ? <span>{formatInteger(result.rows_imported)} samples</span> : null}
          </div>
          {result ? <p className="muted">{result.session_name} · {result.source_format.toUpperCase()} · {result.status}</p> : <p className="muted">Run a simulation to preview telemetry charts.</p>}
          <TelemetryMultiChart samples={samples} compact />
        </section>
      </section>
    </main>
  );
}
