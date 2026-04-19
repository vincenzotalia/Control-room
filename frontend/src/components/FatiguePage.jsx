import React, { useMemo, useState } from "react";

const fmt = (n, d = 1) =>
  n == null || Number.isNaN(n) ? "--" : Number(n).toFixed(d);

// ============================
// MULTI LINE CHART (3 linee)
// ============================
function MultiLineChart({ series, height = 240 }) {
  // series: [{ id, label, color, points: [{label, value, meta}] }]
  const w = 900;
  const h = height;
  const pad = 38;

  const allValues = [];
  series.forEach((s) => {
    (s.points || []).forEach((p) => {
      if (typeof p.value === "number" && !Number.isNaN(p.value)) allValues.push(p.value);
    });
  });

  const minV = allValues.length ? Math.min(...allValues) : 0;
  const maxV = allValues.length ? Math.max(...allValues) : 1;

  // Assumo che tutte le serie abbiano lo stesso numero di punti e stesse label
  const basePoints = series[0]?.points || [];
  const xStep = basePoints.length > 1 ? (w - pad * 2) / (basePoints.length - 1) : 0;

  const y = (v) => {
    const t = (v - minV) / (maxV - minV || 1);
    return (h - pad) - t * (h - pad * 2);
  };

  const [hover, setHover] = useState(null); // {i, x, y, label, values: {id: value}, meta}

  function buildPoly(points) {
    return (points || [])
      .map((p, i) => `${pad + i * xStep},${y(p.value)}`)
      .join(" ");
  }

  return (
    <div style={{ width: "100%", overflowX: "auto" }}>
      <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", minWidth: 700 }}>
        {/* griglia */}
        <rect x="0" y="0" width={w} height={h} fill="transparent" />
        {[0, 0.25, 0.5, 0.75, 1].map((t, i) => {
          const yy = (h - pad) - t * (h - pad * 2);
          const val = minV + t * (maxV - minV);
          return (
            <g key={i}>
              <line
                x1={pad}
                y1={yy}
                x2={w - pad}
                y2={yy}
                stroke="rgba(148,163,184,0.25)"
                strokeWidth="1"
              />
              <text x={10} y={yy + 4} fill="rgba(226,232,240,0.75)" fontSize="10">
                {fmt(val, 0)}
              </text>
            </g>
          );
        })}

        {/* assi */}
        <line
          x1={pad}
          y1={pad}
          x2={pad}
          y2={h - pad}
          stroke="rgba(148,163,184,0.5)"
          strokeWidth="1"
        />
        <line
          x1={pad}
          y1={h - pad}
          x2={w - pad}
          y2={h - pad}
          stroke="rgba(148,163,184,0.5)"
          strokeWidth="1"
        />

        {/* linee */}
        {series.map((s) => (
          <polyline
            key={s.id}
            points={buildPoly(s.points)}
            fill="none"
            stroke={s.color}
            strokeWidth={s.strokeWidth ?? 2.5}
            strokeDasharray={s.dash ?? undefined}
            opacity={s.opacity ?? 1}
          />
        ))}

        {/* punti + labels (usiamo i punti della serie "reale" come riferimento) */}
        {basePoints.map((p, i) => {
          const cx = pad + i * xStep;

          const showLabel =
            i === 0 ||
            i === basePoints.length - 1 ||
            (basePoints.length <= 12 && i % 1 === 0) ||
            (basePoints.length > 12 && i % 2 === 0);

          // y di riferimento: serie reale (0)
          const yVal = series[0]?.points?.[i]?.value;
          const cy = y(typeof yVal === "number" ? yVal : minV);

          return (
            <g
              key={i}
              onMouseEnter={() => {
                const values = {};
                series.forEach((s) => {
                  values[s.id] = s.points?.[i]?.value ?? null;
                });
                setHover({
                  i,
                  x: cx,
                  y: cy,
                  label: p.label,
                  values,
                  meta: p.meta || null,
                });
              }}
              onMouseLeave={() => setHover(null)}
            >
              {/* pallini per ogni serie */}
              {series.map((s) => {
                const vv = s.points?.[i]?.value;
                if (typeof vv !== "number" || Number.isNaN(vv)) return null;
                return (
                  <circle
                    key={s.id}
                    cx={cx}
                    cy={y(vv)}
                    r={s.pointR ?? 3.2}
                    fill={s.color}
                    opacity={s.pointOpacity ?? 0.95}
                  />
                );
              })}

              {showLabel && (
                <text
                  x={cx}
                  y={h - 14}
                  textAnchor="middle"
                  fill="rgba(226,232,240,0.75)"
                  fontSize="10"
                >
                  {p.label}
                </text>
              )}
            </g>
          );
        })}

        {/* Tooltip */}
        {hover && (
          <g>
            <rect
              x={Math.min(hover.x + 10, w - 300)}
              y={Math.max(hover.y - 110, 10)}
              width={290}
              height={112}
              rx={10}
              fill="rgba(15,23,42,0.92)"
              stroke="rgba(148,163,184,0.35)"
            />
            <text
              x={Math.min(hover.x + 22, w - 288)}
              y={Math.max(hover.y - 88, 28)}
              fill="rgba(226,232,240,0.9)"
              fontSize="11"
            >
              {hover.label}
            </text>

            {series.map((s, idx) => (
              <text
                key={s.id}
                x={Math.min(hover.x + 22, w - 288)}
                y={Math.max(hover.y - 70, 46) + idx * 14}
                fill="rgba(226,232,240,0.85)"
                fontSize="11"
              >
                {s.label}: {fmt(hover.values?.[s.id], 1)}
              </text>
            ))}

            {/* Extra meta */}
            <text
              x={Math.min(hover.x + 22, w - 288)}
              y={Math.max(hover.y - 70, 46) + series.length * 14}
              fill="rgba(226,232,240,0.75)"
              fontSize="11"
            >
              Net min: {fmt(hover.meta?.net_minutes, 1)} · Colli: {hover.meta?.colli ?? "--"}
            </text>

            <text
              x={Math.min(hover.x + 22, w - 288)}
              y={Math.max(hover.y - 70, 46) + series.length * 14 + 14}
              fill="rgba(226,232,240,0.75)"
              fontSize="11"
            >
              Fatigue idx:{" "}
              {hover.meta?.fatigue_index != null ? fmt(hover.meta?.fatigue_index, 1) : "--"}{" "}
              · Loss cum: {hover.meta?.loss_colli_cum ?? "--"}
            </text>

            {/* se il backend manda anche gap finestra */}
            <text
              x={Math.min(hover.x + 22, w - 288)}
              y={Math.max(hover.y - 70, 46) + series.length * 14 + 28}
              fill="rgba(226,232,240,0.75)"
              fontSize="11"
            >
              Gap finestra: {hover.meta?.gap_window_colli != null ? fmt(hover.meta?.gap_window_colli, 1) : "--"} colli
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}

export default function FatiguePage({ API_BASE, operators }) {
  const [operator, setOperator] = useState(operators?.[0]?.name?.toString?.() ?? "");
  const [start, setStart] = useState("06:00");
  const [end, setEnd] = useState("22:00");
  const [windowMin, setWindowMin] = useState(60);
  const [minNetMinutes, setMinNetMinutes] = useState(20);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  // ============================
  // PARSING ROBUSTO DATI
  // ============================
  const rows = useMemo(() => (data?.data ?? []).slice(), [data]);

  const chartBasePoints = useMemo(() => {
    return rows
      .map((r) => {
        const label =
          r.label ??
          (typeof r.bucket === "string" && r.bucket.length >= 16 ? r.bucket.substring(11, 16) : r.bucket ?? "");
        return {
          label,
          meta: {
            net_minutes: r.net_minutes,
            colli: r.colli,
            fatigue_index: r.fatigue_pct ?? r.fatigue_index, // <-- usa fatigue_pct se presente
            loss_colli_cum: r.loss_colli_cum,
            gap_window_colli: r.gap_window_colli, // opzionale
          },
        };
      })
      .filter((p) => p.label);
  }, [rows]);

  // Serie 1: Reale
  const realSeries = useMemo(() => {
    const pts = rows.map((r, idx) => {
      const v =
        r.prod_real ??
        r.prod_colli_ora ??
        r.units_per_hour ??
        (typeof r.colli === "number" && typeof r.net_minutes === "number" && r.net_minutes > 0
          ? (r.colli / r.net_minutes) * 60
          : null);

      return {
        label: chartBasePoints[idx]?.label ?? "",
        value: typeof v === "number" && !Number.isNaN(v) ? v : null,
        meta: chartBasePoints[idx]?.meta ?? null,
      };
    });
    return pts.filter((p) => p.label);
  }, [rows, chartBasePoints]);

  // Serie 2: Media progressiva
  const avgSeries = useMemo(() => {
    const pts = rows.map((r, idx) => {
      const v = r.avg_to_now_colli_ora ?? r.avg_to_now ?? null;
      return {
        label: chartBasePoints[idx]?.label ?? "",
        value: typeof v === "number" && !Number.isNaN(v) ? v : null,
        meta: chartBasePoints[idx]?.meta ?? null,
      };
    });
    return pts.filter((p) => p.label);
  }, [rows, chartBasePoints]);

  // Serie 3: Atteso
  const expectedSeries = useMemo(() => {
    const topExpected = data?.expected_colli_ora ?? data?.expected_base ?? null;
    const pts = rows.map((r, idx) => {
      const v = r.expected_colli_ora ?? r.expected ?? topExpected;
      return {
        label: chartBasePoints[idx]?.label ?? "",
        value: typeof v === "number" && !Number.isNaN(v) ? v : null,
        meta: chartBasePoints[idx]?.meta ?? null,
      };
    });
    return pts.filter((p) => p.label);
  }, [rows, chartBasePoints, data]);

  const pointsValid = useMemo(() => {
    return realSeries.filter((p) => typeof p.value === "number" && !Number.isNaN(p.value));
  }, [realSeries]);

  // ============================
  // KPI RIASSUNTIVI PAGINA
  // ============================
  const summary = useMemo(() => {
    if (!rows.length) return null;

    // QUI la modifica che volevi:
    const fatigueVals = rows
      .map((r) => (r.fatigue_pct ?? r.fatigue_index))
      .filter((x) => typeof x === "number" && !Number.isNaN(x));

    const fatigueAvg = fatigueVals.length
      ? fatigueVals.reduce((a, b) => a + b, 0) / fatigueVals.length
      : null;

    const lossCum = rows.length ? rows[rows.length - 1]?.loss_colli_cum ?? null : null;

    // "Atteso base" dal backend nuovo
    const expectedBase =
      data?.expected_base ??
      data?.expected_colli_ora ??
      null;

    return {
      expectedBase, // colli/ora
      fatigueAvg,   // già in % (es: 95.3)
      lossCum,
    };
  }, [rows, data]);

  async function run() {
    if (!operator) {
      setError("Seleziona un operatore.");
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      params.append("operator", operator);
      if (start) params.append("start", start);
      if (end) params.append("end", end);
      params.append("window_min", String(windowMin));
      params.append("min_net_minutes", String(minNetMinutes));

      const url = `${API_BASE}/fatigue?${params.toString()}`;
      const res = await fetch(url, { method: "GET" });
      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`Errore /fatigue (${res.status}) ${t}`);
      }
      const json = await res.json();
      setData(json);
    } catch (e) {
      console.error(e);
      setData(null);
      setError(e.message || "Errore nella richiesta.");
    } finally {
      setLoading(false);
    }
  }

  const chartSeries = useMemo(() => {
    return [
      {
        id: "real",
        label: "Reale",
        color: "rgba(34,197,94,0.95)",
        points: realSeries,
        strokeWidth: 2.8,
        pointR: 3.3,
      },
      {
        id: "avg",
        label: "Media fino a ora",
        color: "rgba(56,189,248,0.95)",
        points: avgSeries,
        strokeWidth: 2.4,
        pointR: 3.0,
        opacity: 0.95,
      },
      {
        id: "exp",
        label: "Atteso",
        color: "rgba(148,163,184,0.85)",
        points: expectedSeries,
        strokeWidth: 2.2,
        pointR: 2.6,
        dash: "6 5",
        opacity: 0.9,
      },
    ];
  }, [realSeries, avgSeries, expectedSeries]);

  return (
    <div>
      <div className="card" style={{ marginBottom: 14 }}>
        <div
          className="card-header"
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            alignItems: "flex-end",
          }}
        >
          <div>
            <h2>Fatica operatore</h2>
            <p>Reale vs Media progressiva vs Atteso (finestre basate su minuti netti)</p>
          </div>

          <button
            onClick={run}
            style={{
              padding: "8px 14px",
              borderRadius: 8,
              border: "none",
              background: "linear-gradient(135deg, #22c55e, #16a34a)",
              color: "#0b1120",
              fontSize: 12,
              fontWeight: 700,
              cursor: "pointer",
              minWidth: 140,
            }}
          >
            {loading ? "Calcolo…" : "Calcola"}
          </button>
        </div>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          <div style={{ minWidth: 220 }}>
            <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>Operatore</div>
            <select
              value={operator}
              onChange={(e) => setOperator(e.target.value)}
              style={{
                width: "100%",
                background: "#020617",
                color: "#e5e7eb",
                borderRadius: 8,
                border: "1px solid rgba(148,163,184,0.7)",
                fontSize: 12,
                padding: "8px 10px",
              }}
            >
              <option value="">— seleziona —</option>
              {operators.map((op) => (
                <option key={op.name} value={op.name.toString()}>
                  Operatore {op.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>Fascia oraria</div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="time"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                style={{
                  background: "#020617",
                  color: "#e5e7eb",
                  borderRadius: 8,
                  border: "1px solid rgba(148,163,184,0.7)",
                  fontSize: 12,
                  padding: "8px 10px",
                }}
              />
              <span style={{ color: "#9ca3af" }}>–</span>
              <input
                type="time"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                style={{
                  background: "#020617",
                  color: "#e5e7eb",
                  borderRadius: 8,
                  border: "1px solid rgba(148,163,184,0.7)",
                  fontSize: 12,
                  padding: "8px 10px",
                }}
              />
            </div>
            <div style={{ fontSize: 11, color: "rgba(226,232,240,0.6)", marginTop: 6 }}>
              (se fine &lt; inizio: attraversa mezzanotte)
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>Finestra</div>
            <input
              type="number"
              value={windowMin}
              min={15}
              step={15}
              onChange={(e) => setWindowMin(Number(e.target.value))}
              style={{
                width: 140,
                background: "#020617",
                color: "#e5e7eb",
                borderRadius: 8,
                border: "1px solid rgba(148,163,184,0.7)",
                fontSize: 12,
                padding: "8px 10px",
              }}
            />
            <div style={{ fontSize: 11, color: "rgba(226,232,240,0.6)", marginTop: 6 }}>
              minuti per punto
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>Minuti netti minimi</div>
            <input
              type="number"
              value={minNetMinutes}
              min={5}
              step={5}
              onChange={(e) => setMinNetMinutes(Number(e.target.value))}
              style={{
                width: 180,
                background: "#020617",
                color: "#e5e7eb",
                borderRadius: 8,
                border: "1px solid rgba(148,163,184,0.7)",
                fontSize: 12,
                padding: "8px 10px",
              }}
            />
            <div style={{ fontSize: 11, color: "rgba(226,232,240,0.6)", marginTop: 6 }}>
              scarta finestre “poco affidabili”
            </div>
          </div>
        </div>

        {error && (
          <div style={{ marginTop: 10, fontSize: 12, color: "#f97373" }}>
            {error}
          </div>
        )}
      </div>

      {/* RISULTATO */}
      <div className="card">
        <div className="card-header">
          <h2>Andamento produttività</h2>
          <p>3 linee: Reale / Media progressiva / Atteso</p>
        </div>

        {!data ? (
          <div className="placeholder">Clicca “Calcola” per ottenere la curva di fatica.</div>
        ) : pointsValid.length === 0 ? (
          <div className="placeholder">
            Nessun punto valido (probabile filtro minuti netti troppo alto o fascia troppo stretta).
          </div>
        ) : (
          <>
            <MultiLineChart series={chartSeries} />

            {/* riepilogo */}
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
              <div
                style={{
                  flex: "1 1 220px",
                  padding: 10,
                  borderRadius: 10,
                  border: "1px solid rgba(148,163,184,0.25)",
                }}
              >
                <div style={{ fontSize: 11, color: "#9ca3af" }}>Punti validi</div>
                <div style={{ fontSize: 18, fontWeight: 800 }}>{pointsValid.length}</div>
              </div>

              <div
                style={{
                  flex: "1 1 220px",
                  padding: 10,
                  borderRadius: 10,
                  border: "1px solid rgba(148,163,184,0.25)",
                }}
              >
                <div style={{ fontSize: 11, color: "#9ca3af" }}>Atteso (base)</div>
                <div style={{ fontSize: 18, fontWeight: 800 }}>
                  {fmt(summary?.expectedBase, 1)}{" "}
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#9ca3af" }}>colli/ora</span>
                </div>
              </div>

              <div
                style={{
                  flex: "1 1 220px",
                  padding: 10,
                  borderRadius: 10,
                  border: "1px solid rgba(148,163,184,0.25)",
                }}
              >
                <div style={{ fontSize: 11, color: "#9ca3af" }}>Indice fatica medio</div>
                <div style={{ fontSize: 18, fontWeight: 800 }}>
                  {/* NON moltiplico per 100: è già % dal backend */}
                  {summary?.fatigueAvg != null ? fmt(summary.fatigueAvg, 0) : "--"}{" "}
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#9ca3af" }}>%</span>
                </div>
              </div>

              <div
                style={{
                  flex: "1 1 220px",
                  padding: 10,
                  borderRadius: 10,
                  border: "1px solid rgba(148,163,184,0.25)",
                }}
              >
                <div style={{ fontSize: 11, color: "#9ca3af" }}>Perdita colli stimata (cum.)</div>
                <div style={{ fontSize: 18, fontWeight: 800 }}>
                  {fmt(summary?.lossCum, 0)}{" "}
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#9ca3af" }}>colli</span>
                </div>
              </div>
            </div>

            {/* LETTURA (insight) */}
            {data?.insight && (
              <div style={{ marginTop: 10, fontSize: 12, color: "rgba(226,232,240,0.85)" }}>
                <b>Lettura:</b> {data.insight}
              </div>
            )}

            <div style={{ marginTop: 10, fontSize: 12, color: "rgba(226,232,240,0.65)" }}>
              Nota: “Media fino a ora” = produttività cumulata dall’inizio della fascia selezionata fino a quel punto.
              “Atteso” è il riferimento (target).
            </div>
          </>
        )}
      </div>
    </div>
  );
}



