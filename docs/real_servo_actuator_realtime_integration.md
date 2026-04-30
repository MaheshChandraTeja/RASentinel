# Real Servo / Actuator Integration Guide

**Project:** RASentinel  
**Purpose:** Connect a real servo, motor controller, or actuator telemetry source to RASentinel for near-real-time actuator health analysis.  
**Scope:** Read-only telemetry ingestion, diagnostics, drift detection, fault classification, and report generation.

---

## 1. Overview

RASentinel is designed to analyze actuator behavior from timestamped telemetry. It does not need to directly control the actuator to produce useful diagnostics. The safest and cleanest production architecture is to let the actuator controller continue handling motion control, limits, motor protection, and emergency stop behavior while RASentinel observes telemetry and performs diagnostics.

```text
Servo / Actuator
    ↓
Motor Driver / Servo Controller
    ↓
Encoder, Current Sensor, Temperature Sensor, Controller State
    ↓
Telemetry Bridge
    ↓
RASentinel Live Ingestion API
    ↓
Feature Extraction → Drift Detection → Fault Classification → Report
```

RASentinel should be treated as a diagnostics and reliability layer, not as a motor-control loop.

---

## 2. Integration Modes

RASentinel supports several practical ways to use real actuator data.

| Mode | Best For | Status | Notes |
|---|---:|---:|---|
| CSV / JSON import | Offline test runs, lab logs, controller exports | Supported | Good first real-data workflow |
| Live USB / Serial bridge | Arduino, ESP32, STM32, simple bench rigs | Supported through bridge script | Recommended first real-time integration |
| Smart actuator telemetry | Dynamixel, ODrive, Roboclaw, ClearPath, etc. | Supported through adapter | Requires controller-specific reader |
| ROS2 bridge | Robot arms, AMRs, research robots | Future adapter pattern | Map `/joint_states` and diagnostics topics to RASentinel samples |
| PLC / industrial controller bridge | Manufacturing and warehouse systems | Future adapter pattern | Common protocols: Modbus, OPC UA, EtherCAT gateway, vendor APIs |

---

## 3. Safety Boundary

RASentinel must remain read-only during this integration.

RASentinel should not:

- Send position, velocity, torque, or PWM commands to the actuator.
- Override motor driver limits.
- Replace the actuator controller.
- Replace an emergency stop system.
- Run inside a hard real-time control loop.

RASentinel should:

- Receive telemetry.
- Store samples locally.
- Extract diagnostic features.
- Detect drift and anomalies.
- Classify likely fault types.
- Generate reports for maintenance review.

This keeps the system safe, explainable, and easier to validate.

---

## 4. Hardware Requirements

### 4.1 Minimum Setup

A minimal real-time integration needs:

- One actuator or servo.
- A controller or microcontroller that can read actuator state.
- A USB, serial, or network connection to the machine running RASentinel.
- Timestamped telemetry samples sent to the RASentinel backend.

### 4.2 Recommended Setup

For meaningful fault analysis, use a feedback-capable actuator setup.

| Signal | Source | Why It Matters |
|---|---|---|
| `commanded_position` | Controller command | Needed to compare expected vs actual movement |
| `actual_position` | Encoder / controller feedback | Main signal for position tracking error |
| `commanded_velocity` | Controller command | Needed for velocity tracking comparison |
| `actual_velocity` | Encoder derivative / controller feedback | Helps identify lag, weakening, instability |
| `motor_current` | Driver telemetry / current sensor | Helps detect friction, load, spikes, motor stress |
| `temperature` | Motor or driver temperature sensor | Helps detect thermal stress and overheating |
| `control_latency_ms` | Controller timing estimate | Helps identify delayed response |
| `encoder_position` | Raw encoder reading | Helps identify encoder inconsistency or noise |

### 4.3 Hobby Servo Warning

A basic RC hobby servo usually accepts a PWM command but does not expose true position, current, or temperature. It can still be tested, but diagnostics will be limited unless extra sensors are added.

For serious RASentinel demos, use one of these instead:

- Smart servo with feedback, such as Dynamixel-class servos.
- DC motor with encoder and current sensing.
- Stepper or servo drive with controller telemetry.
- ODrive / Roboclaw / ClearPath-style controller output.
- Industrial actuator controller with telemetry export.

---

## 5. Software Requirements

