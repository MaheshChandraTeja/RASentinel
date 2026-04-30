# Security and Privacy

RASentinel is designed as a local-first robotics diagnostics tool. It stores actuator telemetry, diagnostics evidence, and reports on the user’s machine by default.

The goal is simple: keep sensitive machine behavior, maintenance evidence, and diagnostic history under local control unless the user chooses to export it.

---

## 1. Privacy Model

RASentinel does not require an account or cloud upload for normal operation.

The application stores local records such as:

- actuator metadata
- telemetry sessions
- command and response samples
- extracted diagnostics features
- healthy baselines
- diagnosis results
- audit reports
- live telemetry session history

In the desktop runtime, the canonical workspace is:

```text
%APPDATA%\rasentinel-desktop\data
```

The SQLite database is stored at:

```text
%APPDATA%\rasentinel-desktop\data\rasentinel.db
```

Report artifacts are stored under the same local workspace.

---

## 2. What Stays Local

By default, the following stays on the device:

| Data | Storage |
|---|---|
| Actuator registry | SQLite |
| Telemetry samples | SQLite |
| Simulated datasets | SQLite / local export |
| Imported CSV/JSON records | SQLite |
| Feature extraction output | SQLite |
| Healthy baselines | SQLite |
| Diagnosis history | SQLite |
| HTML reports | Local AppData report directory |
| Live telemetry sessions | SQLite |

RASentinel should not send telemetry, reports, or actuator metadata to external services unless a future integration explicitly asks the user to export or transmit data.

---

## 3. Sensitive Data Considerations

Actuator telemetry may reveal operational details about a lab, robot, warehouse line, machine cell, or test bench.

Telemetry can indirectly expose:

- mechanical load patterns
- duty cycles
- production timing
- robot motion characteristics
- maintenance condition
- controller behavior
- fault history
- equipment names or locations

Treat telemetry as operationally sensitive. Even if it looks like “just numbers,” it may describe how a real machine behaves.

---

## 4. Desktop Runtime Boundary

RASentinel uses Electron as the desktop shell and FastAPI as a local backend service.

Expected runtime model:

```text
Electron shell
  ↓ launches
FastAPI local backend
  ↓ stores
SQLite + local report artifacts
  ↓ serves
React UI in desktop window
```

The desktop shell should:

- launch the local backend using the project/backend Python environment
- set the backend database path to the AppData workspace
- avoid storing runtime data inside the source repository
- keep backend access local to the machine
- close or clean up child backend processes when the app exits

---

## 5. Local API Security

The backend exposes a local HTTP API for the desktop UI and bridge tools.

Current assumption:

- the API is intended for local machine access
- bridge scripts run under the same user account
- no public internet exposure is required

Recommended production behavior:

- bind backend to `127.0.0.1`, not `0.0.0.0`
- keep CORS limited to local frontend origins
- do not expose the backend port to the network
- avoid accepting arbitrary remote telemetry without authentication
- validate all uploaded files and live sample payloads

If RASentinel is ever used in a networked lab environment, add authentication and explicit device registration before accepting telemetry from remote controllers.

---

## 6. Input Validation

RASentinel accepts data from several places:

- CSV telemetry imports
- JSON telemetry imports
- synthetic simulator requests
- live telemetry bridge requests
- actuator metadata forms
- report generation requests

Every input path should enforce:

- schema validation
- type validation
- numeric finite-value checks
- sane bounds for sample counts and durations
- clean error messages for invalid files
- row-level import error reporting where possible
- duplicate session handling

Telemetry should never be trusted just because it came from a controller. Machines lie too, usually with confidence.

---

## 7. File Import Safety

CSV and JSON import support is intentionally narrow.

Recommended rules:

- parse only expected telemetry formats
- reject unsupported file types
- avoid executing or evaluating file content
- preserve row-level validation errors
- avoid loading huge files fully into memory when streaming is possible
- cap import size for the desktop MVP
- store imported telemetry as normalized records, not as executable artifacts

CSV/JSON files are data inputs, not scripts, plugins, or configuration code.

---

## 8. Live Hardware Bridge Safety

The live hardware bridge is read-only by design.

RASentinel may receive:

- commanded position
- actual position
- velocity
- current
- temperature
- latency
- encoder position
- controller timestamps
- bridge metadata

