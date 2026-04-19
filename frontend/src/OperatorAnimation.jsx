import React, { useEffect, useMemo, useState } from "react";

function OperatorAnimation({ paths }) {
  // ============================
  // 1) Flatten: paths -> lista punti singoli (HOOK SEMPRE ESEGUITO)
  // ============================
  const allPoints = useMemo(() => {
    const pts = [];
    const safePaths = Array.isArray(paths) ? paths : [];

    safePaths.forEach((p, idxOp) => {
      const opName = p?.operator ? String(p.operator) : `Op ${idxOp}`;
      const steps = Array.isArray(p?.steps) ? p.steps : [];

      steps.forEach((s) => {
        const lane = Number(s?.lane);
        const pos = Number(s?.pos);
        const tStr = s?.time ? String(s.time) : null;

        if (!Number.isFinite(lane) || !Number.isFinite(pos)) return;

        let hour = 0;
        if (tStr) {
          const dt = new Date(tStr);
          if (!Number.isNaN(dt.getTime())) {
            hour = dt.getHours() + dt.getMinutes() / 60.0;
          }
        }

        pts.push({
          operator: opName,
          lane,
          pos,
          hour,
          rawTime: tStr,
        });
      });
    });

    return pts;
  }, [paths]);

  // ============================
  // 2) Range corsie / ore / posizioni + lanes (SAFE)
  // ============================
  const ranges = useMemo(() => {
    let minLane = Infinity;
    let maxLane = -Infinity;
    let minHour = Infinity;
    let maxHour = -Infinity;
    let minPos = Infinity;
    let maxPos = -Infinity;

    const laneSet = new Set();

    for (const p of allPoints) {
      const lane = Number(p.lane);
      const hour = Number(p.hour);
      const pos = Number(p.pos);

      if (Number.isFinite(lane)) {
        laneSet.add(lane);
        if (lane < minLane) minLane = lane;
        if (lane > maxLane) maxLane = lane;
      }
      if (Number.isFinite(hour)) {
        if (hour < minHour) minHour = hour;
        if (hour > maxHour) maxHour = hour;
      }
      if (Number.isFinite(pos)) {
        if (pos < minPos) minPos = pos;
        if (pos > maxPos) maxPos = pos;
      }
    }

    // fallback se vuoto
    if (!Number.isFinite(minLane)) minLane = 0;
    if (!Number.isFinite(maxLane)) maxLane = 0;
    if (!Number.isFinite(minPos)) minPos = 0;
    if (!Number.isFinite(maxPos)) maxPos = 0;

    // ore arrotondate
    const minHourInt = Number.isFinite(minHour) ? Math.floor(minHour) : 0;
    const maxHourInt = Number.isFinite(maxHour) ? Math.ceil(maxHour) : 0;

    const lanes = Array.from(laneSet).sort((a, b) => a - b);

    return {
      lanes,
      minLane,
      maxLane,
      minPos,
      maxPos,
      minHour: minHourInt,
      maxHour: maxHourInt,
    };
  }, [allPoints]);

  const operatorList = useMemo(() => {
    return Array.from(new Set(allPoints.map((p) => p.operator)))
      .filter(Boolean)
      .sort((a, b) => String(a).localeCompare(String(b), "it-IT"));
  }, [allPoints]);

  // ============================
  // 3) Stati filtri + play
  // ============================
  const [selectedOp, setSelectedOp] = useState("ALL");
  const [fromHour, setFromHour] = useState(ranges.minHour);
  const [toHour, setToHour] = useState(ranges.maxHour);
  const [playing, setPlaying] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(0);

  // riallineo fascia oraria quando cambiano i dati
  useEffect(() => {
    setFromHour(ranges.minHour);
    setToHour(ranges.maxHour);
  }, [ranges.minHour, ranges.maxHour]);

  // Reset indice quando cambiano operatore o filtri
  useEffect(() => {
    setCurrentIdx(0);
    setPlaying(false);
  }, [selectedOp, fromHour, toHour]);

  // ============================
  // 4) Punti filtrati e pathToPlay (memoizzati)
  // ============================
  const filteredPoints = useMemo(() => {
    return allPoints.filter((p) => {
      const matchOp = selectedOp === "ALL" || p.operator === selectedOp;
      const matchTime = p.hour >= fromHour && p.hour <= toHour;
      return matchOp && matchTime;
    });
  }, [allPoints, selectedOp, fromHour, toHour]);

  const pathToPlay = useMemo(() => {
    if (selectedOp === "ALL") return [];
    return filteredPoints
      .filter((p) => p.operator === selectedOp)
      .slice()
      .sort((a, b) => (a.hour || 0) - (b.hour || 0));
  }, [filteredPoints, selectedOp]);

  // Gestione play / pausa
  useEffect(() => {
    if (!playing) return;
    if (!pathToPlay.length) {
      setPlaying(false);
      return;
    }

    const intervalMs = 300;
    const id = setInterval(() => {
      setCurrentIdx((prev) => {
        if (prev >= pathToPlay.length - 1) {
          return prev;
        }
        return prev + 1;
      });
    }, intervalMs);

    return () => clearInterval(id);
  }, [playing, pathToPlay]);

  // quando arriva alla fine, stoppo (senza loop)
  useEffect(() => {
    if (!playing) return;
    if (pathToPlay.length && currentIdx >= pathToPlay.length - 1) {
      setPlaying(false);
    }
  }, [playing, currentIdx, pathToPlay.length]);

  const laneSpan = Math.max(1, ranges.maxLane - ranges.minLane);
  const posSpan = Math.max(1, ranges.maxPos - ranges.minPos);

  const canPlay = selectedOp !== "ALL" && pathToPlay.length >= 2;

  const trailPoints =
    selectedOp === "ALL" ? filteredPoints : pathToPlay.slice(0, currentIdx + 1);

  const currentPoint =
    selectedOp !== "ALL" && pathToPlay.length > 0
      ? pathToPlay[Math.min(currentIdx, pathToPlay.length - 1)]
      : null;

  // ============================
  // 5) Analisi colli di bottiglia (solo quando Operatore = Tutti)
  // ============================
  const laneLoad = useMemo(() => {
    const map = {};
    for (const p of filteredPoints) {
      const k = String(p.lane);
      map[k] = (map[k] || 0) + 1;
    }
    return map;
  }, [filteredPoints]);

  const topBottlenecks =
    selectedOp === "ALL"
      ? Object.entries(laneLoad)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
      : [];

  // ============================
  // RENDER: placeholder (DOPO hook)
  // ============================
  if (!paths || !Array.isArray(paths) || paths.length === 0) {
    return (
      <div className="placeholder">
        Nessun dato disponibile per l&apos;animazione operatori.
      </div>
    );
  }

  if (!allPoints.length) {
    return (
      <div className="placeholder">
        Nessun punto valido per costruire l&apos;animazione operatori.
      </div>
    );
  }

  return (
    <div
      style={{
        background:
          "radial-gradient(circle at top, rgba(15,23,42,0.9), #020617)",
        borderRadius: 16,
        border: "1px solid rgba(148,163,184,0.4)",
        padding: 12,
        color: "#e5e7eb",
        fontSize: 12,
      }}
    >
      {/* CONTROLLI FILTRO + PLAY */}
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        {/* Operatore */}
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af" }}>Operatore</div>
          <select
            value={selectedOp}
            onChange={(e) => setSelectedOp(e.target.value)}
            style={{
              background: "#020617",
              color: "#e5e7eb",
              borderRadius: 6,
              border: "1px solid rgba(148,163,184,0.6)",
              padding: "4px 6px",
              fontSize: 11,
            }}
          >
            <option value="ALL">Tutti</option>
            {operatorList.map((op) => (
              <option key={op} value={op}>
                Operatore {op}
              </option>
            ))}
          </select>
        </div>

        {/* Fascia oraria */}
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af" }}>
            Fascia oraria (ora inizio)
          </div>
          <input
            type="number"
            min={0}
            max={23}
            value={fromHour}
            onChange={(e) =>
              setFromHour(
                Math.min(Math.max(0, Number(e.target.value) || 0), toHour)
              )
            }
            style={{
              width: 60,
              background: "#020617",
              color: "#e5e7eb",
              borderRadius: 6,
              border: "1px solid rgba(148,163,184,0.6)",
              padding: "2px 4px",
              fontSize: 11,
              marginRight: 4,
            }}
          />
          <span style={{ marginRight: 4 }}>→</span>
          <input
            type="number"
            min={0}
            max={23}
            value={toHour}
            onChange={(e) =>
              setToHour(Math.max(fromHour, Math.min(23, Number(e.target.value) || 0)))
            }
            style={{
              width: 60,
              background: "#020617",
              color: "#e5e7eb",
              borderRadius: 6,
              border: "1px solid rgba(148,163,184,0.6)",
              padding: "2px 4px",
              fontSize: 11,
            }}
          />
        </div>

        {/* Play / Pause */}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
          <button
            onClick={() => {
              if (!canPlay) return;
              setPlaying((p) => {
                const next = !p;
                // se riparto dalla fine, reset
                if (next && currentIdx >= pathToPlay.length - 1) setCurrentIdx(0);
                return next;
              });
            }}
            disabled={!canPlay}
            style={{
              padding: "6px 10px",
              borderRadius: 999,
              border: "none",
              fontSize: 11,
              cursor: canPlay ? "pointer" : "default",
              background: canPlay ? (playing ? "#ef4444" : "#22c55e") : "#1f2937",
              color: canPlay ? "#f9fafb" : "#6b7280",
            }}
          >
            {playing ? "Pausa" : "Play percorso"}
          </button>
          <div style={{ fontSize: 11, color: "#9ca3af" }}>
            Step: <strong>{canPlay ? `${currentIdx + 1}/${pathToPlay.length}` : "-"}</strong>
          </div>
        </div>
      </div>

      {/* AREA GRAFICA: corsie (X) vs posti (Y) */}
      <div
        style={{
          position: "relative",
          height: 260,
          borderRadius: 12,
          background:
            "radial-gradient(circle at top, rgba(15,23,42,0.9), #020617)",
          overflow: "hidden",
          padding: "18px 12px 30px 40px",
        }}
      >
        {/* griglia corsie verticali */}
        {ranges.lanes.map((lane) => {
          const laneNorm = (lane - ranges.minLane) / laneSpan;
          const x = 40 + laneNorm * (100 - 45);
          return (
            <div
              key={`lane-line-${lane}`}
              style={{
                position: "absolute",
                top: 10,
                bottom: 24,
                left: `${x}%`,
                width: 1,
                background:
                  "linear-gradient(to bottom, transparent, rgba(51,65,85,0.7), transparent)",
              }}
            />
          );
        })}

        {/* etichette corsie in basso (ogni ~5) */}
        {ranges.lanes
          .filter((_, idx) => idx % 5 === 0)
          .map((lane) => {
            const laneNorm = (lane - ranges.minLane) / laneSpan;
            const x = 40 + laneNorm * (100 - 45);
            return (
              <div
                key={`lane-label-${lane}`}
                style={{
                  position: "absolute",
                  bottom: 6,
                  left: `${x}%`,
                  transform: "translateX(-50%)",
                  fontSize: 9,
                  color: "#9ca3af",
                }}
              >
                {lane}
              </div>
            );
          })}

        {/* etichette posizioni (assi Y: alto/basso) */}
        <div
          style={{
            position: "absolute",
            left: 6,
            top: 10,
            fontSize: 9,
            color: "#9ca3af",
          }}
        >
          {ranges.maxPos}
        </div>
        <div
          style={{
            position: "absolute",
            left: 6,
            bottom: 26,
            fontSize: 9,
            color: "#9ca3af",
          }}
        >
          {ranges.minPos}
        </div>

        {/* punti (scia percorso singolo oppure tutti gli operatori) */}
        {trailPoints.map((p, idx) => {
          const laneNorm = (p.lane - ranges.minLane) / laneSpan;
          const posNorm = (p.pos - ranges.minPos) / posSpan;

          const x = 40 + laneNorm * (100 - 45);
          const y = 10 + (1 - posNorm) * 210;

          const isSingle = selectedOp !== "ALL";

          return (
            <div
              key={`trail-${p.rawTime || "t"}-${idx}`}
              style={{
                position: "absolute",
                left: `${x}%`,
                top: y,
                width: isSingle ? 4 : 3,
                height: isSingle ? 4 : 3,
                borderRadius: 999,
                backgroundColor: isSingle
                  ? "rgba(148,163,184,0.7)"
                  : "rgba(59,130,246,0.7)",
                opacity: isSingle ? 0.6 : 0.8,
              }}
            />
          );
        })}

        {/* pallino principale corrente (solo operatore singolo) */}
        {currentPoint && canPlay ? (() => {
          const p = currentPoint;
          const laneNorm = (p.lane - ranges.minLane) / laneSpan;
          const posNorm = (p.pos - ranges.minPos) / posSpan;

          const x = 40 + laneNorm * (100 - 45);
          const y = 10 + (1 - posNorm) * 210;
          const color = "#22c55e";

          return (
            <div
              style={{
                position: "absolute",
                left: `${x}%`,
                top: y,
                width: 10,
                height: 10,
                borderRadius: 999,
                backgroundColor: color,
                boxShadow: `0 0 10px ${color}`,
                transform: "translate(-50%, -50%)",
                transition: "top 0.28s linear, left 0.28s linear",
              }}
              title={`Op ${p.operator} • Corsia ${p.lane} • Pos ${p.pos}`}
            />
          );
        })() : null}
      </div>

      {/* TESTO DI SUPPORTO */}
      {selectedOp === "ALL" ? (
        <div style={{ marginTop: 8, fontSize: 11, color: "#9ca3af" }}>
          In questa fascia oraria hai selezionato{" "}
          <strong>{filteredPoints.length}</strong> passaggi totali.
          <br />
          <strong>Colli di bottiglia corsie (per numero di presenze):</strong>{" "}
          {topBottlenecks.length === 0 ? (
            <span>nessuna corsia critica rilevata.</span>
          ) : (
            topBottlenecks.map(([lane, count], idx) => (
              <span key={lane}>
                {idx > 0 && " • "}
                Corsia <strong>{lane}</strong>: <strong>{count}</strong> passaggi
              </span>
            ))
          )}
          <div style={{ marginTop: 4, opacity: 0.8 }}>
            Per analizzare una fascia, imposta le ore (es. 9 → 10) e lascia
            Operatore = <strong>Tutti</strong>.
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 8, fontSize: 11, color: "#9ca3af" }}>
          Seleziona un operatore, imposta la fascia oraria e premi{" "}
          <strong>Play percorso</strong> per vedere il movimento nel magazzino
          (corsie sull&apos;asse X, posti sull&apos;asse Y).
        </div>
      )}
    </div>
  );
}

export default OperatorAnimation;
