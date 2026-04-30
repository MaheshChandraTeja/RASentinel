# RASentinel Architecture

RASentinel is a local-first robotics reliability system for actuator telemetry, drift analysis, fault classification, and audit-ready diagnostic reporting.

It is built around one practical idea: actuator failures usually leave evidence before they become failures. Position tracking gets sloppy. Current rises. Temperature drifts. Latency grows. Encoders get noisy. RASentinel captures those signals, turns them into diagnostics features, compares them against known-good behavior, and produces a report that can be reviewed instead of guessed.

---

## 1. System Overview

RASentinel runs as a desktop application with a local backend service. The UI, API, database, reports, and telemetry artifacts stay on the user’s machine unless the user explicitly exports them.

```text
┌──────────────────────────────────────┐
│ Electron Desktop Shell                │
│ window lifecycle · backend launcher   │
└───────────────────┬──────────────────┘
                    │ local HTTP
                    ▼
┌──────────────────────────────────────┐
│ React + Vite Frontend                 │
│ dashboard · simulation · diagnostics  │
│ reports · live telemetry              │
└───────────────────┬──────────────────┘
                    │ typed API calls
                    ▼
┌──────────────────────────────────────┐
│ FastAPI Backend                       │
│ telemetry · features · drift · faults │
│ reports · live ingestion              │
└───────────────────┬──────────────────┘
                    │ SQLAlchemy repositories
                    ▼
┌──────────────────────────────────────┐
│ SQLite + Local Artifacts              │
│ actuators · sessions · samples        │
│ baselines · diagnoses · reports       │
└──────────────────────────────────────┘
```

The application is intentionally local and inspectable. There is no required account, no default cloud upload, and no remote service quietly deciding whether a motor is healthy from a server farm with better lighting.

---

## 2. Product Workflow

The main workflow is designed for both simulated and real actuator telemetry.

```text
Create actuator
  ↓
Import, simulate, or stream telemetry
  ↓
Store telemetry in a session
  ↓
Extract robotics features
  ↓
Create or select a healthy baseline
  ↓
Run drift detection
  ↓
Classify likely fault
  ↓
Generate audit report
```

Typical demo flow:

1. Register an actuator.
2. Generate synthetic telemetry or ingest controller telemetry.
3. Create a known-good baseline from a healthy run.
4. Run diagnostics on a target session.
5. Review evidence charts, severity, confidence, and maintenance guidance.
6. Generate an HTML audit report.

---

## 3. Runtime Architecture

### Desktop Shell

The Electron shell owns the desktop runtime boundary:

- starts and supervises the local FastAPI backend
- points runtime storage to the AppData workspace
- opens the React UI in a desktop window
- avoids browser-tab dependency for normal use

The shell does not perform diagnostics itself. It provides the desktop container and launches the local backend service.

### Frontend

The frontend owns the product experience:

- fleet dashboard
- actuator registry
- CSV/JSON telemetry import
- simulation lab
- live telemetry monitoring
- diagnostics workspace
- report history and preview
- local settings and workflow guidance

The frontend consumes the backend through typed service calls and keeps user-facing text production-oriented. Setup commands, backend implementation details, and developer-only language should stay out of the UI.

### Backend

The backend owns data validation, storage, analysis, diagnosis, and report generation.

Core responsibilities:

- validate actuator metadata and telemetry samples
- persist sessions and telemetry in SQLite
- generate synthetic actuator telemetry
- import CSV and JSON telemetry
- extract signal-processing features
- create healthy baselines
- detect drift and anomalies
- classify likely actuator faults
- store diagnosis history
- generate HTML/JSON audit reports
- accept live telemetry streams from controller bridges

### Storage

RASentinel uses SQLite for local persistence. In the desktop runtime, the canonical storage location is the user’s application data directory:

```text
%APPDATA%\rasentinel-desktop\data\rasentinel.db
```

Reports and local artifacts are stored under the same AppData workspace.

Project-local `data/` folders are not part of the production storage policy. The repository should remain code, documentation, scripts, and tests. Runtime state belongs in AppData where desktop users expect it to live.

---

## 4. Backend Domain Model

