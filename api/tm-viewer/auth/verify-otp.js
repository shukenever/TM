"use strict";

const handler = require("../../../lib/tm-viewer/routes/auth-verify-otp");

module.exports = async (req, res) => {
  return handler(req, res);
};
