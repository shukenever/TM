/**
 * Universal Tixx marketplace stock labels — homepage + shop carousels + event grids.
 */
(function (global) {
  'use strict';

  function formatStock(n) {
    var c = Number(n) || 0;
    if (c <= 0) return 'Sold out';
    return c === 1 ? '1 ticket left' : c + ' tickets left';
  }

  function formatStockShort(n) {
    var c = Number(n) || 0;
    if (c <= 0) return '0';
    return String(c);
  }

  function sectionMeta(tickets, events) {
    var t = Number(tickets) || 0;
    var e = Number(events) || 0;
    if (!t && !e) return '';
    var parts = [];
    if (t) parts.push(t + ' ticket' + (t === 1 ? '' : 's'));
    if (e) parts.push(e + ' event' + (e === 1 ? '' : 's'));
    return parts.join(' · ');
  }

  function sumTickets(eventGroups) {
    if (!eventGroups || !eventGroups.length) return 0;
    var total = 0;
    for (var i = 0; i < eventGroups.length; i++) {
      total += Number(eventGroups[i].count) || 0;
    }
    return total;
  }

  function cardFooterHtml(ev, esc, money) {
    var count = Number(ev.count) || (ev.listings ? ev.listings.length : 0) || 0;
    return '<p class="tixx-stock-row">' +
      '<span class="tixx-stock-pill">' + esc(formatStock(count)) + '</span>' +
      '<span class="tixx-stock-price">From ' + esc(money(ev.min_price)) + '</span></p>';
  }

  function updateSectionHead(sectionId, events) {
    var sec = document.getElementById(sectionId);
    if (!sec || !events || !events.length) return;
    var head = sec.querySelector('.home-section-head, .carousel-head');
    if (!head) return;
    var h2 = head.querySelector('h2');
    if (!h2) return;
    var base = h2.getAttribute('data-title-base') || h2.textContent.replace(/\s*·.*$/, '').trim();
    if (!h2.getAttribute('data-title-base')) h2.setAttribute('data-title-base', base);
    var meta = sectionMeta(sumTickets(events), events.length);
    h2.textContent = meta ? base + ' · ' + meta : base;
  }

  global.TixxStock = {
    formatStock: formatStock,
    formatStockShort: formatStockShort,
    sectionMeta: sectionMeta,
    sumTickets: sumTickets,
    cardFooterHtml: cardFooterHtml,
    updateSectionHead: updateSectionHead
  };
})(typeof window !== 'undefined' ? window : globalThis);
