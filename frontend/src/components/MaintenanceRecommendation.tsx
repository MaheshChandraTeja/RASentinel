interface MaintenanceRecommendationProps {
  recommendation?: string | null;
}

export function MaintenanceRecommendation({ recommendation }: MaintenanceRecommendationProps) {
  return (
    <section className="recommendation-card">
      <p className="eyebrow">Recommended action</p>
      <h3>{recommendation ? "Maintenance guidance" : "No recommendation available"}</h3>
      <p>
        {recommendation ??
          "Run diagnostics on a telemetry session to generate maintenance guidance and supporting evidence."}
      </p>
    </section>
  );
}
