import React from "react";

export default function TimelineBar() {
  return (
    <div className="timeline-bar">
      <div className="timeline-labels">
        <span>08:00</span>
        <span>10:00</span>
        <span>12:00</span>
        <span>14:00</span>
      </div>
      <div className="timeline-track">
        <div className="timeline-progress" />
      </div>
      <div className="timeline-controls">
        <button>▶</button>
        <button>❚❚</button>
        <button>x2</button>
      </div>
    </div>
  );
}
