import { useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Upload from "./pages/Upload";
import MapVisualise from "./pages/MapVisualise";
import RiskMonitor from "./pages/RiskMonitor";
import Corpus from "./pages/Corpus";
import DrillMind from "./pages/DrillMind";

import "./App.css";

function App() {
  const [darkMode, setDarkMode] = useState(false);

  const toggleTheme = () => {
    setDarkMode((prev) => !prev);
  };

  return (
    <BrowserRouter>

      <div className={darkMode ? "app dark-mode" : "app light-mode"}>

        <div className="app-body">

          <Sidebar
            darkMode={darkMode}
            toggleTheme={toggleTheme}
          />

          <main className="main-content">

            <Routes>

              <Route
                path="/"
                element={<Dashboard />}
              />

              <Route
                path="/upload"
                element={<Upload />}
              />

              <Route
                path="/map"
                element={<MapVisualise />}
              />

              <Route
                path="/risk-monitor"
                element={<RiskMonitor />}
              />

              <Route
                path="/corpus"
                element={<Corpus />}
              />

              <Route
                path="/drill-mind"
                element={<DrillMind />}
              />

            </Routes>

          </main>

        </div>

      </div>

    </BrowserRouter>
  );
}

export default App;