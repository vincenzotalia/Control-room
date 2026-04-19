// src/components/AreaManagerPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import { AreaManagerApi } from "../api/areaManagerApi";
import { buildApiUrl } from "../api/config";

const TABS = [
  { key: "presences", label: "Presenze AM" },
  { key: "breakdowns", label: "Carrelli & Guasti" },
  { key: "documents", label: "Documenti impianto" },
];

function todayISO() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function AreaManagerPage() {
  const [username, setUsername] = useState(localStorage.getItem("am_username") || "vincenzo");
  const [sites, setSites] = useState([]);
  const [siteCode, setSiteCode] = useState(localStorage.getItem("am_site") || "");
  const [tab, setTab] = useState("presences");

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const [presences, setPresences] = useState([]);
  const [forklifts, setForklifts] = useState([]);
  const [breakdowns, setBreakdowns] = useState([]);
  const [documents, setDocuments] = useState([]);

  // form presenze
  const [presenceDate, setPresenceDate] = useState(todayISO());
  const [presenceType, setPresenceType] = useState("OPERATIVA");
  const [presenceNotes, setPresenceNotes] = useState("");

  // form guasti
  const [bdForklift, setBdForklift] = useState("FL-01");
  const [bdDesc, setBdDesc] = useState("");

  // form documenti
  const [docCategory, setDocCategory] = useState("ALTRO");
  const [docTitle, setDocTitle] = useState("Documento");

  // ---- CARRELLI: form + ricerca + archivio
  const [fkArchived, setFkArchived] = useState(0); // 0=attivi, 1=archivio
  const [fkSearch, setFkSearch] = useState("");

  const [fkCode, setFkCode] = useState("");
  const [fkType, setFkType] = useState("");
  const [fkBrand, setFkBrand] = useState("");
  const [fkModel, setFkModel] = useState("");
  const [fkStatus, setFkStatus] = useState("ACTIVE");

  useEffect(() => localStorage.setItem("am_username", username), [username]);
  useEffect(() => localStorage.setItem("am_site", siteCode), [siteCode]);

  async function loadSites() {
    setErr("");
    setLoading(true);
    try {
      const s = await AreaManagerApi.listSites(username);
      setSites(s || []);
      if (s?.length) {
        if (!siteCode) setSiteCode(s[0].site_code);
        if (siteCode && !s.find((x) => x.site_code === siteCode)) setSiteCode(s[0].site_code);
      }
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function reloadTab() {
    if (!username || !siteCode) return;
    setErr("");
    setLoading(true);
    try {
      if (tab === "presences") {
        const rows = await AreaManagerApi.listPresences(username, siteCode);
        setPresences(rows || []);
      } else if (tab === "breakdowns") {
        const fk = await AreaManagerApi.listForklifts(username, siteCode, fkArchived);
        setForklifts(fk || []);
        const bd = await AreaManagerApi.listBreakdowns(username, siteCode, false);
        setBreakdowns(bd || []);
      } else if (tab === "documents") {
        const rows = await AreaManagerApi.listDocuments(username, siteCode);
        setDocuments(rows || []);
      }
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSites();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    reloadTab();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, siteCode, fkArchived]);

  const siteLabel = useMemo(() => {
    const s = sites.find((x) => x.site_code === siteCode);
    return s ? `${s.site_code}${s.site_name ? " — " + s.site_name : ""}` : (siteCode || "—");
  }, [sites, siteCode]);

  const forkliftsFiltered = useMemo(() => {
    const q = (fkSearch || "").trim().toLowerCase();
    if (!q) return forklifts;

    return (forklifts || []).filter((f) => {
      const blob = [f.forklift_code, f.brand, f.model, f.type, f.status]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return blob.includes(q);
    });
  }, [forklifts, fkSearch]);

  async function onAddPresence() {
    setErr("");
    setLoading(true);
    try {
      await AreaManagerApi.addPresence({
        username,
        site_code: siteCode,
        presence_date: presenceDate,
        presence_type: presenceType,
        notes: presenceNotes,
      });
      setPresenceNotes("");
      await reloadTab();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  // ✅ NEW: elimina presenza
  async function onDeletePresence(presenceId) {
    const ok = window.confirm("Vuoi eliminare questa presenza?");
    if (!ok) return;

    setErr("");
    setLoading(true);
    try {
      await AreaManagerApi.deletePresence(presenceId, username, siteCode);
      await reloadTab();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function onOpenBreakdown() {
    setErr("");
    setLoading(true);
    try {
      await AreaManagerApi.openBreakdown({
        site_code: siteCode,
        forklift_code: bdForklift,
        description: bdDesc || "Guasto segnalato",
        opened_by: username,
      });
      setBdDesc("");
      await reloadTab();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function onUploadBreakdownPdf(breakdownId, file) {
    if (!file) return;
    setErr("");
    setLoading(true);
    try {
      await AreaManagerApi.uploadBreakdownPdf(breakdownId, username, siteCode, file);
      await reloadTab();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  // ✅ NEW: elimina guasto
  async function onDeleteBreakdown(breakdownId) {
    const ok = window.confirm("Vuoi eliminare questo guasto? (se c'è PDF verrà eliminato anche quello)");
    if (!ok) return;

    setErr("");
    setLoading(true);
    try {
      await AreaManagerApi.deleteBreakdown(breakdownId, username, siteCode, true);
      await reloadTab();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function onUploadDocument(file) {
    if (!file) return;
    setErr("");
    setLoading(true);
    try {
      await AreaManagerApi.uploadDocument(username, siteCode, docCategory, docTitle, file);
      await reloadTab();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  // ✅ NEW: elimina documento
  async function onDeleteDocument(documentId) {
    const ok = window.confirm("Vuoi eliminare questo documento? (PDF incluso)");
    if (!ok) return;

    setErr("");
    setLoading(true);
    try {
      await AreaManagerApi.deleteDocument(documentId, username, siteCode, true);
      await reloadTab();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  // =========================
  // CARRELLI: add + archive
  // =========================
  async function onAddForklift() {
    const code = fkCode.trim();
    if (!code) {
      setErr("Inserisci un codice carrello (es. FL-123).");
      return;
    }

    setErr("");
    setLoading(true);
    try {
      await AreaManagerApi.addForklift({
        site_code: siteCode,
        forklift_code: code,
        type: fkType,
        brand: fkBrand,
        model: fkModel,
        status: fkStatus,
      });

      // pulizia form
      setFkCode("");
      setFkType("");
      setFkBrand("");
      setFkModel("");
      setFkStatus("ACTIVE");

      await reloadTab();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function onArchiveForklift(forkliftId, forkliftCode) {
    const ok = window.confirm(
      `Archiviare il carrello ${forkliftCode}?\n\nNon verrà cancellato: finirà nell'archivio e potrai recuperarlo in futuro.`
    );
    if (!ok) return;

    setErr("");
    setLoading(true);
    try {
      await AreaManagerApi.archiveForklift(forkliftId, username, siteCode);
      await reloadTab();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Area Manager</h2>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 12, opacity: 0.8 }}>Utente</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} style={{ padding: 6, minWidth: 160 }} />
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 12, opacity: 0.8 }}>Impianto</label>
          <select value={siteCode} onChange={(e) => setSiteCode(e.target.value)} style={{ padding: 6 }}>
            {sites.map((s) => (
              <option key={s.site_code} value={s.site_code}>
                {s.site_code}
              </option>
            ))}
          </select>
          <span style={{ fontSize: 12, opacity: 0.8 }}>{siteLabel}</span>
          <button onClick={loadSites} style={{ padding: "6px 10px" }}>
            Aggiorna siti
          </button>
        </div>

        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button onClick={reloadTab} style={{ padding: "6px 10px" }}>
            Ricarica
          </button>
        </div>
      </div>

      <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: "8px 12px",
              border: "1px solid #333",
              background: tab === t.key ? "#222" : "transparent",
              color: "white",
              cursor: "pointer",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {err ? (
        <div style={{ marginTop: 12, padding: 10, border: "1px solid #a33", borderRadius: 6 }}>
          <b>Errore:</b> <span style={{ whiteSpace: "pre-wrap" }}>{err}</span>
        </div>
      ) : null}

      {loading ? <div style={{ marginTop: 12, opacity: 0.8 }}>Caricamento...</div> : null}

      {/* Presenze */}
      {tab === "presences" ? (
        <div style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>Presenze Area Manager</h3>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <input type="date" value={presenceDate} onChange={(e) => setPresenceDate(e.target.value)} />
            <select value={presenceType} onChange={(e) => setPresenceType(e.target.value)}>
              <option value="OPERATIVA">OPERATIVA</option>
              <option value="AUDIT">AUDIT</option>
              <option value="RIUNIONE">RIUNIONE</option>
              <option value="EMERGENZA">EMERGENZA</option>
              <option value="ALTRO">ALTRO</option>
            </select>

            <input
              value={presenceNotes}
              onChange={(e) => setPresenceNotes(e.target.value)}
              placeholder="Note"
              style={{ padding: 6, minWidth: 420 }}
            />

            <button onClick={onAddPresence} style={{ padding: "6px 12px" }}>
              Salva presenza
            </button>
          </div>

          <div style={{ marginTop: 12 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Data</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Tipo</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Note</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {presences.map((r) => (
                  <tr key={r.id}>
                    <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{r.presence_date}</td>
                    <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{r.presence_type}</td>
                    <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{r.notes}</td>
                    <td style={{ padding: 8, borderBottom: "1px solid #222" }}>
                      <button
                        onClick={() => onDeletePresence(r.id)}
                        style={{ padding: "6px 10px", border: "1px solid #a33", background: "transparent", color: "white", cursor: "pointer" }}
                      >
                        Elimina
                      </button>
                    </td>
                  </tr>
                ))}
                {!presences.length ? (
                  <tr>
                    <td colSpan={4} style={{ padding: 10, opacity: 0.8 }}>
                      Nessuna presenza trovata.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {/* Carrelli & Guasti */}
      {tab === "breakdowns" ? (
        <div style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>Carrelli & Guasti</h3>

          {/* ===== BOX AGGIUNTA CARRELLO ===== */}
          <div
            style={{
              padding: 12,
              border: "1px solid #333",
              borderRadius: 8,
              marginBottom: 12,
              background: "rgba(255,255,255,0.03)",
            }}
          >
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <b style={{ marginRight: 8 }}>Aggiungi carrello</b>

              <input
                value={fkCode}
                onChange={(e) => setFkCode(e.target.value)}
                placeholder="Codice (es. FL-123)"
                style={{ padding: 6, minWidth: 180 }}
              />
              <input value={fkType} onChange={(e) => setFkType(e.target.value)} placeholder="Tipo" style={{ padding: 6, minWidth: 160 }} />
              <input value={fkBrand} onChange={(e) => setFkBrand(e.target.value)} placeholder="Marca" style={{ padding: 6, minWidth: 160 }} />
              <input value={fkModel} onChange={(e) => setFkModel(e.target.value)} placeholder="Modello" style={{ padding: 6, minWidth: 160 }} />
              <select value={fkStatus} onChange={(e) => setFkStatus(e.target.value)} style={{ padding: 6 }}>
                <option value="ACTIVE">ACTIVE</option>
                <option value="IN_SERVICE">IN_SERVICE</option>
                <option value="OUT_OF_SERVICE">OUT_OF_SERVICE</option>
              </select>

              <button onClick={onAddForklift} style={{ padding: "6px 12px" }}>
                Salva carrello
              </button>
            </div>

            <div style={{ marginTop: 8, fontSize: 12, opacity: 0.85 }}>
              Suggerimento: per caricare 2000 carrelli, dopo mettiamo un <b>import massivo da Excel</b>. Ora partiamo “manuale” per la struttura.
            </div>
          </div>

          {/* ===== BOX GUASTI ===== */}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <input
              value={bdForklift}
              onChange={(e) => setBdForklift(e.target.value)}
              placeholder="Codice carrello (es. FL-01)"
              style={{ padding: 6, minWidth: 220 }}
            />
            <input
              value={bdDesc}
              onChange={(e) => setBdDesc(e.target.value)}
              placeholder="Descrizione guasto"
              style={{ padding: 6, minWidth: 520 }}
            />
            <button onClick={onOpenBreakdown} style={{ padding: "6px 12px" }}>
              Apri guasto
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 14, marginTop: 12 }}>
            {/* ===== LISTA CARRELLI CON RICERCA + ARCHIVIO ===== */}
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "space-between" }}>
                <h4 style={{ marginTop: 0 }}>Carrelli</h4>

                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <button
                    onClick={() => setFkArchived(0)}
                    style={{
                      padding: "6px 10px",
                      border: "1px solid #333",
                      background: fkArchived === 0 ? "#222" : "transparent",
                      color: "white",
                      cursor: "pointer",
                    }}
                    title="Mostra carrelli attivi"
                  >
                    Attivi
                  </button>
                  <button
                    onClick={() => setFkArchived(1)}
                    style={{
                      padding: "6px 10px",
                      border: "1px solid #333",
                      background: fkArchived === 1 ? "#222" : "transparent",
                      color: "white",
                      cursor: "pointer",
                    }}
                    title="Mostra carrelli archiviati"
                  >
                    Archivio
                  </button>
                </div>
              </div>

              <input
                value={fkSearch}
                onChange={(e) => setFkSearch(e.target.value)}
                placeholder="Cerca (codice, marca, modello...)"
                style={{ padding: 6, width: "100%", marginBottom: 8 }}
              />

              <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>
                Risultati: <b>{forkliftsFiltered.length}</b> {fkArchived ? "(archiviati)" : "(attivi)"}
              </div>

              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Codice</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Info</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Stato</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {forkliftsFiltered.map((f) => (
                    <tr key={f.id}>
                      <td style={{ padding: 8, borderBottom: "1px solid #222" }}>
                        <b>{f.forklift_code}</b>
                      </td>
                      <td style={{ padding: 8, borderBottom: "1px solid #222", opacity: 0.9 }}>
                        {[f.brand, f.model, f.type].filter(Boolean).join(" — ") || "—"}
                      </td>
                      <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{f.status || "—"}</td>
                      <td style={{ padding: 8, borderBottom: "1px solid #222", textAlign: "right" }}>
                        {fkArchived === 0 ? (
                          <button
                            onClick={() => onArchiveForklift(f.id, f.forklift_code)}
                            style={{ padding: "6px 10px", border: "1px solid #a33", background: "transparent", color: "white", cursor: "pointer" }}
                            title="Archivia (non cancella, salva nello storico)"
                          >
                            Archivia
                          </button>
                        ) : (
                          <span style={{ fontSize: 12, opacity: 0.7 }}>In archivio</span>
                        )}
                      </td>
                    </tr>
                  ))}

                  {!forkliftsFiltered.length ? (
                    <tr>
                      <td colSpan={4} style={{ padding: 10, opacity: 0.8 }}>
                        Nessun carrello trovato.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            {/* ===== GUASTI ===== */}
            <div>
              <h4 style={{ marginTop: 0 }}>Guasti aperti</h4>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>ID</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Carrello</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Descrizione</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>PDF</th>
                    <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Azioni</th>
                  </tr>
                </thead>
                <tbody>
                  {breakdowns.map((b) => (
                    <tr key={b.id}>
                      <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{b.id}</td>
                      <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{b.forklift_code}</td>
                      <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{b.description}</td>
                      <td style={{ padding: 8, borderBottom: "1px solid #222" }}>
                        {b.pdf_path ? (
                          <a
                            href={buildApiUrl(`/area-manager/files/breakdown/${b.id}?username=${encodeURIComponent(username)}&site_code=${encodeURIComponent(siteCode)}`)}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Apri PDF
                          </a>
                        ) : (
                          "—"
                        )}

                        <div style={{ marginTop: 6 }}>
                          <input
                            type="file"
                            accept="application/pdf"
                            onChange={(e) => onUploadBreakdownPdf(b.id, e.target.files?.[0])}
                          />
                        </div>
                      </td>
                      <td style={{ padding: 8, borderBottom: "1px solid #222" }}>
                        <button
                          onClick={() => onDeleteBreakdown(b.id)}
                          style={{ padding: "6px 10px", border: "1px solid #a33", background: "transparent", color: "white", cursor: "pointer" }}
                        >
                          Elimina
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!breakdowns.length ? (
                    <tr>
                      <td colSpan={5} style={{ padding: 10, opacity: 0.8 }}>
                        Nessun guasto aperto.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}

      {/* Documenti */}
      {tab === "documents" ? (
        <div style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>Documenti impianto</h3>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <select value={docCategory} onChange={(e) => setDocCategory(e.target.value)}>
              <option value="CONTRATTO">CONTRATTO</option>
              <option value="SLA">SLA</option>
              <option value="CAPITOLATO">CAPITOLATO</option>
              <option value="VERBALE">VERBALE</option>
              <option value="ALTRO">ALTRO</option>
            </select>

            <input value={docTitle} onChange={(e) => setDocTitle(e.target.value)} style={{ padding: 6, minWidth: 320 }} />
            <input type="file" accept="application/pdf" onChange={(e) => onUploadDocument(e.target.files?.[0])} />
          </div>

          <div style={{ marginTop: 12 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>ID</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Categoria</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Titolo</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Path</th>
                  <th style={{ textAlign: "left", borderBottom: "1px solid #444", padding: 8 }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((d) => (
                  <tr key={d.id}>
                    <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{d.id}</td>
                    <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{d.category}</td>
                    <td style={{ padding: 8, borderBottom: "1px solid #222" }}>{d.title}</td>
                    <td style={{ padding: 8, borderBottom: "1px solid #222", opacity: 0.8 }}>{d.file_path}</td>
                    <td style={{ padding: 8, borderBottom: "1px solid #222" }}>
                      <button
                        onClick={() => onDeleteDocument(d.id)}
                        style={{ padding: "6px 10px", border: "1px solid #a33", background: "transparent", color: "white", cursor: "pointer" }}
                      >
                        Elimina
                      </button>
                    </td>
                  </tr>
                ))}
                {!documents.length ? (
                  <tr>
                    <td colSpan={5} style={{ padding: 10, opacity: 0.8 }}>
                      Nessun documento trovato.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
