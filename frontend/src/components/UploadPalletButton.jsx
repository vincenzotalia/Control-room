import React, { useState } from "react";

export default function UploadPalletButton({ API_BASE, onUploaded }) {
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setErr("");
    setMsg("");

    try {
      const form = new FormData();
      form.append("dataset", "pallet");
      form.append("file", file);

      const res = await fetch(`${API_BASE}/data/upload`, {
        method: "POST",
        body: form,
      });

      const json = await res.json();
      if (!res.ok) throw new Error(json?.detail || "Upload fallito");

      setMsg(json?.message || "Upload completato");
      if (onUploaded) onUploaded();
    } catch (e2) {
      setErr(e2?.message || "Errore sconosciuto");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  return (
    <div style={{ marginBottom: 10 }}>
      <label
        style={{
          display: "inline-block",
          padding: "6px 10px",
          borderRadius: 8,
          border: "1px solid rgba(148,163,184,0.6)",
          background: "rgba(2,6,23,0.6)",
          color: "#e5e7eb",
          fontSize: 12,
          cursor: uploading ? "default" : "pointer",
          opacity: uploading ? 0.7 : 1,
        }}
      >
        {uploading ? "Caricamento pallet…" : "Carica file scarico pallet (dati_pallet.xlsx)"}
        <input type="file" accept=".xlsx,.xls" onChange={handleFile} disabled={uploading} style={{ display: "none" }} />
      </label>

      {msg && <div style={{ fontSize: 11, color: "#86efac", marginTop: 6 }}>{msg}</div>}
      {err && <div style={{ fontSize: 11, color: "#fca5a5", marginTop: 6 }}>{err}</div>}
    </div>
  );
}
