import {
  LayoutDashboard,
  Upload,
  Map,
  ShieldAlert,
  Database,
  Brain,
  Moon,
  Sun,
} from "lucide-react";

import { NavLink } from "react-router-dom";

function Sidebar({ darkMode, toggleTheme }) {

  const menuItems = [
    {
      name: "Dashboard",
      icon: LayoutDashboard,
      path: "/",
    },
    {
      name: "Upload",
      icon: Upload,
      path: "/upload",
    },
    {
      name: "Map Visualise",
      icon: Map,
      path: "/map",
    },
    {
      name: "Risk Monitor",
      icon: ShieldAlert,
      path: "/risk-monitor",
    },
    {
      name: "Corpus",
      icon: Database,
      path: "/corpus",
    },
    {
      name: "Drill Mind",
      icon: Brain,
      path: "/drill-mind",
    },
  ];

  return (
    <aside className="sidebar">

      {/* =========================================
          BRAND
      ========================================= */}

      <div className="sidebar-brand">

        <div className="sidebar-brand-icon">
          <span>💧</span>
        </div>

        <div>
          <h2>eRTMAC-NWIS</h2>
          <p>Nearby Wells Intelligence</p>
        </div>

      </div>


      {/* =========================================
          MENU
      ========================================= */}

      <div className="sidebar-title">
        <span>MENU</span>
      </div>

      <nav className="sidebar-menu">

        {menuItems.map((item) => {

          const Icon = item.icon;

          return (
            <NavLink
              key={item.name}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) =>
                `menu-item ${isActive ? "active" : ""}`
              }
            >

              <Icon size={19} />

              <span>{item.name}</span>

            </NavLink>
          );

        })}

      </nav>


      {/* =========================================
          DARK / LIGHT MODE
      ========================================= */}

      <div className="theme-section">

        <div className="theme-label">

          {darkMode ? (
            <Sun size={17} />
          ) : (
            <Moon size={17} />
          )}

          <span>
            {darkMode ? "Light Mode" : "Dark Mode"}
          </span>

        </div>


        <button
          className={`theme-switch ${
            darkMode ? "active" : ""
          }`}
          onClick={toggleTheme}
          aria-label="Toggle dark mode"
        >

          <span className="theme-switch-circle"></span>

        </button>

      </div>


      {/* =========================================
          SYSTEM STATUS
      ========================================= */}

      <div className="sidebar-footer">

        <div className="system-status">

          <span className="status-dot"></span>

          <div>
            <strong>System Online</strong>
            <small>NWIS Platform</small>
          </div>

        </div>

        <div className="sidebar-version">
          eRTMAC-NWIS v1.0
        </div>

      </div>

    </aside>
  );
}

export default Sidebar;