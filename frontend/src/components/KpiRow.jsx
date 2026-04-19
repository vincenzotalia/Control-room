import React from "react";

function KpiCard({ label, value, suffix }) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {value !== null && value !== undefined ? value : "--"}
        {suffix && <span className="kpi-suffix">{suffix}</span>}
      </div>
    </div>
  );
}

export default function KpiRow({ kpi }) {
  if (!kpi) {
    return (
      <div className="kpi-row-inner">
        <KpiCard label="Colli/ora reali" value={null} />
        <KpiCard label="Colli/ora attesi" value={null} />
        <KpiCard label="Colli per riga" value={null} />
        <KpiCard label="Colli per lista" value={null} />
        <KpiCard label="Ritorni + recuperi" value={null} />
      </div>
    );
  }

  // dal backend (agora_analysis.py)
  const unitsPerHour = kpi.units_per_hour ?? null;                     // produttività reale
  const targetUnitsPerHour =
    kpi.target_units_per_hour ?? kpi.prod_target_colli_ora ?? null;    // colli/ora attesi da PARAM
  const colliPerRiga = kpi.colli_per_riga ?? null;                     // media colli per riga
  const colliPerLista =
    kpi.colli_per_lista ?? kpi.media_colli_lista ?? null;              // media colli per lista
  const totalIssues = kpi.return_rate ?? null;                         // ritorni + recuperi (numero)

  return (
    <div className="kpi-row-inner">
      <KpiCard label="Colli/ora reali" value={unitsPerHour?.toFixed?.(1) ?? unitsPerHour} />
      <KpiCard label="Colli/ora attesi" value={targetUnitsPerHour?.toFixed?.(1) ?? targetUnitsPerHour} />
      <KpiCard label="Colli per riga" value={colliPerRiga?.toFixed?.(2) ?? colliPerRiga} />
      <KpiCard label="Colli per lista" value={colliPerLista?.toFixed?.(1) ?? colliPerLista} />
      <KpiCard label="Ritorni + recuperi" value={totalIssues} />
    </div>
  );
}