The backend data model is centered on traceable actuator sessions.

```text
Actuator
  ├─ SessionRun
  │   ├─ TelemetrySample
  │   ├─ CommandSignal
  │   ├─ FeatureSet
  │   ├─ DriftResult
  │   └─ DiagnosisResult
  ├─ HealthyBaseline
  └─ LiveHardwareSession
```

### Actuator

Represents a motor, servo, joint, drive, linear actuator, or other controlled movement element.

Common fields:

- name
- type
- manufacturer
- model number
- serial number
- location
- rated torque/current/voltage
- health status

### SessionRun

Represents a telemetry recording or imported run.

Sources include:

- synthetic simulator
- CSV import
- JSON import
- live hardware bridge
- manual or external capture

### TelemetrySample

Stores timestamped actuator behavior.

Key fields:

- commanded position
- actual position
- commanded velocity
- actual velocity
- commanded torque
- estimated torque
- motor current
- temperature
- load estimate
- control latency
- encoder position
- position error
- velocity error
- optional fault label

### FeatureSet

Stores computed diagnostics features for a session.

Examples:

- mean position error
- max position error
- mean velocity error
- response delay
- overshoot percentage
- settling time
- current drift percentage
- temperature rise rate
- error variance
- oscillation score
- health deviation score

### HealthyBaseline

Stores known-good feature references for an actuator.

A baseline is created from a healthy session and later used for comparison. It acts as the actuator’s “normal behavior” reference, not a universal guess pulled from the void.

### DiagnosisResult

Stores the final diagnostic output:

- fault label
- severity score
- severity band
- confidence score
- summary
- evidence signals
- recommendation
- report linkage

---

## 5. Telemetry Flow

RASentinel supports three major telemetry paths.

### Synthetic Telemetry

The simulator creates repeatable actuator telemetry for healthy and faulty conditions.

Supported profiles include:

- healthy actuator
- friction increase
- backlash
- encoder noise
- motor weakening
- overheating
- delayed response
- load imbalance
- oscillation/control instability
- current spike anomaly

Synthetic telemetry supports deterministic seeds so the same scenario can be reproduced during testing, demos, and benchmarks.

### File Import

CSV and JSON telemetry files can be imported into a selected actuator session.

The import pipeline handles:

- schema validation
- row-level error collection
- duplicate session strategy
- session metadata tracking
- bulk persistence
- clean import summaries

### Live Telemetry

Live telemetry uses a read-only bridge model.

```text
Actuator controller
  ↓
Serial / ROS2 / CAN / PLC / custom bridge
  ↓
RASentinel live ingestion API
  ↓
SQLite telemetry session
  ↓
rolling diagnostics and report workflow
```

RASentinel does not control motors. It receives telemetry and performs diagnostics. Control loops, safety interlocks, emergency stop behavior, and actuator limits remain the responsibility of the controller hardware/software.

---

## 6. Signal Processing Pipeline

Raw telemetry is converted into diagnostic features before drift detection or classification.

```text
Telemetry samples
  ↓
missing-value safe extraction
  ↓
position and velocity error calculation
  ↓
moving-average smoothing
  ↓
latency and response estimation
  ↓
overshoot / settling / steady-state features
  ↓
current and temperature trends
  ↓
noise and oscillation scoring
  ↓
feature persistence
```

The extraction layer is deterministic. The same session should produce the same feature set unless the underlying telemetry changes.

---

## 7. Baseline and Drift Detection

Drift detection compares a target session against a healthy baseline.

The detector considers:

- position error growth
- velocity error growth
- current deviation
- temperature trend
- latency changes
- oscillation score
- statistical thresholds
- z-score style anomaly indicators

The output is not just a score. It includes evidence describing which signals contributed to the drift result.

```text
Target FeatureSet
  + HealthyBaseline
  ↓
comparison metrics
  ↓
severity scoring
  ↓
evidence signals
  ↓
drift result
```

Severity is scored from 0 to 100 and mapped to a readable band: none, low, medium, high, or critical.

---

## 8. Fault Classification

The classifier maps extracted features and drift evidence to likely actuator faults.

Supported fault categories include:

