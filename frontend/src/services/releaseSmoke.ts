import { navItems } from "../navigation/pages";

export const requiredApiRoutes = [
  "/health",
  "/actuators",
  "/telemetry/import",
  "/telemetry/simulate",
  "/live/sessions",
  "/live/sessions/{live_session_id}/samples",
  "/diagnostics/run/{session_id}",
  "/diagnostics/{diagnosis_id}",
  "/actuators/{actuator_id}/health",
  "/reports/{diagnosis_id}",
  "/release/benchmark"
] as const;

export function getFrontendSmokeSummary() {
  return {
    product: "RASentinel",
    pageCount: navItems.length,
    pages: navItems.map((item) => item.id),
    requiredApiRoutes: [...requiredApiRoutes]
  };
}
