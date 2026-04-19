import React, { useState } from "react";

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    setErr("");

    // ✅ LOGIN SEMPLICE (da cambiare dopo con backend)
    // Cambia qui le credenziali:
    const OK_USER = "admin";
    const OK_PASS = "1234";

    if (username === OK_USER && password === OK_PASS) {
      onLogin({ username });
      return;
    }

    setErr("Credenziali non corrette");
  }

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#0b1220" }}>
      <div
        style={{
          width: 360,
          padding: 18,
          borderRadius: 12,
          border: "1px solid rgba(148,163,184,0.35)",
          background: "rgba(2,6,23,0.65)",
          color: "#e5e7eb",
        }}
      >
        <h2 style={{ margin: 0, marginBottom: 6 }}>Login</h2>
        <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 14 }}>
          Inserisci le credenziali per entrare nella Control Room
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, marginBottom: 4 }}>Username</div>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={{
                width: "100%",
                padding: 10,
                borderRadius: 8,
                border: "1px solid rgba(148,163,184,0.5)",
                background: "#020617",
                color: "#e5e7eb",
              }}
            />
          </div>

          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, marginBottom: 4 }}>Password</div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: "100%",
                padding: 10,
                borderRadius: 8,
                border: "1px solid rgba(148,163,184,0.5)",
                background: "#020617",
                color: "#e5e7eb",
              }}
            />
          </div>

          {err && (
            <div style={{ fontSize: 12, color: "#f97373", marginBottom: 10 }}>
              {err}
            </div>
          )}

          <button
            type="submit"
            style={{
              width: "100%",
              padding: 10,
              borderRadius: 8,
              border: "none",
              background: "linear-gradient(135deg, #38bdf8, #0ea5e9)",
              color: "#0b1120",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Entra
          </button>
        </form>
      </div>
    </div>
  );
}
