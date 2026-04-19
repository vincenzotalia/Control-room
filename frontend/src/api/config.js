function resolveDefaultApiBase() {
  if (typeof window === "undefined") {
    return "http://127.0.0.1:8000";
  }

  const hostname = window.location.hostname;

  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return "http://127.0.0.1:8000";
  }

  // Demo fallback for Azure Static Web Apps builds where VITE_API_BASE_URL
  // was not injected correctly at build time.
  return "https://control-room-demo-api.azurewebsites.net";
}

const rawApiBase = import.meta.env.VITE_API_BASE_URL || resolveDefaultApiBase();

export const API_BASE = rawApiBase.replace(/\/+$/, "");

export function buildApiUrl(path = "") {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalizedPath}`;
}
