// frontend/src/components/ForkliftPage.jsx
import React, { useEffect, useMemo, useState } from "react";

export default function ForkliftPage({ API_BASE }) {
  const [overview, setOverview] = useState(null);
  const [operators, setOperators] = useState([]);
  const [selectedOp, setSelectedOp] = useState("ALL");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  // ✅ pallet-demand (map)
  const [demand, setDemand] = useState(null);
  const [demandLoading, setDemandLoading] = useState(false);
  const [demandErr, setDemandErr] = useState(null);

  const [windowMin, setWindowMin] = useState(30); // 30/60
  const [view, setView] = useState("mix"); // mix | inbound | abb_arr | abb_par

  /**
   * ✅ Nuova logica slot:
   * - "AUTO" = ultimo slot disponibile
   * - "ALL"  = totale giornata (somma su tutti gli slot)
   * - "HH:MM" = slot specifico
   */
  const [slot, setSlot] = useState("AUTO");

  const [showNonStok, setShowNonStok] = useState(false);
  const [nonStokQ, setNonStokQ] = useState("");

  async function loadForklift() {
    setLoading(true);
    setErr(null);

    try {
      const [oRes, opRes] = await Promise.all([
        fetch(`${API_BASE}/forklift/overview`),
        fetch(`${API_BASE}/forklift/operators`),
      ]);

      if (!oRes.ok) throw new Error(`Errore HTTP ${oRes.status} su /forklift/overview`);
      if (!opRes.ok) throw new Error(`Errore HTTP ${opRes.status} su /forklift/operators`);

      const [oJson, opJson] = await Promise.all([oRes.json(), opRes.json()]);

      setOverview(oJson);
      setOperators(Array.isArray(opJson) ? opJson : []);
      setSelectedOp("ALL");
    } catch (e) {
      setErr(e?.message || "Errore sconosciuto");
    } finally {
      setLoading(false);
    }
  }

  async function loadDemand({ force = false } = {}) {
    setDemandLoading(true);
    setDemandErr(null);

    try {
      const qs = new URLSearchParams();
      qs.set("window_min", String(windowMin || 30));
      qs.set("view", String(view || "mix"));

      // ✅ AUTO => non passiamo slot
      // ✅ ALL  => passiamo slot=ALL (backend aggrega)
      // ✅ HH:MM => passiamo slot=HH:MM
      if (slot && slot !== "AUTO") qs.set("slot", slot);

      if (force) qs.set("force", "true");

      const res = await fetch(`${API_BASE}/forklift/pallet-demand?${qs.toString()}`);
      if (!res.ok) throw new Error(`Errore HTTP ${res.status} su /forklift/pallet-demand`);

      const json = await res.json();
      setDemand(json);

      // ✅ Sync slot UI col backend:
      // - AUTO resta AUTO
      // - ALL resta ALL
      // - HH:MM si riallinea se backend risponde con altro
      if (slot && slot !== "AUTO" && slot !== "ALL") {
        const backendSlot = json?.slot ? String(json.slot).slice(0, 5) : null;
        if (backendSlot && backendSlot !== slot) setSlot(backendSlot);
      }
    } catch (e) {
      setDemandErr(e?.message || "Errore sconosciuto");
      setDemand(null);
    } finally {
      setDemandLoading(false);
    }
  }

  useEffect(() => {
    loadForklift();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // quando cambio view/window/slot, ricarico (senza force)
  useEffect(() => {
    loadDemand({ force: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowMin, view, slot]);

  // ---------- helpers ----------
  function n(x, d = 0) {
    const v = Number(x);
    return Number.isFinite(v) ? v : d;
  }
  function fmtInt(x) {
    return Math.round(n(x)).toLocaleString("it-IT");
  }
  function fmtH(x) {
    return `${n(x).toFixed(2)} h`;
  }
  function fmtRate(x) {
    return n(x).toFixed(1);
  }

  // ---------- dataset (ALL o operatore) ----------
  const selectedRow = useMemo(() => {
    if (selectedOp === "ALL") return null;
    return operators.find((r) => String(r?.name) === String(selectedOp)) || null;
  }, [operators, selectedOp]);

  // ALL: usa overview
  const allData = useMemo(() => {
    const o = overview || {};
    return {
      label: "Totale (escluso Kardex)",
      pallet_totali: n(o.pallet_totali ?? o.colli_totali ?? 0),
      ore_totali: n(o.ore_totali ?? 0),
      pallet_ora: n(o.pallet_ora ?? o.prod_colli_ora ?? 0),
      kardex: o.kardex || { pallet: 0, ore: 0, pallet_ora: 0 },
      stok: o.stok || { pallet: 0, ore: 0, pallet_ora: 0 },
      abbassamenti: o.abbassamenti || { pallet: 0, ore: 0, pallet_ora: 0 },
    };
  }, [overview]);

  // OP: usa riga operatore
  const opData = useMemo(() => {
    const r = selectedRow || {};
    return {
      label: `Operatore ${selectedOp}`,
      pallet_totali: n(r.pallet ?? r.colli_total ?? r.colli ?? 0),
      ore_totali: n(r.ore ?? 0),
      pallet_ora: n(r.pallet_ora ?? r.units_per_hour ?? 0),
      kardex: r.kardex || { pallet: 0, ore: 0, pallet_ora: 0 },
      stok: r.stok || { pallet: 0, ore: 0, pallet_ora: 0 },
      abbassamenti: r.abbassamenti || { pallet: 0, ore: 0, pallet_ora: 0 },
    };
  }, [selectedRow, selectedOp]);

  const data = selectedOp === "ALL" ? allData : opData;

  // lista operatori per dropdown
  const opOptions = useMemo(() => {
    const arr = [...operators];
    arr.sort((a, b) => String(a?.name).localeCompare(String(b?.name), "it", { numeric: true }));
    return arr.map((r) => String(r.name));
  }, [operators]);

  // =========================
  // PALLET DEMAND (map data)
  // =========================
  const demandOk = (demand && (demand.status === "ok" || demand.ok === true)) || false;

  // ✅ slot options: usa la lista backend (demand.slots), + AUTO e ALL in cima
  const slotOptions = useMemo(() => {
    const backendSlots = Array.isArray(demand?.slots) ? demand.slots : [];
    const cleaned = backendSlots
      .map((s) => String(s || "").trim())
      .map((s) => (s.toUpperCase() === "ALL" ? "ALL" : s.slice(0, 5)))
      .filter((s) => s === "ALL" || /^\d{2}:\d{2}$/.test(s));

    const opts = ["AUTO", "ALL", ...cleaned];
    return Array.from(new Set(opts));
  }, [demand?.slots]);

  // label dropdown
  function slotLabel(s) {
    if (s === "AUTO") return "Auto (ultimo slot)";
    if (s === "ALL") return "Σ Totale giornata";
    return s;
  }

  // TOP rows (normalizzati)
  const topRows = useMemo(() => {
    const t = demand?.top || {};
    const v = t?.[view] || [];
    if (!Array.isArray(v)) return [];

    return v.map((r) => {
      const label = r.label ?? r.corsia ?? r.corsia_num ?? r.corsia_label ?? r.aisle ?? null;
      const labelStr = label != null ? String(label) : "";

      const inbound = n(r.inbound ?? r.scarico ?? r.scarico_pallet ?? r.pallet_scarico ?? 0);
      const abbArr = n(r.abb_arr ?? r.abbArr ?? r.abbassamenti_arr ?? r.riprist_arr ?? r.ripristino_arr ?? 0);
      const abbPar = n(r.abb_par ?? r.abbPar ?? r.abbassamenti_par ?? r.riprist_par ?? r.ripristino_par ?? 0);

      // 🔥 FIX: mix = inbound + abbArr + abbPar (se backend non lo manda)
      const mixVal = inbound + abbArr + abbPar;


      return {
        ...r,
        label: labelStr,
        corsia: r.corsia ?? labelStr,
        inbound,
        abbArr,
        abbPar,
        mix: mixVal,
      };
    });
  }, [demand, view]);

  // normalizzo corsie: 75 → 13
  const corsie = useMemo(() => {
    const arr = Array.isArray(demand?.corsie) ? demand.corsie : [];

    const normalized = arr
      .map((r) => {
        const label = r.label ?? r.corsia ?? r.corsia_num ?? r.corsia_label ?? r.aisle ?? null;

        const labelStr = label != null ? String(label) : "";
        const labelNum = parseInt(labelStr, 10);

        // metriche (robuste ai nomi)
        const inbound = n(r.inbound ?? r.scarico ?? r.scarico_pallet ?? r.pallet_scarico ?? 0);
        const abbArr = n(r.abb_arr ?? r.abbArr ?? r.abbassamenti_arr ?? r.riprist_arr ?? r.ripristino_arr ?? 0);
        const abbPar = n(r.abb_par ?? r.abbPar ?? r.abbassamenti_par ?? r.riprist_par ?? r.ripristino_par ?? 0);

        // 🔥 FIX: mix = inbound + abbArr + abbPar (fallback)
        const mixVal = inbound + abbArr + abbPar;


        return {
          ...r,
          label: labelStr,
          labelNum: Number.isFinite(labelNum) ? labelNum : null,
          inbound,
          abbArr,
          abbPar,
          mix: mixVal,
        };
      })
      .filter((r) => r.labelNum != null)
      .filter((r) => r.labelNum <= 75 && r.labelNum >= 13)
      .sort((a, b) => (b.labelNum || 0) - (a.labelNum || 0));

    return normalized;
  }, [demand]);

  const maxMetric = useMemo(() => {
    const key =
      view === "inbound" ? "inbound" : view === "abb_arr" ? "abbArr" : view === "abb_par" ? "abbPar" : "mix";

    const m =
      corsie.reduce((acc, r) => {
        const v = key === "inbound" ? r.inbound : key === "abbArr" ? r.abbArr : key === "abbPar" ? r.abbPar : r.mix;
        return v > acc ? v : acc;
      }, 0) || 1;

    return m;
  }, [corsie, view]);

  const nonStokRows = useMemo(() => {
    const arr = Array.isArray(demand?.non_stok) ? demand.non_stok : [];
    const q = (nonStokQ || "").trim().toLowerCase();
    if (!q) return arr;

    return arr.filter((r) => {
      const s = JSON.stringify(r || {}).toLowerCase();
      return s.includes(q);
    });
  }, [demand, nonStokQ]);

  const nonStokCount = useMemo(() => {
    const arr = Array.isArray(demand?.non_stok) ? demand.non_stok : [];
    return arr.length;
  }, [demand]);

  // ✅ KPI “totali”: Totale = inbound + abbArr + abbPar
  const demandTotals = useMemo(() => {
    const sum = { inbound: 0, abbArr: 0, abbPar: 0, mix: 0 };
    for (const r of corsie) {
      sum.inbound += n(r.inbound);
      sum.abbArr += n(r.abbArr);
      sum.abbPar += n(r.abbPar);
      sum.mix += n(r.inbound) + n(r.abbArr) + n(r.abbPar);
    }
    return sum;
  }, [corsie]);

  const slotBadge = useMemo(() => {
    const s = String(demand?.slot || "—").toUpperCase();
    return s === "ALL" ? "Σ Totale giornata" : s;
  }, [demand?.slot]);

  // ---------- render ----------
  return (
    <div style={{ padding: 16 }}>
      {/* HEADER KPI CARRELLISTI */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <div>
            <h2 style={{ margin: 0 }}>Carrellisti</h2>
            <p style={{ margin: "4px 0 0 0", opacity: 0.8 }}>KPI pallet/ora con dettaglio: Kardex / Stok / Abbassamenti</p>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 220 }}>
              <div style={{ fontSize: 11, opacity: 0.75 }}>Seleziona operatore</div>
              <select
                value={selectedOp}
                onChange={(e) => setSelectedOp(e.target.value)}
                style={{
                  width: "100%",
                  background: "#020617",
                  color: "#e5e7eb",
                  borderRadius: 8,
                  border: "1px solid rgba(148,163,184,0.5)",
                  fontSize: 12,
                  padding: "6px 8px",
                }}
              >
                <option value="ALL">TUTTI (escluso Kardex)</option>
                {opOptions.map((op) => (
                  <option key={op} value={op}>
                    Operatore {op}
                  </option>
                ))}
              </select>
            </div>

            <button onClick={loadForklift} style={btnSecondary}>
              {loading ? "Carico…" : "Ricarica"}
            </button>
          </div>
        </div>

        {err && <div style={{ marginTop: 10, color: "#f97373", fontSize: 12 }}>Errore: {err}</div>}

        <div style={{ marginTop: 10, fontSize: 12, opacity: 0.85 }}>
          Vista: <strong>{data.label}</strong>
        </div>
      </div>

      {/* KPI principali (NO Kardex nel totale) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
        <KpiCard
          title="Pallet totali"
          value={fmtInt(data.pallet_totali)}
          subtitle={selectedOp === "ALL" ? "Somma movimenti (NO Kardex)" : "Somma movimenti operatore"}
        />
        <KpiCard title="Ore totali" value={fmtH(data.ore_totali)} subtitle="Somma tempi validi (gap > 40 min escluso)" />
        <KpiCard title="Pallet/ora" value={fmtRate(data.pallet_ora)} subtitle="Pallet totali / ore totali" />
        <KpiCard
          title="Controllo Kardex"
          value={fmtRate(n(data.kardex?.pallet_ora))}
          subtitle={`${fmtInt(n(data.kardex?.pallet))} pallet • ${fmtH(n(data.kardex?.ore))}`}
        />
      </div>

      {/* KPI categorie */}
      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
        <KpiCard title="STOK pallet/ora" value={fmtRate(n(data.stok?.pallet_ora))} subtitle={`${fmtInt(n(data.stok?.pallet))} pallet • ${fmtH(n(data.stok?.ore))}`} />
        <KpiCard title="ABBASSAMENTI pallet/ora" value={fmtRate(n(data.abbassamenti?.pallet_ora))} subtitle={`${fmtInt(n(data.abbassamenti?.pallet))} pallet • ${fmtH(n(data.abbassamenti?.ore))}`} />
      </div>

      {loading && <div className="info-banner" style={{ marginTop: 12 }}>Caricamento dati carrellisti…</div>}

      {/* ============================
          ✅ WOW: PALLET DEMAND MAP
         ============================ */}
      <div className="card" style={{ marginTop: 14 }}>
        <div
          className="card-header"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div style={{ minWidth: 280 }}>
            <h2 style={{ margin: 0 }}>Fabbisogno carrellisti</h2>
            <p style={{ margin: "4px 0 0 0", opacity: 0.8 }}>
              Mappa corsie 75→13 (no Kardex): inbound da scarico + abbassamenti (RIPRIST.TOT).
            </p>

            <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Badge>Slot: {slotBadge}</Badge>
              <Badge>Window: {windowMin} min</Badge>
              <Badge>View: {viewLabel(view)}</Badge>
              <Badge>NON STOK: {fmtInt(nonStokCount)}</Badge>
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
            {/* window */}
            <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 110 }}>
              <div style={miniLabel}>Finestra</div>
              <select value={windowMin} onChange={(e) => setWindowMin(Number(e.target.value))} style={selectStyle}>
                <option value={30}>30 min</option>
                <option value={60}>60 min</option>
              </select>
            </div>

            {/* slot */}
            <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 150 }}>
              <div style={miniLabel}>Slot</div>
              <select value={slot} onChange={(e) => setSlot(e.target.value)} style={selectStyle}>
                {slotOptions.map((s) => (
                  <option key={s} value={s}>
                    {slotLabel(s)}
                  </option>
                ))}
              </select>
            </div>

            {/* quick buttons */}
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={miniLabel}>Azioni</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <ToggleBtn active={slot === "AUTO"} onClick={() => setSlot("AUTO")}>
                  Auto
                </ToggleBtn>
                <ToggleBtn active={slot === "ALL"} onClick={() => setSlot("ALL")}>
                  Σ Totale
                </ToggleBtn>
              </div>
            </div>

            {/* view toggle */}
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={miniLabel}>Vista</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <ToggleBtn active={view === "mix"} onClick={() => setView("mix")}>
                  Mix
                </ToggleBtn>
                <ToggleBtn active={view === "inbound"} onClick={() => setView("inbound")}>
                  Inbound
                </ToggleBtn>
                <ToggleBtn active={view === "abb_arr"} onClick={() => setView("abb_arr")}>
                  Abb ARR
                </ToggleBtn>
                <ToggleBtn active={view === "abb_par"} onClick={() => setView("abb_par")}>
                  Abb PAR
                </ToggleBtn>
              </div>
            </div>

            <button onClick={() => loadDemand({ force: false })} style={btnSecondary}>
              {demandLoading ? "Carico…" : "Aggiorna"}
            </button>

            <button onClick={() => loadDemand({ force: true })} style={btnPrimary} title="Ricalcola anche se è in cache">
              {demandLoading ? "Ricalcolo…" : "Forza ricalcolo"}
            </button>

            <button
              onClick={() => setShowNonStok(true)}
              style={{
                ...btnWarn,
                opacity: nonStokCount > 0 ? 1 : 0.7,
              }}
              title="Apri lista NON STOK"
            >
              NON STOK ({fmtInt(nonStokCount)})
            </button>
          </div>
        </div>

        {demandErr && <div style={{ marginTop: 10, color: "#f97373", fontSize: 12 }}>Errore: {demandErr}</div>}

        {!demandOk && !demandLoading && (
          <div style={{ marginTop: 10, fontSize: 12, opacity: 0.8 }}>
            Nessun dato disponibile. Carica <strong>dati_pallet.xlsx</strong> + <strong>carrellisti.xlsm</strong> e poi clicca Aggiorna.
          </div>
        )}

        {demandLoading && <div className="info-banner" style={{ marginTop: 12 }}>Calcolo fabbisogno corsie…</div>}

        {/* ✅ KPI “somma” sempre visibili quando demandOk */}
        {demandOk && (
          <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
            <KpiCard
              title={slot === "ALL" ? "Inbound totale (giornata)" : "Inbound (slot)"}
              value={fmtInt(demandTotals.inbound)}
              subtitle={slot === "ALL" ? "Somma inbound su tutti gli slot" : "Somma inbound nello slot selezionato"}
            />
            <KpiCard
              title={slot === "ALL" ? "Abb ARR totale (giornata)" : "Abb ARR (slot)"}
              value={fmtInt(demandTotals.abbArr)}
              subtitle={slot === "ALL" ? "Somma ripristini ARR su tutti gli slot" : "Somma ripristini ARR nello slot"}
            />
            <KpiCard
              title={slot === "ALL" ? "Abb PAR totale (giornata)" : "Abb PAR (slot)"}
              value={fmtInt(demandTotals.abbPar)}
              subtitle={slot === "ALL" ? "Somma ripristini PAR su tutti gli slot" : "Somma ripristini PAR nello slot"}
            />
            <KpiCard
              title={slot === "ALL" ? "Totale (giornata)" : "Totale (slot)"}
              value={fmtInt(demandTotals.mix)}
              subtitle="Totale = inbound + abb_arr + abb_par"
            />
          </div>
        )}

        {demandOk && (
          <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "minmax(0, 1.6fr) minmax(0, 1fr)", gap: 12 }}>
            {/* MAP */}
            <div style={panelCard}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div style={{ fontWeight: 900, fontSize: 13 }}>
                  Mappa corsie (intensità = {viewLabel(view)}) {slot === "ALL" ? "— Σ Totale" : ""}
                </div>
                <div style={{ fontSize: 11, opacity: 0.75 }}>
                  max: <strong>{fmtInt(maxMetric)}</strong>
                </div>
              </div>

              <DemandVerticalMap rows={corsie} view={view} maxMetric={maxMetric} />

              <div style={{ marginTop: 10, fontSize: 11, opacity: 0.75 }}>
                Suggerimento: usa <strong>Mix</strong> per bilanciare inbound + abbassamenti, poi passa a <strong>Abb ARR</strong> per vedere dove “atterrano” i ripristini.
              </div>
            </div>

            {/* TOP */}
            <div style={panelCard}>
              <div style={{ fontWeight: 900, fontSize: 13, marginBottom: 10 }}>
                Top corsie ({viewLabel(view)}) {slot === "ALL" ? "— Σ Totale" : ""}
              </div>
              {topRows.length === 0 ? <div style={{ fontSize: 12, opacity: 0.75 }}>Nessun top disponibile per questa vista.</div> : <TopList rows={topRows} />}

              <div style={{ marginTop: 12, fontSize: 12, opacity: 0.85 }}>
                Obiettivo operativo: sposta 1 retrattilista dalle corsie a intensità bassa verso le top corsie {slot === "ALL" ? "del totale giornata." : "di questo slot."}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* MODAL NON STOK */}
      {showNonStok && (
        <Modal onClose={() => setShowNonStok(false)} title={`Pallet NON STOK (${fmtInt(nonStokCount)})`}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
            <input
              value={nonStokQ}
              onChange={(e) => setNonStokQ(e.target.value)}
              placeholder="Cerca (supporto / articolo / descrizione...)"
              style={{
                width: "min(520px, 100%)",
                background: "#020617",
                color: "#e5e7eb",
                borderRadius: 10,
                border: "1px solid rgba(148,163,184,0.5)",
                fontSize: 12,
                padding: "8px 10px",
              }}
            />
            <div style={{ fontSize: 12, opacity: 0.8 }}>
              Mostrati: <strong>{fmtInt(nonStokRows.length)}</strong>
            </div>
          </div>

          <div style={{ overflowX: "auto", borderRadius: 12, border: "1px solid rgba(148,163,184,0.18)" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={th}>Supporto</th>
                  <th style={th}>Ora scarico</th>
                  <th style={th}>Articolo</th>
                  <th style={th}>Descrizione</th>
                </tr>
              </thead>
              <tbody>
                {nonStokRows.map((r, idx) => (
                  <tr key={idx}>
                    <td style={td}>{String(r.SUPPORTO ?? r.supporto ?? "")}</td>
                    <td style={td}>{String(r["ORA INIZIO CONSEGNA"] ?? r.ora ?? r.ora_scarico ?? "")}</td>
                    <td style={td}>{String(r.ARTICOLO ?? r.articolo ?? "")}</td>
                    <td style={td}>{String(r["DESCRIZIONE ARTICOLO"] ?? r.descrizione ?? r.descr_articolo ?? "")}</td>
                  </tr>
                ))}
                {nonStokRows.length === 0 && (
                  <tr>
                    <td style={td} colSpan={4}>
                      Nessun risultato.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 10, fontSize: 12, opacity: 0.8 }}>
            Nota: NON STOK = scaricato ma non risulta preso in carico/stoccato da nessun retrattilista nel file carrellisti.
          </div>
        </Modal>
      )}
    </div>
  );
}