### 5.1 RASentinel Desktop

Use the Electron desktop version when running a local test.

Expected storage location on Windows:

```text
C:\Users\<User>\AppData\Roaming\rasentinel-desktop\data\rasentinel.db
```

### 5.2 Backend Live API

The live integration uses these backend routes:

```text
POST /api/v1/live/sessions
GET  /api/v1/live/sessions
GET  /api/v1/live/sessions/{live_session_id}
POST /api/v1/live/sessions/{live_session_id}/samples
POST /api/v1/live/sessions/{live_session_id}/diagnose
POST /api/v1/live/sessions/{live_session_id}/stop
GET  /api/v1/live/sessions/{live_session_id}/telemetry/recent
```

### 5.3 Python Bridge Dependencies

For a USB / Serial controller bridge:

```powershell
cd F:\Projects-INT\RASentinel
.\backend\.venv\Scripts\activate
pip install pyserial requests
```

---

## 6. Telemetry Data Contract

Each telemetry sample should be a JSON object with actuator command, feedback, and condition signals.

### 6.1 Required Fields

RASentinel can accept partial samples, but these fields are strongly recommended:

```json
{
  "timestamp": "2026-04-29T12:00:00.000Z",
  "commanded_position": 10.0,
  "actual_position": 9.82,
  "commanded_velocity": 2.0,
  "actual_velocity": 1.91,
  "motor_current": 2.4,
  "temperature": 39.1,
  "control_latency_ms": 18.0,
  "encoder_position": 9.81,
  "fault_label": "none"
}
```

### 6.2 Full Supported Sample

```json
{
  "timestamp": "2026-04-29T12:00:00.000Z",
  "sequence_number": 1205,
  "controller_timestamp": "2026-04-29T12:00:00.000Z",
  "monotonic_ms": 24100.0,
  "commanded_position": 10.0,
  "actual_position": 9.82,
  "commanded_velocity": 2.0,
  "actual_velocity": 1.91,
  "commanded_torque": 1.2,
  "estimated_torque": 1.35,
  "motor_current": 2.4,
  "temperature": 39.1,
  "load_estimate": 0.42,
  "control_latency_ms": 18.0,
  "encoder_position": 9.81,
  "fault_label": "none"
}
```

### 6.3 Batch Payload

The live bridge sends samples in batches:

```json
{
  "samples": [
    {
      "sequence_number": 1,
      "commanded_position": 10.0,
      "actual_position": 9.82,
      "motor_current": 2.4,
      "temperature": 39.1
    }
  ]
}
```

Recommended batch size:

| Sample Rate | Batch Size | Notes |
|---:|---:|---|
| 10 Hz | 10-25 | Low volume test rigs |
| 50 Hz | 50-100 | Recommended default |
| 100 Hz | 100-250 | Higher-volume bench tests |
| 250+ Hz | 250-500 | Use only if backend and UI remain responsive |

---

## 7. Step-by-Step Integration: USB / Serial Controller

This is the recommended first real-time hardware path.

### Step 1: Confirm the actuator controller can emit telemetry

The controller should produce one JSON object per sample over USB serial.

Example line:

```json
{"commanded_position":10.0,"actual_position":9.83,"commanded_velocity":2.0,"actual_velocity":1.92,"motor_current":2.41,"temperature":38.9,"control_latency_ms":18.0,"encoder_position":9.82}
```

Each line must be valid JSON and end with a newline.

### Step 2: Connect the controller to the PC

Connect the controller over USB and identify the port.

On Windows, common ports look like:

```text
COM3
COM4
COM5
```

Check Device Manager if the port is not obvious.

### Step 3: Start RASentinel

Use the desktop application, or run the backend and frontend manually.

For Electron desktop:

```powershell
cd F:\Projects-INT\RASentinel
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_desktop.ps1
```

### Step 4: Create or select an actuator

In RASentinel:

1. Open **Actuators**.
2. Create a record for the physical actuator.
3. Use a clear name, such as `Bench Servo A1` or `Joint Motor Shoulder A1`.
4. Copy or note the actuator ID if needed by the bridge script.

### Step 5: Run the live serial bridge

From the project root:

