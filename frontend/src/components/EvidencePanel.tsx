import type { EvidenceSignal, FaultEvidenceItem } from "../types/domain";
import { formatNumber, labelize } from "../utils/format";
import { EmptyState } from "./EmptyState";

type EvidenceLike = EvidenceSignal | FaultEvidenceItem;

interface EvidencePanelProps {
  evidence: EvidenceLike[];
}

export function EvidencePanel({ evidence }: EvidencePanelProps) {
  if (!evidence.length) {
    return (
      <EmptyState
        title="No evidence available"
        message="Run diagnostics to populate the evidence panel with signal-level findings."
      />
    );
  }

  return (
    <div className="evidence-list">
      {evidence.map((item, index) => (
        <article className="evidence-item" key={`${item.signal}-${index}`}>
          <div>
            <strong>{labelize(item.signal)}</strong>
            <p>{item.message}</p>
            {item.recommendation ? <small>{item.recommendation}</small> : null}
          </div>
          <div className="evidence-score">
            <span>{formatNumber(item.score, 1)}</span>
            <small>score</small>
          </div>
        </article>
      ))}
    </div>
  );
}