/* =======================
   WOW MAP COMPONENT
======================= */

function DemandVerticalMap({ rows, view, maxMetric }) {
  const [hovered, setHovered] = useState(null);
  const [selected, setSelected] = useState(null);

  function metricOf(r) {
    if (view === "inbound") return r.inbound;
    if (view === "abb_arr") return r.abbArr;
    if (view === "abb_par") return r.abbPar;
    return r.mix;
  }

  function colorFor(intensity) {
    const safe = 0.15 + intensity * 0.85;

    if (view === "mix") return `rgba(14, 165, 233, ${safe})`; // cyan
    if (view === "inbound") return `rgba(59, 130, 246, ${safe})`; // blue
    if (view === "abb_arr") return `rgba(248, 113, 113, ${safe})`; // red
    return `rgba(251, 191, 36, ${safe})`; // amber (abb_par)
  }

  if (!rows || rows.length === 0) {
    return <div style={{ fontSize: 12, opacity: 0.75 }}>Nessuna corsia nel range 75→13.</div>;
  }

  return (
    <div style={{ position: "relative" }}>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 6,
          width: "100%",
          maxHeight: 560,
          overflowY: "auto",
          overflowX: "hidden",
          paddingRight: 6,
        }}
      >
        {rows.map((r, idx) => {
          const metric = metricOf(r);
          const intensity = maxMetric > 0 ? metric / maxMetric : 0;

          const glow =
            intensity > 0.75
              ? "0 0 18px rgba(56,189,248,0.55)"
              : intensity > 0.45
              ? "0 0 12px rgba(56,189,248,0.35)"
              : "0 0 6px rgba(15,23,42,0.6)";

          const baseColor = colorFor(intensity);

          const title = `Corsia ${r.label} | Mix=${r.mix} | Inbound=${r.inbound} | Abb ARR=${r.abbArr} | Abb PAR=${r.abbPar}`;

          return (
            <div
              key={`${r.label}-${idx}`}
              style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}
              onMouseEnter={() => setHovered(r)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => setSelected(r)}
              title={title}
            >
              <div style={{ width: 56, fontSize: 12, color: "#9ca3af", textAlign: "right" }}>{r.label}</div>

              <div
                style={{
                  flex: 1,
                  height: 10,
                  borderRadius: 999,
                  background: "#020617",
                  border: "1px solid rgba(148,163,184,0.35)",
                  overflow: "hidden",
                  position: "relative",
                }}
              >
                <div
                  style={{
                    width: "100%",
                    height: "100%",
                    borderRadius: 999,
                    background: baseColor,
                    boxShadow: glow,
                    transition: "all 250ms ease-out",
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background: "linear-gradient(90deg, rgba(255,255,255,0.05), rgba(255,255,255,0), rgba(255,255,255,0.04))",
                    mixBlendMode: "screen",
                    pointerEvents: "none",
                  }}
                />
              </div>

              <div style={{ width: 86, fontSize: 12, fontWeight: 900, color: "#e5e7eb", textAlign: "right" }}>
                {Math.round(metric)}
              </div>
            </div>
          );
        })}
      </div>

      {/* hover panel */}
      <div
        style={{
          marginTop: 12,
          padding: 12,
          borderRadius: 12,
          background: "linear-gradient(135deg, rgba(15,23,42,0.95), rgba(15,23,42,0.8))",
          border: "1px solid rgba(148,163,184,0.25)",
          fontSize: 12,
          color: "#e5e7eb",
          minHeight: 56,
        }}
      >
        {hovered ? (
          <>
            <div style={{ fontWeight: 900, marginBottom: 6 }}>
              Corsia {hovered.label} — {viewLabel(view)}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 10 }}>
              <MiniKpi title="Mix" value={hovered.mix} />
              <MiniKpi title="Inbound" value={hovered.inbound} />
              <MiniKpi title="Abb ARR" value={hovered.abbArr} />
              <MiniKpi title="Abb PAR" value={hovered.abbPar} />
            </div>
          </>
        ) : (
          <div style={{ opacity: 0.75 }}>Passa il mouse su una corsia per vedere il dettaglio (Mix / Inbound / Abb ARR / Abb PAR).</div>
        )}
      </div>

      {/* click popup */}
      {selected && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: "rgba(15,23,42,0.78)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 20,
          }}
          onClick={() => setSelected(null)}
        >
          <div
            style={{
              background: "rgba(2,6,23,0.98)",
              borderRadius: 16,
              border: "1px solid rgba(148,163,184,0.35)",
              padding: 16,
              width: "min(520px, 94vw)",
              boxShadow: "0 20px 60px rgba(0,0,0,0.65)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div>
                <div style={{ fontSize: 12, opacity: 0.7, letterSpacing: 0.08, textTransform: "uppercase" }}>Corsia</div>
                <div style={{ fontSize: 22, fontWeight: 950, color: "#e5e7eb" }}>{selected.label}</div>
              </div>
              <button onClick={() => setSelected(null)} style={{ ...btnGhost, fontSize: 18 }}>
                ×
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 10 }}>
              <KpiCard title="Mix" value={String(Math.round(selected.mix))} subtitle="Inbound + Abb ARR + Abb PAR (peso operativo)" />
              <KpiCard title="Inbound" value={String(Math.round(selected.inbound))} subtitle="Pallet scaricati (stimati)" />
              <KpiCard title="Abb ARR" value={String(Math.round(selected.abbArr))} subtitle="Riprist.TOT per corsia arrivo" />
              <KpiCard title="Abb PAR" value={String(Math.round(selected.abbPar))} subtitle="Riprist.TOT per corsia partenza" />
            </div>

            <div style={{ marginTop: 12, fontSize: 12, opacity: 0.8 }}>
              Azione consigliata: se questa corsia è in top, sposta 1 retrattilista qui nello slot corrente.
            </div>

            <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button onClick={() => setSelected(null)} style={btnSecondary}>
                Chiudi
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TopList({ rows }) {
  function pickLabel(r) {
    return String(r.corsia ?? r.label ?? r.aisle ?? "");
  }
  function pickValue(r) {
    const v = r.value ?? r.score ?? r.metric ?? r.mix ?? r.inbound ?? r.abbArr ?? r.abb_arr ?? r.abbPar ?? r.abb_par ?? 0;
    return Number(v) || 0;
  }

  const top10 = rows.slice(0, 10);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {top10.map((r, i) => (
        <div
          key={`${pickLabel(r)}-${i}`}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "10px 12px",
            borderRadius: 12,
            border: "1px solid rgba(148,163,184,0.18)",
            background: "rgba(15,23,42,0.55)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 26,
                height: 26,
                borderRadius: 10,
                display: "grid",
                placeItems: "center",
                fontWeight: 900,
                background: "rgba(56,189,248,0.14)",
                border: "1px solid rgba(56,189,248,0.22)",
                color: "#e5e7eb",
                fontSize: 12,
              }}
            >
              {i + 1}
            </div>
            <div>
              <div style={{ fontWeight: 950, fontSize: 13 }}>Corsia {pickLabel(r)}</div>
              <div style={{ fontSize: 11, opacity: 0.7 }}>Priorità operativa nello slot</div>
            </div>
          </div>
          <div style={{ fontWeight: 950, fontSize: 14 }}>{Math.round(pickValue(r))}</div>
        </div>
      ))}
    </div>
  );
}

