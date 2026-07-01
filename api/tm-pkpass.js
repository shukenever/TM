"use strict";

/**
 * GET /api/tm-pkpass?p=<base64url(json)>&s=<hex hmac-sha256(secret,p)>
 *
 * Returns a signed **.pkpass** (Apple Wallet) for the ticket. The pass encodes a **QR / barcode
 * message** = your **HTTPS pass page URL** (`TM_WALLET_PASS_PUBLIC_ORIGIN/tickets/{gid}/{slug}`) so
 * Wallet opens the live rotating SafeTix page. Apple does not run your PDF417 script inside Wallet
 * without PassKit Web Service + push updates.
 *
 * Vercel env (Sensitive where noted):
 *   TM_WALLET_PKPASS_SECRET — same as TM_VIEWER_WALLET_PKPASS_SECRET at generate time (HMAC).
 *   TM_WALLET_PASS_PUBLIC_ORIGIN — https://your.domain (no trailing slash); must match pass links.
 *   TM_WALLET_PASS_TYPE_ID — e.g. pass.com.yourcompany.tickets
 *   TM_WALLET_TEAM_ID — Apple 10-char team ID
 *   TM_WALLET_ORG_NAME — shown on pass (optional, default "Tickets")
 *   TM_WALLET_APPLE_WWDR_PEM_BASE64 — WWDR G4 cert PEM, base64 (or paste multiline in TM_WALLET_APPLE_WWDR_PEM)
 *   TM_WALLET_APPLE_SIGNER_P12_BASE64 — Pass Type ID .p12, base64
 *   TM_WALLET_APPLE_SIGNER_P12_PASSWORD — p12 password
 *
 * If ``TM_WALLET_PKPASS_SECRET`` / ``TM_WALLET_PASS_PUBLIC_ORIGIN`` are unset, **TM_WALLET_FALLBACK_*** below
 * is used (must match ``_TM_VIEWER_WALLET_HARDCODE_*`` in tm_hit_viewer.py). Edit both files if you change domain/secret.
 */

/** @see tm_hit_viewer.py _TM_VIEWER_WALLET_HARDCODE_* */
const TM_WALLET_FALLBACK_PKPASS_SECRET =
  "8vItCsvoKLVgPiOmWk_dAQNgD3GZhpi-XJZKPX1Oi9bCKvDeeznimUWAQop9Tx-s";
const TM_WALLET_FALLBACK_PASS_PUBLIC_ORIGIN = "https://securetixx.com"; 

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const forge = require("node-forge");
const { PKPass } = require("passkit-generator");

const ASSETS_DIR = path.join(__dirname, "..", "wallet-pass-assets");

let _certCache = null;

