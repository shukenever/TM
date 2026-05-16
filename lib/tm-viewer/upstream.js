"use strict";

/**
 * Registry HTTP base (no trailing slash). Server-side only — not exposed to the browser.
 * Strips a trailing `/api` so mis-set `.../api` does not become `.../api/api/tm-viewer/...`.
 */
function normalizeBackendUrl(raw) {
  let b = (raw || "").trim().replace(/\/+$/, "");
  if (b.length >= 4 && /\/api$/i.test(b)) {
    b = b.slice(0, -4).replace(/\/+$/, "");
  }
  return b;
}

function getUpstreamBase() {
  return normalizeBackendUrl(process.env.TM_VIEWER_BACKEND_URL);
}

/**
 * Optional second origin for buyer email (send-mail / transfer-to-buyer only).
 * Use stubby proxy on e.g. :9440 while `TM_VIEWER_BACKEND_URL` stays on :3919 for generate, OTP, tickets, etc.
 */
function getEmailUpstreamBase() {
  const email = normalizeBackendUrl(process.env.TM_VIEWER_EMAIL_BACKEND_URL);
  if (email) return email;
  return getUpstreamBase();
}

module.exports = { getUpstreamBase, getEmailUpstreamBase, normalizeBackendUrl };
