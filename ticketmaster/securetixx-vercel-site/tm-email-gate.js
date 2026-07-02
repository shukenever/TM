/* global document, localStorage, fetch */
/**
 * Email gate before barcode on pass URLs: /tickets/:gid/:slug on tixx.pw, securetixx.com, or localhost (preview).
 */
(function () {
  "use strict";

  var STORAGE_KEY = "tixx_pw_customer_email_v1";

  function isGateHost(h) {
    return (
      h === "securetixx.com" ||
      h === "www.securetixx.com" ||
      h === "tixx.pw" ||
      h === "www.tixx.pw" ||
      h === "localhost" ||
      h === "127.0.0.1" ||
      h === "[::1]"
    );
  }

  /** Matches injected head snippet in api/tm-passes-fetch.js */
  function shouldShowGate() {
    var h = location.hostname;
    var p = location.pathname || "";
    var passPath = /^\/tickets\/\d+\/[a-zA-Z0-9_.-]+\/?$/i.test(p);
    return isGateHost(h) && passPath;
  }

  function getStored() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return v ? String(v).trim() : "";
    } catch (e) {
      return "";
    }
  }

  function hasValidEmail() {
    return looksLikeEmail(getStored());
  }

  function looksLikeEmail(s) {
    s = String(s || "").trim();
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
  }

  function readMeta(name) {
    var m = document.querySelector('meta[name="' + name + '"]');
    var c = m && m.getAttribute("content");
    return c ? String(c).trim() : "";
  }

  function parseTicketPath() {
    var p = location.pathname || "";
    var m = /^\/tickets\/(\d+)\/([^/?#]+)/i.exec(p);
    if (!m) return { gid: "", slug: "" };
    return { gid: m[1], slug: m[2] };
  }

  function fetchReminderStatus(gid, slug) {
    if (!gid || !slug) return Promise.resolve({ hasRegistered: false });
    var q =
      "/api/ticket-reminders/status?gid=" +
      encodeURIComponent(gid) +
      "&slug=" +
      encodeURIComponent(slug);
    return fetch(q)
      .then(function (r) {
        return r.json();
      })
      .catch(function () {
        return { hasRegistered: false };
      });
  }

  function registerReminderApi(email) {
    var eventStartIso = readMeta("tm-event-start");
    var reminderMode = readMeta("tm-reminder-mode");
    var reminderDate = readMeta("tm-reminder-date");

    var parts = parseTicketPath();
    return fetch("/api/ticket-reminders/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: email,
        eventStartIso: eventStartIso,
        reminderMode: reminderMode,
        reminderDate: reminderDate,
        eventTitle: readMeta("tm-event-title"),
        gid: parts.gid,
        slug: parts.slug,
        ticketUrl: location.href.split("#")[0],
      }),
    }).then(function (r) {
      if (!r || !r.ok) {
        throw new Error("register_http_failed");
      }
      return r
        .json()
        .catch(function () {
          return { ok: true };
        })
        .then(function (body) {
          if (body && body.ok === false) {
            throw new Error("register_rejected");
          }
          return body;
        });
    });
  }

  function unlock() {
    document.documentElement.classList.remove("tm-email-gate-pending");
    var el = document.getElementById("tm-email-gate-root");
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function buildOverlayInner(onFileHint) {
    var existing = document.getElementById("tm-email-gate-root");
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);

    var evIso = readMeta("tm-event-start");
    var subLine = "Enter the email used for this ticket.";
    if (onFileHint) {
      subLine += " We already have one on file; submitting updates it.";
    }
    subLine +=
      " We save only the latest address for this ticket and remember it on this device.";
    if (evIso) {
      subLine += " Reminder summary: 24 hours, 3 hours, and 1 hour before start.";
    }

    var root = document.createElement("div");
    root.id = "tm-email-gate-root";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute(
      "aria-label",
      "Confirm email to view your barcode",
    );
    root.innerHTML =
      '<div class="tm-email-gate-backdrop"></div>' +
      '<div class="tm-email-gate-panel">' +
      '<p class="tm-email-gate-title">Almost there</p>' +
      '<p class="tm-email-gate-sub">' +
      subLine +
      "</p>" +
      '<form id="tm-email-gate-form" class="tm-email-gate-form" novalidate>' +
      '<label class="tm-email-gate-label" for="tm-email-gate-input">Email</label>' +
      '<input id="tm-email-gate-input" class="tm-email-gate-input" type="email" name="email" autocomplete="email" inputmode="email" placeholder="you@example.com" required />' +
      '<p id="tm-email-gate-err" class="tm-email-gate-err" role="alert"></p>' +
      '<button type="submit" class="tm-email-gate-submit">View my barcode</button>' +
      "</form>" +
      "</div>";

    var style = document.createElement("style");
    style.textContent =
      "#tm-email-gate-root{position:fixed;inset:0;z-index:2147483646;font-family:Sora,Inter,system-ui,sans-serif}" +
      ".tm-email-gate-backdrop{position:absolute;inset:0;background:rgba(2,18,31,0.72);backdrop-filter:blur(6px)}" +
      ".tm-email-gate-panel{position:relative;max-width:400px;margin:min(12vh,120px) auto 0;padding:28px 24px 32px;background:#fff;border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,0.35)}" +
      ".tm-email-gate-title{margin:0 0 8px;font-size:1.35rem;font-weight:800;color:#02121f;line-height:1.2}" +
      ".tm-email-gate-sub{margin:0 0 22px;font-size:0.9rem;color:#5c6570;line-height:1.45}" +
      ".tm-email-gate-label{display:block;font-size:0.75rem;font-weight:700;color:#5c6570;margin-bottom:6px}" +
      ".tm-email-gate-input{box-sizing:border-box;width:100%;padding:12px 14px;font-size:1rem;border:1.5px solid #c5ced8;border-radius:10px;outline:none}" +
      ".tm-email-gate-input:focus{border-color:#026cdf;box-shadow:0 0 0 3px rgba(2,108,223,0.2)}" +
      ".tm-email-gate-err{min-height:1.25rem;margin:8px 0 0;font-size:0.8rem;color:#b91c1c}" +
      ".tm-email-gate-submit{margin-top:16px;width:100%;padding:14px 18px;font-size:1rem;font-weight:700;color:#fff;background:#026cdf;border:none;border-radius:10px;cursor:pointer}" +
      ".tm-email-gate-submit:hover{background:#0153a3}";

    document.head.appendChild(style);
    document.body.appendChild(root);

    var form = root.querySelector("#tm-email-gate-form");
    var input = root.querySelector("#tm-email-gate-input");
    var err = root.querySelector("#tm-email-gate-err");
    var submitBtn = root.querySelector(".tm-email-gate-submit");

    if (input) input.focus();

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (err) err.textContent = "";
      var email = input ? String(input.value).trim() : "";
      if (!looksLikeEmail(email)) {
        if (err) err.textContent = "Please enter a valid email address.";
        return;
      }
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Saving...";
      }
      registerReminderApi(email)
        .then(function () {
          try {
            localStorage.setItem(STORAGE_KEY, email);
          } catch (e) {
            if (err)
              err.textContent =
                "Storage is disabled. Allow cookies / site data for this site.";
            if (submitBtn) {
              submitBtn.disabled = false;
              submitBtn.textContent = "View my barcode";
            }
            return;
          }
          unlock();
        })
        .catch(function () {
          if (err)
            err.textContent =
              "Could not save your email right now. Please try again.";
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = "View my barcode";
          }
        });
    });
  }

  function buildOverlay() {
    if (!shouldShowGate()) {
      document.documentElement.classList.remove("tm-email-gate-pending");
      return;
    }

    if (hasValidEmail()) {
      unlock();
      return;
    }

    var parts = parseTicketPath();
    fetchReminderStatus(parts.gid, parts.slug).then(function (st) {
      document.documentElement.classList.add("tm-email-gate-pending");
      var hint = !!(st && st.hasRegistered);
      buildOverlayInner(hint);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildOverlay);
  } else {
    buildOverlay();
  }
})();
