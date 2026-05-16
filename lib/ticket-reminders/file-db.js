"use strict";

const fs = require("fs/promises");
const path = require("path");

function defaultDbPath() {
  const custom = String(process.env.TM_REMINDER_FILE_DB || "").trim();
  if (custom) return custom;
  if (process.platform === "win32") {
    return "C:\\Users\\Administrator\\Desktop\\Stubhub\\stubhub\\tm.bz\\tm_reminder_db.json";
  }
  return path.resolve(process.cwd(), "tm_reminder_db.json");
}

function normalizeDb(raw) {
  const db = raw && typeof raw === "object" ? raw : {};
  db.subs = db.subs && typeof db.subs === "object" ? db.subs : {};
  db.refs = db.refs && typeof db.refs === "object" ? db.refs : {};
  return db;
}

async function loadReminderDb() {
  const filePath = defaultDbPath();
  try {
    const raw = await fs.readFile(filePath, "utf8");
    return { db: normalizeDb(JSON.parse(raw)), filePath };
  } catch {
    return { db: normalizeDb({}), filePath };
  }
}

async function saveReminderDb(filePath, db) {
  const normalized = normalizeDb(db);
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const tmp = `${filePath}.tmp`;
  await fs.writeFile(tmp, `${JSON.stringify(normalized, null, 2)}\n`, "utf8");
  await fs.rename(tmp, filePath);
}

function refKey(gid, slug) {
  return `${gid}:${slug}`;
}

function removeSub(db, subId) {
  if (!db || !subId) return;
  delete db.subs[subId];
  for (const k of Object.keys(db.refs)) {
    if (db.refs[k] === subId) delete db.refs[k];
  }
}

module.exports = {
  loadReminderDb,
  saveReminderDb,
  refKey,
  removeSub,
};

