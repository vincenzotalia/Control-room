import React, { useEffect, useState } from "react";
import "./styles.css";

const API_BASE = "http://127.0.0.1:8000";

function App() {
  const [kpi, setKpi] = useState(null);
  const [operators, setOperators] = useState([]);
  const [layout, setLayout] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mapMode, setMapMode] = useState("overview"); // "overview" | "heatmap"

  useEffect(() => {
    async function loadData() {
      try {
        const [kpiRes, opRes, layoutRes] = await Promise.all([
          fetch(`${API_BASE}/kpi/overview`),
          fetch(`${API_BASE}/operators`),
          fetch(`${API_BASE}/layout`),
        ]);

        if (!kpiRes.ok || !opRes.ok || !layoutRes.ok) {
          throw new Error("Errore nel caricamento delle API");
        }

        const [kpiJson, opJson, layoutJson] = await Promise.all([
          kpiRes.json(),
          opRes.json(),
          layoutRes.json(),
        ]);

        setKpi(kpiJson);
        setOperators(opJson);
        setLayout(layoutJson);
      } catch (err) {
        console.error(err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, []);

  const topOperators = [...operators]
    .sort((a, b) => b.units_per_hour - a.units_per_hour)
    .slice(0, 15);

  return (
    <div className="app-root">
      <aside className="sidebar">
        <div className="logo">MHW</div>
        <nav className="menu">
          <div className="menu-section">VISTA</div>
          <button className="menu-item active">Overview</button>
          <button className="menu-item">Flussi</button>
          <button className="menu-item">Ritorni</button>
          <button className="menu-item">Mappa termica</button>
        </nav>
        <div className="sidebar-footer">
          <span>Agorà DC</span>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <h1>Sala di controllo Pick</h1>
            <p>Monitor in tempo reale del picking Agorà</p>
          </div>
          <div className="topbar-right">
            <span className="pill">Oggi</span>
          </div>
        </header>

        {loading && <div className="info-banner">Caricamento dati da Python…</div>}
        {error && (
          <div className="info-banner error">
            Errore nel caricamento dati: {error}
          </div>
        )}

        <section className="kpi-row">
          <KpiCard
            title="Colli/ora complessivi"
            value={kpi ? kpi.units_per_hour.toFixed(1) : "--"}
            subtitle={
              kpi
                ? `${kpi.colli_totali} colli su ${kpi.tempo_netto_ore.toFixed(
                    1
                  )} ore`
                : "In attesa dati…"
            }
          />
          <KpiCard
            title="Saturazione"
            value={kpi ? `${(kpi.capacity_utilization * 100).toFixed(0)}%` : "0%"}
            subtitle="Capacità utilizzata (placeholder)"
          />
          <KpiCard
            title="Ritorni su missioni"
            value={kpi ? `${(kpi.return_rate * 100).toFixed(2)}%` : "--"}
            subtitle="Ultimo periodo analizzato"
          />
          <KpiCard
            title="Tempo medio cambio missione"
            value={
              kpi
                ? `${(kpi.tempo_medio_cambio_ore * 60).toFixed(1)} min`
                : "--"
            }
            subtitle="Calcolato sulle missioni valide"
          />
        </section>

        <section className="middle-row">
          <div className="card map-card">
            <div className="card-header">
              <div>
                <h2>Mappa magazzino</h2>
                <p>
                  Ogni barra rappresenta una corsia con missioni di picking
                </p>
              </div>
              <div className="map-mode-toggle">
                <button
                  className={
                    mapMode === "overview"
                      ? "map-mode-button active"
                      : "map-mode-button"
                  }
                  onClick={() => setMapMode("overview")}
                >
                  Overview
                </button>
                <button
                  className={
                    mapMode === "heatmap"
                      ? "map-mode-button active"
                      : "map-mode-button"
                  }
                  onClick={() => setMapMode("heatmap")}
                >
                  Heatmap
                </button>
              </div>
            </div>
            <div className="map-container">
              {layout && layout.cells && layout.cells.length > 0 ? (
                <WarehouseMap layout={layout} mode={mapMode} />
              ) : (
                <div className="placeholder">Caricamento mappa…</div>
              )}
            </div>
          </div>

          <div className="card operator-card">
            <div className="card-header">
              <h2>Operatori</h2>
              <p>Top produttività colli/ora (solo PIK)</p>
            </div>
            <div className="operator-list">
              {topOperators.length === 0 ? (
                <div className="placeholder">Nessun dato operatore</div>
              ) : (
                topOperators.map((op) => (
                  <div key={op.name} className="operator-row">
                    <div className="operator-main">
                      <div className="avatar">
                        <span>{(op.name || "?").toString().slice(-2)}</span>
                      </div>
                      <div>
                        <div className="operator-name">
                          Operatore {op.name}
                        </div>
                        <div className="operator-sub">
                          {op.colli} colli • {op.ore.toFixed(2)} h
                        </div>
                      </div>
                    </div>
                    <div className="operator-kpi">
                      <span className="operator-kpi-value">
                        {op.units_per_hour.toFixed(1)}
                      </span>
                      <span className="operator-kpi-label">colli/ora</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function KpiCard({ title, value, subtitle }) {
  return (
    <div className="card kpi-card">
      <div className="kpi-title">{title}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-subtitle">{subtitle}</div>
    </div>
  );
}

function WarehouseMap({ layout, mode }) {
  const cells = layout.cells || [];
  const margin = 10;
  const scaleX = 70;
  const height = 160;
  const width = margin * 2 + cells.length * scaleX;

  const values = cells.map((c) => {
    const raw =
      c.intensity ??
      c.load ??
      c.value ??
      c.colli ??
      0;
    return typeof raw === "number" ? raw : 0;
  });
  const maxVal = values.reduce((m, v) => (v > m ? v : m), 0) || 1;

  return (
    <svg
      className="map-svg"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <rect
        x="0"
        y="0"
        width={width}
        height={height}
        className="map-background"
        rx="8"
      />
      {cells.map((cell, idx) => {
        const x = margin + cell.x * scaleX;
        const w = cell.w * scaleX;

        const val = values[idx] || 0;
        const intensity = val / maxVal; // 0–1
        const isHot = mode === "heatmap" && intensity > 0.6;

        const rectClass = [
          "rack-rect",
          mode === "heatmap" ? "rack-rect-heat" : "",
          isHot ? "rack-rect-pulse" : "",
        ]
          .filter(Boolean)
          .join(" ");

        return (
          <g key={cell.id || idx}>
            <rect
              x={x}
              y={20}
              width={w}
              height={120}
              className={rectClass}
              style={
                mode === "heatmap"
                  ? {
                      fill: `rgb(${100 + intensity * 155}, ${
                        60 + (1 - intensity) * 80
                      }, 120)`,
                    }
                  : undefined
              }
              rx="4"
            />
            <text x={x + w / 2} y={150} className="rack-label">
              {cell.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default App;