function sendText(res, status, body) {
  res.writeHead(status, {
    "Content-Type": "text/plain; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function loadPemFromEnv() {
  const raw = (process.env.TM_WALLET_APPLE_WWDR_PEM || "").trim();
  if (raw) return raw;
  const b64 = (process.env.TM_WALLET_APPLE_WWDR_PEM_BASE64 || "").trim();
  if (!b64) return "";
  return Buffer.from(b64, "base64").toString("utf-8");
}

function p12ToSigner(p12Base64, password) {
  const der = forge.util.createBuffer(Buffer.from(p12Base64, "base64").toString("binary"));
  const asn1 = forge.asn1.fromDer(der);
  const p12 = forge.pkcs12.pkcs12FromAsn1(asn1, false, password || "");
  const certBags = p12.getBags({ bagType: forge.pki.oids.certBag })[forge.pki.oids.certBag];
  if (!certBags || !certBags[0] || !certBags[0].cert) {
    throw new Error("p12: no certificate");
  }
  const cert = certBags[0].cert;
  let key = null;
  const shrouded = p12.getBags({ bagType: forge.pki.oids.pkcs8ShroudedKeyBag })[
    forge.pki.oids.pkcs8ShroudedKeyBag
  ];
  if (shrouded && shrouded[0] && shrouded[0].key) key = shrouded[0].key;
  if (!key) {
    const plain = p12.getBags({ bagType: forge.pki.oids.keyBag })[forge.pki.oids.keyBag];
    if (plain && plain[0] && plain[0].key) key = plain[0].key;
  }
  if (!key) throw new Error("p12: no private key");
  return {
    signerCert: forge.pki.certificateToPem(cert),
    signerKey: forge.pki.privateKeyToPem(key),
  };
}

function getCertificates() {
  if (_certCache) return _certCache;
  const wwdr = loadPemFromEnv();
  const p12b64 = (process.env.TM_WALLET_APPLE_SIGNER_P12_BASE64 || "").trim().replace(/\s/g, "");
  const p12pass = process.env.TM_WALLET_APPLE_SIGNER_P12_PASSWORD || "";
  if (!wwdr || !p12b64) return null;
  const { signerCert, signerKey } = p12ToSigner(p12b64, p12pass);
  _certCache = {
    wwdr,
    signerCert,
    signerKey,
    signerKeyPassphrase: p12pass,
  };
  return _certCache;
}

function verifyPayload(pB64, sigHex, secret) {
  if (!pB64 || !sigHex || !secret) return false;
  const expect = crypto.createHmac("sha256", secret).update(pB64, "utf8").digest("hex");
  try {
    const a = Buffer.from(expect, "hex");
    const b = Buffer.from(String(sigHex).trim(), "hex");
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

function decodePayload(pB64) {
  let pad = pB64.length % 4;
  let s = pB64.replace(/-/g, "+").replace(/_/g, "/");
  if (pad) s += "=".repeat(4 - pad);
  const json = Buffer.from(s, "base64").toString("utf-8");
  return JSON.parse(json);
}

function readAsset(name) {
  return fs.readFileSync(path.join(ASSETS_DIR, name));
}

module.exports = async (req, res) => {
  try {
    if (req.method !== "GET" && req.method !== "HEAD") {
      return sendText(res, 405, "Method Not Allowed");
    }

    const secret = (
      process.env.TM_WALLET_PKPASS_SECRET || TM_WALLET_FALLBACK_PKPASS_SECRET
    ).trim();
    const origin = (
      process.env.TM_WALLET_PASS_PUBLIC_ORIGIN || TM_WALLET_FALLBACK_PASS_PUBLIC_ORIGIN
    )
      .trim()
      .replace(/\/+$/, "");
    const passTypeId = (process.env.TM_WALLET_PASS_TYPE_ID || "").trim();
    const teamId = (process.env.TM_WALLET_TEAM_ID || "").trim();
    const orgName = (process.env.TM_WALLET_ORG_NAME || "Tickets").trim() || "Tickets";

    if (!secret || !origin || !passTypeId || !teamId) {
      return sendText(
        res,
        503,
        "Wallet pass not configured: set TM_WALLET_PKPASS_SECRET, TM_WALLET_PASS_PUBLIC_ORIGIN, TM_WALLET_PASS_TYPE_ID, TM_WALLET_TEAM_ID (+ Apple cert env vars).",
      );
    }

    const certs = getCertificates();
    if (!certs) {
      return sendText(
        res,
        503,
        "Missing Apple certs: TM_WALLET_APPLE_WWDR_PEM / _BASE64 and TM_WALLET_APPLE_SIGNER_P12_BASE64 (+ password).",
      );
    }

    let pB64 = "";
    let sigHex = "";
    try {
      const url = new URL(req.url || "/", "http://localhost");
      pB64 = (url.searchParams.get("p") || "").trim();
      sigHex = (url.searchParams.get("s") || "").trim();
    } catch {
      return sendText(res, 400, "Bad request");
    }

    if (!pB64 || !sigHex || !verifyPayload(pB64, sigHex, secret)) {
      return sendText(res, 403, "Invalid or missing signature");
    }

    let payload;
    try {
      payload = decodePayload(pB64);
    } catch {
      return sendText(res, 400, "Invalid payload");
    }

    if (payload.v !== 1 || typeof payload.gid !== "number" || typeof payload.slug !== "string") {
      return sendText(res, 400, "Unsupported payload");
    }
    const slug = payload.slug.replace(/[^a-zA-Z0-9_.-]/g, "").slice(0, 200);
    if (!slug) return sendText(res, 400, "Bad slug");

    const passPageUrl = `${origin}/tickets/${payload.gid}/${slug}`;
    const ev = String(payload.ev || "Event").slice(0, 200);
    const sub = String(payload.sub || "").slice(0, 300);
    const sec = String(payload.sec || "—").slice(0, 64);
    const row = String(payload.row || "—").slice(0, 64);
    const seat = String(payload.seat || "—").slice(0, 64);

    const serialNumber = crypto
      .createHash("sha256")
      .update(`${pB64}|${sigHex}`)
      .digest("hex")
      .slice(0, 40);

    const passJson = {
      formatVersion: 1,
      passTypeIdentifier: passTypeId,
      teamIdentifier: teamId,
      organizationName: orgName,
      description: `Ticket — ${ev}`.slice(0, 120),
      foregroundColor: "rgb(255,255,255)",
      backgroundColor: "rgb(2,108,223)",
      labelColor: "rgb(230,240,255)",
      eventTicket: {
        primaryFields: [],
        secondaryFields: [],
        auxiliaryFields: [],
        backFields: [],
      },
    };

    const buffers = {
      "pass.json": Buffer.from(JSON.stringify(passJson), "utf-8"),
      "icon.png": readAsset("icon.png"),
      "icon@2x.png": readAsset("icon@2x.png"),
      "icon@3x.png": readAsset("icon@3x.png"),
      "logo.png": readAsset("logo.png"),
    };

    const pass = new PKPass(
      buffers,
      {
        wwdr: certs.wwdr,
        signerCert: certs.signerCert,
        signerKey: certs.signerKey,
        signerKeyPassphrase: certs.signerKeyPassphrase,
      },
      { serialNumber, description: passJson.description },
    );

    pass.primaryFields.push({ key: "event", label: "EVENT", value: ev });
    if (sub) {
      pass.secondaryFields.push({ key: "when", label: "WHEN / INFO", value: sub.slice(0, 120) });
    }
    pass.auxiliaryFields.push(
      { key: "section", label: "SECTION", value: sec },
      { key: "row", label: "ROW", value: row },
      { key: "seat", label: "SEAT", value: seat },
    );
    pass.backFields.push({
      key: "live",
      label: "Live SafeTix barcode",
      value: `Open this link on your iPhone for the rotating venue barcode (PDF417):\n${passPageUrl}`,
    });

    pass.setBarcodes(passPageUrl);

    if (req.method === "HEAD") {
      res.writeHead(200, {
        "Content-Type": "application/vnd.apple.pkpass",
        "Cache-Control": "no-store",
      });
      res.end();
      return;
    }

    const buf = pass.getAsBuffer();
    res.writeHead(200, {
      "Content-Type": "application/vnd.apple.pkpass",
      "Content-Disposition": 'attachment; filename="ticket.pkpass"',
      "Content-Length": String(buf.length),
      "Cache-Control": "no-store",
    });
    res.end(buf);
  } catch (e) {
    const msg = (e && e.message) || String(e);
    sendText(res, 500, `tm-pkpass: ${msg.slice(0, 280)}`);
  }
};
