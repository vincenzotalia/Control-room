import React, { useEffect, useMemo, useState } from "react";

export default function AlertsPage({ API_BASE }) {
  const HUB = `${API_BASE}/alert-hub`;

  // ALL | OPEN | IN_PROGRESS | RESOLVED | ARCHIVED
  const [tab, setTab] = useState("ALL");
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const [selectedId, setSelectedId] = useState(null);

  // modal crea alert
  const [openModal, setOpenModal] = useState(false);
  const [warehouse, setWarehouse] = useState("MAGAZZINO_NOVARA");
  const [tipo, setTipo] = useState("NEAR_MISS"); // NEAR_MISS | TICKET
  const [gravita, setGravita] = useState("WARNING"); // INFO | WARNING | CRITICAL
  const [descrizione, setDescrizione] = useState("");

  // messaggi alert selezionato
  const [messages, setMessages] = useState([]);
  const [msgText, setMsgText] = useState("");

  const counts = useMemo(() => {
    const c = { ALL: alerts.length, OPEN: 0, IN_PROGRESS: 0, RESOLVED: 0 };
    for (const a of alerts) c[a.stato] = (c[a.stato] || 0) + 1;
    return c;
  }, [alerts]);

  async function loadAlerts() {
    setLoading(true);
    setErr(null);
    try {
      const params = new URLSearchParams();

      // FILTRO ARCHIVIO:
      // - se tab = ARCHIVED: voglio SOLO archiviati
      // - altrimenti: voglio SOLO non archiviati
      if (tab === "ARCHIVED") {
        params.set("archived", "1");
        params.set("include_archived", "1"); // se il backend usa questo nome
        params.set("stato", "RESOLVED");      // archivio = risolti archiviati
      } else {
        params.set("archived", "0");
        if (tab !== "ALL") params.set("stato", tab);
      }

      const res = await fetch(`${HUB}/alerts?${params.toString()}`);
      if (!res.ok) throw new Error(`Errore lista alert (${res.status})`);
      const data = await res.json();
      const list = Array.isArray(data) ? data : [];
      setAlerts(list);

      // selezione "sicura": se selected non esiste più, prendi il primo
      if (!list.length) {
        setSelectedId(null);
      } else {
        const stillThere = selectedId && list.some((a) => a.id === selectedId);
        if (!stillThere) setSelectedId(list[0].id);
      }
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadMessages(alertId) {
    if (!alertId) return;
    try {
      const res = await fetch(`${HUB}/alerts/${alertId}/messages`);
      if (!res.ok) throw new Error(`Errore messaggi (${res.status})`);
      const data = await res.json();
      setMessages(Array.isArray(data) ? data : []);
    } catch {
      // non blocchiamo la UI se messaggi falliscono
    }
  }

  // refresh lista quando cambia tab
  useEffect(() => {
    loadAlerts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // polling messaggi ogni 2s sull'alert selezionato
  useEffect(() => {
    setMessages([]);
    if (!selectedId) return;
    loadMessages(selectedId);
    const t = setInterval(() => loadMessages(selectedId), 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  async function createAlert() {
    if (!descrizione.trim()) return;
    setErr(null);
    try {
      const res = await fetch(`${HUB}/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          warehouse,
          tipo,
          gravita,
          descrizione,
        }),
      });
      if (!res.ok) throw new Error(`Errore creazione alert (${res.status})`);
      setOpenModal(false);
      setDescrizione("");
      await loadAlerts();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function ackAlert(alertId) {
    const responsabile = prompt("Nome responsabile (es. Vincenzo):");
    if (!responsabile) return;
    setErr(null);
    try {
      const res = await fetch(
        `${HUB}/alerts/${alertId}/ack?responsabile=${encodeURIComponent(responsabile)}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`Errore presa in carico (${res.status})`);
      await loadAlerts();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function resolveAlert(alertId) {
    const responsabile = prompt("Nome responsabile (es. Vincenzo):");
    if (!responsabile) return;
    const nota = prompt("Nota risoluzione (opzionale):") || "";
    setErr(null);
    try {
      const url = `${HUB}/alerts/${alertId}/resolve?responsabile=${encodeURIComponent(
        responsabile
      )}&nota=${encodeURIComponent(nota)}`;
      const res = await fetch(url, { method: "POST" });
      if (!res.ok) throw new Error(`Errore risoluzione (${res.status})`);
      await loadAlerts();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function sendMessage() {
    if (!selectedId || !msgText.trim()) return;
    try {
      const res = await fetch(`${HUB}/alerts/${selectedId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mittente: "CONTROL_ROOM", testo: msgText }),
      });
      if (!res.ok) throw new Error("Invio messaggio fallito");
      setMsgText("");
      await loadMessages(selectedId);
    } catch (e) {
      setErr(e.message);
    }
  }

  const selected = alerts.find((a) => a.id === selectedId);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "420px 1fr", gap: 14 }}>
      {/* COLONNA SINISTRA: KPI + LISTA */}
      <div className="card" style={{ padding: 12 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 10,
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 16 }}>Control Room Alerts</h2>
            <div style={{ fontSize: 12, opacity: 0.75 }}>{HUB}</div>
          </div>
          <button
            onClick={() => setOpenModal(true)}
            style={{
              width: 40,
              height: 40,
              borderRadius: 10,
              border: "none",
              background: "linear-gradient(135deg,#38bdf8,#0ea5e9)",
              color: "#0b1120",
              fontWeight: 800,
              fontSize: 18,
              cursor: "pointer",
            }}
            title="Apri Near Miss / Ticket"
          >
            +
          </button>
        </div>

        {/* TAB */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(5,1fr)",
            gap: 8,
            marginBottom: 10,
          }}
        >
          <Tab label={`Tutti (${counts.ALL || 0})`} active={tab === "ALL"} onClick={() => setTab("ALL")} />
          <Tab label={`Open (${counts.OPEN || 0})`} active={tab === "OPEN"} onClick={() => setTab("OPEN")} />
          <Tab
            label={`In carico (${counts.IN_PROGRESS || 0})`}
            active={tab === "IN_PROGRESS"}
            onClick={() => setTab("IN_PROGRESS")}
          />
          <Tab
            label={`Risolti (${counts.RESOLVED || 0})`}
            active={tab === "RESOLVED"}
            onClick={() => setTab("RESOLVED")}
          />
          <Tab
            label={`Archivio`}
            active={tab === "ARCHIVED"}
            onClick={() => setTab("ARCHIVED")}
          />
        </div>

        {err && <div style={{ fontSize: 12, color: "#f97373", marginBottom: 8 }}>{err}</div>}
        {loading ? (
          <div style={{ fontSize: 12, opacity: 0.75 }}>Caricamento…</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 520, overflow: "auto" }}>
            {alerts.length === 0 ? (
              <div style={{ fontSize: 12, opacity: 0.7 }}>
                {tab === "ARCHIVED" ? "Nessun alert archiviato." : "Nessun alert."}
              </div>
            ) : (
              alerts.map((a) => (
                <button
                  key={a.id}
                  onClick={() => setSelectedId(a.id)}
                  style={{
                    textAlign: "left",
                    borderRadius: 10,
                    border:
                      selectedId === a.id
                        ? "1px solid rgba(56,189,248,0.9)"
                        : "1px solid rgba(148,163,184,0.35)",
                    background: "rgba(2,6,23,0.6)",
                    padding: 10,
                    cursor: "pointer",
                    color: "#e5e7eb",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>
                      #{a.id} • {a.tipo} • {a.gravita}
                    </div>
                    <span style={{ fontSize: 11, opacity: 0.75 }}>{a.stato}</span>
                  </div>
                  <div style={{ fontSize: 12, opacity: 0.85, marginTop: 4 }}>{a.warehouse}</div>
                  <div style={{ fontSize: 12, opacity: 0.95, marginTop: 6 }}>{a.descrizione}</div>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      {/* COLONNA DESTRA: DETTAGLIO + CHAT */}
      <div className="card" style={{ padding: 12, minHeight: 620 }}>
        {!selected ? (
          <div style={{ fontSize: 12, opacity: 0.75 }}>Seleziona un alert a sinistra.</div>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 16 }}>
                  Alert #{selected.id} — {selected.tipo} ({selected.gravita})
                </h2>
                <div style={{ fontSize: 12, opacity: 0.8 }}>
                  {selected.warehouse} • Stato: <strong>{selected.stato}</strong>
                  {tab === "ARCHIVED" ? " • (ARCHIVIATO)" : ""}
                </div>
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={() => ackAlert(selected.id)}
                  style={btnStyle("#22c55e")}
                  disabled={selected.stato === "RESOLVED" || tab === "ARCHIVED"}
                  title={tab === "ARCHIVED" ? "In archivio non si modifica" : ""}
                >
                  Prendi in carico
                </button>
                <button
                  onClick={() => resolveAlert(selected.id)}
                  style={btnStyle("#f59e0b")}
                  disabled={selected.stato === "RESOLVED" || tab === "ARCHIVED"}
                  title={tab === "ARCHIVED" ? "In archivio non si modifica" : ""}
                >
                  Risolvi
                </button>
              </div>
            </div>

            <div style={{ marginTop: 12, padding: 10, borderRadius: 10, border: "1px solid rgba(148,163,184,0.35)" }}>
              <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>Descrizione</div>
              <div style={{ fontSize: 13 }}>{selected.descrizione}</div>
            </div>

            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", height: 360 }}>
              <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>Messaggi (APP ↔ Control Room)</div>
              <div
                style={{
                  flex: 1,
                  overflow: "auto",
                  borderRadius: 10,
                  border: "1px solid rgba(148,163,184,0.35)",
                  padding: 10,
                  background: "rgba(2,6,23,0.45)",
                }}
              >
                {messages.length === 0 ? (
                  <div style={{ fontSize: 12, opacity: 0.7 }}>Nessun messaggio.</div>
                ) : (
                  messages.map((m) => (
                    <div key={m.id} style={{ marginBottom: 10 }}>
                      <div style={{ fontSize: 11, opacity: 0.7 }}>
                        {m.data} • <strong>{m.mittente}</strong>
                      </div>
                      <div style={{ fontSize: 13 }}>{m.testo}</div>
                    </div>
                  ))
                )}
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <input
                  value={msgText}
                  onChange={(e) => setMsgText(e.target.value)}
                  placeholder={tab === "ARCHIVED" ? "In archivio puoi solo leggere…" : "Scrivi un messaggio…"}
                  disabled={tab === "ARCHIVED"}
                  style={{
                    flex: 1,
                    background: "#020617",
                    color: "#e5e7eb",
                    borderRadius: 10,
                    border: "1px solid rgba(148,163,184,0.55)",
                    padding: "10px 12px",
                    fontSize: 12,
                    opacity: tab === "ARCHIVED" ? 0.6 : 1,
                  }}
                />
                <button onClick={sendMessage} style={btnStyle("#38bdf8")} disabled={tab === "ARCHIVED"}>
                  Invia
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* MODAL CREA */}
      {openModal && (
        <div style={modalOverlay}>
          <div style={modalBox}>
            <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 10 }}>Apri Near Miss / Ticket</div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
              <Field label="Warehouse">
                <input value={warehouse} onChange={(e) => setWarehouse(e.target.value)} style={inputStyle} />
              </Field>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <Field label="Tipo">
                  <select value={tipo} onChange={(e) => setTipo(e.target.value)} style={inputStyle}>
                    <option value="NEAR_MISS">NEAR_MISS</option>
                    <option value="TICKET">TICKET</option>
                  </select>
                </Field>
                <Field label="Gravità">
                  <select value={gravita} onChange={(e) => setGravita(e.target.value)} style={inputStyle}>
                    <option value="INFO">INFO</option>
                    <option value="WARNING">WARNING</option>
                    <option value="CRITICAL">CRITICAL</option>
                  </select>
                </Field>
              </div>

              <Field label="Descrizione (breve)">
                <textarea
                  value={descrizione}
                  onChange={(e) => setDescrizione(e.target.value)}
                  style={{ ...inputStyle, minHeight: 90, resize: "vertical" }}
                />
              </Field>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 6 }}>
                <button onClick={() => setOpenModal(false)} style={btnGhost}>
                  Annulla
                </button>
                <button onClick={createAlert} style={btnStyle("#22c55e")} disabled={!descrizione.trim()}>
                  Invia
                </button>
              </div>

              <div style={{ fontSize: 11, opacity: 0.65 }}>Invio verso: {HUB}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Tab({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "10px 8px",
        borderRadius: 10,
        border: active ? "1px solid rgba(56,189,248,0.9)" : "1px solid rgba(148,163,184,0.35)",
        background: active ? "rgba(56,189,248,0.15)" : "rgba(2,6,23,0.55)",
        color: "#e5e7eb",
        cursor: "pointer",
        fontSize: 12,
        fontWeight: 700,
      }}
    >
      {label}
    </button>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div style={{ fontSize: 11, opacity: 0.75, marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  );
}

const btnStyle = (accent) => ({
  padding: "10px 12px",
  borderRadius: 10,
  border: "none",
  background: accent,
  color: "#0b1120",
  fontWeight: 800,
  fontSize: 12,
  cursor: "pointer",
  opacity: 1,
});

const btnGhost = {
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid rgba(148,163,184,0.55)",
  background: "transparent",
  color: "#e5e7eb",
  fontWeight: 700,
  fontSize: 12,
  cursor: "pointer",
};

const inputStyle = {
  width: "100%",
  background: "#020617",
  color: "#e5e7eb",
  borderRadius: 10,
  border: "1px solid rgba(148,163,184,0.55)",
  padding: "10px 12px",
  fontSize: 12,
};

const modalOverlay = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.55)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 999,
};

const modalBox = {
  width: 640,
  maxWidth: "92vw",
  borderRadius: 16,
  padding: 16,
  background: "rgba(15,23,42,0.98)",
  border: "1px solid rgba(148,163,184,0.35)",
};
