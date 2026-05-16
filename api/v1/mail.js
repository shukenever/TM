"use strict";

/** POST /api/v1/mail — nested route (use when /api/send-mail 404s on Vercel). */
module.exports = require("../tm-viewer/send-mail");