- friction increase
- backlash
- encoder fault
- motor weakening
- thermal stress
- control instability
- delayed response
- load imbalance
- unknown anomaly

The classifier is intentionally conservative. If the evidence does not strongly match a known profile, it should return an unknown anomaly instead of inventing a confident fantasy with a fault label attached.

---

## 9. Reports and Audit Trail

Reports are generated from persisted diagnostic data, not fragile UI state.

A report includes:

- actuator information
- telemetry session summary
- detected fault
- severity and confidence
- evidence signals
- drift timeline context
- maintenance recommendation
- technical notes

Reports are stored locally and can be searched from the UI.

Current export target:

- HTML report

Planned export targets:

- PDF report
- structured report bundle
- evidence artifact archive

---

## 10. API Surface

RASentinel exposes a local HTTP API under:

```text
/api/v1
```

Main API areas:

```text
GET    /health
POST   /actuators
GET    /actuators
GET    /actuators/{id}
POST   /telemetry/import
POST   /telemetry/simulate
POST   /diagnostics/run/{session_id}
GET    /diagnostics/{diagnosis_id}
GET    /actuators/{id}/health
GET    /reports/{diagnosis_id}
POST   /live/sessions
POST   /live/sessions/{live_session_id}/samples
POST   /live/sessions/{live_session_id}/diagnose
POST   /live/sessions/{live_session_id}/stop
```

The API is local-first. It is designed for the desktop UI, test scripts, and controlled bridge adapters.

---

## 11. Repository Layout

```text
RASentinel/
├─ backend/
│  ├─ app/
│  │  ├─ api/                 FastAPI routers
│  │  ├─ core/                configuration and logging
│  │  ├─ db/                  SQLite session and initialization
│  │  ├─ models/              SQLAlchemy domain models
│  │  ├─ schemas/             Pydantic request/response contracts
│  │  └─ services/            simulation, ingestion, features, diagnosis
│  ├─ tests/                  backend unit and integration tests
│  └─ requirements.txt
│
├─ frontend/
│  ├─ src/
│  │  ├─ components/          shared UI components
│  │  ├─ pages/               product pages
│  │  ├─ services/            API client
│  │  ├─ types/               domain types
│  │  └─ navigation/          page metadata
│  └─ package.json
│
├─ desktop/
│  ├─ src/                    Electron main and preload scripts
│  ├─ package.json
│  └─ electron-builder.yml
│
├─ scripts/                   desktop launch, benchmark, demo, bridge scripts
├─ docs/                      architecture and project documentation
└─ README.md
```

---

## 12. Design Constraints

RASentinel deliberately avoids becoming a giant distributed system.

Current constraints:

- local-first desktop workflow
- SQLite persistence
- FastAPI sidecar backend
- React desktop UI
- read-only hardware telemetry bridge
- deterministic simulator and test flows
- explainable diagnosis output

Planned extensions should preserve these properties unless there is a clear reason not to.

Stretch areas:

- ROS2 bag import
- Arduino/ESP32 telemetry adapters
- PyTorch sequence models
- ONNX export
- fleet-level monitoring
- maintenance scheduler
- PDF reports
- anomaly replay timeline

---

## 13. Architecture Principles

| Principle | Meaning |
|---|---|
| Local-first | Telemetry, diagnoses, and reports stay on the machine by default. |
| Evidence-centered | Fault labels must be backed by signals, scores, and session data. |
| Reviewable | Diagnostics should be readable by a human, not treated as magic. |
| Deterministic where possible | Simulations, feature extraction, and tests should be reproducible. |
| Safe by boundary | RASentinel observes actuator behavior; it does not command motion. |
| Contract-driven | Frontend, backend, reports, and scripts share stable data shapes. |
| Demo-ready | A developer should be able to clone, run, simulate, diagnose, and report without a hardware bench. |

---

## 14. Known Boundaries

RASentinel is a diagnostic system, not a certified safety controller.

It does not replace:

- motor driver protections
- emergency stop circuits
- PLC safety logic
- mechanical limit switches
- certified industrial safety systems
- controller-side real-time loops

It should be used as a telemetry analysis and reliability engineering layer.
