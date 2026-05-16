"use strict";

const handler = require("../../../lib/tm-viewer/routes/auth-send-otp");

module.exports = async (req, res) => {
  return handler(req, res);
};
