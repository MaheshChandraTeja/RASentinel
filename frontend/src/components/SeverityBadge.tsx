import type { SeverityBand } from "../types/domain";
import { formatNumber, labelize } from "../utils/format";

interface SeverityBadgeProps {
  band?: SeverityBand | string | null;
  score?: number | null;
}

export function SeverityBadge({ band, score }: SeverityBadgeProps) {
  const safeBand = String(band ?? "unknown");
  const scoreText = score !== undefined && score !== null ? `${formatNumber(score, 1)} · ` : "";

  return (
    <span className={`severity-badge severity-badge--${safeBand}`}>
      {scoreText}{labelize(safeBand)}
    </span>
  );
}
