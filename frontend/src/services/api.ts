import type {
  Actuator,
  ActuatorHealthTimelineResponse,
  AuditReportResponse,
  BaselineRead,
  DiagnosisResult,
  DiagnosisRunResponse,
  DiagnosticReportResponse,
  DriftDetectionResponse,
  DuplicateSessionStrategy,
  FaultProfileInfo,
  FeatureExtractionResponse,
  FeatureSetRead,
  HealthResponse,
  LiveRecentTelemetryResponse,
  LiveSessionListResponse,
  LiveSessionRead,
  LiveSessionStartPayload,
  LiveTelemetryBatchResponse,
  ReportGenerationResponse,
  ReportHistoryResponse,
  SessionRun,
  SimulationConfig,
  SimulationImportResponse,
  TelemetrySample
} from "../types/domain";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.toString() ?? "http://127.0.0.1:8000/api/v1";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: isFormData
      ? options.headers
      : {
          "Content-Type": "application/json",
          ...(options.headers ?? {})
        },
    ...options
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    const body = contentType.includes("application/json")
      ? JSON.stringify(await response.json())
      : await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const defaultSimulationConfig: SimulationConfig = {
  fault_profile: "healthy",
  seed: 42,
  sample_rate_hz: 50,
  duration_s: 20,
  commanded_amplitude: 45,
  command_frequency_hz: 0.2,
  nominal_current_a: 2.2,
  nominal_temperature_c: 34,
  nominal_load: 0.45,
  response_time_constant_s: 0.08,
  base_latency_ms: 12,
  sensor_noise_std: 0.04,
  current_noise_std: 0.03,
  temperature_noise_std: 0.05,
  fault_intensity: 0.65
};

export function reportHtmlUrl(diagnosisId: string): string {
  return `${API_BASE_URL}/reports/${diagnosisId}/html`;
}

