import type { CSSProperties } from "react";

import { healthFromSeverity } from "../utils/format";
import { SeverityBadge } from "./SeverityBadge";

interface HealthScoreCardProps {
  title: string;
  score: number;
  band: string;
  helper: string;
}

export function HealthScoreCard({ title, score, band, helper }: HealthScoreCardProps) {
  const health = healthFromSeverity(score);

  return (
    <article className="health-score-card">
      <div className="health-score-ring" style={{ "--score": `${health}%` } as CSSProperties}>
        <strong>{health.toFixed(0)}</strong>
        <span>Health</span>
      </div>
      <div className="health-score-copy">
        <p>{title}</p>
        <SeverityBadge band={band} score={score} />
        <small>{helper}</small>
      </div>
    </article>
  );
}
