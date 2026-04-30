# Testing Guide

RASentinel is tested across the backend, frontend, simulator, feature extraction, diagnostics pipeline, report generation, and live telemetry bridge.

The goal is not just “tests pass.” The goal is that a developer can clone the project, run a repeatable demo, generate telemetry, diagnose a fault, and produce a report without needing a physical actuator bench.

---

## 1. Test Strategy

RASentinel uses layered testing.

```text
Unit tests
  ↓
service tests
  ↓
API integration tests
  ↓
frontend smoke tests
  ↓
benchmark scripts
  ↓
manual desktop QA
```

Each layer catches a different class of failure:

| Layer | Purpose |
|---|---|
| Backend unit tests | Validate formulas, feature extraction, simulation, classification logic. |
| Backend API tests | Validate routes, persistence, status codes, and end-to-end workflows. |
| Frontend tests | Validate navigation metadata, API route assumptions, and UI smoke behavior. |
| Benchmark scripts | Measure import time, diagnosis time, memory use, and synthetic accuracy. |
| Manual QA | Confirm desktop runtime, visual layout, reports, and live telemetry flow. |

---

## 2. Backend Test Setup

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pytest
```

Expected result:

```text
all tests passed
```

Backend tests use isolated test databases. Test data should not persist into the desktop AppData database.

This is intentional. Tests should be repeatable, not haunted by whatever actuator was created during last night’s debugging spiral.

---

## 3. Frontend Test Setup

From the project root:

```powershell
cd frontend
pnpm install
pnpm build
pnpm test
```

Expected result:

```text
build completed
test files passed
```

A Vite chunk-size warning may appear because charting libraries are not small. That warning is not a failed build.

---

## 4. Desktop Runtime Check

From the project root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_desktop.ps1
```

Expected behavior:

- Electron window opens.
- Backend starts automatically.
- UI loads without browser involvement.
- Settings page shows production storage and workflow text.
- Data is stored under AppData, not the source repository.

Canonical desktop data path:

```text
%APPDATA%\rasentinel-desktop\data
```

---

## 5. Backend API Health Check

Run the backend manually:

```powershell
cd backend
.\.venv\Scripts\activate
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

Check:

```text
GET /api/v1/health
```

Expected response:

```json
{
  "app": "RASentinel",
  "status": "ok",
  "database": "ok",
  "environment": "development"
}
```

---

## 6. Core Backend Test Areas

### Actuator and Session Tests

These verify that:

- actuators can be created
- sessions can be created for actuators
- telemetry samples are linked to sessions
- diagnosis results are linked to sessions
- invalid IDs return clean errors

### Simulator Tests

These verify that:

- healthy telemetry can be generated
- fault telemetry can be generated
- generated sample counts match requested duration/sample rate
- seeds are reproducible
- at least 1,000 samples can be generated and imported

Recommended assertions:

- same seed produces same telemetry
- different fault profiles produce distinguishable patterns
- delayed response increases latency/error
- overheating increases temperature trend
- friction increase raises current and position error

### Import Tests

These verify that:

- valid CSV imports successfully
- valid JSON imports successfully
- invalid files return structured errors
- duplicate session handling works
- imported rows are persisted
- large imports do not crash the backend

### Feature Extraction Tests

These verify formulas for:

- mean position error
- max position error
- mean velocity error
- current drift
- temperature trend
- response latency
- overshoot
- settling time
- steady-state error
- error variance
- oscillation score
- health deviation score

Feature extraction should be deterministic and missing-value safe.

### Baseline and Drift Tests

These verify that:

- healthy sessions produce low drift scores
- faulty sessions produce elevated drift scores
- higher severity faults produce higher drift scores
- evidence fields identify contributing signals
- baseline comparison behaves consistently

### Fault Classification Tests

These verify that the classifier recognizes major simulated faults:

- friction increase
- delayed response
- thermal stress
- encoder fault
- control instability
- load imbalance

Unknown anomalies should be handled safely instead of forcing a confident wrong label.

### Report Tests

These verify that:

- every diagnosis can produce a report
- report history is searchable
- reports include actuator metadata
- reports include severity/confidence
- reports include evidence signals
- report files are saved locally

### Live Telemetry Tests

These verify that:

- live sessions can be created
- batches of live samples can be posted
- recent telemetry can be queried
- live diagnosis can be triggered
- sessions can be stopped
- ingestion does not discard telemetry if rolling diagnostics fails

---

## 7. Full Demo Flow Test

This is the minimum end-to-end product validation.

```text
Create actuator
  ↓
Generate healthy synthetic telemetry
  ↓
Create baseline
  ↓
Generate faulty synthetic telemetry
  ↓
Run diagnosis
  ↓
Generate report
```

Expected result:

- actuator exists in registry
- both sessions are stored
- baseline is created from healthy session
- faulty session receives elevated drift/severity
- diagnosis includes evidence
- report is generated and visible in report history

---

## 8. Mock Real-Time Telemetry Test

This test validates the live ingestion pipeline without physical hardware.

Start backend:

```powershell
cd backend
.\.venv\Scripts\activate
uvicorn app.main:app --reload
```

Start frontend or desktop shell.

Create an actuator in the UI, then run the mock stream from the project root:

```powershell
.\backend\.venv\Scripts\activate

python .\scripts\mock_live_actuator_stream.py `
  --actuator-id YOUR_ACTUATOR_ID `
  --session-name "Mock live delayed response test" `
  --fault-mode delayed_response `
  --sample-rate-hz 50 `
  --duration-s 60 `
  --fault-after-s 20 `
  --batch-size 50 `
  --diagnose-every-samples 500
