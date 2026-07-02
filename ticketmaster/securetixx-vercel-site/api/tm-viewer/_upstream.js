"use strict";

/** VPS registry API (same host as tm-viewer generate / OTP). */
function getUpstreamBase() {
  const raw =
    process.env.TM_VIEWER_BACKEND_URL ||
    process.env.TM_SHOP_BACKEND_URL ||
    "";
  return String(raw).trim().replace(/\/+$/, "");
}

module.exports = { getUpstreamBase };
