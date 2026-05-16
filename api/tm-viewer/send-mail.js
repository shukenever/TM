"use strict";

const { getEmailUpstreamBase } = require("./_upstream");
const { writeJson, corsOptions, readRequestBody } = require("./_http");

function _vercelDebugOn() {
  const v = (process.env.TM_VIEWER_VERCEL_DEBUG || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

/** Shown in DevTools → Network → Headers when TM_VIEWER_VERCEL_DEBUG=1 on Vercel. Stubby logs stay on the VPS only. */
function _vercelDebugHdr(extra) {
  if (!_vercelDebugOn()) return extra || {};
  return {
    "X-TM-Handler": "vercel-api/tm-viewer/send-mail",
    "X-TM-Debug-Where":
      "Stubby: set STUBBY_TM_VIEWER_PROXY_DEBUG=1 on VPS; logs = stdout/journal where stubby runs (not Chrome).",
    ...(extra || {}),
  };
}

const _STUBBY_EXPOSE =
  "X-TM-Stubby-Registry-Base, X-TM-Stubby-Upstream-Full-Url, X-TM-Stubby-Upstream-Status, X-TM-Stubby-Log-File";

/** Forward stubby debug headers from fetch() to the browser (check Response Headers on send-mail). */
function _stubbyHeadersFromUpstream(fetchRes) {
  const o = {};
  if (!fetchRes || !fetchRes.headers || typeof fetchRes.headers.forEach !== "function") return o;
  fetchRes.headers.forEach(function (value, key) {
    if (String(key).toLowerCase().indexOf("x-tm-stubby") === 0) {
      o[key] = value;
    }
  });
  return o;
}

/** Vercel often targets stubby :9440; plain 404 there usually means STUBBY_TM_VIEWER_PROXY off, not :3919. */
function _upstreamLooksLikeStubbyViewer(base, lastTriedUrl) {
  const s = `${String(base || "")} ${String(lastTriedUrl || "")}`;
  return /:9440(\/|$|[\s"'])/.test(s) || /\/tm-viewer\//i.test(lastTriedUrl || "");
}

/** Same-origin entry (neutral path); proxies to registry POST /api/tm-viewer/transfer-to-buyer. */
module.exports = async (req, res) => {
  try {
    if (req.method === "OPTIONS") {
      return corsOptions(res, "POST, OPTIONS", "Content-Type", _vercelDebugHdr());
    }
    if (req.method !== "POST") {
      return writeJson(res, 405, { ok: false, error: "method_not_allowed" }, _vercelDebugHdr());
    }
    const base = getEmailUpstreamBase();
    if (!base) {
      return writeJson(
        res,
        503,
        {
          ok: false,
          error: "proxy_misconfigured",
          detail:
            "Set TM_VIEWER_BACKEND_URL on Vercel, or TM_VIEWER_EMAIL_BACKEND_URL for buyer email only (e.g. stubby :9440)",
        },
        _vercelDebugHdr(),
      );
    }
    const buf = await readRequestBody(req);
    const hdr = { "Content-Type": "application/json; charset=utf-8" };

    function isPythonStatic404(status, contentType, body) {
      const b = String(body || "");
      if (status !== 404) return false;
      if (
        /text\/html/i.test(contentType) &&
        (/Nothing matches the given URI/i.test(b) || /<title>Error response<\/title>/i.test(b))
      )
        return true;
      // nginx / aiohttp sometimes return plain "404: Not Found" without text/html
      if (/404:\s*Not Found/i.test(b.trim()) && b.length < 4000) return true;
      return false;
    }

    /** Keep trying paths while we get a “dumb” 404 (plain text / HTML); stop on JSON (real registry answer). */
    function shouldRetryAnotherUpstreamPath(status, contentType, body) {
      if (isPythonStatic404(status, contentType, body)) return true;
      if (status !== 404) return false;
      try {
        const o = JSON.parse(body);
        if (o && typeof o === "object") return false;
      } catch (_) {}
      return true;
    }

    /** Stubby registers /api/tm-viewer/*, /api/send-mail, /api/v1/mail, and /tm-viewer/* when STUBBY_TM_VIEWER_PROXY=1. */
    const upstreamPaths = [
      "/api/tm-viewer/transfer-to-buyer",
      "/api/tm-viewer/send-mail",
      "/api/send-mail",
      "/api/v1/mail",
      "/tm-viewer/transfer-to-buyer",
      "/tm-viewer/send-mail",
    ];

    let r;
    let text;
    let ct;
    let lastTriedUrl = "";
    const triedUrls = [];
    for (const p of upstreamPaths) {
      lastTriedUrl = `${base}${p}`;
      triedUrls.push(lastTriedUrl);
      r = await fetch(lastTriedUrl, { method: "POST", headers: hdr, body: buf });
      text = await r.text();
      ct = r.headers.get("content-type") || "application/json; charset=utf-8";
      if (!shouldRetryAnotherUpstreamPath(r.status, ct, text)) break;
    }

    if (isPythonStatic404(r.status, ct, text)) {
      const stubbyish = _upstreamLooksLikeStubbyViewer(base, lastTriedUrl);
      const body = JSON.stringify({
        ok: false,
        error: "upstream_404",
        detail: stubbyish
          ? "Plain or HTML 404 (not JSON) from a URL that looks like stubby :9440. Most often STUBBY_TM_VIEWER_PROXY is not enabled, so /tm-viewer/* was never registered (same symptom as before stubby.py registered tm_viewer_proxy_disabled JSON)."
          : "Plain or HTML 404 (not JSON) from the upstream. If the registry is on :3919, run tm_viewer_link_registry there or STUBBY_START_TM_VIEWER_API=1.",
        fix: stubbyish
          ? "On the VPS: set STUBBY_TM_VIEWER_PROXY=1, restart stubby. Then POST http://127.0.0.1:9440/tm-viewer/send-mail must return JSON (e.g. error tm_viewer_proxy_disabled or auth), not plain 404. GET http://127.0.0.1:9440/stubby-tm-viewer-ping. Only then, if needed: curl -sS -X POST http://127.0.0.1:3919/api/tm-viewer/send-mail -H 'Content-Type: application/json' -d '{}' → JSON."
          : "GET http://127.0.0.1:9440/stubby-tm-viewer-ping (if using stubby). Ensure POST http://127.0.0.1:3919/api/tm-viewer/send-mail -H 'Content-Type: application/json' -d '{}' returns JSON. See BASE_DIR/tm_viewer_proxy.log on the VPS.",
      });
      res.writeHead(502, {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "Content-Length": Buffer.byteLength(body),
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers":
          "X-TM-Upstream-Last, X-TM-Upstream-Base, X-TM-Handler, X-TM-Debug-Where, " + _STUBBY_EXPOSE,
        "X-TM-Upstream-Base": base,
        "X-TM-Upstream-Last": lastTriedUrl,
        ..._stubbyHeadersFromUpstream(r),
        ..._vercelDebugHdr(),
      });
      res.end(body);
      return;
    }

    /** Upstream returned 4xx/5xx with plain/HTML body — almost always wrong TM_VIEWER_* URL or registry/stubby down. */
    if (r.status >= 400) {
      let parsed = null;
      try {
        const o = JSON.parse(text);
        if (o && typeof o === "object") parsed = o;
      } catch (_) {}
      if (!parsed) {
        const sh = _stubbyHeadersFromUpstream(r);
        const preview = String(text || "")
          .slice(0, 400)
          .replace(/\s+/g, " ");
        const plain404 =
          r.status === 404 && /404:\s*Not Found/i.test(String(text || "").trim());
        const stubbyish = _upstreamLooksLikeStubbyViewer(base, lastTriedUrl);
        const fixPlain404 =
          "Plain 404 from upstream_last: (1) STUBBY_TM_VIEWER_PROXY=1 + restart stubby — without it, :9440 does not register /tm-viewer/* (plain 404). " +
          "(2) curl -sS -X POST http://127.0.0.1:9440/tm-viewer/send-mail -H 'Content-Type: application/json' -d '{}' → JSON, not '404: Not Found'. " +
          "(3) GET http://127.0.0.1:9440/stubby-tm-viewer-ping. " +
          "(4) If ping shows :3919 broken: curl -sS -X POST http://127.0.0.1:3919/api/tm-viewer/send-mail -H 'Content-Type: application/json' -d '{}' → JSON; fix tm.bz vs parent tm_viewer_link_registry. " +
          "nginx in front of :9440 can also return plain 404 before stubby. See tried_urls.";
        const fixGenericStubby =
          "Upstream returned non-JSON but base/URL looks like stubby :9440. Set STUBBY_TM_VIEWER_PROXY=1, restart stubby; see tm_viewer_proxy.log. Then curl POST http://127.0.0.1:3919/api/tm-viewer/send-mail … must return JSON if the proxy is up but mail still fails.";
        const fixGenericOther =
          "Upstream returned non-JSON. Check tm_viewer_proxy.log on the VPS (if stubby). curl -sS -X POST http://127.0.0.1:3919/api/tm-viewer/send-mail -H 'Content-Type: application/json' -d '{}' must return JSON when the registry is the failure point.";
        const fixGeneric = stubbyish ? fixGenericStubby : fixGenericOther;
        const errBody = JSON.stringify({
          ok: false,
          error: "upstream_bad_response",
          upstream_http_status: r.status,
          upstream_preview: preview,
          upstream_last: lastTriedUrl,
          upstream_base: base,
          tried_urls: triedUrls,
          stubby_registry_url: sh["X-TM-Stubby-Upstream-Full-Url"] || undefined,
          stubby_log_file: sh["X-TM-Stubby-Log-File"] || undefined,
          fix: plain404 ? fixPlain404 : fixGeneric,
        });
        res.writeHead(502, {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-store",
          "Content-Length": Buffer.byteLength(errBody),
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Expose-Headers":
            "X-TM-Upstream-Last, X-TM-Upstream-Base, X-TM-Handler, X-TM-Debug-Where, " + _STUBBY_EXPOSE,
          "X-TM-Upstream-Base": base,
          "X-TM-Upstream-Last": lastTriedUrl,
          ..._stubbyHeadersFromUpstream(r),
          ..._vercelDebugHdr(),
        });
        res.end(errBody);
        return;
      }
    }

    const passHdr = _vercelDebugOn()
      ? { "X-TM-Upstream-Base": base, "X-TM-Upstream-Last": lastTriedUrl, ..._vercelDebugHdr() }
      : {};
    res.writeHead(r.status, {
      "Content-Type": ct,
      "Cache-Control": "no-store",
      "Content-Length": Buffer.byteLength(text),
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Expose-Headers":
        "X-TM-Upstream-Last, X-TM-Upstream-Base, X-TM-Handler, X-TM-Debug-Where, " + _STUBBY_EXPOSE,
      ..._stubbyHeadersFromUpstream(r),
      ...passHdr,
    });
    res.end(text);
  } catch (e) {
    return writeJson(
      res,
      502,
      {
        ok: false,
        error: "upstream_unreachable",
        detail: (e && e.message) || String(e),
      },
      _vercelDebugHdr(),
    );
  }
};
