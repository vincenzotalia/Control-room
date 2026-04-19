// frontend/src/App.jsx
import React, { useEffect, useState, useMemo } from "react";
import "./styles.css";

import LoginPage from "./components/LoginPage.jsx";
import ForkliftPage from "./components/ForkLiftPage.jsx";
import UploadDataButton from "./components/UploadDataButton.jsx";

import VerticalMap from "./VerticalMap";
import OperatorAnimation from "./OperatorAnimation";
import FatiguePage from "./components/FatiguePage.jsx";
import AlertsPage from "./components/AlertsPage.jsx";
import ScrollingTicker from "./components/ScrollingTicker.jsx";
import { API_BASE } from "./api/config";

// ✅ NEW: Area Manager page
import AreaManagerPage from "./components/AreaManagerPage.jsx";

// ✅ NEW: distanza breakdown + confronto storico
import DistBreakdownCard from "./components/DistBreakdownCard.jsx";


// ✅ Qui cambi le scritte che scorrono (non impatta performance)
const TICKER_ITEMS = [
  "MHW • Safety first: segnala near miss e anomalie subito",
  "Sala di Controllo • KPI picking aggiornati",
  "Obiettivo qualità: > 99,5% • Ordine e pulizia sempre",
  "Promemoria: DPI obbligatori nelle aree operative",
];

