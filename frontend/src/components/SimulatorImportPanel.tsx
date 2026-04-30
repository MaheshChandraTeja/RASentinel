import { useEffect, useState } from "react";

import { api, defaultSimulationConfig } from "../services/api";
import type {
  DuplicateSessionStrategy,
  FaultProfileInfo,
  SimulationConfig,
  SimulationFaultProfile,
  SimulationImportResponse
} from "../types/domain";

type NumericSimulationConfigKey =
  | "seed"
  | "sample_rate_hz"
  | "duration_s"
  | "commanded_amplitude"
  | "command_frequency_hz"
  | "nominal_current_a"
  | "nominal_temperature_c"
  | "nominal_load"
  | "response_time_constant_s"
  | "base_latency_ms"
  | "sensor_noise_std"
  | "current_noise_std"
  | "temperature_noise_std"
  | "fault_intensity";

interface SimulatorImportPanelProps {
  actuatorId: string;
  onImported: (sessionId: string) => void;
}

export function SimulatorImportPanel({ actuatorId, onImported }: SimulatorImportPanelProps) {
  const [faultProfiles, setFaultProfiles] = useState<FaultProfileInfo[]>([]);
  const [config, setConfig] = useState<SimulationConfig>(defaultSimulationConfig);
  const [sessionName, setSessionName] = useState("Synthetic actuator telemetry");
  const [duplicateStrategy, setDuplicateStrategy] = useState<DuplicateSessionStrategy>("create_new");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [jsonFile, setJsonFile] = useState<File | null>(null);
  const [lastImport, setLastImport] = useState<SimulationImportResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listFaultProfiles()
      .then(setFaultProfiles)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load fault profiles"));
  }, []);

  function updateNumberField(key: NumericSimulationConfigKey, value: string) {
    const parsed = Number(value);
    setConfig((current) => ({
      ...current,
      [key]: Number.isFinite(parsed) ? parsed : current[key]
    }));
  }

  async function runImport(action: () => Promise<SimulationImportResponse>) {
    if (!actuatorId) return;
    setBusy(true);
    setError("");
    setLastImport(null);

    try {
      const result = await action();
      setLastImport(result);
      onImported(result.session_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel simulator-panel">
      <div className="panel-title">
        <div>
          <h2>Simulator and ingestion</h2>
          <p>Generate repeatable telemetry or import CSV/JSON data into a tracked session.</p>
        </div>
      </div>

      <div className="sim-grid">
        <label>
          Fault profile
          <select
            value={config.fault_profile}
            onChange={(event) => setConfig((current) => ({
              ...current,
              fault_profile: event.target.value as SimulationFaultProfile
            }))}
          >
            {faultProfiles.map((profile) => (
              <option key={profile.key} value={profile.key}>{profile.label}</option>
            ))}
          </select>
        </label>

        <label>
          Session name
          <input value={sessionName} onChange={(event) => setSessionName(event.target.value)} />
        </label>

        <label>
          Duplicate handling
          <select
            value={duplicateStrategy}
            onChange={(event) => setDuplicateStrategy(event.target.value as DuplicateSessionStrategy)}
          >
            <option value="reject">Reject duplicate</option>
            <option value="create_new">Create new with suffix</option>
            <option value="replace">Replace existing</option>
          </select>
        </label>

        <label>
          Seed
          <input
            type="number"
            value={config.seed ?? ""}
            onChange={(event) => updateNumberField("seed", event.target.value)}
          />
        </label>

        <label>
          Sample rate Hz
          <input
            type="number"
            value={config.sample_rate_hz}
            onChange={(event) => updateNumberField("sample_rate_hz", event.target.value)}
          />
        </label>

        <label>
          Duration seconds
          <input
            type="number"
            value={config.duration_s}
            onChange={(event) => updateNumberField("duration_s", event.target.value)}
          />
        </label>

        <label>
          Fault intensity
          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={config.fault_intensity}
            onChange={(event) => updateNumberField("fault_intensity", event.target.value)}
          />
        </label>
      </div>

      <div className="import-actions">
        <button
          disabled={!actuatorId || busy}
          onClick={() => runImport(() => api.importSyntheticTelemetry({
            actuator_id: actuatorId,
            session_name: sessionName,
            duplicate_strategy: duplicateStrategy,
            config
          }))}
        >
          Generate and import telemetry
        </button>

        <label className="file-picker">
          CSV file
          <input type="file" accept=".csv,text/csv" onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)} />
        </label>
        <button
          disabled={!csvFile || !actuatorId || busy}
          onClick={() => csvFile && runImport(() => api.importCsvTelemetry({
            actuatorId,
            file: csvFile,
            sessionName,
            duplicateStrategy
          }))}
        >
          Import CSV
        </button>

        <label className="file-picker">
          JSON file
          <input type="file" accept=".json,application/json" onChange={(event) => setJsonFile(event.target.files?.[0] ?? null)} />
        </label>
        <button
          disabled={!jsonFile || !actuatorId || busy}
          onClick={() => jsonFile && runImport(() => api.importJsonTelemetry({
            actuatorId,
            file: jsonFile,
            sessionName,
            duplicateStrategy
          }))}
        >
          Import JSON
        </button>
      </div>

      {error ? <div className="error-panel">{error}</div> : null}

      {lastImport ? (
        <div className="success-panel">
          Imported {lastImport.rows_imported.toLocaleString()} samples into <strong>{lastImport.session_name}</strong>.
          {lastImport.metadata ? <span> Fault: {lastImport.metadata.fault_profile}</span> : null}
        </div>
      ) : null}
    </section>
  );
}