```

Expected behavior:

- live session is created
- samples are posted in batches
- session reaches approximately 3,000 samples for a 60-second, 50 Hz run
- diagnosis runs during or after the stream
- Live Telemetry page shows recent samples
- Diagnostics and Reports pages can use the resulting session

This test proves the live API and UI path. It does not prove electrical hardware integration.

---

## 9. Real Hardware Bridge Test

When hardware is available, validate the same path using a controller bridge.

Recommended first hardware path:

```text
Actuator controller
  ↓ serial / USB
live bridge script
  ↓ local API
RASentinel live session
```

Safety rules:

- RASentinel should remain read-only.
- The controller owns motion and safety limits.
- Emergency stop must remain hardware/controller-side.
- Test at low speed and low load first.
- Do not use RASentinel as a control loop.

Minimum telemetry fields:

- commanded_position
- actual_position
- commanded_velocity
- actual_velocity
- motor_current
- temperature
- encoder_position
- control_latency_ms

---

## 10. Benchmarking

Run benchmark scripts from the project root after installing backend dependencies.

Example:

```powershell
.\backend\.venv\Scripts\activate
python .\scripts\run_backend_benchmark.py --sample-count 1000 --healthy-trials 5
```

Benchmarks should measure:

- telemetry import time
- feature extraction time
- diagnosis runtime
- memory usage
- fault classification accuracy on synthetic data
- false positive rate on healthy telemetry

Benchmark results should be treated as development signals, not scientific claims unless the dataset and environment are documented.

---

## 11. Sample Dataset Generation

Generate demo datasets from the project root:

```powershell
.\backend\.venv\Scripts\activate
python .\scripts\create_demo_dataset.py --sample-count 1000
```

Sample datasets should be synthetic unless real telemetry has been scrubbed and intentionally approved for publication.

Do not commit private machine telemetry by accident. Git remembers. Git is petty.

---

## 12. Manual UI QA Checklist

Before tagging a release or recording a demo, check every page.

### Dashboard

- [ ] Opens without console errors.
- [ ] Shows actuator/session/report status.
- [ ] Cards align at desktop width.
- [ ] Empty states use production wording.

### Actuators

- [ ] Create actuator works.
- [ ] Actuator list refreshes.
- [ ] Long names do not break layout.

### Import

- [ ] CSV file picker is aligned.
- [ ] JSON import path works.
- [ ] Invalid file shows readable error.
- [ ] Import result does not clip.

### Simulation

- [ ] Fault profile dropdown works.
- [ ] Simulation creates a session.
- [ ] Generated telemetry appears in later pages.

### Live Telemetry

- [ ] Live session list loads.
- [ ] Recent samples refresh.
- [ ] Charts render without clipping.
- [ ] Production UI does not show terminal commands.

### Diagnostics

- [ ] Actuator/session/baseline selectors work.
- [ ] Run diagnosis succeeds.
- [ ] Evidence panel populates.
- [ ] Charts do not clip titles or labels.

### Reports

- [ ] Diagnosis selector loads.
- [ ] Generate report works.
- [ ] Search input is not clipped.
- [ ] Report preview wraps long text.
- [ ] HTML export opens.

### Settings

- [ ] No Vite/dev wording appears.
- [ ] Storage path wording is production-friendly.
- [ ] Workflow guidance is clear.

---

## 13. Release Readiness Checklist

Backend:

- [ ] `pytest` passes.
- [ ] Health route returns OK.
- [ ] Synthetic 1,000-sample import passes.
- [ ] Full baseline-to-report flow passes.
- [ ] Live mock stream works.

Frontend:

- [ ] `pnpm build` passes.
- [ ] `pnpm test` passes.
- [ ] No broken desktop layouts at common window sizes.
- [ ] Production copy is used throughout.
- [ ] No developer commands appear in product UI.

Desktop:

- [ ] Electron starts the backend successfully.
- [ ] Database path points to AppData.
- [ ] App closes without orphaning backend processes.
- [ ] Data persists between app launches.

Repository:

- [ ] README is current.
- [ ] Architecture docs are current.
- [ ] Security/privacy docs are current.
- [ ] Test instructions are current.
- [ ] Runtime databases and reports are ignored by Git.

---

## 14. Common Failures and Fixes

### SQLite tables missing during tests

Use a shared in-memory SQLite connection for tests with `StaticPool`. Otherwise each connection gets a separate empty in-memory database. SQLite enjoys tiny alternate universes.

### Electron cannot start backend

Check that Electron is using:

```text
backend\.venv\Scripts\python.exe
```

rather than a missing global `python` command.

### Data appears missing in Electron

Check the database path. Desktop runtime should use AppData:

```text
%APPDATA%\rasentinel-desktop\data\rasentinel.db
```

Project-local databases should not be the production source of truth.

### Frontend JSX typing errors

Ensure frontend dev dependencies include:

- `@types/react`
- `@types/react-dom`
- `vite/client` typing

### Status code test mismatch

Create/import endpoints that create sessions, telemetry, or reports should return `201 Created`. Tests should match the API contract.

---

## 15. Definition of Done

RASentinel is considered demo-ready when:

- synthetic healthy and faulty telemetry can be generated
- CSV/JSON telemetry can be imported
- telemetry is persisted locally
- feature extraction works deterministically
- baseline comparison produces explainable drift scores
- at least five major fault types can be classified
- diagnosis results include severity, confidence, evidence, and recommendations
- reports are generated and searchable
- live mock telemetry works end to end
- backend and frontend tests pass
- Electron runs as a desktop app
- AppData is the canonical runtime storage location
- README and docs explain the project clearly

At that point, the project is no longer just a dashboard with charts. It is a robotics reliability workflow with traceable evidence, which is the whole point.
