"use strict";

/** Vercel Node serverless uses http.ServerResponse — no res.status() / .json() / .send(). */

function writeJson(res, status, obj, extraHeaders) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Length": Buffer.byteLength(body),
    ...(extraHeaders || {}),
  });
  res.end(body);
}

function writeText(res, status, text, contentType) {
  const body = String(text);
  res.writeHead(status, {
    "Content-Type": contentType || "text/plain; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function writeBuffer(res, status, buf, extraHeaders) {
  const h = {
    "Cache-Control": "no-store",
    "Content-Length": String(buf.length),
    ...(extraHeaders || {}),
  };
  res.writeHead(status, h);
  res.end(buf);
}

function corsOptions(res, methods, allowHeaders, extraHeaders) {
  res.writeHead(204, {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": methods,
    "Access-Control-Allow-Headers": allowHeaders || "Content-Type",
    "Cache-Control": "no-store",
    ...(extraHeaders || {}),
  });
  res.end();
}

async function readRequestBody(req) {
  const chunks = [];
  for await (const ch of req) chunks.push(ch);
  return Buffer.concat(chunks);
}

module.exports = { writeJson, writeText, writeBuffer, corsOptions, readRequestBody };
