import { describe, expect, it } from "vitest";

import { isAppPage, navItems } from "../navigation/pages";
import { defaultSimulationConfig, reportHtmlUrl } from "../services/api";
import { getFrontendSmokeSummary, requiredApiRoutes } from "../services/releaseSmoke";


describe("RASentinel frontend smoke checks", () => {
  it("exposes all final MVP pages", () => {
    expect(navItems.map((item) => item.id)).toEqual([
      "dashboard",
      "actuators",
      "import",
      "simulation",
      "live",
      "diagnostics",
      "reports",
      "settings"
    ]);
    expect(isAppPage("diagnostics")).toBe(true);
    expect(isAppPage("banana-lab")).toBe(false);
  });

  it("keeps the default simulator config demo-ready", () => {
    expect(defaultSimulationConfig.sample_rate_hz).toBeGreaterThanOrEqual(1);
    expect(defaultSimulationConfig.duration_s * defaultSimulationConfig.sample_rate_hz).toBeGreaterThanOrEqual(1000);
    expect(defaultSimulationConfig.seed).toBe(42);
  });

  it("tracks API routes needed for the final demo flow", () => {
    expect(requiredApiRoutes).toContain("/telemetry/simulate");
    expect(requiredApiRoutes).toContain("/live/sessions");
    expect(requiredApiRoutes).toContain("/diagnostics/run/{session_id}");
    expect(requiredApiRoutes).toContain("/reports/{diagnosis_id}");
    expect(getFrontendSmokeSummary().pageCount).toBe(8);
  });

  it("builds report html URLs", () => {
    expect(reportHtmlUrl("diag-123")).toContain("/reports/diag-123/html");
  });
});
