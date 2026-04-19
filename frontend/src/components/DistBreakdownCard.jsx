import React, { useEffect, useMemo, useRef, useState } from "react";

export default function DistBreakdownCard({ API_BASE }) {
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [data, setData] = useState(null);

  const [pickedDate, setPickedDate] = useState(""); // YYYY-MM-DD (opzionale)

  // UI: mostra overlay solo su hover o click (pin)
  const [hover, setHover] = useState(false);
  const [pinned, setPinned] = useState(false);
  const cardRef = useRef(null);

  const overlayOpen = hover || pinned;

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const url = pickedDate
        ? `${API_BASE}/kpi/dist-breakdown?date=${encodeURIComponent(pickedDate)}`
        : `${API_BASE}/kpi/dist-breakdown`;

      const res = await fetch(url);
      if (!res.ok) throw new Error("Errore nel caricamento dist-breakdown");
      const json = await res.json();
      setData(json);
    } catch (e) {
      console.error(e);
      setErr(e?.message || "Errore sconosciuto");
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  // carica una volta
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ricarica quando cambia la data (debounce)
  useEffect(() => {
    const t = setTimeout(() => load(), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickedDate]);

  // chiudi overlay se clicchi fuori (quando pinned)
  useEffect(() => {
    function onDocMouseDown(e) {
      if (!pinned) return;
      const el = cardRef.current;
      if (!el) return;
      if (!el.contains(e.target)) setPinned(false);
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [pinned]);

  const distValue = useMemo(() => {
    const v = Number(data?.dist_media_step_m || 0);
    if (!isFinite(v)) return null;
    return v;
  }, [data]);

  const breakdownSections = useMemo(() => {
    const b = data?.breakdown || {};
    return [
      { key: "AREA", label: "AREA", rows: Array.isArray(b.AREA) ? b.AREA : [] },
      { key: "CIRCUITO", label: "CIRCUITO", rows: Array.isArray(b.CIRCUITO) ? b.CIRCUITO : [] },
      { key: "EVENTO", label: "EVENTO", rows: Array.isArray(b.EVENTO) ? b.EVENTO : [] },
    ];
  }, [data]);

  const compareRows = useMemo(() => {
    const c = data?.compare || {};
    if (c.status !== "ok") return [];
    return Array.isArray(c.rows) ? c.rows : [];
  }, [data]);

  const hasCompare = (data?.compare?.status || "missing") === "ok" && compareRows.length > 0;

  const infoTooltip =
    "Passa col mouse (o clicca per bloccare) per vedere la scomposizione (AREA/CIRCUITO/EVENTO) " +
    "e la comparativa vs storico se hai caricato report_storico.xlsx.";

  return (
    <div
      ref={cardRef}
      className="card kpi-card"
      style={{ position: "relative", cursor: "default" }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => setPinned((v) => !v)}
      title="Hover per dettagli • Click per bloccare"
    >
      {/* HEADER KPI (sempre visibile, come prima) */}
      <div className="kpi-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span>Distanza media tra righe</span>

        <span
          title={infoTooltip}
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 18,
            height: 18,
            borderRadius: 999,
            fontSize: 12,
            cursor: "help",
            border: "1px solid rgba(148,163,184,0.6)",
            color: "#e5e7eb",
            background: "rgba(2,6,23,0.5)",
          }}
          onClick={(e) => {
            // evita toggle pinned cliccando sulla i
            e.stopPropagation();
            setPinned((v) => !v);
          }}
        >
          i
        </span>

        {/* piccolo indicatore "pinned" non invasivo */}
        {pinned && (
          <span
            style={{
              marginLeft: 6,
              fontSize: 11,
              color: "#9ca3af",
              border: "1px solid rgba(148,163,184,0.35)",
              padding: "2px 6px",
              borderRadius: 999,
              background: "rgba(2,6,23,0.25)",
            }}
            title="Dettagli bloccati (clicca per chiudere o clicca fuori)"
            onClick={(e) => {
              e.stopPropagation();
              setPinned(false);
            }}
          >
            blocca ✓
          </span>
        )}

        {/* date picker SOLO quando overlay aperto (così non sporca la card) */}
        {overlayOpen && (
          <div
            style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}
            onClick={(e) => e.stopPropagation()}
          >
            <input
              type="date"
              value={pickedDate}
              onChange={(e) => setPickedDate(e.target.value)}
              style={{
                background: "#020617",
                color: "#e5e7eb",
                borderRadius: 6,
                border: "1px solid rgba(148,163,184,0.7)",
                fontSize: 12,
                padding: "4px 6px",
                height: 28,
              }}
              title="Seleziona una data. Se vuoto: ultima data disponibile."
            />
            <button
              onClick={load}
              style={{
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid rgba(148,163,184,0.6)",
                background: "rgba(2,6,23,0.5)",
                color: "#e5e7eb",
                fontSize: 12,
                cursor: "pointer",
                height: 28,
              }}
              title="Ricarica"
            >
              ↻
            </button>
          </div>
        )}
      </div>

      {/* KPI VALUE (sempre visibile, come prima) */}
      {loading ? (
        <>
          <div className="kpi-value">--</div>
          <div className="kpi-subtitle">Caricamento…</div>
        </>
      ) : err ? (
        <>
          <div className="kpi-value">--</div>
          <div className="kpi-subtitle" style={{ color: "#f97373" }}>
            {err}
          </div>
        </>
      ) : data?.status !== "ok" ? (
        <>
          <div className="kpi-value">--</div>
          <div className="kpi-subtitle" style={{ color: "#f97373" }}>
            {data?.message || "Dati non disponibili"}
          </div>
        </>
      ) : (
        <>
          <div className="kpi-value">{distValue != null ? `${distValue.toFixed(1)} m` : "--"}</div>
          <div className="kpi-subtitle">
            {data?.date ? `Data: ${data.date}` : "Data: --"} • (hover/click per dettagli)
          </div>
        </>
      )}

      {/* OVERLAY DETTAGLI (solo su hover/click) */}
      {overlayOpen && !loading && !err && data?.status === "ok" && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            position: "absolute",
            left: 0,
            top: "calc(100% + 8px)",
            width: "min(720px, 90vw)",
            zIndex: 50,
            padding: 12,
            borderRadius: 12,
            border: "1px solid rgba(148,163,184,0.35)",
            background: "linear-gradient(135deg, rgba(15,23,42,0.98), rgba(2,6,23,0.96))",
            boxShadow: "0 20px 60px rgba(0,0,0,0.45)",
          }}
        >
          {/* Breakdown */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
            {breakdownSections.map((sec) => (
              <div key={sec.key}>
                <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 6, letterSpacing: 0.5 }}>
                  {sec.label}
                </div>

                {sec.rows.length === 0 ? (
                  <div style={{ fontSize: 12, opacity: 0.7 }}>Nessun dato</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {sec.rows.slice(0, 6).map((r, idx) => {
                      const pct = r?.pct_steps != null ? Number(r.pct_steps) : null;
                      const mean = r?.mean_m != null ? Number(r.mean_m) : null;

                      return (
                        <div
                          key={`${sec.key}-${idx}`}
                          style={{
                            display: "grid",
                            gridTemplateColumns: "1fr auto auto",
                            gap: 8,
                            alignItems: "center",
                            fontSize: 12,
                            padding: "6px 8px",
                            borderRadius: 10,
                            border: "1px solid rgba(148,163,184,0.18)",
                            background: "rgba(2,6,23,0.35)",
                          }}
                        >
                          <div style={{ color: "#e5e7eb", fontWeight: 700 }}>{String(r?.Bucket || "-")}</div>
                          <div style={{ color: "#e5e7eb" }}>
                            {mean != null && isFinite(mean) ? `${mean.toFixed(2)} m` : "--"}
                          </div>
                          <div style={{ color: "#9ca3af" }}>{pct != null && isFinite(pct) ? `${pct.toFixed(1)}%` : ""}</div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Comparativa */}
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid rgba(148,163,184,0.25)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: "#e5e7eb" }}>Comparativa vs storico</div>
              <div style={{ fontSize: 11, color: "#9ca3af" }}>
                {data?.compare?.status === "ok" ? `(${data?.compare?.mode || "ok"})` : "(storico non caricato / non valido)"}
              </div>

              <div style={{ marginLeft: "auto", fontSize: 11, color: "#9ca3af" }}>
                Δ negativo = <span style={{ color: "#22c55e", fontWeight: 800 }}>migliora</span> • Δ positivo ={" "}
                <span style={{ color: "#f97373", fontWeight: 800 }}>peggiora</span>
              </div>
            </div>

            {!hasCompare ? (
              <div style={{ fontSize: 12, opacity: 0.8 }}>
                Nessuna comparativa disponibile. Carica <strong>report_storico.xlsx</strong> con dataset{" "}
                <code>history</code> e riprova.
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ textAlign: "left", color: "#9ca3af" }}>
                      <th style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.18)" }}>Dim</th>
                      <th style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.18)" }}>Bucket</th>
                      <th style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.18)" }}>Oggi</th>
                      <th style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.18)" }}>Storico</th>
                      <th style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.18)" }}>Δ m</th>
                      <th style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.18)" }}>Δ %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compareRows.slice(0, 24).map((r, idx) => {
                      const dm = r?.delta_m != null ? Number(r.delta_m) : null;
                      const dp = r?.delta_pct != null ? Number(r.delta_pct) : null;

                      const deltaColor =
                        dm == null || !isFinite(dm)
                          ? "#9ca3af"
                          : dm < 0
                          ? "#22c55e"
                          : dm > 0
                          ? "#f97373"
                          : "#e5e7eb";

                      return (
                        <tr key={idx}>
                          <td style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.10)" }}>
                            {String(r?.Dimensione || "-")}
                          </td>
                          <td style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.10)" }}>
                            {String(r?.Bucket || "-")}
                          </td>
                          <td style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.10)" }}>
                            {isFinite(Number(r?.mean_m_today)) ? Number(r.mean_m_today).toFixed(2) : "--"}
                          </td>
                          <td style={{ padding: "6px 6px", borderBottom: "1px solid rgba(148,163,184,0.10)" }}>
                            {isFinite(Number(r?.mean_m_base)) ? Number(r.mean_m_base).toFixed(2) : "--"}
                          </td>
                          <td
                            style={{
                              padding: "6px 6px",
                              borderBottom: "1px solid rgba(148,163,184,0.10)",
                              color: deltaColor,
                              fontWeight: 900,
                            }}
                          >
                            {dm != null && isFinite(dm) ? dm.toFixed(2) : "--"}
                          </td>
                          <td
                            style={{
                              padding: "6px 6px",
                              borderBottom: "1px solid rgba(148,163,184,0.10)",
                              color: deltaColor,
                              fontWeight: 900,
                            }}
                          >
                            {dp != null && isFinite(dp) ? `${dp.toFixed(1)}%` : "--"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* footer hint */}
          <div style={{ marginTop: 10, fontSize: 11, color: "#9ca3af" }}>
            Suggerimento: hover per vedere • click per bloccare • clic fuori per chiudere.
          </div>
        </div>
      )}
    </div>
  );
}
