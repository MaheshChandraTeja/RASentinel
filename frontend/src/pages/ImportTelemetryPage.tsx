import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { api } from "../services/api";
import type { Actuator, DuplicateSessionStrategy, SimulationImportResponse } from "../types/domain";
import { formatDateTime, formatInteger } from "../utils/format";

export function ImportTelemetryPage() {
  const [actuators, setActuators] = useState<Actuator[]>([]);
  const [actuatorId, setActuatorId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [format, setFormat] = useState<"csv" | "json">("csv");
  const [sessionName, setSessionName] = useState("Imported actuator telemetry");
  const [duplicateStrategy, setDuplicateStrategy] = useState<DuplicateSessionStrategy>("create_new");
  const [result, setResult] = useState<SimulationImportResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void api.listActuators().then((payload) => {
      setActuators(payload);
      setActuatorId(payload[0]?.id ?? "");
    });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !actuatorId) return;
    setError("");
    setResult(null);
    try {
      const payload = format === "csv"
        ? await api.importCsvTelemetry({ actuatorId, file, sessionName, duplicateStrategy })
        : await api.importJsonTelemetry({ actuatorId, file, sessionName, duplicateStrategy });
      setResult(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Telemetry import failed.");
    }
  }

  return (
    <main className="page-stack">
      <PageHeader
        eyebrow="Telemetry import"
        title="Import CSV or JSON telemetry"
        description="Validate actuator telemetry files, create a traceable session, and store the samples locally for diagnostics."
      />

      {error ? <div className="error-panel">{error}</div> : null}

      <section className="split-layout">
        <form className="panel form-stack" onSubmit={submit}>
          <div className="panel-title-row">
            <div>
              <h2>Import setup</h2>
              <p className="muted">Choose a target actuator, file format, and duplicate handling strategy.</p>
            </div>
          </div>
          <label className="form-field">Actuator<select value={actuatorId} onChange={(e) => setActuatorId(e.target.value)} required>{actuators.map((actuator) => <option key={actuator.id} value={actuator.id}>{actuator.name}</option>)}</select></label>
          <label className="form-field">Session name<input value={sessionName} onChange={(e) => setSessionName(e.target.value)} required /></label>
          <label className="form-field">File format<select value={format} onChange={(e) => setFormat(e.target.value as "csv" | "json")}><option value="csv">CSV</option><option value="json">JSON</option></select></label>
          <label className="form-field">Duplicate sessions<select value={duplicateStrategy} onChange={(e) => setDuplicateStrategy(e.target.value as DuplicateSessionStrategy)}><option value="reject">Reject duplicate</option><option value="create_new">Create new session</option><option value="replace">Replace existing session</option></select></label>
          <label className="file-drop">
            <span>Telemetry file</span>
            <strong>{file?.name ?? "Choose a file"}</strong>
            <small>{format.toUpperCase()} files are parsed and validated before storage.</small>
            <input type="file" accept={format === "csv" ? ".csv,text/csv" : ".json,application/json"} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button type="submit" disabled={!file || !actuatorId}>Import telemetry</button>
        </form>

        <section className="panel panel--wide">
          <div className="panel-title-row">
            <div>
              <h2>Import result</h2>
              <p className="muted">Validation details and persisted session information appear here.</p>
            </div>
          </div>
          {result ? (
            <div className="result-card">
              <strong>{result.status}</strong>
              <p>{formatInteger(result.rows_imported)} imported · {formatInteger(result.rows_failed)} failed · {formatInteger(result.rows_received)} received</p>
              <small>Session: {result.session_name}</small>
              <small>Imported: {formatDateTime(result.created_at)}</small>
              {result.errors.length > 0 ? <pre>{JSON.stringify(result.errors.slice(0, 10), null, 2)}</pre> : null}
            </div>
          ) : (
            <div className="empty-state empty-state--inline">
              <strong>No import has run yet</strong>
              <p>Select a telemetry file and start the import to create a session.</p>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
