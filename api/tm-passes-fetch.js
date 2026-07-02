"use strict";

/**
 * Hybrid deploy: Vercel rewrites GET /tickets/:gid/:slug → this function, which pulls HTML from your VPS(es).
 * Uses raw Node res.writeHead/end (Vercel Node functions are not Express — no res.status().send()).
 *
 * Env:
 *   TM_PASSES_STATIC_URL — required: one origin or comma-separated list, e.g. http://YOUR_VPS:3919 (no trailing slash).
 *   TM_PASSES_STATIC_URL_FALLBACKS — optional: extra comma-separated origins, tried after primary (still **your** hosts only).
 *
 * There is **no** built-in list of third-party VPS IPs. If an old deploy relied on that, set every origin explicitly
 * in TM_PASSES_STATIC_URL / FALLBACKS.
 *
 * After a direct miss, fetches /tm_viewer_pass_slug_aliases.json from each base and retries the mapped path
 * (stale slug → new file after tm_hit_viewer regenerate).
 *
 * Email gate (optional): HTML responses include tm-email-gate.js so viewers enter email once per browser (localStorage).
 * Disable with TM_EMAIL_GATE_DISABLE=1 on Vercel if you don't want the overlay on proxied passes.
 */

/** Gate on pass URLs (/tickets/:gid/:slug): tixx.pw prod + localhost loopback for slug preview stub. */
const EMAIL_GATE_HEAD_SNIPPET = `
<script>(function(){try{
var h=location.hostname,p=location.pathname||"";
var gateHost=h==="tixx.pw"||h==="www.tixx.pw"||h==="localhost"||h==="127.0.0.1"||h==="[::1]";
var passPath=/^\\/tickets\\/\\d+\\/[a-zA-Z0-9_.-]+\\/?$/i.test(p);
if(!gateHost||!passPath)return;
var k="tixx_pw_customer_email_v1",v=localStorage.getItem(k);
if(v&&/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(String(v).trim()))return;
document.documentElement.classList.add("tm-email-gate-pending");
}catch(e){var h=location.hostname,p=location.pathname||"";
var gateHost=h==="tixx.pw"||h==="www.tixx.pw"||h==="localhost"||h==="127.0.0.1"||h==="[::1]";
if(gateHost&&/^\\/tickets\\/\\d+\\/[a-zA-Z0-9_.-]+\\/?$/i.test(p))
document.documentElement.classList.add("tm-email-gate-pending");}})();</script>
<style>.tm-email-gate-pending .safetix-slot,.tm-email-gate-pending .barcode-frame{visibility:hidden!important}</style>
`;

const EMAIL_GATE_BODY_SCRIPT =
  '<script src="/tm-email-gate.js" defer></script>\n';

function shouldInjectEmailGate() {
  const d = (process.env.TM_EMAIL_GATE_DISABLE || "").trim();
  return !/^(1|true|yes|on)$/i.test(d);
}

/** @param {Buffer} buf */
function injectEmailGate(buf) {
  let html = buf.toString("utf8");
  const hm = html.match(/<head[^>]*>/i);
  if (hm) {
    const end = hm.index + hm[0].length;
    html = html.slice(0, end) + EMAIL_GATE_HEAD_SNIPPET + html.slice(end);
  } else {
    html = EMAIL_GATE_HEAD_SNIPPET + html;
  }
  const lb = html.toLowerCase().lastIndexOf("</body>");
  if (lb !== -1) {
    html =
      html.slice(0, lb) + EMAIL_GATE_BODY_SCRIPT + html.slice(lb);
  } else {
    html += EMAIL_GATE_BODY_SCRIPT;
  }
  return Buffer.from(html, "utf8");
}

function sendText(res, status, body, extraHeaders) {
  const h = {
    "Content-Type": "text/plain; charset=utf-8",
    "Cache-Control": "no-store",
    ...(extraHeaders || {}),
  };
  res.writeHead(status, h);
  res.end(body);
}

/** @param {string} base */
function trimBase(base) {
  return (base || "").trim().replace(/\/+$/, "");
}

/**
 * Ordered unique bases: primary (+ commas) + FALLBACKS (+ commas). No hardcoded defaults.
 */
function collectStaticBases() {
  const primary = (process.env.TM_PASSES_STATIC_URL || "").trim();
  const fallbacks = (process.env.TM_PASSES_STATIC_URL_FALLBACKS || "").trim();
  const out = [];
  const seen = new Set();
  function addChunk(chunk) {
    if (!chunk) return;
    for (const p of chunk.split(",")) {
      const b = trimBase(p);
      if (b && !seen.has(b)) {
        seen.add(b);
        out.push(b);
      }
    }
  }
  addChunk(primary);
  addChunk(fallbacks);
  return out;
}

function buildPathAttempts(base, gid, slug) {
  const rel = `/tickets/${gid}/${slug}`;
  const attempts = [`${base}${rel}.html`, `${base}${rel}`];
  if (gid !== "0") {
    attempts.push(`${base}/tickets/0/${slug}.html`, `${base}/tickets/0/${slug}`);
  }
  return attempts;
}

function withAccessParam(url, access) {
  const a = (access || "").trim();
  if (!a) return url;
  const join = url.includes("?") ? "&" : "?";
  return `${url}${join}access=${encodeURIComponent(a)}`;
}

