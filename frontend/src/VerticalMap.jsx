// frontend/src/VerticalMap.jsx
import React, { useState } from "react";

function VerticalMap({ layout, mode }) {
  const cells = (layout && layout.cells) || [];
  const [hovered, setHovered] = useState(null);
  const [selected, setSelected] = useState(null); // corsia cliccata per il popup

  if (!cells.length) {
    return <div className="placeholder">Caricamento mappa…</div>;
  }

  // ---- 1) Valori di base per COLLI e PROBLEMI ----
  const colliValues = cells.map((c) =>
    typeof c.colli === "number" ? c.colli : 0
  );

  const issuesValues = cells.map((c) => {
    if (typeof c.issues_total === "number") return c.issues_total;
    const r = typeof c.return_count === "number" ? c.return_count : 0;
    const rec = typeof c.recupero_count === "number" ? c.recupero_count : 0;
    return r + rec;
  });

  const maxColli =
    colliValues.reduce((m, v) => (v > m ? v : m), 0) || 1;

  const maxIssues =
    issuesValues.reduce((m, v) => (v > m ? v : m), 0) || 1;

  // ---- 2) Arricchisco le celle con tutti i campi che servono ----
  const cellsWithData = cells.map((cell, idx) => ({
    ...cell,
    colli: colliValues[idx],
    issues_total: issuesValues[idx],
    return_count:
      typeof cell.return_count === "number" ? cell.return_count : 0,
    recupero_count:
      typeof cell.recupero_count === "number" ? cell.recupero_count : 0,
    return_rate:
      typeof cell.return_rate === "number" ? cell.return_rate : 0,
  }));

  // ---- 3) Ordine visivo corsie (75 → 13) ----
  const sortedByLabel = [...cellsWithData].sort((a, b) => {
    const na = parseInt(a.label, 10);
    const nb = parseInt(b.label, 10);
    if (isNaN(na) || isNaN(nb)) {
      return (b.label || "").localeCompare(a.label || "");
    }
    return nb - na;
  });

  return (
    <div
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        gap: 2,               // prima 4
        width: "100%",
        height: "100%",
        overflowY: "auto",    // prima "hidden"
        overflowX: "hidden",
      }}
    >
      {/* RIGHE CORSIE */}
      {sortedByLabel.map((cell, idx) => {
        const colli = cell.colli || 0;
        const issues = cell.issues_total || 0;

        // metrica principale in base alla modalità
        const metric = mode === "heatmap" ? issues : colli;
        const maxMetric = mode === "heatmap" ? maxIssues : maxColli;

        const intensity = maxMetric > 0 ? metric / maxMetric : 0; // 0–1
        const safeIntensity = 0.2 + intensity * 0.8;
        const isHot = mode === "heatmap" && intensity > 0.6;

        const returnCount = cell.return_count || 0;
        const recuperoCount = cell.recupero_count || 0;
        const returnRate = cell.return_rate || 0;

        // Colori:
        //  - Overview: verde (colli)
        //  - Heatmap: rosso/arancio (problemi)
        const baseColor =
          mode === "heatmap"
            ? `rgba(248, 113, 113, ${safeIntensity})` // rosso "problema"
            : `rgba(16, 185, 129, ${safeIntensity})`; // verde "volume"

        const titleOverview = `Corsia ${cell.label} – ${colli} colli (${(
          (colli / maxColli) *
          100
        ).toFixed(1)}% della corsia top)`;

        const titleHeatmap = `Corsia ${cell.label} – Problemi: ${issues} (Ritorni: ${returnCount}, Liste di recupero: ${recuperoCount})`;

        return (
          <div
            key={cell.id || idx}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              cursor: "pointer",
            }}
            onMouseEnter={() =>
              setHovered({
                label: cell.label,
                colli,
                issues,
                intensity,
                returnCount,
                recuperoCount,
                returnRate,
              })
            }
            onMouseLeave={() => setHovered(null)}
            onClick={() =>
              setSelected({
                label: cell.label,
                colli,
                issues,
                intensity,
                returnCount,
                recuperoCount,
                returnRate,
              })
            }
          >
            {/* Etichetta corsia */}
            <div
              style={{
                width: 60,
                fontSize: 11,
                color: "#9ca3af",
                textAlign: "right",
              }}
            >
              {cell.label}
            </div>

            {/* Barra corsia */}
            <div
              style={{
                flex: 1,
                height: 6, // prima 10
                borderRadius: 999,
                background: "#020617",
                overflow: "hidden",
                border: "1px solid rgba(148,163,184,0.5)",
              }}
              title={mode === "heatmap" ? titleHeatmap : titleOverview}
            >
              <div
                style={{
                  width: "100%",
                  height: "100%",
                  borderRadius: 999,
                  background: baseColor,
                  boxShadow: isHot
                    ? "0 0 10px rgba(248,113,113,0.9)"
                    : "0 0 4px rgba(15,23,42,0.7)",
                  transition: "background-color 0.4s ease-out",
                }}
              />
            </div>
          </div>
        );
      })}

      {/* PANNELLO DETTAGLI CORSIA (hover) */}
      <div
        style={{
          marginTop: 12,
          padding: 10,
          borderRadius: 8,
          background:
            "linear-gradient(135deg, rgba(15,23,42,0.95), rgba(15,23,42,0.8))",
          border: "1px solid rgba(148,163,184,0.4)",
          fontSize: 12,
          color: "#e5e7eb",
          minHeight: 40,
        }}
      >
        {hovered ? (
          <>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>
              Dettaglio corsia {hovered.label}
            </div>

            {mode === "overview" ? (
              <>
                <div>
                  • Colli totali prelevati:{" "}
                  <strong>{hovered.colli}</strong>
                </div>
                <div>
                  • Peso rispetto alla corsia più utilizzata:{" "}
                  <strong>
                    {(hovered.intensity * 100).toFixed(1)}%
                  </strong>
                </div>
                <div>
                  • Ritorni BF:{" "}
                  <strong>{hovered.returnCount}</strong>{" "}
                  ({(hovered.returnRate * 100).toFixed(2)}% delle righe)
                </div>
              </>
            ) : (
              <>
                <div>
                  • Problemi totali (ritorni + recuperi):{" "}
                  <strong>{hovered.issues}</strong>
                </div>
                <div>
                  • Ritorni BF:{" "}
                  <strong>{hovered.returnCount}</strong>
                </div>
                <div>
                  • Liste di recupero uniche:{" "}
                  <strong>{hovered.recuperoCount}</strong>
                </div>
                <div>
                  • Incidenza ritorni sulle righe:{" "}
                  <strong>
                    {(hovered.returnRate * 100).toFixed(2)}%
                  </strong>
                </div>
              </>
            )}

            <div style={{ opacity: 0.7, marginTop: 4 }}>
              (Valori calcolati sui dati reali del periodo analizzato)
            </div>
          </>
        ) : (
          <div style={{ opacity: 0.7 }}>
            Passa il mouse su una corsia per vedere i dettagli.  
            In modalità <strong>Heatmap</strong> il colore evidenzia dove
            si concentrano i problemi (ritorni + liste di recupero).
          </div>
        )}
      </div>

      {/* POPUP DETTAGLIO CORSIA CLICCATA */}
      {selected && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: "rgba(15,23,42,0.85)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 20,
          }}
          onClick={() => setSelected(null)}
        >
          <div
            style={{
              background: "rgba(15,23,42,0.98)",
              borderRadius: 12,
              border: "1px solid rgba(148,163,184,0.6)",
              padding: 16,
              width: "360px",
              boxShadow: "0 20px 40px rgba(0,0,0,0.6)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 8,
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: 14,
                    color: "#9ca3af",
                    textTransform: "uppercase",
                    letterSpacing: 0.08,
                  }}
                >
                  Corsia
                </div>
                <div
                  style={{ fontSize: 20, fontWeight: 600, color: "#e5e7eb" }}
                >
                  {selected.label}
                </div>
              </div>
              <button
                onClick={() => setSelected(null)}
                style={{
                  border: "none",
                  background: "transparent",
                  color: "#9ca3af",
                  fontSize: 18,
                  cursor: "pointer",
                }}
              >
                ×
              </button>
            </div>

            <div style={{ fontSize: 13, color: "#e5e7eb" }}>
              <div style={{ marginBottom: 6 }}>
                • Colli totali prelevati nel periodo:{" "}
                <strong>{selected.colli}</strong>
              </div>
              <div style={{ marginBottom: 6 }}>
                • Problemi totali (ritorni + recuperi):{" "}
                <strong>{selected.issues}</strong>
              </div>
              <div style={{ marginBottom: 6 }}>
                • Ritorni BF:{" "}
                <strong>{selected.returnCount}</strong>
              </div>
              <div style={{ marginBottom: 6 }}>
                • Liste di recupero uniche:{" "}
                <strong>{selected.recuperoCount}</strong>
              </div>
              <div style={{ marginBottom: 6 }}>
                • Incidenza ritorni sulle righe:{" "}
                <strong>
                  {(selected.returnRate * 100).toFixed(2)}%
                </strong>
              </div>
              <div style={{ marginTop: 8, opacity: 0.8 }}>
                Usa la heatmap per intercettare corsie critiche dove
                si concentrano problemi di stock, baia o copertura
                carrellisti.
              </div>
            </div>

            <div
              style={{
                marginTop: 12,
                display: "flex",
                justifyContent: "flex-end",
                gap: 8,
              }}
            >
              <button
                onClick={() => setSelected(null)}
                style={{
                  padding: "6px 10px",
                  borderRadius: 6,
                  border: "1px solid rgba(148,163,184,0.7)",
                  background: "transparent",
                  color: "#e5e7eb",
                  fontSize: 12,
                  cursor: "pointer",
                }}
              >
                Chiudi
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default VerticalMap;


