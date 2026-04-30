// RASentinel ESP32 serial telemetry example
// Emits one JSON object per line. RASentinel does not command the actuator here;
// the embedded controller remains responsible for motion, limits, and safety.

unsigned long sequenceNumber = 0;
const float sampleRateHz = 50.0;
const unsigned long sampleDelayMs = (unsigned long)(1000.0 / sampleRateHz);

float readEncoderPosition() {
  // Replace with encoder read logic.
  return sin(millis() / 1000.0) * 45.0;
}

float readMotorCurrent() {
  // Replace with ADC/current-sensor read logic.
  return 2.2 + 0.08 * sin(millis() / 700.0);
}

float readMotorTemperature() {
  // Replace with thermistor/driver telemetry.
  return 34.0 + 0.02 * (millis() / 1000.0);
}

void setup() {
  Serial.begin(115200);
}

void loop() {
  const float t = millis() / 1000.0;
  const float commandedPosition = sin(t * 1.256637) * 45.0;
  const float actualPosition = readEncoderPosition();
  const float commandedVelocity = cos(t * 1.256637) * 45.0 * 1.256637;
  const float actualVelocity = commandedVelocity * 0.96;
  const float motorCurrent = readMotorCurrent();
  const float temperature = readMotorTemperature();
  const float latencyMs = 14.0;

  Serial.print("{");
  Serial.print("\"sequence_number\":"); Serial.print(sequenceNumber); Serial.print(",");
  Serial.print("\"monotonic_ms\":"); Serial.print(millis()); Serial.print(",");
  Serial.print("\"commanded_position\":"); Serial.print(commandedPosition, 4); Serial.print(",");
  Serial.print("\"actual_position\":"); Serial.print(actualPosition, 4); Serial.print(",");
  Serial.print("\"commanded_velocity\":"); Serial.print(commandedVelocity, 4); Serial.print(",");
  Serial.print("\"actual_velocity\":"); Serial.print(actualVelocity, 4); Serial.print(",");
  Serial.print("\"motor_current\":"); Serial.print(motorCurrent, 4); Serial.print(",");
  Serial.print("\"temperature\":"); Serial.print(temperature, 4); Serial.print(",");
  Serial.print("\"control_latency_ms\":"); Serial.print(latencyMs, 4); Serial.print(",");
  Serial.print("\"encoder_position\":"); Serial.print(actualPosition, 4);
  Serial.println("}");

  sequenceNumber++;
  delay(sampleDelayMs);
}
