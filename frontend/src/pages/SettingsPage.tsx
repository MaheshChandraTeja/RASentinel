import { PageHeader } from "../components/PageHeader";

export function SettingsPage() {
  return (
    <main className="page-stack settings-page">
      <PageHeader
        eyebrow="Settings"
        title="Application settings"
        description="Review local storage, report handling, and the recommended operating workflow for actuator diagnostics."
      />

      <section className="settings-grid settings-grid--production">
        <article className="panel settings-card">
          <h2>Runtime service</h2>
          <p>
            RASentinel runs a local diagnostics service on this workstation. The desktop app starts and uses this service automatically.
          </p>
          <p className="muted">
            Telemetry, diagnoses, and report records stay on this device unless you export them.
          </p>
        </article>

        <article className="panel settings-card">
          <h2>Local workspace</h2>
          <p>
            Application data is stored in the user application-data folder, outside the project source tree.
          </p>
          <code>%APPDATA%\rasentinel-desktop\data</code>
          <p className="muted">
            This keeps runtime data separate from the repository and preserves sessions between desktop launches.
          </p>
        </article>

        <article className="panel settings-card">
          <h2>Report storage</h2>
          <p>
            Diagnostic reports are saved locally as reviewable audit records with actuator metadata, evidence, and recommendations.
          </p>
          <code>%APPDATA%\rasentinel-desktop\data\reports</code>
          <p className="muted">
            Open a saved report to share findings with a team, attach it to a maintenance ticket, or archive it with test results.
          </p>
        </article>
      </section>

      <section className="panel workflow-panel">
        <div className="panel-title-row">
          <div>
            <h2>Recommended workflow</h2>
            <p className="muted">Use this sequence for consistent actuator diagnostics and report generation.</p>
          </div>
        </div>

        <ol className="workflow-steps">
          <li>
            <strong>Register the actuator</strong>
            <span>Add the actuator name, type, location, and relevant controller metadata.</span>
          </li>
          <li>
            <strong>Capture or import telemetry</strong>
            <span>Use a live controller stream, a CSV/JSON file, or a simulation session.</span>
          </li>
          <li>
            <strong>Create a healthy baseline</strong>
            <span>Use a known-good run when available to improve drift comparison.</span>
          </li>
          <li>
            <strong>Run diagnostics</strong>
            <span>Extract features, classify the likely fault, and review the evidence.</span>
          </li>
          <li>
            <strong>Generate the report</strong>
            <span>Save the diagnosis, evidence, and recommended action as an audit record.</span>
          </li>
        </ol>
      </section>
    </main>
  );
}
