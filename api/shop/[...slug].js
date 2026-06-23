"use strict";

const { writeJson } = require("../../lib/tm-viewer/http");
const { proxy } = require("../../lib/shop/proxy");

function routeKey(req) {
  const host = req.headers.host || "localhost";
  const url = new URL(req.url || "/", `http://${host}`);
  const parts = url.pathname.replace(/^\/api\/shop\/?/i, "").split("/").filter(Boolean);
  return parts.join("/") || "listings";
}

const GET_ROUTES = {
  listings: "/api/shop/listings",
  orders: "/api/shop/orders",
  account: "/api/shop/account",
  health: "/api/shop/health",
  sync: "/api/shop/sync",
};

const POST_ROUTES = {
  purchase: "/api/shop/purchase",
  checkout: "/api/shop/checkout",
  "event-images": "/api/shop/event-images",
  account: "/api/shop/account",
  sync: "/api/shop/sync",
};

module.exports = async (req, res) => {
  try {
    const key = routeKey(req);
    if (req.method === "GET" && GET_ROUTES[key]) {
      return proxy(req, res, GET_ROUTES[key], { methods: "GET, OPTIONS" });
    }
    if ((req.method === "POST" || req.method === "PUT" || req.method === "PATCH") && POST_ROUTES[key]) {
      return proxy(req, res, POST_ROUTES[key], {
        methods: "GET, POST, OPTIONS",
        allowBody: true,
      });
    }
    return writeJson(res, 404, { ok: false, error: "not_found" });
  } catch (e) {
    return writeJson(res, 502, {
      ok: false,
      error: "unavailable",
      message: "Events are temporarily unavailable. Please try again shortly.",
    });
  }
};
