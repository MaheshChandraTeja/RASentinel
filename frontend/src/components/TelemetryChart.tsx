import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import type { TelemetrySample } from "../types/domain";

interface TelemetryChartProps {
  samples: TelemetrySample[];
}

export function TelemetryChart({ samples }: TelemetryChartProps) {
  const data = samples.map((sample, index) => ({
    index,
    commanded: sample.commanded_position ?? 0,
    actual: sample.actual_position ?? 0,
    error: sample.error_position ?? 0,
    current: sample.motor_current ?? 0,
    temperature: sample.temperature ?? 0
  }));

  if (samples.length === 0) {
    return (
      <div className="empty-panel">
        No telemetry loaded yet. Add demo telemetry and pretend the actuator behaved itself.
      </div>
    );
  }

  return (
    <div className="chart-shell">
      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="index" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="commanded" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="actual" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="error" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="current" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}