RASentinel should not send actuator commands, change controller parameters, disable safety checks, or control motion.

Safety-critical behavior must remain inside:

- motor controller firmware
- PLC logic
- robot controller software
- emergency stop wiring
- driver protection circuits
- mechanical limit systems

RASentinel is a diagnostics and evidence layer. It is not a certified safety device, and it should never be marketed as one.

---

## 9. Report Privacy

Reports can contain sensitive operational information.

A report may include:

- actuator names
- test session names
- fault labels
- severity scores
- confidence scores
- evidence signals
- maintenance recommendations
- timestamps
- local report paths

Before sharing reports publicly, review them for machine names, location names, operational identifiers, or test data that should not leave the device.

Future report export options should include redaction support for:

- actuator serial number
- lab or facility name
- operator notes
- controller identifiers
- exact timestamps

---

## 10. Logging Policy

Logs should help diagnose the application without leaking sensitive data.

Recommended logging rules:

- log service startup and shutdown
- log route-level errors
- log import summaries, not entire telemetry files
- log report generation status
- log live session lifecycle events
- avoid logging full telemetry streams by default
- avoid logging user file contents
- avoid logging secrets or access tokens if integrations are added later

When errors occur, prefer concise operational messages and store detailed traces only in local logs.

---

## 11. Secrets and Configuration

The current local MVP should not require secrets for normal use.

If future integrations add cloud storage, remote devices, or authenticated telemetry sources, store secrets using platform-appropriate secure storage rather than plain text files.

Potential future needs:

- bridge API tokens
- device enrollment keys
- cloud export credentials
- signed report keys
- remote fleet endpoint credentials

Until those exist, keep the application simple. A security model that does not need secrets is easier to secure than one that hides secrets badly.

---

## 12. Dependency Security

RASentinel uses Python and Node/Electron dependencies.

Recommended maintenance checks:

```powershell
cd backend
pip list --outdated

cd ../frontend
pnpm audit

cd ../desktop
pnpm audit
```

Before release:

- pin dependency versions where practical
- remove unused dependencies
- avoid experimental packages for core paths
- keep Electron updated
- review transitive dependency warnings
- avoid adding packages for trivial utilities

Every dependency is another tiny stranger living in the project. Invite fewer strangers.

---

## 13. Database and Artifact Protection

SQLite data is stored locally. The protection level depends on the operating system account and filesystem permissions.

Recommended practices:

- store production runtime data in AppData
- exclude runtime database files from Git
- exclude generated reports from Git unless intentionally adding samples
- back up AppData workspace manually if needed
- do not commit real telemetry or reports unless scrubbed

The repository should not contain real machine telemetry by accident.

---

## 14. Current Security Limits

Current MVP limitations:

- no user authentication
- no per-device authentication
- no encrypted SQLite database by default
- no signed report artifacts yet
- no role-based access control
- no networked fleet mode
- no certified safety behavior

These are acceptable for a local MVP, but they should be documented clearly.

If the app grows into remote fleet monitoring, the security model must be upgraded before accepting remote telemetry.

---

## 15. Recommended Future Hardening

Planned or recommended improvements:

- signed audit receipts
- report integrity hashes
- encrypted local database option
- device enrollment for live bridges
- local API token for bridge clients
- configurable port and token rotation
- secure export bundles
- report redaction mode
- Electron context isolation review
- packaged backend executable instead of dev virtualenv launch
- automated dependency scanning in CI

---

## 16. Security Checklist

Before publishing or packaging:

- [ ] Backend binds only to localhost.
- [ ] Runtime data is stored in AppData, not project folders.
- [ ] `.gitignore` excludes SQLite databases, logs, reports, and generated datasets.
- [ ] UI does not expose developer commands in production pages.
- [ ] CSV/JSON imports reject malformed files cleanly.
- [ ] Live telemetry bridge is read-only.
- [ ] Reports do not include unnecessary sensitive details.
- [ ] Dependency audit is reviewed.
- [ ] Test data is synthetic or scrubbed.
- [ ] README describes local-first behavior accurately.

---

## 17. Privacy Statement for README Use

Suggested short version:

> RASentinel is local-first. Actuator telemetry, diagnostics, baselines, and reports are stored on the user’s machine by default. The application does not require an account or mandatory cloud upload. Live hardware integration is read-only and intended for telemetry capture, not actuator control.
