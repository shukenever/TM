"use strict";

/**
 * Single Vercel function for all /api/tm-viewer/* routes (Hobby plan 12-function limit).
 */
const { writeJson } = require("../../lib/tm-viewer/http");

function routeKey(req) {
  const host = req.headers.host || "localhost";
  const url = new URL(req.url || "/", `http://${host}`);
  const parts = url.pathname
    .replace(/^\/api\/tm-viewer\/?/i, "")
    .split("/")
    .filter(Boolean);
  return parts.join("/");
}

const routes = {
  ping: require("../../lib/tm-viewer/routes/ping"),
  generate: require("../../lib/tm-viewer/routes/generate"),
  "send-mail": require("../../lib/tm-viewer/routes/send-mail"),
  tickets: require("../../lib/tm-viewer/routes/tickets"),
  "transfer-to-buyer": require("../../lib/tm-viewer/routes/transfer-to-buyer"),
  "tm-viewer-mail-api-base": require("../../lib/tm-viewer/routes/tm-viewer-mail-api-base"),
  "auth/send-otp": require("../../lib/tm-viewer/routes/auth-send-otp"),
  "auth/verify-otp": require("../../lib/tm-viewer/routes/auth-verify-otp"),
};

module.exports = async (req, res) => {
  const key = routeKey(req);
  const handler = routes[key];
  if (!handler) {
    return writeJson(res, 404, {
      ok: false,
      error: "not_found",
      route: key || "(empty)",
    });
  }
  return handler(req, res);
};