```powershell
cd F:\Projects-INT\RASentinel
.\backend\.venv\Scripts\activate

python .\scripts\live_serial_bridge.py `
  --port COM5 `
  --baud 115200 `
  --actuator-id YOUR_ACTUATOR_ID `
  --session-name "Bench actuator live run 001" `
  --duration-s 60 `
  --batch-size 100 `
  --diagnose-every 1000
```

Expected output:

```text
Live session created: <live_session_id>
Imported 100 samples
Imported 200 samples
...
Live diagnosis updated
Capture complete
```

### Step 6: Monitor the live session

In RASentinel:

1. Open **Live Telemetry**.
2. Select the active session.
3. Watch sample count, position error, current, temperature, and latency.
4. Refresh if the UI does not update automatically.

### Step 7: Run diagnosis

After enough samples have arrived:

1. Open **Diagnostics**.
2. Select the actuator.
3. Select the live session.
4. Select a healthy baseline if available, or use classifier-only mode.
5. Run diagnosis.

### Step 8: Generate a report

1. Open **Reports**.
2. Select the actuator, session, and diagnosis.
3. Generate the audit report.
4. Review fault type, severity, confidence, evidence signals, and recommendation.

---

## 8. Controller Firmware Example

This example shows the telemetry shape expected by RASentinel. Adapt the sensor-reading functions to the controller being used.

```cpp
void loop() {
  float commandedPosition = getCommandedPosition();
  float actualPosition = readEncoderPosition();
  float commandedVelocity = getCommandedVelocity();
  float actualVelocity = estimateVelocityFromEncoder();
  float commandedTorque = getCommandedTorque();
  float estimatedTorque = estimateTorqueFromCurrent();
  float motorCurrent = readMotorCurrent();
  float temperature = readMotorTemperature();
  float loadEstimate = estimateLoad();
  float latencyMs = estimateControlLatencyMs();

  Serial.print("{");
  Serial.print("\"commanded_position\":"); Serial.print(commandedPosition, 4); Serial.print(",");
  Serial.print("\"actual_position\":"); Serial.print(actualPosition, 4); Serial.print(",");
  Serial.print("\"commanded_velocity\":"); Serial.print(commandedVelocity, 4); Serial.print(",");
  Serial.print("\"actual_velocity\":"); Serial.print(actualVelocity, 4); Serial.print(",");
  Serial.print("\"commanded_torque\":"); Serial.print(commandedTorque, 4); Serial.print(",");
  Serial.print("\"estimated_torque\":"); Serial.print(estimatedTorque, 4); Serial.print(",");
  Serial.print("\"motor_current\":"); Serial.print(motorCurrent, 4); Serial.print(",");
  Serial.print("\"temperature\":"); Serial.print(temperature, 4); Serial.print(",");
  Serial.print("\"load_estimate\":"); Serial.print(loadEstimate, 4); Serial.print(",");
  Serial.print("\"control_latency_ms\":"); Serial.print(latencyMs, 4); Serial.print(",");
  Serial.print("\"encoder_position\":"); Serial.print(actualPosition, 4);
  Serial.println("}");

  delay(20); // 50 Hz
}
```

---

## 9. Baseline Workflow

A healthy baseline improves drift detection quality.

### Step 1: Capture a known-good run

Run the actuator under normal load and normal operating conditions.

Recommended baseline capture:

```text
Duration: 60-120 seconds
Sample rate: 50 Hz
Fault condition: none
Load: normal expected load
Temperature: normal operating range
```

### Step 2: Create a baseline

In RASentinel:

1. Open **Diagnostics**.
2. Select the known-good session.
3. Create a baseline.
4. Use a name such as `Bench Servo A1 Known Good Baseline`.

### Step 3: Capture a target run

Run the actuator again under test conditions.

### Step 4: Compare against baseline

Run diagnostics against the target session and select the known-good baseline.

RASentinel will compare the target run against the healthy baseline and produce:

- Drift score.
- Fault classification.
- Severity score.
- Confidence score.
- Evidence signals.
- Maintenance recommendation.

---

## 10. Real-Time Test Plan

Use this procedure for a complete real-time hardware validation.

### 10.1 Pre-Test Checklist

| Item | Expected State |
|---|---|
| Actuator securely mounted | Yes |
| Emergency stop available | Yes |
| Controller limits configured | Yes |
| RASentinel desktop opens | Yes |
| Backend live API reachable | Yes |
| Controller emits JSON lines | Yes |
| Telemetry fields validated | Yes |
| Known-good baseline available | Preferred |

### 10.2 Test Run

1. Start RASentinel desktop.
2. Create or select the actuator record.
3. Start the telemetry bridge.
4. Run the actuator using the controller's normal control software.
5. Confirm live samples appear in RASentinel.
6. Capture at least 1,000 samples.
7. Run diagnosis.
8. Review evidence signals.
9. Generate a report.
10. Save the report for comparison.

### 10.3 Expected Results

Healthy actuator run:

- Low position error.
- Stable current draw.
- Stable temperature rise.
- Low drift score.
- No major fault classification.

Degraded or loaded run:

- Higher position or velocity error.
- Increased current draw.
- Higher temperature rise.
- Increased latency or settling time.
- Elevated drift score.
- Fault classification with evidence.

---

## 11. Validation Criteria

A real actuator integration is considered successful when:

- RASentinel receives live samples continuously.
- At least 1,000 samples can be stored without backend failure.
- Telemetry appears in the Live Telemetry page.
- A diagnostic run completes successfully.
- Evidence signals are populated.
- A report can be generated for the diagnostic result.
- The controller remains responsible for actuation and safety.

---

## 12. Troubleshooting

### No data appears in RASentinel

Check:

- Backend is running.
- Correct actuator ID is used.
- Controller is connected to the correct COM port.
- Serial baud rate matches controller firmware.
- Controller is emitting newline-delimited JSON.
- Windows firewall is not blocking localhost requests.

### JSON parsing errors

Check that each serial line is valid JSON.

Bad:

```text
position=10.0,current=2.4
```

Good:

```json
{"actual_position":10.0,"motor_current":2.4}
```

### Diagnostics look weak or generic

Likely causes:

- Missing current or temperature data.
- No healthy baseline.
- Too few samples.
- Only commanded position is available.
- Actual feedback is noisy or not calibrated.

Recommended fix:

- Add encoder feedback.
- Add current telemetry.
- Capture a known-good baseline.
- Capture longer sessions.

### Position error is always zero

Likely causes:

- `actual_position` is being copied from `commanded_position`.
- Encoder feedback is not being read.
- Unit conversion is missing.

Recommended fix:

- Confirm actual position comes from encoder/controller feedback.
- Verify units: degrees, radians, millimeters, or ticks.
- Convert values consistently before sending to RASentinel.

### Current or temperature is missing

RASentinel can still analyze position and velocity behavior, but classification quality will be lower.

Recommended upgrade:

- Use controller-provided current telemetry when available.
- Add an inline current sensor.
- Add a temperature sensor near the motor or driver.

---

## 13. Production Notes

For a polished hardware demo or lab deployment:

- Use a feedback-capable actuator.
- Capture a healthy baseline first.
- Keep RASentinel read-only.
- Use AppData for local storage.
- Keep raw telemetry and reports on the same machine unless the operator exports them.
- Clearly document actuator units and sensor sources.
- Label every session with test conditions.
- Use separate sessions for baseline, normal-load test, and fault/load test.

---

## 14. Recommended Demo Script

A clean demonstration should follow this sequence:

1. Open RASentinel desktop.
2. Show the actuator registry.
3. Select the physical actuator.
4. Start the controller telemetry bridge.
5. Show live samples arriving.
6. Run a healthy baseline capture.
7. Run a loaded or degraded test capture.
8. Run diagnosis against the baseline.
9. Show fault type, severity, confidence, and evidence.
10. Generate the audit report.

Suggested explanation:

```text
RASentinel receives live actuator telemetry from the controller in read-only mode. The actuator controller remains responsible for motion and safety. RASentinel stores the telemetry locally, extracts robotics diagnostics features, compares behavior against a healthy baseline, classifies likely actuator faults, and generates an evidence-backed maintenance report.
```

---

## 15. Summary

Real servo or actuator integration requires a telemetry bridge between the controller and RASentinel. The controller remains in charge of motion. RASentinel receives telemetry, analyzes actuator behavior, detects drift, classifies faults, and generates reports.

The safest first production path is:

```text
Feedback-capable actuator → controller telemetry → USB/Serial bridge → RASentinel live API → diagnostics report
```

This creates a credible real-time robotics reliability workflow without turning the diagnostics dashboard into an unsafe motor controller.
