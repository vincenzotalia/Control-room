import React from "react";

export default function OperatorList({ operators }) {
  if (!operators || operators.length === 0) {
    return <div className="placeholder">Nessun dato operatore.</div>;
  }

  return (
    <ul className="operator-list">
      {operators.map(op => (
        <li key={op.name} className="operator-item">
          <div className="operator-name">{op.name}</div>
          <div className="operator-metric">
            {op.units_per_hour} colli/ora
          </div>
        </li>
      ))}
    </ul>
  );
}
