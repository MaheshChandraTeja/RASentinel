export type ActuatorType =
  | "servo"
  | "dc_motor"
  | "stepper"
  | "linear"
  | "hydraulic"
  | "pneumatic"
  | "unknown";

export type HealthStatus =
  | "healthy"
  | "watch"
  | "degraded"
  | "critical"
  | "unknown";

export type FaultLabel =
  | "none"
  | "friction_increase"
  | "backlash"
  | "response_delay"
  | "overshoot"
  | "oscillation"
  | "current_spike"
  | "thermal_rise"
  | "encoder_inconsistency"
  | "load_anomaly"
  | "encoder_fault"
  | "motor_weakening"
  | "thermal_stress"
  | "control_instability"
  | "delayed_response"
  | "unknown_anomaly"
  | "unknown";

export type SeverityBand = "none" | "low" | "medium" | "high" | "critical";

export type DuplicateSessionStrategy = "reject" | "create_new" | "replace";

export type SimulationFaultProfile =
  | "healthy"
  | "friction_increase"
  | "backlash"
  | "encoder_noise"
  | "motor_weakening"
  | "overheating"
  | "delayed_response"
  | "load_imbalance"
  | "oscillation_control_instability"
  | "current_spike_anomaly";

export interface HealthResponse {
  app: string;
  status: string;
  database: string;
  environment: string;
}

export interface Actuator {
  id: string;
  name: string;
  actuator_type: ActuatorType;
  manufacturer: string | null;
  model_number: string | null;
  serial_number: string | null;
  location: string | null;
  rated_torque_nm: number | null;
  rated_current_a: number | null;
  rated_voltage_v: number | null;
  health_status: HealthStatus;
  created_at: string;
  updated_at: string;
}

export interface SessionRun {
  id: string;
  actuator_id: string;
  name: string;
  source: string;
  notes: string | null;
  started_at: string;
  ended_at: string | null;
  sample_count: number;
  tags: Record<string, unknown>;
}

export interface TelemetrySample {
  id: number;
  session_id: string;
  actuator_id: string;
  timestamp: string;
  commanded_position: number | null;
  actual_position: number | null;
  commanded_velocity: number | null;
  actual_velocity: number | null;
  motor_current: number | null;
  temperature: number | null;
  control_latency_ms: number | null;
  error_position: number | null;
  error_velocity: number | null;
  fault_label: FaultLabel;
}

export interface DiagnosisResult {
  id: string;
  session_id: string;
  actuator_id: string;
  diagnosis_time: string;
  fault_label: FaultLabel;
  severity_score: number;
  severity_band: SeverityBand;
  confidence_score: number;
  summary: string;
  recommendation: string | null;
  evidence: Record<string, unknown>;
  created_at: string;
}

export interface SimulationConfig {
  fault_profile: SimulationFaultProfile;
  seed: number | null;
  sample_rate_hz: number;
  duration_s: number;
  commanded_amplitude: number;
  command_frequency_hz: number;
  nominal_current_a: number;
  nominal_temperature_c: number;
  nominal_load: number;
  response_time_constant_s: number;
  base_latency_ms: number;
  sensor_noise_std: number;
  current_noise_std: number;
  temperature_noise_std: number;
  fault_intensity: number;
}

export interface SimulationMetadata {
  fault_profile: SimulationFaultProfile;
  fault_label: FaultLabel;
  seed: number | null;
  sample_rate_hz: number;
  duration_s: number;
  sample_count: number;
  generated_by: string;
}

export interface SimulationImportResponse {
  import_job_id: string;
  actuator_id: string;
  session_id: string;
  session_name: string;
  source_format: "csv" | "json" | "synthetic";
  duplicate_strategy: DuplicateSessionStrategy;
  rows_received: number;
  rows_imported: number;
  rows_failed: number;
  status: string;
  errors: Array<{ row: number | null; field: string | null; message: string }>;
  created_at: string;
  metadata?: SimulationMetadata;
}

export interface FaultProfileInfo {
  key: SimulationFaultProfile;
  label: string;
  description: string;
  expected_pattern: string;
}