function App() {
  const [user, setUser] = useState(null);

  const [kpi, setKpi] = useState(null);
  const [operators, setOperators] = useState([]);
  const [layout, setLayout] = useState(null);

  // ✅ Paths ora vengono caricati SOLO quando serve (lazy vero)
  const [allOperatorPaths, setAllOperatorPaths] = useState([]);
  const [filteredPaths, setFilteredPaths] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mapMode, setMapMode] = useState("overview"); // "overview" | "heatmap"

  // ✅ Routing semplice
  const [page, setPage] = useState("overview");
  // "overview" | "fatigue" | "alerts" | "forklift" | "area_manager"

  // filtri animazione
  const [selectedOps, setSelectedOps] = useState([]);
  const [timeStart, setTimeStart] = useState("07:00");
  const [timeEnd, setTimeEnd] = useState("23:00");

  const [pathStats, setPathStats] = useState(null);
  const [pathsLoading, setPathsLoading] = useState(false);
  const [pathsError, setPathsError] = useState(null);

  // Assistente IA
  const [iaQuestion, setIaQuestion] = useState("");
  const [iaAnswer, setIaAnswer] = useState("");
  const [iaLoading, setIaLoading] = useState(false);
  const [iaError, setIaError] = useState(null);

  // ✅ FUNZIONE RIUTILIZZABILE: carica dati base (KPI / operatori / layout)
  async function loadData() {
    try {
      setLoading(true);
      setError(null);

      // ✅ Carico SOLO i dati essenziali (no operator paths)
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

      // ✅ IMPORTANTISSIMO: i percorsi NON si caricano qui
      setAllOperatorPaths([]);
      setFilteredPaths([]);

      const defaultOps = (opJson || []).slice(0, 2).map((o) => o.name.toString());
      setSelectedOps(defaultOps);
    } catch (err) {
      console.error(err);
      setError(err?.message || "Errore sconosciuto");
    } finally {
      setLoading(false);
    }
  }

  // ✅ carica all’avvio
  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const topOperators = useMemo(() => {
    return [...operators]
      .sort((a, b) => (b.units_per_hour || 0) - (a.units_per_hour || 0))
      .slice(0, 15);
  }, [operators]);

  function isStepInTimeRange(stepTimeIso, start, end) {
    if (!stepTimeIso) return true;
    try {
      const hhmm = stepTimeIso.substring(11, 16);
      if (start && hhmm < start) return false;
      if (end && hhmm > end) return false;
      return true;
    } catch {
      return true;
    }
  }

  // ✅ Nuova funzione: carica i percorsi SOLO quando serve
  async function loadOperatorPathsIfNeeded() {
    if (allOperatorPaths && allOperatorPaths.length > 0) return;

    setPathsError(null);
    setPathsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/operator-paths`);
      if (!res.ok) throw new Error("Errore nel caricamento dei percorsi operatori");

      const json = await res.json();
      const opPaths = json.operator_paths || [];

      setAllOperatorPaths(opPaths);
      setFilteredPaths(opPaths);
    } catch (err) {
      console.error(err);
      setPathsError(err?.message || "Errore sconosciuto");
    } finally {
      setPathsLoading(false);
    }
  }

  async function handleRunAnimation() {
    if (!selectedOps || selectedOps.length === 0) {
      setPathsError("Seleziona almeno un operatore.");
      return;
    }

    setPathsError(null);
    setPathsLoading(true);

    try {
      // ✅ Lazy vero: carica i percorsi SOLO al primo Play
      await loadOperatorPathsIfNeeded();

      const params = new URLSearchParams();
      params.append("operators", selectedOps.join(","));
      if (timeStart) params.append("start", timeStart);
      if (timeEnd) params.append("end", timeEnd);

      const res = await fetch(`${API_BASE}/paths/stats?${params.toString()}`);
      if (!res.ok) throw new Error("Errore nel calcolo delle statistiche percorsi");

      const statsJson = await res.json();
      setPathStats(statsJson);

      const selectedSet = new Set(selectedOps.map((s) => s.toString()));
      const newFiltered = (allOperatorPaths || [])
        .filter((p) => selectedSet.has(p.operator?.toString()))
        .map((p) => ({
          ...p,
          steps: (p.steps || []).filter((st) => isStepInTimeRange(st.time, timeStart, timeEnd)),
        }))
        .filter((p) => p.steps && p.steps.length >= 2);

      setFilteredPaths(newFiltered);
    } catch (err) {
      console.error(err);
      setPathsError(err?.message || "Errore sconosciuto");
    } finally {
      setPathsLoading(false);
    }
  }

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

      if (!res.ok) throw new Error("Errore nella risposta dell'assistente IA");

      const data = await res.json();
      setIaAnswer(data.answer || "Nessuna risposta ricevuta.");
    } catch (err) {
      console.error(err);
      setIaError(err?.message || "Errore sconosciuto");
    } finally {
      setIaLoading(false);
    }
  }

  // ✅ LOGIN GATE
  if (!user) {
    return <LoginPage onLogin={(u) => setUser(u)} />;
  }

  return (
    <div className="app-root">
      <aside className="sidebar">
        <div className="logo">
          <img src="/logo-mhw.png" alt="MHW" className="logo-img" />
        </div>

        <nav className="menu">
          <div className="menu-section">VISTA</div>

          <button className={page === "overview" ? "menu-item active" : "menu-item"} onClick={() => setPage("overview")}>
            Overview
          </button>

          <button className={page === "forklift" ? "menu-item active" : "menu-item"} onClick={() => setPage("forklift")}>
            Carrellisti
          </button>

          <button className={page === "fatigue" ? "menu-item active" : "menu-item"} onClick={() => setPage("fatigue")}>
            Fatica
          </button>

          <button className={page === "alerts" ? "menu-item active" : "menu-item"} onClick={() => setPage("alerts")}>
            Alert Hub
          </button>

          {/*
           <button
            className={page === "area_manager" ? "menu-item active" : "menu-item"}
            onClick={() => setPage("area_manager")}
          >
            Area Manager
          </button>
          */}

          <button className="menu-item" disabled style={{ opacity: 0.6 }}>
            Ritorni (presto)
          </button>
          <button className="menu-item" disabled style={{ opacity: 0.6 }}>
            Mappa termica (presto)
          </button>
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

        <ScrollingTicker items={TICKER_ITEMS} />

        {loading && <div className="info-banner">Caricamento dati da Python…</div>}
        {error && <div className="info-banner error">Errore nel caricamento dati: {error}</div>}

        {page === "area_manager" && <AreaManagerPage />}
        {page === "forklift" && <ForkliftPage API_BASE={API_BASE} />}
        {page === "fatigue" && <FatiguePage API_BASE={API_BASE} operators={operators} />}
        {page === "alerts" && <AlertsPage API_BASE={API_BASE} />}

        {page === "overview" && (
          <>
            <UploadDataButton API_BASE={API_BASE} onUploaded={loadData} />

            <section className="kpi-row">
              <KpiCard
                title="Colli/ora complessivi"
                value={kpi ? Number(kpi.units_per_hour || 0).toFixed(1) : "--"}
                subtitle={
                  kpi
                    ? `${kpi.colli_totali} colli su ${Number(kpi.tempo_netto_ore || 0).toFixed(1)} ore`
                    : "In attesa dati…"
                }
              />

              <KpiCard
                title="Colli/ora attesi"
                value={
                  kpi && (kpi.target_units_per_hour ?? kpi.prod_target_colli_ora) != null
                    ? Number(kpi.target_units_per_hour ?? kpi.prod_target_colli_ora).toFixed(1)
                    : "--"
                }
                subtitle={
                  kpi && kpi.media_colli_lista != null
                    ? `Benchmark PARAM – lista media ${Number(kpi.media_colli_lista).toFixed(1)} colli`
                    : "Benchmark PARAM"
                }
              />

              <KpiCard
                title="Ritorni + Recuperi"
                value={kpi ? Number(kpi.return_rate || 0).toLocaleString("it-IT") : "--"}
                subtitle="Numero totale fenomeni rilevati"
              />

              <KpiCard
                title="Tempo medio cambio missione"
                value={kpi ? `${(Number(kpi.tempo_medio_cambio_ore || 0) * 60).toFixed(1)} min` : "--"}
                subtitle="Calcolato sulle missioni valide"
              />
            </section>

            <section className="kpi-row">
              <KpiCard
                title="Distanza media per missione"
                value={kpi ? `${Number(kpi.dist_media_missione_m || 0).toFixed(1)} m` : "--"}
                subtitle="Metri stimati percorsi per ogni lista di picking"
              />

              {/* ✅ QUI: sostituita la vecchia card con la card breakdown + storico */}
              <DistBreakdownCard API_BASE={API_BASE} />

              <KpiCard
                title="Colli per riga"
                value={kpi && kpi.colli_per_riga != null ? Number(kpi.colli_per_riga).toFixed(2) : "--"}
                subtitle="Media colli prelevati per ogni riga di picking"
              />
              <KpiCard
                title="Colli per lista"
                value={kpi && kpi.colli_per_lista != null ? Number(kpi.colli_per_lista).toFixed(1) : "--"}
                subtitle="Media colli per ogni lista di picking"
              />
            </section>

            <section className="middle-row">
              {/* MAPPA + ANIMAZIONE */}
              <div className="card map-card">
                <div className="card-header">
                  <div>
                    <h2>Mappa magazzino</h2>
                    <p>Ogni barra rappresenta una corsia con missioni di picking</p>
                  </div>

                  <div className="map-mode-toggle">
                    <button
                      className={mapMode === "overview" ? "map-mode-button active" : "map-mode-button"}
                      onClick={() => setMapMode("overview")}
                    >
                      Overview
                    </button>
                    <button
                      className={mapMode === "heatmap" ? "map-mode-button active" : "map-mode-button"}
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

                <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid rgba(148,163,184,0.3)" }}>
                  <h2 style={{ fontSize: 14, marginBottom: 8 }}>Movimenti operatori</h2>

                  {(!allOperatorPaths || allOperatorPaths.length === 0) && (
                    <div style={{ fontSize: 12, opacity: 0.75, marginBottom: 8 }}>
                      I percorsi non sono ancora caricati. Premi <strong>Calcola / Play</strong> per caricarli e avviare
                      l’animazione.
                    </div>
                  )}

                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 8, alignItems: "center" }}>
                    <div style={{ minWidth: 180 }}>
                      <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>
                        Operatori (puoi selezionarne più di uno)
                      </div>
                      <select
                        multiple
                        value={selectedOps}
                        onChange={(e) => {
                          const opts = Array.from(e.target.selectedOptions).map((o) => o.value);
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

                    <div>
                      <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>Fascia oraria</div>
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

                    <div style={{ alignSelf: "flex-end", display: "flex", gap: 8 }}>
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

                      <button
                        onClick={loadOperatorPathsIfNeeded}
                        style={{
                          padding: "6px 10px",
                          borderRadius: 6,
                          border: "1px solid rgba(148,163,184,0.6)",
                          background: "rgba(2,6,23,0.5)",
                          color: "#e5e7eb",
                          fontSize: 12,
                          cursor: "pointer",
                        }}
                        title="Carica i percorsi senza avviare l'animazione"
                      >
                        Carica percorsi
                      </button>
                    </div>
                  </div>

                  {pathsError && <div style={{ fontSize: 11, color: "#f97373", marginBottom: 4 }}>{pathsError}</div>}

                  <div
                    style={{
                      marginTop: 4,
                      marginBottom: 8,
                      fontSize: 12,
                      color: "#e5e7eb",
                      padding: 8,
                      borderRadius: 8,
                      background: "linear-gradient(135deg, rgba(15,23,42,0.95), rgba(15,23,42,0.8))",
                      border: "1px solid rgba(148,163,184,0.4)",
                    }}
                  >
                    {pathStats && pathStats.overall ? (
                      <>
                        <div style={{ marginBottom: 4 }}>
                          <strong>Operatori selezionati:</strong> {pathStats.overall.operators.join(", ")}
                        </div>
                        <div>
                          • Missioni (liste) nel periodo: <strong>{pathStats.overall.missions}</strong>
                        </div>
                        <div>
                          • Righe di picking: <strong>{pathStats.overall.rows}</strong>
                        </div>
                        <div>
                          • Colli prelevati: <strong>{pathStats.overall.colli}</strong>
                        </div>
                        <div>
                          • Ore lavorate (netto): <strong>{Number(pathStats.overall.hours || 0).toFixed(2)} h</strong>
                        </div>
                        <div>
                          • Produttività fascia:{" "}
                          <strong>{Number(pathStats.overall.prod_colli_ora || 0).toFixed(1)} colli/ora</strong>
                        </div>
                      </>
                    ) : (
                      <div style={{ opacity: 0.7 }}>
                        Seleziona operatori e fascia oraria, poi clicca <strong>Calcola / Play</strong>.
                      </div>
                    )}
                  </div>

                  {filteredPaths && filteredPaths.length > 0 ? (
                    <OperatorAnimation paths={filteredPaths} />
                  ) : (
                    <div className="placeholder">Nessun dato disponibile per l’animazione con i filtri attuali.</div>
                  )}
                </div>
              </div>

              {/* OPERATORI + IA (ripristinato) */}
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
                              {op.colli} colli • {Number(op.ore || 0).toFixed(2)} h
                            </div>
                          </div>
                        </div>
                        <div className="operator-kpi">
                          <span className="operator-kpi-value">{Number(op.units_per_hour || 0).toFixed(1)}</span>
                          <span className="operator-kpi-label">colli/ora</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid rgba(148,163,184,0.3)" }}>
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

                  {iaError && <div style={{ fontSize: 11, color: "#f97373", marginBottom: 4 }}>{iaError}</div>}

                  {iaAnswer && (
                    <div
                      style={{
                        fontSize: 12,
                        color: "#e5e7eb",
                        padding: 8,
                        borderRadius: 8,
                        background: "linear-gradient(135deg, rgba(15,23,42,0.95), rgba(15,23,42,0.8))",
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

export default App;
