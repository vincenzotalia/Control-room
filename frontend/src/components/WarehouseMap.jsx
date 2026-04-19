import React from "react";

// Very simple SVG-based map.
export default function WarehouseMap({ layout }) {
  if (!layout) return <div className="placeholder">Caricamento mappa...</div>;

  const cells = layout.cells || [];

  return (
    <svg className="warehouse-map" viewBox="0 0 10 10">
      {cells.map(cell => {
        const color =
          cell.type === "rack" ? "#2d8cff" :
          cell.type === "corridor" ? "#444" :
          "#666";

        return (
          <rect
            key={cell.id}
            x={cell.x}
            y={cell.y}
            width={cell.w}
            height={cell.h}
            rx="0.3"
            ry="0.3"
            fill={color}
          />
        );
      })}
    </svg>
  );
}