export interface FeatureVector {
  sample_count: number;
  duration_ms: number;
  mean_position_error: number;
  max_position_error: number;
  mean_velocity_error: number;
  max_velocity_error: number;
  response_delay_ms: number;
  overshoot_percent: number;
  settling_time_ms: number;
  steady_state_error: number;
  current_drift_percent: number;
  temperature_rise_rate: number;
  error_variance: number;
  noise_level: number;
  oscillation_score: number;
  health_deviation_score: number;
  commanded_position_range: number;
  actual_position_range: number;
  mean_motor_current: number;
  max_motor_current: number;
  mean_temperature: number;
  max_temperature: number;
  mean_latency_ms: number;
  max_latency_ms: number;
}

export interface FeatureExtractionResponse {
  session_id: string;
  actuator_id: string;
  persisted: boolean;
  feature_set_id: string | null;
  features: FeatureVector;
}

export interface FeatureSetRead {
  id: string;
  session_id: string;
  actuator_id: string;
  generated_at: string;
  algorithm_version: string;
  smoothing_window: number;
  sample_count: number;
  duration_ms: number;
  mean_position_error: number;
  max_position_error: number;
  mean_velocity_error: number;
  max_velocity_error: number;
  response_delay_ms: number;
  overshoot_percent: number;
  settling_time_ms: number;
  steady_state_error: number;
  current_drift_percent: number;
  temperature_rise_rate: number;
  error_variance: number;
  noise_level: number;
  oscillation_score: number;
  health_deviation_score: number;
  feature_vector: Record<string, unknown>;
  baseline_comparison: Record<string, unknown>;
}

