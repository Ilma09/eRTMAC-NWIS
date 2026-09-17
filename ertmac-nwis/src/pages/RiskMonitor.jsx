import { useEffect, useState } from "react";
import {
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  MapPin,
  Activity,
  Ruler,
  Gauge,
  Crosshair,
  Layers,
  GitCompareArrows,
} from "lucide-react";

import api from "../api/client";

import "./RiskMonitor.css";

/* Real severity domain (src/database.py): HIGH | CRITICAL | MEDIUM. Mapped
   onto the existing low/moderate/high/critical badge styles rather than
   inventing new ones - MEDIUM reads as "moderate", anything unexpected
   falls back to the neutral "low" look instead of breaking. */
const severityToClass = (severity) => {
  const value = (severity || "").toUpperCase();
  if (value === "CRITICAL") return "critical";
  if (value === "HIGH") return "high";
  if (value === "MEDIUM") return "moderate";
  return "low";
};

/* =====================================================
   WELL COMPARISON - lets the user pick wells directly
   (no coordinates required) and correlates their real
   depth/formation/mud-type/hazard data against each
   other. Built specifically because most of the real
   corpus has no verified coordinates, so the radius-based
   check above can't reach most wells at all.
===================================================== */

function WellComparisonPanel() {
  const [wells, setWells] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);

  const [comparing, setComparing] = useState(false);
  const [compareResult, setCompareResult] = useState(null);
  const [compareError, setCompareError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    api
      .get("/api/wells")
      .then((res) => {
        if (!cancelled) setWells(res.data);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError("Could not reach the backend. Is the server running?");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const toggleWell = (id) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const runCompare = async () => {
    if (selectedIds.length < 2) {
      alert("Select at least 2 wells to compare.");
      return;
    }

    setComparing(true);
    setCompareError(null);

    try {
      const res = await api.post("/api/wells/compare", { well_ids: selectedIds });
      setCompareResult(res.data);
    } catch (err) {
      setCompareError(
        err.response?.data?.detail ||
          "Could not run the comparison. Is the backend running?"
      );
      setCompareResult(null);
    } finally {
      setComparing(false);
    }
  };

  if (loading) {
    return (
      <div className="prediction-info-card">
        <div className="prediction-info-icon">
          <Activity size={20} />
        </div>
        <div>
          <strong>Loading wells...</strong>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="risk-alert-panel">
        <div className="alert-icon">
          <AlertTriangle size={21} />
        </div>
        <div className="alert-content">
          <strong>Could not load wells</strong>
          <p>{loadError}</p>
        </div>
      </div>
    );
  }

  return (
    <>

      <div className="risk-card" style={{ marginBottom: 18 }}>

        <div className="risk-card-header">
          <div>
            <span>WELL COMPARISON</span>
            <h2>Select Wells to Correlate</h2>
          </div>
          <GitCompareArrows size={20} />
        </div>

        <p style={{ marginTop: 0, marginBottom: 12, fontSize: 9, color: "var(--text-muted)" }}>
          Works on any well in the corpus, whether or not its coordinates
          were ever verified - pick 2 or more to compare their depth,
          formation, mud type, and recorded hazards.
        </p>

        <div className="well-compare-list">

          {wells.length === 0 ? (
            <p style={{ fontSize: 10, color: "var(--text-muted)" }}>
              No wells in the corpus yet.
            </p>
          ) : (
            wells.map((well) => (
              <label className="well-compare-item" key={well.id}>
                <input
                  type="checkbox"
                  checked={selectedIds.includes(well.id)}
                  onChange={() => toggleWell(well.id)}
                />
                <div>
                  <strong>{well.name}</strong>
                  <span>
                    {well.location}
                    {well.depth ? ` · ${well.depth} m` : ""}
                    {well.formation ? ` · ${well.formation}` : ""}
                    {well.mud_type ? ` · ${well.mud_type}` : ""}
                  </span>
                </div>
              </label>
            ))
          )}

        </div>

        <button
          type="button"
          className="radius-apply-btn"
          style={{ marginTop: 12 }}
          onClick={runCompare}
          disabled={comparing || selectedIds.length < 2}
        >
          {comparing ? "Comparing..." : `Compare Selected (${selectedIds.length})`}
        </button>

      </div>


      {compareError && (

        <div className="risk-alert-panel" style={{ marginBottom: 18 }}>
          <div className="alert-icon">
            <AlertTriangle size={21} />
          </div>
          <div className="alert-content">
            <strong>Comparison failed</strong>
            <p>{compareError}</p>
          </div>
        </div>

      )}

      {compareResult && (

        <>

          {compareResult.shared_hazard_types.length > 0 && (

            <div className="risk-alert-panel" style={{ marginBottom: 18 }}>
              <div className="alert-icon">
                <AlertTriangle size={21} />
              </div>
              <div className="alert-content">
                <strong>Recurring risk pattern found</strong>
                <p>
                  {compareResult.shared_hazard_types
                    .map((s) => `"${s.hazard_type}" appears on ${s.well_count} of the selected wells`)
                    .join(" · ")}
                </p>
              </div>
            </div>

          )}

          {compareResult.formation_hazard_correlation && compareResult.formation_hazard_correlation.length > 0 && (

            <div className="risk-alert-panel" style={{ marginBottom: 18 }}>
              <div className="alert-icon">
                <Layers size={21} />
              </div>
              <div className="alert-content">
                <strong>Formation-specific risk correlation</strong>
                <p>
                  {compareResult.formation_hazard_correlation
                    .map(
                      (s) =>
                        `"${s.hazard_type}" appears on ${s.well_count} wells sharing the ${s.formation} formation`
                    )
                    .join(" · ")}
                </p>
              </div>
            </div>

          )}

          {compareResult.wells.map((well) => (

            <div className="risk-card zones-card" key={well.id} style={{ marginBottom: 14 }}>

              <div className="risk-card-header">
                <div>
                  <span>{well.location}</span>
                  <h2>{well.name}</h2>
                </div>
                <Layers size={20} />
              </div>

              <div className="well-compare-facts">
                <div>
                  <span>Depth</span>
                  <strong>{well.depth ? `${well.depth} m` : "Unknown"}</strong>
                </div>
                <div>
                  <span>Formation</span>
                  <strong>{well.formation || "Unknown"}</strong>
                </div>
                <div>
                  <span>Mud Type</span>
                  <strong>{well.mud_type || "Unknown"}</strong>
                </div>
                <div>
                  <span>Mud Weight</span>
                  <strong>{well.mud_weight || "Unknown"}</strong>
                </div>
                <div>
                  <span>Status</span>
                  <strong>{well.status}</strong>
                </div>
                <div>
                  <span>Reservoir Characteristics</span>
                  <strong>{well.reservoir_notes || "Unknown"}</strong>
                </div>
                <div>
                  <span>Casing Program</span>
                  <strong>{well.casing_notes || "Unknown"}</strong>
                </div>
                <div>
                  <span>Cementing Practice</span>
                  <strong>{well.cementing_notes || "Unknown"}</strong>
                </div>
              </div>

              {well.hazards.length === 0 ? (

                <p style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 10 }}>
                  No hazards recorded on this well.
                </p>

              ) : (

                <div className="risk-table" style={{ marginTop: 10 }}>

                  <div className="risk-table-header">
                    <span>HAZARD TYPE</span>
                    <span>DEPTH</span>
                    <span>SEVERITY</span>
                    <span>CONFIDENCE</span>
                    <span>PAGE</span>
                    <span></span>
                  </div>

                  {well.hazards.map((hazard, index) => (

                    <div className="risk-table-row" key={index}>

                      <span className="zone-location">{hazard.hazard_type}</span>

                      <span className="zone-location">
                        <Ruler size={13} />
                        {hazard.depth_m} m
                      </span>

                      <div className="zone-score">
                        <span className={`risk-badge ${severityToClass(hazard.severity)}`}>
                          {hazard.severity}
                        </span>
                      </div>

                      <span className="well-count">{hazard.confidence}</span>

                      <span className="well-count">{hazard.page_num}</span>

                      <span></span>

                    </div>

                  ))}

                </div>

              )}

            </div>

          ))}

        </>

      )}

    </>
  );
}

