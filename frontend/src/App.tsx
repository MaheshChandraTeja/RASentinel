import { useEffect, useState } from "react";

import { AppShell } from "./components/AppShell";
import { isAppPage, type AppPage } from "./navigation/pages";
import { ActuatorsPage } from "./pages/ActuatorsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DiagnosticsPage } from "./pages/DiagnosticsPage";
import { ImportTelemetryPage } from "./pages/ImportTelemetryPage";
import { LiveTelemetryPage } from "./pages/LiveTelemetryPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SimulationLabPage } from "./pages/SimulationLabPage";

function getInitialPage(): AppPage {
  const raw = window.location.hash.replace("#", "");
  return isAppPage(raw) ? raw : "dashboard";
}

export default function App() {
  const [activePage, setActivePage] = useState<AppPage>(getInitialPage);

  useEffect(() => {
    const onHashChange = () => setActivePage(getInitialPage());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function navigate(page: AppPage) {
    window.location.hash = page;
    setActivePage(page);
  }

  return (
    <AppShell activePage={activePage} onNavigate={navigate}>
      {activePage === "dashboard" ? <DashboardPage /> : null}
      {activePage === "actuators" ? <ActuatorsPage /> : null}
      {activePage === "import" ? <ImportTelemetryPage /> : null}
      {activePage === "simulation" ? <SimulationLabPage /> : null}
      {activePage === "live" ? <LiveTelemetryPage /> : null}
      {activePage === "diagnostics" ? <DiagnosticsPage /> : null}
      {activePage === "reports" ? <ReportsPage /> : null}
      {activePage === "settings" ? <SettingsPage /> : null}
    </AppShell>
  );
}
