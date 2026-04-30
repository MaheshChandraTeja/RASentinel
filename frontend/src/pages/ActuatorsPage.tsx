import { FormEvent, useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { SeverityBadge } from "../components/SeverityBadge";
import { api } from "../services/api";
import type { Actuator } from "../types/domain";
import { labelize } from "../utils/format";

export function ActuatorsPage() {
  const [actuators, setActuators] = useState<Actuator[]>([]);
  const [selected, setSelected] = useState<Actuator | null>(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ name: "", actuator_type: "servo", location: "", manufacturer: "" });

  async function load() {
    setError("");
    try {
      const payload = await api.listActuators();
      setActuators(payload);
      setSelected((current) => current ?? payload[0] ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load actuator records.");
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const actuator = await api.createActuator({
        name: form.name,
        actuator_type: form.actuator_type,
        location: form.location || undefined,
        manufacturer: form.manufacturer || undefined
      });
      setActuators((current) => [actuator, ...current]);
      setSelected(actuator);
      setForm({ name: "", actuator_type: "servo", location: "", manufacturer: "" });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create actuator.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <main className="page-stack">
      <PageHeader
        eyebrow="Actuators"
        title="Actuator registry"
        description="Register robot joints, motors, drives, and linear actuators before importing telemetry or running diagnostics."
        actions={<button onClick={load}>Refresh list</button>}
      />

      {error ? <div className="error-panel">{error}</div> : null}

      <section className="split-layout">
        <div className="panel">
          <div className="panel-title-row">
            <div>
              <h2>Add actuator</h2>
              <p className="muted">Create a record with the metadata needed for diagnostics and reports.</p>
            </div>
          </div>
          <form className="form-stack" onSubmit={create}>
            <label className="form-field">Name<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required placeholder="Joint A1 shoulder servo" /></label>
            <label className="form-field">Type<select value={form.actuator_type} onChange={(e) => setForm({ ...form, actuator_type: e.target.value })}><option value="servo">Servo</option><option value="dc_motor">DC motor</option><option value="stepper">Stepper</option><option value="linear">Linear actuator</option><option value="hydraulic">Hydraulic actuator</option><option value="pneumatic">Pneumatic actuator</option></select></label>
            <label className="form-field">Location<input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Robot arm / axis 1" /></label>
            <label className="form-field">Manufacturer<input value={form.manufacturer} onChange={(e) => setForm({ ...form, manufacturer: e.target.value })} placeholder="Optional" /></label>
            <button type="submit">Create actuator</button>
          </form>
        </div>

        <div className="panel panel--wide">
          <div className="panel-title-row"><h2>Fleet records</h2><span>{actuators.length}</span></div>
          <div className="entity-grid">
            {actuators.map((actuator) => (
              <button key={actuator.id} className={selected?.id === actuator.id ? "entity-card entity-card--active" : "entity-card"} onClick={() => setSelected(actuator)}>
                <strong>{actuator.name}</strong>
                <span>{labelize(actuator.actuator_type)}</span>
                <small>{actuator.location || "Location not set"}</small>
                <SeverityBadge band={actuator.health_status} />
              </button>
            ))}
          </div>
        </div>
      </section>

      {selected ? (
        <section className="panel">
          <div className="panel-title-row"><h2>{selected.name}</h2><SeverityBadge band={selected.health_status} /></div>
          <div className="report-meta-grid">
            <Meta label="Type" value={labelize(selected.actuator_type)} />
            <Meta label="Location" value={selected.location ?? "Not set"} />
            <Meta label="Manufacturer" value={selected.manufacturer ?? "Not set"} />
            <Meta label="Model" value={selected.model_number ?? "Not set"} />
          </div>
        </section>
      ) : null}
    </main>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return <div className="meta-card"><span>{label}</span><strong>{value}</strong></div>;
}
