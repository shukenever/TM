(function (global) {
  "use strict";

  var STORAGE_KEY = "stx_theme";

  var MOON_SVG =
    '<svg class="stx-theme-icon stx-theme-icon--moon" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<path d="M21 14.5A8.5 8.5 0 0 1 9.5 3 7 7 0 1 0 21 14.5Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>';
  var SUN_SVG =
    '<svg class="stx-theme-icon stx-theme-icon--sun" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2"/>' +
    '<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';

  var docEl = document.documentElement;

  function readStored() {
    try {
      var value = localStorage.getItem(STORAGE_KEY);
      return value === "dark" || value === "light" ? value : null;
    } catch (e) {
      return null;
    }
  }

  function syncToggleButton(theme) {
    var btn = document.querySelector(".stx-theme-toggle");
    if (!btn) return;
    btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    btn.setAttribute(
      "aria-label",
      theme === "dark" ? "Switch to light mode" : "Switch to dark mode",
    );
  }

  function syncMetaThemeColor(theme) {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) return;
    meta.setAttribute("content", theme === "dark" ? "#000a05" : "#047857");
  }

  function applyTheme(theme, persist) {
    var next = theme === "dark" ? "dark" : "light";
    docEl.setAttribute("data-stx-theme", next);
    docEl.style.colorScheme = next;
    syncMetaThemeColor(next);
    syncToggleButton(next);
    if (persist !== false) {
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (e) {}
    }
  }

  function toggleTheme() {
    var current = docEl.getAttribute("data-stx-theme") || "light";
    applyTheme(current === "dark" ? "light" : "dark");
  }

  function injectToggle() {
    if (document.querySelector(".stx-theme-toggle")) return;
    var inner = document.querySelector(".stx-header-inner");
    if (!inner) return;
    var slot = inner.querySelector(".stx-header-actions");
    if (!slot) {
      slot = document.createElement("div");
      slot.className = "stx-header-actions";
      inner.appendChild(slot);
    }
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "stx-theme-toggle";
    btn.innerHTML = MOON_SVG + SUN_SVG;
    btn.addEventListener("click", toggleTheme);
    slot.insertBefore(btn, slot.firstChild);
    syncToggleButton(docEl.getAttribute("data-stx-theme") || "light");
  }

  function boot() {
    var stored = readStored();
    if (stored) applyTheme(stored, false);
    injectToggle();
  }

  var storedEarly = readStored();
  if (storedEarly) {
    docEl.setAttribute("data-stx-theme", storedEarly);
    docEl.style.colorScheme = storedEarly;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  global.StxTheme = { apply: applyTheme, toggle: toggleTheme };
})(window);
