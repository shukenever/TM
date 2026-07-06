"use strict";

const { makeAuthUpstreamProxy } = require("./auth-upstream-proxy");

module.exports = makeAuthUpstreamProxy("/api/tm-viewer/auth/forgot-password");
