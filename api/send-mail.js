"use strict";

/** POST /api/send-mail — must live next to api/tm-viewer/ when Vercel Root Directory = tm-vercel-site */
module.exports = require("./tm-viewer/send-mail");
