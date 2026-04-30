import type { ReactNode } from "react";

import { navItems, type AppPage } from "../navigation/pages";

interface AppShellProps {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
  children: ReactNode;
}

export type { AppPage };

export function AppShell({ activePage, onNavigate, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup" aria-label="RASentinel">
          <div className="brand-mark" aria-hidden="true">
            <img
              src="./brand/rasentinel-mark.png"
              alt=""
              className="brand-mark-image"
              draggable={false}
            />
          </div>
          <div>
            <strong>RASentinel</strong>
            <span>Robotics reliability</span>
          </div>
        </div>

        <nav className="side-nav" aria-label="Primary navigation">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={item.id === activePage ? "nav-item nav-item--active" : "nav-item"}
              onClick={() => onNavigate(item.id)}
              title={item.description}
            >
              <span className="nav-index">{item.icon}</span>
              <span className="nav-copy">
                <strong>{item.label}</strong>
                <small>{item.description}</small>
              </span>
            </button>
          ))}
        </nav>

        <div className="sidebar-note">
          <span className="status-dot" />
          <div>
            <strong>Local workspace</strong>
            <span>Telemetry, diagnoses, and reports stay on this device.</span>
          </div>
        </div>
      </aside>

      <section className="content-shell">
        <div className="content-frame">{children}</div>
      </section>
    </div>
  );
}
