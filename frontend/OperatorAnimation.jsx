import React, { useEffect, useMemo, useState } from "react";

export default function OperatorAnimation({ paths }) {
  // ============================
  // GUARDIE
  // ============================
  const safePaths = Array.isArray(paths) ? paths : [];
  if (safePaths.length === 0) {
    return (
      <div className="placeholder">
        Nessun dato disponibile per l&apos;animazione operatori.
      </div>
    );
  }

  // ============================
  // 1) FLATTEN -> allPoints
  // ============================
  const allPoints = useMemo(() => {
    const pts = [];

    for (let idxOp = 0; idxOp < safePaths.length; idxOp++) {
      const p = safePaths[idxOp];
      const opName = p?.operator != null ? String(p.operator) : `Op ${idxOp}`;
      const steps = Array.isArray(p?.steps) ? p.steps : [];

      for (let i = 0; i < steps.length; i++) {
        const s = steps[i];

        const lane = Number(s?.lane);
        const pos = Number(s?.pos);
        if (!Number.isFinite(lane) || !Number.isFinite(pos)) continue;

        const tStr = s?.time ? String(s.time) : null;

        let hour = 0;
        if (tStr) {
          const dt = new Date(tStr);
          if (!Number.isNaN(dt.getTime())) {
            hour = dt.getHours() + dt.getMinutes() / 60;
          }
        }

        pts.push({
          operator: opName,
          lane,
          pos,
          hour,
          rawTime: tStr ?? `${idxOp}-${i}`,
        });
      }
    }

    return pts;
  }, [safePaths]);

  if (allPoints.length === 0) {
    return (
      <div className="placeholder">
        Nessun punto valido per costruire l&apos;animazione operatori.
      </div>
    );
  }

  // ============================
  // 2) RANGE SAFE + LISTE
  // ============================
  const { minLane, maxLane, minPos, maxPos, minHour, maxHour } = useMemo(() => {
    let minLane = Infinity,
      maxLane = -Infinity,
      minPos = Infinity,
      maxPos = -Infinity,
      minHour = Infinity,
      maxHour = -Infinity;

    for (const p of allPoints) {
      const lane = Number(p.lane);
      const pos = Number(p.pos);
      const hour = Number(p.hour);

      if (Number.isFinite(lane)) {
        if (lane < minLane) minLane = lane;
        if (lane > maxLane) maxLane = lane;
      }
      if (Number.isFinite(pos)) {
        if (pos < minPos) minPos = pos;
        if (pos > maxPos) maxPos = pos;
      }
      if (Number.isFinite(hour)) {
        if (hour < minHour) minHour = hour;
        if (hour > maxHour) maxHour = hour;
      }
    }

    // fallback
    if (!Number.isFinite(minLane)) minLane = 0;
    if (!Number.isFinite(maxLane)) maxLane = 0;
    if (!Number.isFinite(minPos)) minPos = 0;
    if (!Number.isFinite(maxPos)) maxPos = 0;

    // ore arrotondate + clamp 0..23
    minHour = Number.isFinite(minHour) ? Math.floor(minHour) : 0;
    maxHour = Number.isFinite(maxHour) ? Math.ceil(maxHour) : 0;
    minHour = Math.max(0, Math.min(23, minHour));
    maxHour = Math.max(0, Math.min(23, maxHour));

    return { minLane, maxLane, minPos, maxPos, minHour, maxHour };
  }, [allPoints]);

  const uniqueLanes = useMemo(() => {
    const set = new Set();
    for (const p of allPoints) {
      if (Number.isFinite(p.lane)) set.add(p.lane);
    }
    return Array.from(set).sort((a, b) => a - b);
  }, [allPoints]);

  const operatorList = useMemo(() => {
    const set = new Set();
    for (const p of allPoints) set.add(String(p.operator));
    return Array.from(set).filter(Boolean).sort((a, b) => a.localeCompare(b, "it-IT"));
  }, [allPoints]);

  const laneSpan = useMemo(() => Math.max(1, maxLane - minLane), [minLane, maxLane]);
  const posSpan = useMemo(() => Math.max(1, maxPos - minPos), [minPos, maxPos]);

  // ============================
  // 3) STATE
  // ============================
  const [selectedOp, setSelectedOp] = useState("ALL");
  const [fromHour, setFromHour] = useState(minHour);
  const [toHour, setToHour] = useState(maxHour);
  const [playing, setPlaying] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(0);

  useEffect(() => {
    setFromHour(minHour);
    setToHour(maxHour);
  }, [minHour, maxHour]);

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
      .sort((a, b) => a.hour - b.hour);
  }, [filteredPoints, selectedOp]);

  useEffect(() => {
    setCurrentIdx(0);
    setPlaying(false);
  }, [selectedOp, fromHour, toHour]);

  useEffect(() => {
    if (!playing) return;
    if (pathToPlay.length < 2) {
      setPlaying(false);
      return;
    }

    const intervalMs = 250;
    const id = setInterval(() => {
      setCurrentIdx((prev) => {
        if (prev >= pathToPlay.length - 1) return prev;
        return prev + 1;
      });
    }, intervalMs);

    return () => clearInterval(id);
  }, [playing, pathToPlay]);

  const canPlay = selectedOp !== "ALL" && pathToPlay.length >= 2;

  // (anti-freeze) se sono troppi punti, disegno un campione
  const MAX_DRAW = 6000;

  const trailPoints = useMemo(() => {
    const base =
      selectedOp === "ALL" ? filteredPoints : pathToPlay.slice(0, currentIdx + 1);

    if (base.length <= MAX_DRAW) return base;

    const step = Math.ceil(base.length / MAX_DRAW);
    const sampled = [];
    for (let i = 0; i < base.length; i += step) sampled.push(base[i]);
    return sampled;
  }, [selectedOp, filteredPoints, pathToPlay, currentIdx]);

  const currentPoint =
    selectedOp !== "ALL" && pathToPlay.length > 0
      ? pathToPlay[Math.min(currentIdx, pathToPlay.length - 1)]
      : null;

  // ============================
  // 4) BOTTLENECK (solo ALL)
  // ============================
  const topBottlenecks = useMemo(() => {
    if (selectedOp !== "ALL") return [];
    const map = {};
    for (const p of filteredPoints) {
      const k = p.lane;
      map[k] = (map[k] || 0) + 1;
    }
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
  }, [filteredPoints, selectedOp]);

  // ============================
  // RENDER
  // ============================
  return (
    <div
      style={{
        background: "radial-gradient(circle at top, rgba(15,23,42,0.9), #020617)",
        borderRadius: 16,
        border: "1px solid rgba(148,163,184,0.4)",
        padding: 12,
        color: "#e5e7eb",
        fontSize: 12,
      }}
    >
      {/* CONTROLLI */}
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
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

        <div>
          <div style={{ fontSize: 11, color: "#9ca3af" }}>Fascia oraria</div>
          <input
            type="number"
            min={0}
            max={23}
            value={fromHour}
            onChange={(e) =>
              setFromHour(Math.min(Math.max(0, Number(e.target.value) || 0), toHour))
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

        <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
          <button
            onClick={() => {
              if (!canPlay) return;
              setPlaying((p) => !p);
              if (!playing && currentIdx >= pathToPlay.length - 1) setCurrentIdx(0);
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
            Step:{" "}
            <strong>{canPlay ? `${currentIdx + 1}/${pathToPlay.length}` : "-"}</strong>
          </div>
        </div>
      </div>

      {/* AREA GRAFICA */}
      <div
        style={{
          position: "relative",
          height: 260,
          borderRadius: 12,
          background: "radial-gradient(circle at top, rgba(15,23,42,0.9), #020617)",
          overflow: "hidden",
          padding: "18px 12px 30px 40px",
        }}
      >
        {/* griglia corsie */}
        {uniqueLanes.map((lane) => {
          const laneNorm = (lane - minLane) / laneSpan;
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

        {/* etichette corsie */}
        {uniqueLanes
          .filter((_, idx) => idx % 5 === 0)
          .map((lane) => {
            const laneNorm = (lane - minLane) / laneSpan;
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

        {/* etichette pos */}
        <div style={{ position: "absolute", left: 6, top: 10, fontSize: 9, color: "#9ca3af" }}>
          {maxPos}
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
          {minPos}
        </div>

        {/* punti */}
        {trailPoints.map((p, idx) => {
          const laneNorm = (p.lane - minLane) / laneSpan;
          const posNorm = (p.pos - minPos) / posSpan;

          const x = 40 + laneNorm * (100 - 45);
          const y = 10 + (1 - posNorm) * 210;

          const isSingle = selectedOp !== "ALL";

          return (
            <div
              key={`trail-${idx}-${p.rawTime}`}
              style={{
                position: "absolute",
                left: `${x}%`,
                top: y,
                width: isSingle ? 4 : 3,
                height: isSingle ? 4 : 3,
                borderRadius: 999,
                backgroundColor: isSingle ? "rgba(148,163,184,0.7)" : "rgba(59,130,246,0.7)",
                opacity: isSingle ? 0.6 : 0.8,
              }}
            />
          );
        })}

        {/* pallino corrente */}
        {currentPoint && canPlay && (() => {
          const p = currentPoint;
          const laneNorm = (p.lane - minLane) / laneSpan;
          const posNorm = (p.pos - minPos) / posSpan;

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
                transition: "top 0.25s linear, left 0.25s linear",
              }}
              title={`Op ${p.operator} • Corsia ${p.lane} • Pos ${p.pos}`}
            />
          );
        })()}
      </div>

      {/* SUPPORTO */}
      {selectedOp === "ALL" ? (
        <div style={{ marginTop: 8, fontSize: 11, color: "#9ca3af" }}>
          In questa fascia oraria: <strong>{filteredPoints.length}</strong> passaggi.
          <br />
          <strong>Colli di bottiglia corsie:</strong>{" "}
          {topBottlenecks.length === 0
            ? "nessuna corsia critica."
            : topBottlenecks.map(([lane, count], idx) => (
                <span key={lane}>
                  {idx > 0 && " • "}
                  Corsia <strong>{lane}</strong>: <strong>{count}</strong>
                </span>
              ))}
        </div>
      ) : (
        <div style={{ marginTop: 8, fontSize: 11, color: "#9ca3af" }}>
          Seleziona operatore + fascia oraria e premi <strong>Play percorso</strong>.
        </div>
      )}
    </div>
  );
}
