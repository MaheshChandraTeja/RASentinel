import type { ReactNode } from "react";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import type { DriftTimelinePoint, TelemetrySample } from "../types/domain";
import { EmptyState } from "./EmptyState";

type ChartPoint = {
  index: number;
  commanded: number | null;
  actual: number | null;
  positionError: number | null;
  velocityError: number | null;
  current: number | null;
  temperature: number | null;
  latency: number | null;
};

interface TelemetryMultiChartProps {
  samples?: TelemetrySample[];
  timeline?: DriftTimelinePoint[];
  compact?: boolean;
}

export function TelemetryMultiChart({ samples = [], timeline = [], compact = false }: TelemetryMultiChartProps) {
  const data: ChartPoint[] = samples.length > 0
    ? samples.map((sample, index) => ({
        index,
        commanded: sample.commanded_position,
        actual: sample.actual_position,
        positionError: sample.error_position,
        velocityError: sample.error_velocity,
        current: sample.motor_current,
        temperature: sample.temperature,
        latency: sample.control_latency_ms
      }))
    : timeline.map((point, index) => ({
        index,
        commanded: null,
        actual: null,
        positionError: point.position_error,
        velocityError: point.velocity_error,
        current: point.motor_current,
        temperature: point.temperature,
        latency: point.latency_ms
      }));

  if (data.length === 0) {
    return (
      <EmptyState
        title="No telemetry data"
        message="Import or simulate a telemetry session to display signal charts."
      />
    );
  }

  const chartHeight = compact ? 188 : 252;

  return (
    <div className={compact ? "chart-grid chart-grid--compact" : "chart-grid"}>
      <ChartPanel title="Position tracking" helper="Commanded vs actual position">
        <ResponsiveContainer width="100%" height={chartHeight}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="index" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ borderRadius: 12 }} />
            <Line type="monotone" dataKey="commanded" name="Commanded" stroke="var(--chart-a)" strokeWidth={2.4} dot={false} />
            <Line type="monotone" dataKey="actual" name="Actual" stroke="var(--chart-b)" strokeWidth={2.4} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </ChartPanel>

      <ChartPanel title="Error signals" helper="Position and velocity error">
        <ResponsiveContainer width="100%" height={chartHeight}>
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="index" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ borderRadius: 12 }} />
            <Area type="monotone" dataKey="positionError" name="Position error" stroke="var(--chart-c)" fill="var(--chart-c)" strokeWidth={2.2} fillOpacity={0.2} />
            <Area type="monotone" dataKey="velocityError" name="Velocity error" stroke="var(--chart-d)" fill="var(--chart-d)" strokeWidth={2.2} fillOpacity={0.12} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartPanel>

      <ChartPanel title="Load and thermal behavior" helper="Current and temperature trend">
        <ResponsiveContainer width="100%" height={chartHeight}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="index" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ borderRadius: 12 }} />
            <Line type="monotone" dataKey="current" name="Current" stroke="var(--chart-e)" strokeWidth={2.4} dot={false} />
            <Line type="monotone" dataKey="temperature" name="Temperature" stroke="var(--chart-f)" strokeWidth={2.4} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </ChartPanel>

      <ChartPanel title="Control latency" helper="Estimated response timing">
        <ResponsiveContainer width="100%" height={chartHeight}>
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="index" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ borderRadius: 12 }} />
            <Area type="monotone" dataKey="latency" name="Latency" stroke="var(--chart-g)" fill="var(--chart-g)" strokeWidth={2.2} fillOpacity={0.2} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartPanel>
    </div>
  );
}

function ChartPanel({ title, helper, children }: { title: string; helper: string; children: ReactNode }) {
  return (
    <section className="chart-panel">
      <div className="chart-panel-header">
        <h3>{title}</h3>
        <span>{helper}</span>
      </div>
      {children}
    </section>
  );
}
