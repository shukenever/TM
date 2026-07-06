"use strict";

/**
 * All /api/tm-viewer/auth/* — signin, register, send-otp, verify-otp, etc.
 * Required because Vercel does not fall back to api/tm-viewer/[...slug].js for
 * paths under auth/ when this folder contains route files.
 */
const { writeJson } = require("../../../lib/tm-viewer/http");

function routeKey(req) {
  const host = req.headers.host || "localhost";
  const url = new URL(req.url || "/", `http://${host}`);
  const parts = url.pathname
    .replace(/^\/api\/tm-viewer\/auth\/?/i, "")
    .split("/")
    .filter(Boolean);
  return parts.join("/");
}

const routes = {
  "send-otp": require("../../../lib/tm-viewer/routes/auth-send-otp"),
  "verify-otp": require("../../../lib/tm-viewer/routes/auth-verify-otp"),
  register: require("../../../lib/tm-viewer/routes/auth-register"),
  signin: require("../../../lib/tm-viewer/routes/auth-signin"),
  "forgot-password": require("../../../lib/tm-viewer/routes/auth-forgot-password"),
  "reset-password": require("../../../lib/tm-viewer/routes/auth-reset-password"),
};

module.exports = async (req, res) => {
  const key = routeKey(req);
  const handler = routes[key];
  if (!handler) {
    return writeJson(res, 404, {
      ok: false,
      error: "not_found",
      route: key ? `auth/${key}` : "auth/(empty)",
    });
  }
  return handler(req, res);
};