export const api = {
  health(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  listActuators(): Promise<Actuator[]> {
    return request<Actuator[]>("/actuators");
  },

  createActuator(payload: {
    name: string;
    actuator_type: string;
    location?: string;
    manufacturer?: string;
    model_number?: string;
    serial_number?: string;
  }): Promise<Actuator> {
    return request<Actuator>("/actuators", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  listSessions(actuatorId: string): Promise<SessionRun[]> {
    return request<SessionRun[]>(`/actuators/${actuatorId}/sessions`);
  },

  createSession(actuatorId: string, payload: {
    name: string;
    source?: string;
    tags?: Record<string, unknown>;
  }): Promise<SessionRun> {
    return request<SessionRun>(`/actuators/${actuatorId}/sessions`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  listTelemetry(sessionId: string): Promise<TelemetrySample[]> {
    return request<TelemetrySample[]>(`/sessions/${sessionId}/telemetry?limit=10000`);
  },

  listFaultProfiles(): Promise<FaultProfileInfo[]> {
    return request<FaultProfileInfo[]>("/simulator/fault-profiles");
  },

  importSyntheticTelemetry(payload: {
    actuator_id: string;
    session_name: string;
    duplicate_strategy: DuplicateSessionStrategy;
    config: SimulationConfig;
  }): Promise<SimulationImportResponse> {
    return request<SimulationImportResponse>("/simulator/generate/import", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  simulateTelemetryGateway(payload: {
    actuator_id: string;
    session_name: string;
    duplicate_strategy: DuplicateSessionStrategy;
    config: SimulationConfig;
  }): Promise<SimulationImportResponse> {
    return request<SimulationImportResponse>("/telemetry/simulate", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  importCsvTelemetry(payload: {
    actuatorId: string;
    file: File;
    sessionName: string;
    duplicateStrategy: DuplicateSessionStrategy;
  }): Promise<SimulationImportResponse> {
    const form = new FormData();
    form.append("file", payload.file);
    form.append("session_name", payload.sessionName);
    form.append("duplicate_strategy", payload.duplicateStrategy);
    form.append("source", "frontend_csv_upload");

    return request<SimulationImportResponse>(`/actuators/${payload.actuatorId}/imports/csv`, {
      method: "POST",
      body: form
    });
  },

  importJsonTelemetry(payload: {
    actuatorId: string;
    file: File;
    sessionName: string;
    duplicateStrategy: DuplicateSessionStrategy;
  }): Promise<SimulationImportResponse> {
    const form = new FormData();
    form.append("file", payload.file);
    form.append("session_name", payload.sessionName);
    form.append("duplicate_strategy", payload.duplicateStrategy);
    form.append("source", "frontend_json_upload");

    return request<SimulationImportResponse>(`/actuators/${payload.actuatorId}/imports/json`, {
      method: "POST",
      body: form
    });
  },

  extractFeatures(sessionId: string): Promise<FeatureExtractionResponse> {
    return request<FeatureExtractionResponse>(`/sessions/${sessionId}/features/extract`, {
      method: "POST",
      body: JSON.stringify({ smoothing_window: 5, persist: true })
    });
  },

  getLatestFeatures(sessionId: string): Promise<FeatureSetRead> {
    return request<FeatureSetRead>(`/sessions/${sessionId}/features/latest`);
  },

  listBaselines(actuatorId: string): Promise<BaselineRead[]> {
    return request<BaselineRead[]>(`/actuators/${actuatorId}/baselines`);
  },

  createBaseline(payload: {
    actuatorId: string;
    sessionId: string;
    name: string;
  }): Promise<BaselineRead> {
    return request<BaselineRead>(`/actuators/${payload.actuatorId}/baselines/from-session`, {
      method: "POST",
      body: JSON.stringify({
        session_id: payload.sessionId,
        name: payload.name,
        smoothing_window: 5,
        activate: true
      })
    });
  },

  analyzeDrift(sessionId: string, baselineId?: string): Promise<DriftDetectionResponse> {
    return request<DriftDetectionResponse>(`/sessions/${sessionId}/drift/analyze`, {
      method: "POST",
      body: JSON.stringify({
        baseline_id: baselineId || null,
        smoothing_window: 5,
        persist_diagnosis: true
      })
    });
  },

  runDiagnosis(sessionId: string, baselineId?: string): Promise<DiagnosisRunResponse> {
    return request<DiagnosisRunResponse>(`/diagnostics/run/${sessionId}`, {
      method: "POST",
      body: JSON.stringify({
        baseline_id: baselineId || null,
        smoothing_window: 5,
        persist: true,
        use_isolation_forest: true
      })
    });
  },

  getDiagnosis(diagnosisId: string): Promise<DiagnosisResult> {
    return request<DiagnosisResult>(`/diagnostics/${diagnosisId}`);
  },

  listDiagnoses(sessionId: string): Promise<DiagnosisResult[]> {
    return request<DiagnosisResult[]>(`/sessions/${sessionId}/diagnoses`);
  },

  getActuatorHealthTimeline(actuatorId: string): Promise<ActuatorHealthTimelineResponse> {
    return request<ActuatorHealthTimelineResponse>(`/actuators/${actuatorId}/health`);
  },

  getDiagnosticReport(diagnosisId: string): Promise<DiagnosticReportResponse> {
    return request<DiagnosticReportResponse>(`/reports/${diagnosisId}`);
  },

  getAuditReport(diagnosisId: string, persist = false): Promise<AuditReportResponse> {
    return request<AuditReportResponse>(`/reports/${diagnosisId}/audit?persist=${persist ? "true" : "false"}`);
  },

  generateAuditReport(diagnosisId: string): Promise<ReportGenerationResponse> {
    return request<ReportGenerationResponse>(`/reports/${diagnosisId}/audit`, {
      method: "POST"
    });
  },

  listReportHistory(params: { actuatorId?: string; query?: string; limit?: number } = {}): Promise<ReportHistoryResponse> {
    const search = new URLSearchParams();
    if (params.actuatorId) search.set("actuator_id", params.actuatorId);
    if (params.query) search.set("query", params.query);
    search.set("limit", String(params.limit ?? 50));
    const qs = search.toString();
    return request<ReportHistoryResponse>(`/reports/history${qs ? `?${qs}` : ""}`);
  },

  getReportHtmlUrl(diagnosisId: string): string {
    return reportHtmlUrl(diagnosisId);
  },



  listLiveSessions(params: { actuatorId?: string; status?: string; limit?: number } = {}): Promise<LiveSessionListResponse> {
    const search = new URLSearchParams();
    if (params.actuatorId) search.set("actuator_id", params.actuatorId);
    if (params.status) search.set("status", params.status);
    search.set("limit", String(params.limit ?? 50));
    return request<LiveSessionListResponse>(`/live/sessions?${search.toString()}`);
  },

  startLiveSession(payload: LiveSessionStartPayload): Promise<LiveSessionRead> {
    return request<LiveSessionRead>("/live/sessions", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  getLiveSession(liveSessionId: string): Promise<LiveSessionRead> {
    return request<LiveSessionRead>(`/live/sessions/${liveSessionId}`);
  },

  stopLiveSession(liveSessionId: string): Promise<LiveSessionRead> {
    return request<LiveSessionRead>(`/live/sessions/${liveSessionId}/stop`, {
      method: "POST"
    });
  },

  runLiveDiagnosis(liveSessionId: string): Promise<DiagnosisRunResponse> {
    return request<DiagnosisRunResponse>(`/live/sessions/${liveSessionId}/diagnose`, {
      method: "POST",
      body: JSON.stringify({ smoothing_window: 5, persist: true, use_isolation_forest: true })
    });
  },

  getRecentLiveTelemetry(liveSessionId: string, limit = 500): Promise<LiveRecentTelemetryResponse> {
    return request<LiveRecentTelemetryResponse>(`/live/sessions/${liveSessionId}/telemetry/recent?limit=${limit}`);
  },

  ingestLiveSamples(liveSessionId: string, samples: Array<Record<string, unknown>>, runDiagnosis = false): Promise<LiveTelemetryBatchResponse> {
    return request<LiveTelemetryBatchResponse>(`/live/sessions/${liveSessionId}/samples`, {
      method: "POST",
      body: JSON.stringify({ samples, run_diagnosis: runDiagnosis, smoothing_window: 5 })
    });
  },

  addDemoTelemetry(sessionId: string): Promise<TelemetrySample[]> {
    return request<TelemetrySample[]>(`/sessions/${sessionId}/telemetry`, {
      method: "POST",
      body: JSON.stringify({
        samples: Array.from({ length: 32 }).map((_, index) => {
          const commanded = index * 2;
          const drift = index > 18 ? (index - 18) * 0.08 : 0;
          const actual = commanded - 0.25 - drift;

          return {
            commanded_position: commanded,
            actual_position: actual,
            commanded_velocity: 2,
            actual_velocity: 1.85 - drift * 0.05,
            commanded_torque: 1.2,
            estimated_torque: 1.25 + drift,
            motor_current: 2.1 + drift,
            temperature: 36.5 + drift * 3,
            load_estimate: 0.42,
            control_latency_ms: 16 + drift * 12,
            encoder_position: actual,
            fault_label: drift > 0.4 ? "response_delay" : "none"
          };
        })
      })
    });
  }
};
