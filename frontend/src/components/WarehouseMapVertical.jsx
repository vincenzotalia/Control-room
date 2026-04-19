import React from "react";
import "./WarehouseMapVertical.css";

export default function WarehouseMapVertical({ missions }) {
  // Se non ci sono dati
  if (!missions || missions.length === 0) {
    return (
      <div className="map-container">
        <p>Caricamento mappa…</p>
      </div>
    );
  }

  // Ordina corsie in modo DESC → 75 → 13
  const lanes = [...new Set(missions.map(m => m.corsia))]
    .sort((a, b) => b - a);

  // Per ogni corsia raccogliamo i posti con attività
  const laneData = lanes.map(lane => {
    const filtered = missions.filter(m => m.corsia === lane);

    // heatmap: calcoliamo l'intensità sulla base dei colli
    const maxColli = Math.max(...filtered.map(f => f.colli), 1);

    // ordina i posti in sequenza corretta SERPENTINA
    let posti = filtered
      .map(f => ({
        posto: f.posto,
        colli: f.colli,
      }))
      .sort((a, b) => a.posto - b.posto);

    // serpentina: corsia dispari → inverti la direzione
    if (lane % 2 === 1) {
      posti.reverse();
    }

    return {
      lane,
      posti: posti.map(p => ({
        ...p,
        intensity: p.colli / maxColli, // 0–1
      })),
    };
  });

  return (
    <div className="map-container">
      {laneData.map(({ lane, posti }) => (
        <div key={lane} className="lane-row">
          <span className="lane-label">Corsia {lane}</span>
          <div className="lane-bar">
            {posti.map((p, idx) => (
              <div
                key={idx}
                className="posto-cell"
                style={{
                  backgroundColor: `rgba(0, 255, 0, ${p.intensity})`,
                }}
                title={`Corsia ${lane} - Posto ${p.posto} (${p.colli} colli)`}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
