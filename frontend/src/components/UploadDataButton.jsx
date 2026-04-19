import { useState } from "react";
import { buildApiUrl } from "../api/config";

export default function UploadDataButton() {
  const [dataset, setDataset] = useState("picking");
  const [file, setFile] = useState(null);
  const [msg, setMsg] = useState("");

  async function handleUpload() {
    if (!file) {
      setMsg("❌ Seleziona un file prima");
      return;
    }

    const formData = new FormData();
    formData.append("dataset", dataset);
    formData.append("file", file);

    setMsg("⏳ Caricamento in corso...");

    try {
      const res = await fetch(buildApiUrl("/data/upload"), {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        setMsg("❌ Errore: " + (data.detail || "upload fallito"));
        return;
      }

      setMsg("✅ " + data.message);

      // opzionale: ricarica la pagina per vedere i nuovi dati
      setTimeout(() => window.location.reload(), 600);
    } catch (err) {
      setMsg("❌ Errore di rete: " + err.message);
    }
  }

  return (
    <div style={{ border: "1px solid #ddd", padding: 12, borderRadius: 8, marginBottom: 12 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <b>Carica dati</b>

        <select value={dataset} onChange={(e) => setDataset(e.target.value)}>
          <option value="picking">Picking (mappe / KPI)</option>
          <option value="operators">Carrellisti (carrellisti.xlsm)</option>
        </select>

        <input
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />

        <button onClick={handleUpload}>Carica</button>
      </div>

      {msg && <div style={{ marginTop: 8 }}>{msg}</div>}
    </div>
  );
}
