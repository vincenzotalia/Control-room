// src/api/areaManagerApi.js
import { buildApiUrl } from "./config";

const BASE = buildApiUrl("/area-manager");

async function httpJson(url, options) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* ignore */ }

  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) ? (data.detail || data.message) : text;
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return data;
}

async function httpForm(url, formData) {
  const res = await fetch(url, { method: "POST", body: formData });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* ignore */ }

  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) ? (data.detail || data.message) : text;
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return data;
}

export const AreaManagerApi = {
  // =========================
  // SITES
  // =========================
  listSites(username) {
    return httpJson(`${BASE}/sites?username=${encodeURIComponent(username)}`);
  },

  // ✅ (utile) assegna utente al sito per evitare 403 "non assegnato"
  assignSite(username, siteCode) {
    return httpJson(`${BASE}/sites/assign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, site_code: siteCode }),
    });
  },

  // =========================
  // PRESENCES
  // =========================
  addPresence(payload) {
    return httpJson(`${BASE}/presences`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  listPresences(username, siteCode) {
    const qs = new URLSearchParams({ username, site_code: siteCode });
    return httpJson(`${BASE}/presences?${qs.toString()}`);
  },

  // ✅ NUOVO: elimina una presenza (per pulire prove/errori)
  deletePresence(presenceId, username, siteCode) {
    const qs = new URLSearchParams({ username, site_code: siteCode });
    return httpJson(`${BASE}/presences/${presenceId}?${qs.toString()}`, {
      method: "DELETE",
    });
  },

  // =========================
  // FORKLIFTS
  // =========================
  addForklift(payload) {
    return httpJson(`${BASE}/forklifts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  listForklifts(username, siteCode, archived = 0) {
    const qs = new URLSearchParams({ username, site_code: siteCode, archived: String(archived) });
    return httpJson(`${BASE}/forklifts?${qs.toString()}`);
  },

  archiveForklift(forkliftId, username, siteCode) {
    const qs = new URLSearchParams({ username, site_code: siteCode });
    return httpJson(`${BASE}/forklifts/${forkliftId}/archive?${qs.toString()}`, {
      method: "POST",
    });
  },

  // =========================
  // BREAKDOWNS
  // =========================
  openBreakdown(payload) {
    return httpJson(`${BASE}/breakdowns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  listBreakdowns(username, siteCode, includeClosed = false) {
    const qs = new URLSearchParams({
      username,
      site_code: siteCode,
      include_closed: includeClosed ? "true" : "false",
    });
    return httpJson(`${BASE}/breakdowns?${qs.toString()}`);
  },

  uploadBreakdownPdf(breakdownId, username, siteCode, file) {
    const qs = new URLSearchParams({ username, site_code: siteCode });
    const fd = new FormData();
    fd.append("file", file);
    return httpForm(`${BASE}/breakdowns/${breakdownId}/upload-pdf?${qs.toString()}`, fd);
  },

  // ✅ NUOVO: elimina un breakdown (per pulire prove)
  // (se nel backend poi vuoi invece "archivia" e non cancellare, lo cambiamo)
  deleteBreakdown(breakdownId, username, siteCode, deleteFile = true) {
    const qs = new URLSearchParams({
      username,
      site_code: siteCode,
      delete_file: deleteFile ? "true" : "false",
    });
    return httpJson(`${BASE}/breakdowns/${breakdownId}?${qs.toString()}`, {
      method: "DELETE",
    });
  },

  // =========================
  // DOCUMENTS
  // =========================
  uploadDocument(username, siteCode, category, title, file) {
    const qs = new URLSearchParams({
      username,
      site_code: siteCode,
      category,
      title,
    });
    const fd = new FormData();
    fd.append("file", file);
    return httpForm(`${BASE}/documents/upload?${qs.toString()}`, fd);
  },

  listDocuments(username, siteCode) {
    const qs = new URLSearchParams({ username, site_code: siteCode });
    return httpJson(`${BASE}/documents?${qs.toString()}`);
  },

  // ✅ NUOVO: elimina un documento (e opzionalmente il file PDF)
  deleteDocument(documentId, username, siteCode, deleteFile = true) {
    const qs = new URLSearchParams({
      username,
      site_code: siteCode,
      delete_file: deleteFile ? "true" : "false",
    });
    return httpJson(`${BASE}/documents/${documentId}?${qs.toString()}`, {
      method: "DELETE",
    });
  },
};
