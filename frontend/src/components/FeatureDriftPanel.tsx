import { useEffect, useState } from "react";

import { api } from "../services/api";
import type { BaselineRead, DriftDetectionResponse, FeatureExtractionResponse } from "../types/domain";

interface FeatureDriftPanelProps {
  actuatorId: string;
  sessionId: string;
  onAnalysisComplete?: () => void;
}

function number(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function FeatureDriftPanel({ actuatorId, sessionId, onAnalysisComplete }: FeatureDriftPanelProps) {
  const [baselines, setBaselines] = useState<BaselineRead[]>([]);
  const [selectedBaselineId, setSelectedBaselineId] = useState<string>("");
  const [features, setFeatures] = useState<FeatureExtractionResponse | null>(null);
  const [drift, setDrift] = useState<DriftDetectionResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");

  async function loadBaselines() {
    if (!actuatorId) {
      setBaselines([]);
      return;
    }
    try {
      const payload = await api.listBaselines(actuatorId);
      setBaselines(payload);
      const active = payload.find((item) => item.is_active) ?? payload[0];
      setSelectedBaselineId(active?.id ?? "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load baselines");
    }
  }

  async function extractFeatures() {
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      const payload = await api.extractFeatures(sessionId);
      setFeatures(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Feature extraction failed.");
    } finally {
      setBusy(false);
    }
  }

  async function createBaseline() {
    if (!actuatorId || !sessionId) return;
    setBusy(true);
    setError("");
    try {
      const baseline = await api.createBaseline({
        actuatorId,
        sessionId,
        name: `Baseline from selected session`
      });
      await loadBaselines();
      setSelectedBaselineId(baseline.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Baseline creation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function analyzeDrift() {
    if (!sessionId) return;
    setBusy(true);
    setError("");
    try {
      const payload = await api.analyzeDrift(sessionId, selectedBaselineId || undefined);
      setDrift(payload);
      onAnalysisComplete?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Drift analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadBaselines();
  }, [actuatorId]);

  useEffect(() => {
    setFeatures(null);
    setDrift(null);
  }, [sessionId]);

  const vector = drift?.features ?? features?.features ?? null;

  return (
    <section className="analysis-panel">
      <div className="panel-title">
        <div>
          <h2>Signal processing & drift detection</h2>
          <p>Extract deterministic robotics features, create healthy baselines, and compare session drift.</p>
        </div>
        {drift ? <span className={`severity-pill severity-pill--${drift.severity_band}`}>{drift.severity_band}</span> : null}
      </div>

      {error ? <div className="error-panel">{error}</div> : null}

      <div className="analysis-actions">
        <button onClick={extractFeatures} disabled={!sessionId || busy}>Extract features</button>
        <button onClick={createBaseline} disabled={!actuatorId || !sessionId || busy}>Create healthy baseline</button>
        <button onClick={analyzeDrift} disabled={!sessionId || busy}>Analyze drift</button>

        <label>
          Baseline
          <select value={selectedBaselineId} onChange={(event) => setSelectedBaselineId(event.target.value)}>
            <option value="">Use active baseline</option>
            {baselines.map((baseline) => (
              <option key={baseline.id} value={baseline.id}>
                {baseline.name} · Q{number(baseline.baseline_quality_score, 0)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {vector ? (
        <div className="feature-grid">
          <div><span>Mean position error</span><strong>{number(vector.mean_position_error)}</strong></div>
          <div><span>Max position error</span><strong>{number(vector.max_position_error)}</strong></div>
          <div><span>Response delay</span><strong>{number(vector.response_delay_ms)} ms</strong></div>
          <div><span>Overshoot</span><strong>{number(vector.overshoot_percent)}%</strong></div>
          <div><span>Settling time</span><strong>{number(vector.settling_time_ms)} ms</strong></div>
          <div><span>Current drift</span><strong>{number(vector.current_drift_percent)}%</strong></div>
          <div><span>Temperature trend</span><strong>{number(vector.temperature_rise_rate, 3)} °C/s</strong></div>
          <div><span>Oscillation</span><strong>{number(vector.oscillation_score)}</strong></div>
          <div><span>Noise level</span><strong>{number(vector.noise_level, 3)}</strong></div>
          <div><span>Health deviation</span><strong>{number(vector.health_deviation_score)}</strong></div>
        </div>
      ) : (
        <div className="empty-panel">No extracted features yet. Run feature extraction to calculate diagnostics-ready metrics.</div>
      )}

      {drift ? (
        <div className="drift-result">
          <div className="drift-score">
            <span>Drift score</span>
            <strong>{number(drift.drift_score, 1)}/100</strong>
          </div>
          <p>{drift.summary}</p>
          <p className="recommendation">{drift.recommendation}</p>

          <div className="evidence-list">
            {drift.evidence.length === 0 ? (
              <div className="empty-panel">No threshold violations were detected for this session.</div>
            ) : drift.evidence.map((item) => (
              <div key={item.signal} className="evidence-card">
                <strong>{item.signal.replaceAll("_", " ")}</strong>
                <span>{item.message}</span>
                <small>
                  observed {number(item.observed)} · baseline {number(item.baseline)} · threshold {number(item.threshold)}
                </small>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