function RiskMonitor() {
  const [activeTab, setActiveTab] = useState("proximity");

  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [depth, setDepth] = useState("");

  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);
  const [checkError, setCheckError] = useState(null);

  const runCheck = async (e) => {
    e.preventDefault();

    const latNum = Number(lat);
    const lngNum = Number(lng);
    const depthNum = Number(depth);

    if (lat === "" || Number.isNaN(latNum) || latNum < -90 || latNum > 90) {
      alert("Please enter a valid latitude between -90 and 90.");
      return;
    }

    if (lng === "" || Number.isNaN(lngNum) || lngNum < -180 || lngNum > 180) {
      alert("Please enter a valid longitude between -180 and 180.");
      return;
    }

    if (depth === "" || Number.isNaN(depthNum) || depthNum < 0) {
      alert("Please enter a valid bit depth in metres.");
      return;
    }

    setChecking(true);
    setCheckError(null);

    try {
      const res = await api.post("/api/risk/telemetry", {
        lat: latNum,
        lng: lngNum,
        bit_depth_m: depthNum,
      });
      setResult(res.data);
    } catch (err) {
      setCheckError(
        err.response?.data?.detail ||
          "Could not run the check. Is the backend running?"
      );
      setResult(null);
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="risk-monitor-page">

      {/* =====================================================
          HEADER
      ===================================================== */}

      <div className="risk-header">

        <div>
          <span className="risk-eyebrow">
            eRTMAC-NWIS / DRILLING RISK INTELLIGENCE
          </span>

          <h1>Drilling Risk Monitor</h1>

          <p>
            Check a rig's current position and bit depth against
            historical offset-well hazards from drilling reports.
          </p>
        </div>

        <div className="risk-header-status">
          <span className="risk-online-dot"></span>
          Predictive Engine Active
        </div>

      </div>


      {/* =====================================================
          TABS
      ===================================================== */}

      <div className="risk-tabs">

        <button
          type="button"
          className={`risk-tab ${activeTab === "proximity" ? "active" : ""}`}
          onClick={() => setActiveTab("proximity")}
        >
          <Crosshair size={14} />
          Hazard Proximity Check
        </button>

        <button
          type="button"
          className={`risk-tab ${activeTab === "compare" ? "active" : ""}`}
          onClick={() => setActiveTab("compare")}
        >
          <GitCompareArrows size={14} />
          Well Comparison
        </button>

      </div>


      {activeTab === "proximity" && (

        <>

          {/* =====================================================
              TELEMETRY CHECK FORM
          ===================================================== */}

          <div className="risk-card" style={{ marginBottom: 18 }}>

            <div className="risk-card-header">

              <div>
                <span>LIVE HAZARD CHECK</span>
                <h2>Rig Position &amp; Bit Depth</h2>
              </div>

              <Crosshair size={20} />

            </div>

            <form
              onSubmit={runCheck}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr 1fr auto",
                gap: 12,
                alignItems: "end",
              }}
            >

              <div className="form-field">
                <label>Latitude</label>
                <input
                  type="number"
                  step="any"
                  placeholder="23.2443"
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                />
              </div>

              <div className="form-field">
                <label>Longitude</label>
                <input
                  type="number"
                  step="any"
                  placeholder="72.5036"
                  value={lng}
                  onChange={(e) => setLng(e.target.value)}
                />
              </div>

              <div className="form-field">
                <label>Bit Depth (m)</label>
                <input
                  type="number"
                  step="any"
                  placeholder="3450"
                  value={depth}
                  onChange={(e) => setDepth(e.target.value)}
                />
              </div>

              <button
                type="submit"
                className="radius-apply-btn"
                style={{ height: 32 }}
                disabled={checking}
              >
                {checking ? "Checking..." : "Check Hazards"}
              </button>

            </form>

            <p
              style={{
                marginTop: 10,
                marginBottom: 0,
                fontSize: 9,
                color: "var(--text-muted)",
              }}
            >
              Searches offset wells within a 10 km radius and a ±50 m depth
              window of the entered bit depth.
            </p>

          </div>


          {/* =====================================================
              RESULTS
          ===================================================== */}

          {checkError && (

            <div className="risk-alert-panel" style={{ marginBottom: 18 }}>
              <div className="alert-icon">
                <AlertTriangle size={21} />
              </div>
              <div className="alert-content">
                <strong>Check failed</strong>
                <p>{checkError}</p>
              </div>
            </div>

          )}

          {!result && !checkError && (

            <div className="prediction-info-card">
              <div className="prediction-info-icon">
                <Activity size={20} />
              </div>
              <div>
                <strong>No check run yet</strong>
                <p>
                  Enter a rig's position and bit depth above to check for
                  nearby historical drilling hazards.
                </p>
              </div>
            </div>

          )}

          {result && (

            <>

              <div
                className="risk-alert-panel"
                style={
                  !result.triggered
                    ? {
                        border: "1px solid #bbf7d0",
                        background:
                          "linear-gradient(90deg, #f0fdf4, var(--bg-card))",
                      }
                    : undefined
                }
              >
                <div
                  className="alert-icon"
                  style={
                    !result.triggered
                      ? { background: "#dcfce7", color: "#16a34a" }
                      : undefined
                  }
                >
                  {result.triggered ? (
                    <AlertTriangle size={21} />
                  ) : (
                    <CheckCircle2 size={21} />
                  )}
                </div>
                <div className="alert-content">
                  <strong>
                    {result.triggered
                      ? `${result.alerts.length} hazard${
                          result.alerts.length === 1 ? "" : "s"
                        } found nearby`
                      : "No hazards found nearby"}
                  </strong>
                  <p>
                    {result.triggered
                      ? "Review the wells below before proceeding with drilling operations."
                      : "No offset-well hazards were recorded within range of this position and depth."}
                  </p>
                </div>
              </div>


              {result.triggered && (

                <div className="risk-card zones-card" style={{ marginTop: 18 }}>

                  <div className="risk-card-header">
                    <div>
                      <span>OFFSET-WELL EVIDENCE</span>
                      <h2>Nearby Hazards</h2>
                    </div>
                    <ShieldAlert size={20} />
                  </div>

                  <div className="risk-table">

                    <div className="risk-table-header">
                      <span>WELL</span>
                      <span>HAZARD TYPE</span>
                      <span>DEPTH</span>
                      <span>DISTANCE</span>
                      <span>SEVERITY</span>
                      <span>CONFIDENCE</span>
                    </div>

                    {result.alerts.map((alert, index) => (

                      <div className="risk-table-row" key={index}>

                        <span className="zone-location">
                          <MapPin size={13} />
                          {alert.well_name}
                        </span>

                        <span className="zone-location">
                          {alert.hazard_type}
                        </span>

                        <span className="zone-location">
                          <Ruler size={13} />
                          {alert.hazard_depth_m} m
                        </span>

                        <span className="zone-location">
                          <Gauge size={13} />
                          {alert.distance_km} km
                        </span>

                        <div className="zone-score">
                          <span
                            className={`risk-badge ${severityToClass(
                              alert.severity
                            )}`}
                          >
                            {alert.severity}
                          </span>
                        </div>

                        <span className="well-count">
                          {alert.confidence}
                        </span>

                      </div>

                    ))}

                  </div>

                </div>

              )}

            </>

          )}


          {/* =====================================================
              PREDICTION DESCRIPTION
          ===================================================== */}

          <div className="prediction-info-card" style={{ marginTop: 18 }}>

            <div className="prediction-info-icon">
              <Activity size={20} />
            </div>

            <div>

              <strong>
                Offset-Well Predictive Analysis
              </strong>

              <p>
                Each check compares the entered position and bit depth against
                historical hazards extracted from nearby drilling reports,
                surfacing mud losses, stuck pipe, overpressure, torque spikes
                and cementing problems recorded on wells within range.
              </p>

            </div>

          </div>

        </>

      )}


      {activeTab === "compare" && <WellComparisonPanel />}

    </div>
  );
}

export default RiskMonitor;