export interface BaselineRead {
  id: string;
  actuator_id: string;
  source_session_id: string;
  source_feature_set_id: string | null;
  name: string;
  notes: string | null;
  algorithm_version: string;
  sample_count: number;
  baseline_quality_score: number;
  features: Record<string, number>;
  thresholds: Record<string, unknown>;
  metadata: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DriftEvidenceItem {
  signal: string;
  observed: number;
  baseline: number;
  threshold: number;
  z_score: number;
  contribution: number;
  message: string;
}

export interface DriftDetectionResponse {
  session_id: string;
  actuator_id: string;
  baseline_id: string;
  drift_score: number;
  severity_band: SeverityBand;
  is_drifted: boolean;
  feature_set_id: string | null;
  diagnosis_id: string | null;
  summary: string;
  recommendation: string;
  features: FeatureVector;
  evidence: DriftEvidenceItem[];
}

export interface FaultEvidenceItem {
  signal: string;
  score: number;
  observed: number | null;
  expected: number | null;
  message: string;
  recommendation: string | null;
}

export interface FaultClassificationResult {
  fault_label: FaultLabel;
  confidence_score: number;
  severity_score: number;
  severity_band: SeverityBand;
  anomaly_score: number;
  classifier_version: string;
  summary: string;
  recommendation: string;
  evidence: FaultEvidenceItem[];
  rule_hits: string[];
  model_used: string;
}

export interface DiagnosisRunResponse {
  session_id: string;
  actuator_id: string;
  diagnosis_id: string | null;
  feature_set_id: string | null;
  baseline_id: string | null;
  drift_score: number | null;
  diagnosis: DiagnosisResult | null;
  classification: FaultClassificationResult;
  features: FeatureVector;
  report_url: string | null;
}

export interface HealthTimelinePoint {
  timestamp: string;
  session_id: string | null;
  diagnosis_id: string | null;
  feature_set_id: string | null;
  severity_score: number;
  severity_band: SeverityBand;
  health_status: HealthStatus;
  fault_label: FaultLabel;
  summary: string;
  metrics: Record<string, unknown>;
}

export interface ActuatorHealthTimelineResponse {
  actuator_id: string;
  actuator_name: string;
  current_health_status: HealthStatus;
  points: HealthTimelinePoint[];
}

export interface DiagnosticReportResponse {
  diagnosis_id: string;
  generated_at: string;
  actuator: Record<string, unknown>;
  session: Record<string, unknown>;
  diagnosis: DiagnosisResult;
  features: Record<string, unknown>;
  baseline: Record<string, unknown> | null;
  classification: Record<string, unknown>;
  drift: Record<string, unknown> | null;
  maintenance_action: string;
  audit: Record<string, unknown>;
}

export interface EvidenceSignal {
  signal: string;
  score: number;
  observed: number | null;
  expected: number | null;
  message: string;
  recommendation: string | null;
}

export interface DriftTimelinePoint {
  timestamp: string;
  position_error: number | null;
  velocity_error: number | null;
  motor_current: number | null;
  temperature: number | null;
  latency_ms: number | null;
  fault_label: FaultLabel | string | null;
}

export interface AuditReportResponse {
  diagnosis_id: string;
  generated_at: string;
  title: string;
  actuator_information: Record<string, unknown>;
  telemetry_session_summary: Record<string, unknown>;
  detected_fault: Record<string, unknown>;
  severity_and_confidence: Record<string, unknown>;
  evidence_signals: EvidenceSignal[];
  drift_timeline: DriftTimelinePoint[];
  recommended_action: string;
  technical_notes: string[];
  diagnosis_history_count: number;
  report_record_id: string | null;
  html_url: string;
}

export interface ReportRecordRead {
  id: string;
  diagnosis_id: string;
  actuator_id: string;
  session_id: string;
  title: string;
  report_format: string;
  file_path: string | null;
  content_hash: string;
  fault_label: string;
  severity_band: string;
  summary: string;
  generated_at: string;
}

export interface ReportHistoryResponse {
  items: ReportRecordRead[];
  total: number;
  query: string | null;
}

export interface ReportGenerationResponse {
  record: ReportRecordRead;
  audit_report: AuditReportResponse;
}


export type LiveControllerTransport =
  | "http_bridge"
  | "serial"
  | "ros2"
  | "can"
  | "modbus"
  | "opc_ua"
  | "plc"
  | "custom";

export type LiveSessionStatus = "active" | "paused" | "stopped" | "error";

export interface LiveLatestMetrics {
  latest_timestamp: string | null;
  sample_count: number;
  batch_count: number;
  last_sequence: number | null;
  commanded_position: number | null;
  actual_position: number | null;
  position_error: number | null;
  velocity_error: number | null;
  motor_current: number | null;
  temperature: number | null;
  control_latency_ms: number | null;
  health_deviation_score: number | null;
  rolling_mean_position_error: number | null;
  rolling_max_position_error: number | null;
  rolling_mean_current: number | null;
  rolling_mean_temperature: number | null;
}

export interface LiveSessionRead {
  id: string;
  actuator_id: string;
  session_id: string;
  controller_name: string;
  controller_type: string;
  transport: LiveControllerTransport | string;
  endpoint: string | null;
  status: LiveSessionStatus | string;
  sample_rate_hint_hz: number | null;
  min_diagnosis_samples: number;
  auto_extract_features: boolean;
  auto_diagnose_every_n_samples: number | null;
  batch_count: number;
  sample_count: number;
  last_sequence: number | null;
  latest_metrics: Record<string, unknown>;
  connection_metadata: Record<string, unknown>;
  last_error: string | null;
  started_at: string;
  last_seen_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LiveSessionListResponse {
  items: LiveSessionRead[];
  total: number;
}

export interface LiveSessionStartPayload {
  actuator_id: string;
  session_name: string;
  duplicate_strategy: DuplicateSessionStrategy;
  controller_name: string;
  controller_type: string;
  transport: LiveControllerTransport;
  endpoint?: string | null;
  sample_rate_hint_hz?: number | null;
  min_diagnosis_samples?: number;
  auto_extract_features?: boolean;
  auto_diagnose_every_n_samples?: number | null;
  notes?: string | null;
  tags?: Record<string, unknown>;
  connection_metadata?: Record<string, unknown>;
}

export interface LiveTelemetryBatchResponse {
  live_session: LiveSessionRead;
  rows_received: number;
  rows_imported: number;
  rows_failed: number;
  latest_metrics: LiveLatestMetrics;
  rolling_features: FeatureVector | null;
  diagnosis: DiagnosisRunResponse | null;
  errors: string[];
}

export interface LiveRecentTelemetryResponse {
  live_session_id: string;
  session_id: string;
  samples: TelemetrySample[];
}
