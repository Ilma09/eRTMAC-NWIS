import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  Map,
  FileText,
  Drill,
  ShieldAlert,
  Database,
  Brain,
  Activity,
  AlertTriangle,
  CheckCircle2,
  ArrowUpRight,
  Gauge,
} from "lucide-react";

import api from "../api/client";

import "./Dashboard.css";


/* =====================================================
   OIL DROP ICON
===================================================== */

function OilDrop({ size = 32, className = "" }) {
  return (
    <svg
      className={`oil-drop-svg ${className}`}
      viewBox="0 0 64 64"
      width={size}
      height={size}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* Main petroleum drop */}

      <path
        d="
          M32 3
          C32 3 10 27 10 43
          C10 55 19 62 32 62
          C45 62 54 55 54 43
          C54 27 32 3 32 3Z
        "
        fill="currentColor"
      />

      {/* Oil shine */}

      <ellipse
        cx="24"
        cy="35"
        rx="5"
        ry="10"
        fill="rgba(255,255,255,0.24)"
        transform="rotate(25 24 35)"
      />

      {/* Small shine */}

      <ellipse
        cx="29"
        cy="25"
        rx="2"
        ry="4"
        fill="rgba(255,255,255,0.16)"
        transform="rotate(25 29 25)"
      />
    </svg>
  );
}


/* =====================================================
   DASHBOARD
   The app's home page - a summary view built entirely from real backend
   data (no hardcoded numbers). It calls two endpoints:
     GET /api/dashboard/summary -> total wells, active wells, hazards, docs
     GET /api/corpus            -> the full document list, used here just
                                    to compute the WCR/DDR/review breakdown
                                    and the "recent activity" feed, since
                                    the backend doesn't expose those as
                                    separate endpoints of their own.
===================================================== */

