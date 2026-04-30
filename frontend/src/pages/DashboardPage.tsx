import { useEffect, useMemo, useState } from "react";

import { HealthScoreCard } from "../components/HealthScoreCard";
import { PageHeader } from "../components/PageHeader";
import { SeverityBadge } from "../components/SeverityBadge";
import { TelemetryMultiChart } from "../components/TelemetryMultiChart";
import { api } from "../services/api";
import type { Actuator, ActuatorHealthTimelineResponse, HealthResponse, SessionRun, TelemetrySample } from "../types/domain";
import { formatDateTime, formatInteger } from "../utils/format";

export function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [actuators, setActuators] = useState<Actuator[]>([]);
  const [sessions, setSessions] = useState<SessionRun[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetrySample[]>([]);
  const [timeline, setTimeline] = useState<ActuatorHealthTimelineResponse | null>(null);
  const [selectedActuatorId, setSelectedActuatorId] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [error, setError] = useState("");

  const selectedActuator = useMemo(
    () => actuators.find((item) => item.id === selectedActuatorId) ?? null,
    [actuators, selectedActuatorId]
  );

  const latestPoint = timeline?.points.at(-1);
  const severityScore = latestPoint?.severity_score ?? 0;
  const severityBand = latestPoint?.severity_band ?? "none";

  async function refresh() {
    setError("");
    try {
      const [healthPayload, actuatorPayload] = await Promise.all([api.health(), api.listActuators()]);
      setHealth(healthPayload);
      setActuators(actuatorPayload);
      setSelectedActuatorId((current) => current || actuatorPayload[0]?.id || "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load dashboard data.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!selectedActuatorId) return;
    void Promise.all([api.listSessions(selectedActuatorId), api.getActuatorHealthTimeline(selectedActuatorId)])
      .then(([sessionPayload, timelinePayload]) => {
        setSessions(sessionPayload);
        setTimeline(timelinePayload);
        setSelectedSessionId(sessionPayload[0]?.id ?? "");
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load actuator data."));
  }, [selectedActuatorId]);

  useEffect(() => {
    if (!selectedSessionId) {
      setTelemetry([]);
      return;
    }
    void api.listTelemetry(selectedSessionId)
      .then(setTelemetry)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load telemetry."));
  }, [selectedSessionId]);

  return (
    <main className="page-stack">
      <PageHeader
        eyebrow="Overview"
        title="Actuator health overview"
        description="Review fleet status, recent diagnostic outcomes, and telemetry trends from a single local workspace."
        actions={<button onClick={refresh}>Refresh data</button>}
      />

      {error ? <div className="error-panel">{error}</div> : null}

      <section className="kpi-grid">
        <div className="kpi-card"><span>Backend status</span><strong>{health?.status ?? "Unknown"}</strong><small>Database: {health?.database ?? "Unknown"}</small></div>
        <div className="kpi-card"><span>Actuators</span><strong>{formatInteger(actuators.length)}</strong><small>Registered units</small></div>
        <div className="kpi-card"><span>Sessions</span><strong>{formatInteger(sessions.length)}</strong><small>Runs for selected actuator</small></div>
        <div className="kpi-card"><span>Telemetry samples</span><strong>{formatInteger(telemetry.length)}</strong><small>Loaded in current session</small></div>
      </section>

      <section className="dashboard-grid">
        <div className="panel">
          <div className="panel-title-row">
            <div>
              <h2>Actuator list</h2>
              <p className="muted">Select a unit to inspect current health and session data.</p>
            </div>
            <span>{formatInteger(actuators.length)}</span>
          </div>
          <div className="list-stack">
            {actuators.map((actuator) => (
              <button
                key={actuator.id}
                className={actuator.id === selectedActuatorId ? "entity-row entity-row--active" : "entity-row"}
                onClick={() => setSelectedActuatorId(actuator.id)}
              >
                <strong>{actuator.name}</strong>
                <small>{actuator.location || actuator.actuator_type}</small>
                <SeverityBadge band={actuator.health_status} />
              </button>
            ))}
          </div>
        </div>

        <div className="panel panel--wide">
          <div className="panel-title-row">
            <div>
              <h2>{selectedActuator?.name ?? "No actuator selected"}</h2>
              <p className="muted">{selectedActuator?.location ?? "Create or select an actuator to view session data."}</p>
            </div>
            <SeverityBadge band={selectedActuator?.health_status ?? "unknown"} />
          </div>

          <div className="two-column-grid">
            <HealthScoreCard
              title="Current health score"
              score={severityScore}
              band={severityBand}
              helper={latestPoint?.summary ?? "No diagnosis has been recorded for this actuator."}
            />

            <label className="form-field">
              Session
              <select value={selectedSessionId} onChange={(event) => setSelectedSessionId(event.target.value)}>
                <option value="">No session selected</option>
                {sessions.map((session) => (
                  <option key={session.id} value={session.id}>
                    {session.name} · {formatInteger(session.sample_count)} samples
                  </option>
                ))}
              </select>
              <span className="field-help">Latest timeline update: {formatDateTime(latestPoint?.timestamp)}</span>
            </label>
          </div>

          <TelemetryMultiChart samples={telemetry} compact />
        </div>
      </section>
    </main>
  );
}