/* =======================
   UI atoms
======================= */

function KpiCard({ title, value, subtitle }) {
  return (
    <div
      style={{
        padding: 12,
        borderRadius: 14,
        border: "1px solid rgba(148,163,184,0.22)",
        background: "linear-gradient(135deg, rgba(15,23,42,0.95), rgba(15,23,42,0.75))",
      }}
    >
      <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: 22, fontWeight: 950, color: "#e5e7eb" }}>{value}</div>
      <div style={{ fontSize: 11, opacity: 0.75, marginTop: 4 }}>{subtitle}</div>
    </div>
  );
}

function MiniKpi({ title, value }) {
  return (
    <div
      style={{
        padding: 10,
        borderRadius: 12,
        border: "1px solid rgba(148,163,184,0.18)",
        background: "rgba(15,23,42,0.55)",
      }}
    >
      <div style={{ fontSize: 11, opacity: 0.7 }}>{title}</div>
      <div style={{ fontSize: 16, fontWeight: 950 }}>{Math.round(Number(value || 0))}</div>
    </div>
  );
}

function Badge({ children }) {
  return (
    <div
      style={{
        fontSize: 11,
        padding: "6px 10px",
        borderRadius: 999,
        border: "1px solid rgba(148,163,184,0.22)",
        background: "rgba(15,23,42,0.55)",
        color: "#e5e7eb",
      }}
    >
      {children}
    </div>
  );
}

function ToggleBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "7px 10px",
        borderRadius: 12,
        border: active ? "1px solid rgba(56,189,248,0.55)" : "1px solid rgba(148,163,184,0.22)",
        background: active ? "rgba(56,189,248,0.16)" : "rgba(15,23,42,0.55)",
        color: "#e5e7eb",
        cursor: "pointer",
        fontWeight: 900,
        fontSize: 12,
      }}
    >
      {children}
    </button>
  );
}

function Modal({ title, onClose, children }) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(2,6,23,0.72)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: "min(1100px, 96vw)",
          maxHeight: "88vh",
          overflow: "auto",
          background: "rgba(2,6,23,0.98)",
          borderRadius: 18,
          border: "1px solid rgba(148,163,184,0.28)",
          boxShadow: "0 30px 80px rgba(0,0,0,0.65)",
          padding: 14,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div style={{ fontSize: 16, fontWeight: 950, color: "#e5e7eb" }}>{title}</div>
          <button onClick={onClose} style={btnGhost}>
            Chiudi
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function viewLabel(v) {
  if (v === "inbound") return "Inbound (scarico)";
  if (v === "abb_arr") return "Abbassamenti (ARR corsia)";
  if (v === "abb_par") return "Abbassamenti (PAR corsia)";
  return "Mix (Inbound + Abb ARR + Abb PAR)";
}