function Dashboard() {
  // summary/documents start as null/[] and only get real values once the
  // API calls below finish - loading/loadError track that in-between state
  // so the page can show "Loading..." or a clear error instead of crashing
  // on undefined data.
  const [summary, setSummary] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  // Runs once when the page first loads. Fetches both endpoints at the same
  // time (Promise.all) rather than one after another, since neither result
  // depends on the other.
  useEffect(() => {
    // If the user navigates away before the request finishes, this flag
    // stops the late-arriving response from calling setState on a page
    // that's no longer showing (React would otherwise warn about this).
    let cancelled = false;

    Promise.all([
      api.get("/api/dashboard/summary"),
      api.get("/api/corpus"),
    ])
      .then(([summaryRes, corpusRes]) => {
        if (cancelled) return;
        setSummary(summaryRes.data);
        setDocuments(corpusRes.data);
        setLoadError(null);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError(
            "Could not reach the backend. Is the server running?"
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="dashboard-page">
        <p>Loading dashboard...</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="dashboard-page">
        <p>{loadError}</p>
      </div>
    );
  }

  // Everything below is computed from the two real API responses above -
  // nothing here is fetched separately, it's all derived in the browser.
  const totalWells = summary.total_wells;
  const activeWells = summary.active_wells;
  const inactiveWells = totalWells - activeWells;
  const activePct = totalWells ? Math.round((activeWells / totalWells) * 100) : 0;
  const inactivePct = totalWells ? 100 - activePct : 0;

  // The backend's /api/corpus response doesn't group documents by type or
  // status itself, so that counting happens here instead.
  const wcrCount = documents.filter((doc) => doc.type === "WCR").length;
  const ddrCount = documents.filter((doc) => doc.type === "DDR").length;
  const reviewCount = documents.filter((doc) => doc.status === "Review").length;

  // documents is already sorted newest-first by the backend (it orders by
  // upload time), so the first 3 entries are simply the most recent uploads -
  // that's what powers the "Recent Activity" list further down.
  const recentDocuments = documents.slice(0, 3);

  return (
    <div className="dashboard-page">


      {/* =================================================
          HEADER
      ================================================= */}

      <div className="dashboard-header">

        <div>

          <span className="dashboard-eyebrow">
            eRTMAC-NWIS / INTELLIGENCE PLATFORM
          </span>

          <h1>
            Nearby Wells Intelligence
          </h1>

          <p>
            Monitor, analyse and manage oil &amp; gas
            well intelligence from one platform.
          </p>

        </div>


        <div className="dashboard-status">

          <span></span>

          System Operational

        </div>

      </div>



      {/* =================================================
          KPI CARDS
      ================================================= */}

      <div className="dashboard-stats">


        {/* TOTAL WELLS */}

        <div className="stat-card blue">

          <div className="stat-icon oil-icon">

            <OilDrop size={28} />

          </div>


          <div className="stat-content">

            <span>
              Total Wells
            </span>

            <strong>
              {totalWells}
            </strong>

            <small>

              <Database size={11} />

              From extracted reports

            </small>

          </div>


          <ArrowUpRight
            className="stat-arrow"
            size={17}
          />

        </div>



        {/* ACTIVE WELLS */}

        <div className="stat-card green">

          <div className="stat-icon">

            <Activity size={22} />

          </div>


          <div className="stat-content">

            <span>
              Active Wells
            </span>

            <strong>
              {activeWells}
            </strong>

            <small>

              <CheckCircle2 size={11} />

              {activePct}% of total

            </small>

          </div>


          <ArrowUpRight
            className="stat-arrow"
            size={17}
          />

        </div>



        {/* HAZARDS LOGGED */}

        <div className="stat-card orange">

          <div className="stat-icon">

            <ShieldAlert size={22} />

          </div>


          <div className="stat-content">

            <span>
              Hazards Logged
            </span>

            <strong>
              {summary.total_hazards}
            </strong>

            <small>

              <AlertTriangle size={11} />

              Extracted from documents

            </small>

          </div>


          <ArrowUpRight
            className="stat-arrow"
            size={17}
          />

        </div>



        {/* DOCUMENTS */}

        <div className="stat-card purple">

          <div className="stat-icon">

            <FileText size={22} />

          </div>


          <div className="stat-content">

            <span>
              Documents
            </span>

            <strong>
              {summary.total_documents}
            </strong>

            <small>
              WCR + DDR
            </small>

          </div>


          <ArrowUpRight
            className="stat-arrow"
            size={17}
          />

        </div>

      </div>



      {/* =================================================
          MAIN GRID
      ================================================= */}

      <div className="dashboard-main-grid">


        {/* WELL OVERVIEW */}

        <div className="dashboard-card well-overview">


          <div className="card-header">

            <div>

              <span>
                WELL NETWORK
              </span>

              <h2>
                Well Monitoring Overview
              </h2>

            </div>


            <Map size={20} />

          </div>



          <div className="well-visual">


            <div className="well-circle">

              <OilDrop
                size={38}
              />

              <strong>
                {totalWells}
              </strong>

              <span>
                Total Wells
              </span>

            </div>



            <div className="well-status-list">


              <div>

                <span className="legend-dot green"></span>

                <div>

                  <strong>
                    Active
                  </strong>

                  <small>
                    {activeWells} wells
                  </small>

                </div>

                <b>
                  {activePct}%
                </b>

              </div>



              <div>

                <span className="legend-dot red"></span>

                <div>

                  <strong>
                    Inactive
                  </strong>

                  <small>
                    {inactiveWells} wells
                  </small>

                </div>

                <b>
                  {inactivePct}%
                </b>

              </div>


            </div>

          </div>

        </div>



        {/* =================================================
            RISK MONITOR
            No standing "risk score" exists in the backend - hazard
            checking is a live, per-query lookup (lat/lng/depth in,
            nearby hazards out), not a precomputed dashboard number. So
            this card is just a CTA linking to the real tool on the Risk
            Monitor page, instead of showing a fabricated score here.
        ================================================= */}

        <div className="dashboard-card risk-card">


          <div className="card-header">

            <div>

              <span>
                RISK MONITOR
              </span>

              <h2>
                Hazard Proximity Check
              </h2>

            </div>

            <ShieldAlert size={20} />

          </div>



          <div className="ai-content">

            <div className="ai-icon">
              <Gauge size={27} />
            </div>

            <div>

              <strong>
                Live telemetry-based check
              </strong>

              <p>
                Enter a rig's current position and bit depth
                to check for nearby historical drilling hazards.
              </p>

            </div>

          </div>


          <Link to="/risk-monitor" className="ai-button">
            Open Risk Monitor
            <ArrowUpRight size={15} />
          </Link>


        </div>

      </div>



      {/* =================================================
          DOCUMENTS + DRILL MIND
      ================================================= */}

      <div className="dashboard-bottom-grid">


        {/* DOCUMENTS */}

        <div className="dashboard-card">


          <div className="card-header">

            <div>

              <span>
                DOCUMENT INTELLIGENCE
              </span>

              <h2>
                Document Corpus
              </h2>

            </div>

            <Database size={20} />

          </div>



          <div className="document-grid">


            <div className="document-stat wcr">

              <FileText size={19} />

              <div>

                <strong>
                  {wcrCount}
                </strong>

                <span>
                  WCR
                </span>

              </div>

            </div>



            <div className="document-stat ddr">

              <Drill size={19} />

              <div>

                <strong>
                  {ddrCount}
                </strong>

                <span>
                  DDR
                </span>

              </div>

            </div>



            <div className="document-stat ocred">

              <Database size={19} />

              <div>

                <strong>
                  {reviewCount}
                </strong>

                <span>
                  Needs Review
                </span>

              </div>

            </div>


          </div>

        </div>



        {/* DRILL MIND */}

        <div className="dashboard-card drill-card">


          <div className="card-header">

            <div>

              <span>
                AI INTELLIGENCE
              </span>

              <h2>
                Drill Mind
              </h2>

            </div>

            <Brain size={20} />

          </div>



          <div className="ai-content">


            <div className="ai-icon">

              <Brain size={27} />

            </div>


            <div>

              <strong>
                Intelligence Engine Ready
              </strong>

              <p>
                Analyse drilling patterns,
                nearby wells and historical
                reports.
              </p>

            </div>


          </div>



          <Link to="/drill-mind" className="ai-button">

            Open Drill Mind

            <ArrowUpRight size={15} />

          </Link>


        </div>

      </div>



      {/* =================================================
          RECENT ACTIVITY
      ================================================= */}

      <div className="dashboard-card activity-card">


        <div className="card-header">

          <div>

            <span>
              PLATFORM ACTIVITY
            </span>

            <h2>
              Recent Activity
            </h2>

          </div>

          <Activity size={20} />

        </div>



        <div className="activity-list">

          {recentDocuments.length === 0 ? (

            <div className="activity-item">
              <div>
                <strong>No documents uploaded yet</strong>
                <span>Upload a WCR or DDR to see activity here.</span>
              </div>
            </div>

          ) : (

            recentDocuments.map((doc) => {
              const needsReview = doc.status === "Review";

              return (
                <div className="activity-item" key={doc.id}>

                  <div
                    className={`activity-icon ${
                      doc.type === "WCR" ? "blue" : "orange"
                    }`}
                  >
                    {doc.type === "WCR" ? (
                      <FileText size={15} />
                    ) : (
                      <Drill size={15} />
                    )}
                  </div>

                  <div>
                    <strong>
                      {doc.type} document uploaded
                    </strong>

                    <span>
                      {doc.well} · {doc.date}
                    </span>
                  </div>

                  {needsReview ? (
                    <AlertTriangle
                      size={16}
                      className="activity-warning"
                    />
                  ) : (
                    <CheckCircle2
                      size={16}
                      className="activity-check"
                    />
                  )}

                </div>
              );
            })

          )}

        </div>

      </div>


    </div>
  );
}

export default Dashboard;
