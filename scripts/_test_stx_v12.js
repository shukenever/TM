"use strict";
const fs = require("fs");
const { applySecureTixxPassBranding } = require("../lib/tm-viewer/securetixx-pass-branding");

let html = fs.readFileSync(
  "_test_sg_gen/site/tickets/0/6OOVgqx4YbUhJ2ibeUio.html",
  "utf8",
);
html = html.replace(
  "</header>",
  '</header><div class="tm-arrival-warning" role="alert"><span class="tm-arrival-warning__icon">!</span><div><span class="tm-arrival-warning__title">Warn</span><div class="tm-arrival-warning__body">Body</div></div></div>',
);
html = html.replace(
  '<div class="tm-pass-rail"',
  '<div class="tm-pass-brand-strip"><img src="x" alt=""/></div><div class="tm-pass-rail"',
);
html = html.replace("tm-pass-visual", "tm-pass-visual tm-pass-visual--overlay");

const out = applySecureTixxPassBranding(html);
console.log("no warn", !out.includes("tm-arrival-warning"));
console.log("bc row", out.includes("stx-bc-row"));
console.log("meta", out.includes("stx-meta-grid"));
console.log("gate", out.includes("stx-entry-gate"));
console.log("foot", out.includes("Unauthorized duplication"));
console.log("v12", out.includes("v=12"));