async function tryServeUrl(req, res, u) {
  const r = await fetch(u, {
    method: req.method,
    headers: { Accept: "text/html,application/xhtml+xml,*/*;q=0.8" },
    redirect: "follow",
  });
  if (!r.ok) return { ok: false, status: r.status };
  const ct = r.headers.get("content-type") || "text/html; charset=utf-8";
  if (req.method === "HEAD") {
    res.writeHead(200, {
      "Content-Type": ct,
      "Cache-Control": "no-store",
    });
    res.end();
    return { ok: true, status: 200 };
  }
  let buf = Buffer.from(await r.arrayBuffer());
  const ctLower = (ct || "").toLowerCase();
  if (
    shouldInjectEmailGate() &&
    ctLower.includes("text/html") &&
    buf.length > 0
  ) {
    try {
      buf = injectEmailGate(buf);
    } catch {
      /* keep original buf */
    }
  }
  res.writeHead(200, {
    "Content-Type": ct,
    "Cache-Control": "no-store",
    "Content-Length": String(buf.length),
  });
  res.end(buf);
  return { ok: true, status: 200 };
}

module.exports = async (req, res) => {
  try {
    if (req.method !== "GET" && req.method !== "HEAD") {
      return sendText(res, 405, "Method Not Allowed");
    }

    const bases = collectStaticBases();
    if (!bases.length) {
      return sendText(
        res,
        503,
        "Set TM_PASSES_STATIC_URL on Vercel (VPS origin(s) for ticket HTML). Optional: TM_PASSES_STATIC_URL_FALLBACKS for additional origins you control.",
      );
    }

    let gid = "";
    let slug = "";
    let access = "";
    try {
      const url = new URL(req.url || "/", "http://localhost");
      gid = (url.searchParams.get("gid") || "").trim();
      slug = (url.searchParams.get("slug") || "").trim();
      access = (url.searchParams.get("access") || "").trim();
    } catch {
      return sendText(res, 400, "Bad request");
    }

    if (!/^\d+$/.test(gid) || !/^[a-zA-Z0-9_.-]+$/.test(slug)) {
      return sendText(res, 400, "Bad path");
    }

    const allTried = [];
    let lastStatus = 502;
    let lastErr = "";

    for (const base of bases) {
      const attempts = buildPathAttempts(base, gid, slug).map((u) =>
        withAccessParam(u, access),
      );
      for (const u of attempts) {
        allTried.push(u);
        try {
          const got = await tryServeUrl(req, res, u);
          if (got.ok) return;
          lastStatus = got.status;
        } catch (e) {
          lastErr = (e && e.message) || String(e);
        }
      }
    }

    let aliasDiag = "aliases_json_not_fetched";
    const relFromAlias = { value: "" };

    for (const base of bases) {
      try {
        const aj = await fetch(`${base}/tm_viewer_pass_slug_aliases.json`, {
          headers: { Accept: "application/json" },
        });
        aliasDiag = `aliases_json_http_${aj.status}@${base.replace(/^https?:\/\//, "").slice(0, 24)}`;
        if (!aj.ok) continue;
        const j = await aj.json();
        const red = (j && j.redirects) || {};
        const relRaw = (typeof red[slug] === "string" && red[slug].trim()) || "";
        if (relRaw) {
          relFromAlias.value = relRaw.replace(/^\/+/, "");
          aliasDiag = `aliases_json_mapped_slug@${base.replace(/^https?:\/\//, "").slice(0, 24)}`;
          break;
        }
        aliasDiag = `aliases_json_ok_no_slug@${base.replace(/^https?:\/\//, "").slice(0, 24)}`;
      } catch (e) {
        aliasDiag = `aliases_json_fetch_err_${(e && e.message) || String(e)}`.slice(0, 120);
      }
    }

    if (relFromAlias.value) {
      const relNorm = relFromAlias.value;
      for (const base of bases) {
        const altUrls = [`${base}/${relNorm}`];
        if (!relNorm.toLowerCase().endsWith(".html")) {
          altUrls.push(`${base}/${relNorm}.html`);
        }
        for (const u0 of altUrls) {
          const u = withAccessParam(u0, access);
          allTried.push(u);
          try {
            const got = await tryServeUrl(req, res, u);
            if (got.ok) return;
            lastStatus = got.status;
          } catch (e) {
            lastErr = (e && e.message) || String(e);
          }
        }
      }
    }

    const tried = `${allTried.join(" | ")} | aliases (${aliasDiag})`;
    const msg = lastErr
      ? `Upstream unreachable: ${lastErr.slice(0, 200)} (tried: ${tried})`
      : `Pass HTML not found on VPS — upstream HTTP ${lastStatus}. Tried: ${tried}. ` +
        `Deploy latest tm_viewer_link_registry.py (serves /tm_viewer_pass_slug_aliases.json), run tm-generate once ` +
        `so old slugs map to new paths, or point TM_PASSES_STATIC_URL / TM_PASSES_STATIC_URL_FALLBACKS at the host ` +
        `that has TM_VIEWER_PASSES_STATIC_DIR + tm_viewer_transfer_state.json for this ticket.`;
    return sendText(res, lastStatus >= 400 ? lastStatus : 404, msg);
  } catch (e) {
    const msg = (e && e.message) || String(e);
    return sendText(res, 500, `tm-passes-fetch error: ${msg.slice(0, 300)}`);
  }
};
