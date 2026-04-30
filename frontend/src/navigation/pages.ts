export type AppPage =
  | "dashboard"
  | "actuators"
  | "import"
  | "simulation"
  | "live"
  | "diagnostics"
  | "reports"
  | "settings";

export interface NavItem {
  id: AppPage;
  label: string;
  icon: string;
  description: string;
}

export const navItems: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: "01", description: "Fleet health overview" },
  { id: "actuators", label: "Actuators", icon: "02", description: "Registered motors and joints" },
  { id: "import", label: "Import", icon: "03", description: "Load telemetry files" },
  { id: "simulation", label: "Simulation", icon: "04", description: "Generate test runs" },
  { id: "live", label: "Live Telemetry", icon: "05", description: "Monitor controller streams" },
  { id: "diagnostics", label: "Diagnostics", icon: "06", description: "Classify actuator faults" },
  { id: "reports", label: "Reports", icon: "07", description: "Audit reports and history" },
  { id: "settings", label: "Settings", icon: "08", description: "Storage and workflow" }
];

export const pageIds = new Set<AppPage>(navItems.map((item) => item.id));

export function isAppPage(value: string): value is AppPage {
  return pageIds.has(value as AppPage);
}
