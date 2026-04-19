import FatiguePage from "./components/FatiguePage.jsx";
import CarrellistiPage from "./components/CarrellistiPage.jsx";
import React, { useEffect, useState } from "react";
import "./styles.css";
import VerticalMap from "./VerticalMap";
import OperatorAnimation from "./OperatorAnimation";

const API_BASE = "http://127.0.0.1:8000";

function App() {
  const [kpi, setKpi] = useState(null);
  const [operators, setOperators] = useState([]);
  const [layout, setLayout] = useState(null);

  const [allOperatorPaths, setAllOperatorPaths] = useState([]); // tutti i percorsi dal backend
  const [filteredPaths, setFilteredPaths] = useState([]); // percorsi filtrati per animazione

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mapMode, setMapMode] = useState("overview"); // "overview" | "heatmap"

  // ✅ NUOVO: pagina attiva (routing semplice)
  const [page, setPage] = useState("overview"); // "overview" | "fatigue" | "carrellisti"

  // stato per i filtri animazione
  const [selectedOps, setSelectedOps] = useState([]); // array di stringhe (codici operatore)
  const [timeStart, setTimeStart] = useState("07:00");
  const [timeEnd, setTimeEnd] = useState("23:00");

  const [pathStats, setPathStats] = useState(null); // risposta di /paths/stats
  const [pathsLoading, setPathsLoading] = useState(false);
  const [pathsError, setPathsError] = useState(null);

  // ============================
  // STATO ASSISTENTE IA
  // ============================
  const [iaQuestion, setIaQuestion] = useState("");
  const [iaAnswer, setIaAnswer] = useState("");
  const [iaLoading, setIaLoading] = useState(false);
  const [iaError, setIaError] = useState(null);

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

        const opPaths = layoutJson.operator_paths || [];
        setAllOperatorPaths(opPaths);
        setFilteredPaths(opPaths); // inizialmente tutti (demo)

        // di default seleziono i primi 1-2 operatori, se esistono
        const defaultOps = opJson.slice(0, 2).map((o) => o.name.toString());
        setSelectedOps(defaultOps);
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

  // helper per controllare se uno step è nella fascia oraria
  function isStepInTimeRange(stepTimeIso, start, end) {
    if (!stepTimeIso) return true;
    try {
      const hhmm = stepTimeIso.substring(11, 16); // "HH:MM" da "YYYY-MM-DDTHH:MM:SS"
      if (start && hhmm < start) return false;
      if (end && hhmm > end) return false;
      return true;
    } catch {
      return true;
    }
  }

  // handler per il bottone "Calcola / Play"
  async function handleRunAnimation() {
    if (!selectedOps || selectedOps.length === 0) {
      setPathsError("Seleziona almeno un operatore.");
      return;
    }

    setPathsError(null);
    setPathsLoading(true);

    try {
      // 1) Chiamo il backend per le statistiche numeriche
      const params = new URLSearchParams();
      params.append("operators", selectedOps.join(","));
      if (timeStart) params.append("start", timeStart);
      if (timeEnd) params.append("end", timeEnd);

      const res = await fetch(`${API_BASE}/paths/stats?${params.toString()}`);
      if (!res.ok) {
        throw new Error("Errore nel calcolo delle statistiche percorsi");
      }
      const statsJson = await res.json();
      setPathStats(statsJson);

      // 2) Filtro i percorsi per animazione (operatori + fascia oraria)
      const selectedSet = new Set(selectedOps.map((s) => s.toString()));

      const newFiltered = (allOperatorPaths || [])
        .filter((p) => selectedSet.has(p.operator?.toString()))
        .map((p) => ({
          ...p,
          steps: (p.steps || []).filter((st) =>
            isStepInTimeRange(st.time, timeStart, timeEnd)
          ),
        }))
        .filter((p) => p.steps && p.steps.length >= 2);

      setFilteredPaths(newFiltered);
    } catch (err) {
      console.error(err);
      setPathsError(err.message);
    } finally {
      setPathsLoading(false);
    }
  }

  // ============================
  // HANDLER ASSISTENTE IA
  // ============================
  async function handleAskAssistant() {
    if (!iaQuestion.trim()) {
      setIaError("Scrivi una domanda da fare all'assistente.");
      return;
    }
    setIaError(null);
    setIaLoading(true);
    setIaAnswer("");

    try {
      const res = await fetch(`${API_BASE}/assistant`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: iaQuestion }),
      });

      if (!res.ok) {
        throw new Error("Errore nella risposta dell'assistente IA");
      }

      const data = await res.json();
      setIaAnswer(data.answer || "Nessuna risposta ricevuta.");
    } catch (err) {
      console.error(err);
      setIaError(err.message);
    } finally {
      setIaLoading(false);
    }
  }

  return (
    <div className="app-root">
      <aside className="sidebar">
        <div className="logo">MHW</div>

        <nav className="menu">
          <div className="menu-section">VISTA</div>

          {/* ✅ Overview */}
          <button
            className={page === "overview" ? "menu-item active" : "menu-item"}
            onClick={() => setPage("overview")}
          >
            Overview
          </button>

          {/* ✅ Fatica */}
          <button
            className={page === "fatigue" ? "menu-item active" : "menu-item"}
            onClick={() => setPage("fatigue")}
          >
            Fatica
          </button>

          {/* ✅ Carrellisti */}
          <button
            className={page === "carrellisti" ? "menu-item active" : "menu-item"}
            onClick={() => setPage("carrellisti")}
          >
            Carrellisti
          </button>

          {/* placeholder: in futuro */}
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
          <div className="info-banner error">Errore nel caricamento dati: {error}</div>
        )}

        {/* ✅ CAMBIO PAGINA */}
        {page === "overview" ? (
          <>
            {/* KPI PRINCIPALI */}
            <section className="kpi-row">
              {/* Colli/ora reali */}
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

              {/* Colli/ora attesi da PARAM */}
              <KpiCard
                title="Colli/ora attesi"
                value={
                  kpi &&
                  (kpi.target_units_per_hour ?? kpi.prod_target_colli_ora) != null
                    ? (
                        kpi.target_units_per_hour ?? kpi.prod_target_colli_ora
                      ).toFixed(1)
                    : "--"
                }
                subtitle={
                  kpi && kpi.media_colli_lista != null
                    ? `Benchmark PARAM – lista media ${kpi.media_colli_lista.toFixed(
                        1
                      )} colli`
                    : "Benchmark PARAM"
                }
              />

              {/* Ritorni + recuperi */}
              <KpiCard
                title="Ritorni + Recuperi"
                value={kpi ? kpi.return_rate.toLocaleString("it-IT") : "--"}
                subtitle="Numero totale fenomeni rilevati"
              />

              {/* Tempo medio cambio missione */}
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

            {/* KPI distanze percorse + rapporti colli */}
            <section className="kpi-row">
              <KpiCard
                title="Distanza media per missione"
                value={kpi ? `${kpi.dist_media_missione_m.toFixed(1)} m` : "--"}
                subtitle="Metri stimati percorsi per ogni lista di picking"
              />
              <KpiCard
                title="Distanza media tra righe"
                value={kpi ? `${kpi.dist_media_step_m.toFixed(1)} m` : "--"}
                subtitle="Spostamento medio tra una riga e la successiva"
              />
              <KpiCard
                title="Colli per riga"
                value={
                  kpi && kpi.colli_per_riga != null
                    ? kpi.colli_per_riga.toFixed(2)
                    : "--"
                }
                subtitle="Media colli prelevati per ogni riga di picking"
              />
              <KpiCard
                title="Colli per lista"
                value={
                  kpi && kpi.colli_per_lista != null
                    ? kpi.colli_per_lista.toFixed(1)
                    : "--"
                }
                subtitle="Media colli per ogni lista di picking"
              />
            </section>

            <section className="middle-row">
              <div className="card map-card">
                <div className="card-header">
                  <div>
                    <h2>Mappa magazzino</h2>
                    <p>Ogni barra rappresenta una corsia con missioni di picking</p>
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
                    <VerticalMap layout={layout} mode={mapMode} />
                  ) : (
                    <div className="placeholder">Caricamento mappa…</div>
                  )}
                </div>

                {/* PANNELLO ANIMAZIONE OPERATORI */}
                {allOperatorPaths && allOperatorPaths.length > 0 && (
                  <div
                    style={{
                      marginTop: 16,
                      paddingTop: 12,
                      borderTop: "1px solid rgba(148,163,184,0.3)",
                    }}
                  >
                    <h2 style={{ fontSize: 14, marginBottom: 8 }}>
                      Movimenti operatori
                    </h2>

                    {/* Filtri */}
                    <div
                      style={{
                        display: "flex",
                        gap: 12,
                        flexWrap: "wrap",
                        marginBottom: 8,
                        alignItems: "center",
                      }}
                    >
                      {/* Operatori */}
                      <div style={{ minWidth: 180 }}>
                        <div
                          style={{
                            fontSize: 11,
                            color: "#9ca3af",
                            marginBottom: 4,
                          }}
                        >
                          Operatori (puoi selezionarne più di uno)
                        </div>
                        <select
                          multiple
                          value={selectedOps}
                          onChange={(e) => {
                            const opts = Array.from(e.target.selectedOptions).map(
                              (o) => o.value
                            );
                            setSelectedOps(opts);
                          }}
                          style={{
                            width: "100%",
                            minHeight: 60,
                            background: "#020617",
                            color: "#e5e7eb",
                            borderRadius: 6,
                            border: "1px solid rgba(148,163,184,0.7)",
                            fontSize: 12,
                            padding: 4,
                          }}
                        >
                          {operators.map((op) => (
                            <option key={op.name} value={op.name.toString()}>
                              Operatore {op.name}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Fascia oraria */}
                      <div>
                        <div
                          style={{
                            fontSize: 11,
                            color: "#9ca3af",
                            marginBottom: 4,
                          }}
                        >
                          Fascia oraria
                        </div>
                        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                          <input
                            type="time"
                            value={timeStart}
                            onChange={(e) => setTimeStart(e.target.value)}
                            style={{
                              background: "#020617",
                              color: "#e5e7eb",
                              borderRadius: 6,
                              border: "1px solid rgba(148,163,184,0.7)",
                              fontSize: 12,
                              padding: "4px 6px",
                            }}
                          />
                          <span style={{ fontSize: 12, color: "#9ca3af" }}>–</span>
                          <input
                            type="time"
                            value={timeEnd}
                            onChange={(e) => setTimeEnd(e.target.value)}
                            style={{
                              background: "#020617",
                              color: "#e5e7eb",
                              borderRadius: 6,
                              border: "1px solid rgba(148,163,184,0.7)",
                              fontSize: 12,
                              padding: "4px 6px",
                            }}
                          />
                        </div>
                      </div>

                      {/* Bottone */}
                      <div style={{ alignSelf: "flex-end" }}>
                        <button
                          onClick={handleRunAnimation}
                          style={{
                            padding: "6px 12px",
                            borderRadius: 6,
                            border: "none",
                            background: "linear-gradient(135deg, #22c55e, #16a34a)",
                            color: "#0b1120",
                            fontSize: 12,
                            fontWeight: 600,
                            cursor: "pointer",
                          }}
                        >
                          {pathsLoading ? "Calcolo in corso…" : "Calcola / Play"}
                        </button>
                      </div>
                    </div>

                    {/* Messaggi errore/situazione */}
                    {pathsError && (
                      <div style={{ fontSize: 11, color: "#f97373", marginBottom: 4 }}>
                        {pathsError}
                      </div>
                    )}

                    {/* Zona testo riepilogo numerico */}
                    <div
                      style={{
                        marginTop: 4,
                        marginBottom: 8,
                        fontSize: 12,
                        color: "#e5e7eb",
                        padding: 8,
                        borderRadius: 8,
                        background:
                          "linear-gradient(135deg, rgba(15,23,42,0.95), rgba(15,23,42,0.8))",
                        border: "1px solid rgba(148,163,184,0.4)",
                      }}
                    >
                      {pathStats && pathStats.overall ? (
                        <>
                          <div style={{ marginBottom: 4 }}>
                            <strong>Operatori selezionati:</strong>{" "}
                            {pathStats.overall.operators.join(", ")}
                          </div>
                          <div>
                            • Missioni (liste) nel periodo:{" "}
                            <strong>{pathStats.overall.missions}</strong>
                          </div>
                          <div>
                            • Righe di picking: <strong>{pathStats.overall.rows}</strong>
                          </div>
                          <div>
                            • Colli prelevati: <strong>{pathStats.overall.colli}</strong>
                          </div>
                          <div>
                            • Ore lavorate (netto tempo di movimento):{" "}
                            <strong>{pathStats.overall.hours.toFixed(2)} h</strong>
                          </div>
                          <div>
                            • Produttività fascia selezionata:{" "}
                            <strong>
                              {pathStats.overall.prod_colli_ora.toFixed(1)} colli/ora
                            </strong>
                          </div>
                        </>
                      ) : (
                        <div style={{ opacity: 0.7 }}>
                          Seleziona operatori e fascia oraria, poi clicca
                          <strong> Calcola / Play</strong> per vedere missioni, colli e
                          produttività del periodo.
                        </div>
                      )}
                    </div>

                    {/* Animazione vera e propria */}
                    {filteredPaths && filteredPaths.length > 0 ? (
                      <OperatorAnimation paths={filteredPaths} />
                    ) : (
                      <div className="placeholder">
                        Nessun dato disponibile per l&apos;animazione operatori con i
                        filtri attuali.
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* COLONNA DESTRA: OPERATORI + ASSISTENTE IA */}
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
                            <div className="operator-name">Operatore {op.name}</div>
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

                {/* ASSISTENTE IA */}
                <div
                  style={{
                    marginTop: 16,
                    paddingTop: 12,
                    borderTop: "1px solid rgba(148,163,184,0.3)",
                  }}
                >
                  <div className="card-header" style={{ paddingLeft: 0 }}>
                    <h2>Assistente IA</h2>
                    <p>Fagli una domanda sui KPI e sui dati</p>
                  </div>

                  <div style={{ marginBottom: 8 }}>
                    <textarea
                      value={iaQuestion}
                      onChange={(e) => setIaQuestion(e.target.value)}
                      placeholder="Es: Spiegami perché la produttività è scesa rispetto al target…"
                      style={{
                        width: "100%",
                        minHeight: 70,
                        resize: "vertical",
                        background: "#020617",
                        color: "#e5e7eb",
                        borderRadius: 8,
                        border: "1px solid rgba(148,163,184,0.7)",
                        padding: 8,
                        fontSize: 12,
                      }}
                    />
                  </div>

                  <div style={{ marginBottom: 8, display: "flex", justifyContent: "flex-end" }}>
                    <button
                      onClick={handleAskAssistant}
                      disabled={iaLoading}
                      style={{
                        padding: "6px 12px",
                        borderRadius: 6,
                        border: "none",
                        background: "linear-gradient(135deg, #38bdf8, #0ea5e9)",
                        color: "#0b1120",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: iaLoading ? "default" : "pointer",
                        opacity: iaLoading ? 0.7 : 1,
                      }}
                    >
                      {iaLoading ? "Elaborazione…" : "Chiedi all'assistente"}
                    </button>
                  </div>

                  {iaError && (
                    <div style={{ fontSize: 11, color: "#f97373", marginBottom: 4 }}>
                      {iaError}
                    </div>
                  )}

                  {iaAnswer && (
                    <div
                      style={{
                        fontSize: 12,
                        color: "#e5e7eb",
                        padding: 8,
                        borderRadius: 8,
                        background:
                          "linear-gradient(135deg, rgba(15,23,42,0.95), rgba(15,23,42,0.8))",
                        border: "1px solid rgba(148,163,184,0.4)",
                        maxHeight: 200,
                        overflowY: "auto",
                      }}
                    >
                      {iaAnswer}
                    </div>
                  )}
                </div>
              </div>
            </section>
          </>
        ) : page === "fatigue" ? (
          <FatiguePage API_BASE={API_BASE} operators={operators} />
        ) : (
          <CarrellistiPage API_BASE={API_BASE} />
        )}
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

// (Questo WarehouseMap non lo stai usando, ma lo lascio come nel tuo file originale)
function WarehouseMap({ layout, mode }) {
  const cells = layout.cells || [];
  const margin = 10;
  const scaleX = 70;
  const height = 160;
  const width = margin * 2 + cells.length * scaleX;

  const values = cells.map((c) => {
    const raw = c.intensity ?? c.load ?? c.value ?? c.colli ?? 0;
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
                      fill: `rgb(${100 + intensity * 155}, ${60 + (1 - intensity) * 80}, 120)`,
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
