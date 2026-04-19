
import React from "react";
import ScrollingTicker from "./ScrollingTicker.jsx";
import KpiRow from "./KpiRow.jsx";
import WarehouseMap from "./WarehouseMap.jsx";
import OperatorList from "./OperatorList.jsx";
import TimelineBar from "./TimelineBar.jsx";
import logo from "../assets/logo-mhw.png";


export default function DashboardLayout({ kpi, operators, layout }) {
  return (
    <div className="app-root">
      <aside className="sidebar">
      <div className="logo">
  <img
    src="/logo-mhw.png"
    alt="ManHandWork"
    className="logo-img"
  />
</div>


       <nav>
          <button>Overview</button>
          <button>Flussi</button>
          <button>Ritorni</button>
          <button>Heatmap</button>
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <h1>Pick Control Room</h1>
          <div className="filters">
            <select>
              <option>Oggi</option>
              <option>Ultimi 7 giorni</option>
            </select>
            <select>
              <option>Tutti i magazzini</option>
            </select>
          </div>
        </header>
<div style={{ background: "yellow", padding: 10 }}>TEST: DashboardLayout caricato</div>


        <section className="kpi-row">
          <KpiRow kpi={kpi} />
        </section>

        <section className="middle-row">
          <div className="map-card">
            <h2>Mappa magazzino</h2>
            <WarehouseMap layout={layout} />
            <TimelineBar />
          </div>
          <div className="side-card">
            <h2>Operatori</h2>
            <OperatorList operators={operators} />
          </div>
        </section>

        {/* ✅ QUI, dentro <main>, alla fine */}
        <ScrollingTicker />
      </main>
    </div>
  );
}