/* =======================
   styles
======================= */

const panelCard = {
  padding: 12,
  borderRadius: 16,
  border: "1px solid rgba(148,163,184,0.22)",
  background: "linear-gradient(135deg, rgba(15,23,42,0.95), rgba(15,23,42,0.75))",
};

const miniLabel = { fontSize: 11, opacity: 0.75 };

const selectStyle = {
  width: "100%",
  background: "#020617",
  color: "#e5e7eb",
  borderRadius: 10,
  border: "1px solid rgba(148,163,184,0.5)",
  fontSize: 12,
  padding: "8px 10px",
};

const btnSecondary = {
  padding: "10px 12px",
  borderRadius: 12,
  border: "1px solid rgba(148,163,184,0.25)",
  background: "rgba(15,23,42,0.6)",
  color: "#e5e7eb",
  cursor: "pointer",
  fontWeight: 900,
};

const btnPrimary = {
  padding: "10px 12px",
  borderRadius: 12,
  border: "1px solid rgba(56,189,248,0.35)",
  background: "linear-gradient(135deg, rgba(56,189,248,0.22), rgba(34,197,94,0.12))",
  color: "#e5e7eb",
  cursor: "pointer",
  fontWeight: 950,
};

const btnWarn = {
  padding: "10px 12px",
  borderRadius: 12,
  border: "1px solid rgba(248,113,113,0.35)",
  background: "linear-gradient(135deg, rgba(248,113,113,0.22), rgba(251,191,36,0.12))",
  color: "#e5e7eb",
  cursor: "pointer",
  fontWeight: 950,
};

const btnGhost = {
  padding: "8px 10px",
  borderRadius: 12,
  border: "1px solid rgba(148,163,184,0.22)",
  background: "transparent",
  color: "#e5e7eb",
  cursor: "pointer",
  fontWeight: 900,
};

const th = {
  textAlign: "left",
  padding: "10px 10px",
  borderBottom: "1px solid rgba(148,163,184,0.22)",
  opacity: 0.85,
  background: "rgba(15,23,42,0.6)",
  position: "sticky",
  top: 0,
};

const td = {
  padding: "9px 10px",
  borderBottom: "1px solid rgba(148,163,184,0.12)",
  opacity: 0.95,
};
