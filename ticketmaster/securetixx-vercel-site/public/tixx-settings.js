/** Tixx account center — profile, orders, addresses, cards, preferences (local + API). */
(function () {
  var LOC_KEY = 'tixx_user_city';
  var REG_KEY = 'tixx_user_region';
  var DATE_KEY = 'tixx_default_date';
  var PROFILE_KEY = 'tixx_profile';
  var ADDR_KEY = 'tixx_addresses';
  var CARDS_KEY = 'tixx_cards';
  var ORDERS_KEY = 'tixx_orders_local';
  var PREFS_KEY = 'tixx_prefs';
  var TOKEN_KEY = 'tm_viewer_session_token';
  var EMAIL_KEY = 'tm_viewer_session_email';
  var activeTab = 'account';

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }
  function uid() { return 'id_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }

  function readJson(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  }
  function writeJson(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {}
  }

  function getCity() {
    try { return localStorage.getItem(LOC_KEY) || ''; } catch (e) { return ''; }
  }
  function getRegion() {
    try { return localStorage.getItem(REG_KEY) || ''; } catch (e) { return ''; }
  }
  function getDefaultDate() {
    try { return localStorage.getItem(DATE_KEY) || 'all'; } catch (e) { return 'all'; }
  }
  function getProfile() {
    return readJson(PROFILE_KEY, { firstName: '', lastName: '', phone: '' });
  }
  function getAddresses() { return readJson(ADDR_KEY, []); }
  function getCards() { return readJson(CARDS_KEY, []); }
  function getLocalOrders() { return readJson(ORDERS_KEY, []); }
  function getPrefs() { return readJson(PREFS_KEY, { emailUpdates: true }); }

  function authEmail() {
    try { return (localStorage.getItem(EMAIL_KEY) || sessionStorage.getItem(EMAIL_KEY) || '').trim(); } catch (e) { return ''; }
  }
  function authToken() {
    try { return (localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || '').trim(); } catch (e) { return ''; }
  }
  function apiBase() {
    try { return String(location.origin || '').replace(/\/+$/, ''); } catch (e) { return ''; }
  }

  function saveCity(city, region) {
    try {
      if (city) localStorage.setItem(LOC_KEY, city);
      else localStorage.removeItem(LOC_KEY);
      if (region) localStorage.setItem(REG_KEY, region);
      else localStorage.removeItem(REG_KEY);
    } catch (e) {}
    window.dispatchEvent(new CustomEvent('tixx:location', {
      detail: { city: city || '', region: region || '' }
    }));
    refreshLabels();
  }

  function fullName() {
    var p = getProfile();
    return [p.firstName, p.lastName].filter(Boolean).join(' ').trim();
  }

  function refreshLabels() {
    var city = getCity();
    var region = getRegion();
    var label = city ? city + (region ? ', ' + region : '') : 'Set location';
    var chip = el('loc-label');
    if (chip) chip.textContent = label;
    var homeLoc = el('home-loc');
    if (homeLoc && city && !homeLoc.value.trim()) homeLoc.value = city;
    var setLocDisplay = el('tixx-settings-loc-display');
    if (setLocDisplay) {
      setLocDisplay.textContent = city
        ? 'Showing events near ' + label
        : 'Optional — enter a city to personalize results';
    }
    var setLocInput = el('tixx-settings-loc-input');
    if (setLocInput && document.activeElement !== setLocInput) setLocInput.value = city;
    var setRegInput = el('tixx-settings-region-input');
    if (setRegInput && document.activeElement !== setRegInput) setRegInput.value = region;
    var setDate = el('tixx-settings-date');
    if (setDate) setDate.value = getDefaultDate();
    var emDisplay = el('tixx-settings-email-display');
    if (emDisplay) {
      var em = authEmail();
      emDisplay.textContent = em || 'Not signed in';
    }
    var p = getProfile();
    var fn = el('tixx-settings-first');
    var ln = el('tixx-settings-last');
    var ph = el('tixx-settings-phone');
    if (fn && document.activeElement !== fn) fn.value = p.firstName || '';
    if (ln && document.activeElement !== ln) ln.value = p.lastName || '';
    if (ph && document.activeElement !== ph) ph.value = p.phone || '';
    var prefEmail = el('tixx-settings-email-updates');
    if (prefEmail) prefEmail.checked = !!getPrefs().emailUpdates;
  }

  function setStatus(msg, isErr) {
    var st = el('tixx-settings-status');
    if (!st) return;
    st.textContent = msg || '';
    st.className = 'tixx-settings-status' + (isErr ? ' tixx-settings-status--err' : '');
  }

  function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll('.tixx-settings-tab').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.getAttribute('data-tab') === tab);
    });
    document.querySelectorAll('.tixx-settings-pane').forEach(function (pane) {
      pane.hidden = pane.getAttribute('data-pane') !== tab;
    });
    if (tab === 'orders') renderOrders();
    if (tab === 'addresses') renderAddresses();
    if (tab === 'cards') renderCards();
    setStatus('');
  }

  function renderOrders() {
    var host = el('tixx-settings-orders');
    if (!host) return;
    host.innerHTML = '<p class="tixx-settings-loading">Loading orders…</p>';
    var local = getLocalOrders();
    var tok = authToken();
    var base = apiBase();
    if (!tok || !base) {
      host.innerHTML = ordersHtml(local, !authEmail());
      return;
    }
    fetch(base + '/api/shop/orders?token=' + encodeURIComponent(tok), { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var remote = (data && data.ok && data.orders) ? data.orders : [];
        var merged = mergeOrders(remote, local);
        host.innerHTML = ordersHtml(merged, false);
      })
      .catch(function () {
        host.innerHTML = ordersHtml(local, false);
      });
  }

  function mergeOrders(remote, local) {
    var seen = {};
    var out = [];
    function add(o) {
      var k = (o.listing_id || '') + '|' + (o.at || '') + '|' + (o.event_name || '');
      if (seen[k]) return;
      seen[k] = true;
      out.push(o);
    }
    remote.forEach(add);
    local.forEach(add);
    out.sort(function (a, b) { return String(b.at || '').localeCompare(String(a.at || '')); });
    return out;
  }

  function ordersHtml(list, needSignIn) {
    if (needSignIn && !list.length) {
      return '<p class="tixx-settings-empty">Sign in to sync order history from your account. ' +
        '<a href="/login">Sign in</a></p>';
    }
    if (!list.length) {
      return '<p class="tixx-settings-empty">No orders yet. Browse the <a href="/shop.html">shop</a> to get started.</p>';
    }
    return '<ul class="tixx-settings-list">' + list.map(function (o) {
      var price = o.price_usd != null ? '$' + Number(o.price_usd).toFixed(2) : '';
      var when = (o.at || '').slice(0, 10) || '—';
      var link = o.link
        ? '<a class="tixx-settings-order-link" href="' + esc(o.link) + '">View ticket</a>'
        : '';
      return '<li class="tixx-settings-order">' +
        '<div class="tixx-settings-order-main">' +
        '<strong>' + esc(o.event_name || 'Event') + '</strong>' +
        '<span class="tixx-settings-order-meta">' + esc(when) + (price ? ' · ' + esc(price) : '') + '</span></div>' +
        link + '</li>';
    }).join('') + '</ul>';
  }

  function renderAddresses() {
    var host = el('tixx-settings-addresses');
    if (!host) return;
    var list = getAddresses();
    if (!list.length) {
      host.innerHTML = '<p class="tixx-settings-empty">No saved addresses.</p>';
      return;
    }
    host.innerHTML = '<ul class="tixx-settings-list">' + list.map(function (a) {
      var def = a.isDefault ? ' <span class="tixx-settings-tag">Default</span>' : '';
      return '<li class="tixx-settings-card-item">' +
        '<div><strong>' + esc(a.label || 'Address') + def + '</strong>' +
        '<p class="tixx-settings-item-meta">' + esc(a.line1) +
        (a.line2 ? ', ' + esc(a.line2) : '') + '<br/>' +
        esc([a.city, a.state, a.zip].filter(Boolean).join(', ')) + '</p></div>' +
        '<button type="button" class="tixx-settings-icon-btn" data-rm-addr="' + esc(a.id) + '" title="Remove">×</button></li>';
    }).join('') + '</ul>';
    host.querySelectorAll('[data-rm-addr]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = btn.getAttribute('data-rm-addr');
        writeJson(ADDR_KEY, getAddresses().filter(function (x) { return x.id !== id; }));
        renderAddresses();
        setStatus('Address removed.');
      });
    });
  }

  function renderCards() {
    var host = el('tixx-settings-cards');
    if (!host) return;
    var list = getCards();
    if (!list.length) {
      host.innerHTML = '<p class="tixx-settings-empty">No saved payment methods.</p>';
      return;
    }
    host.innerHTML = '<ul class="tixx-settings-list">' + list.map(function (c) {
      var def = c.isDefault ? ' <span class="tixx-settings-tag">Default</span>' : '';
      return '<li class="tixx-settings-card-item">' +
        '<div><strong>' + esc(c.brand || 'Card') + ' ···· ' + esc(c.last4) + def + '</strong>' +
        '<p class="tixx-settings-item-meta">Exp ' + esc(String(c.expMonth || '').padStart(2, '0')) + '/' +
        esc(String(c.expYear || '').slice(-2)) + ' · ' + esc(c.name || '') + '</p></div>' +
        '<button type="button" class="tixx-settings-icon-btn" data-rm-card="' + esc(c.id) + '" title="Remove">×</button></li>';
    }).join('') + '</ul>';
    host.querySelectorAll('[data-rm-card]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = btn.getAttribute('data-rm-card');
        writeJson(CARDS_KEY, getCards().filter(function (x) { return x.id !== id; }));
        renderCards();
        setStatus('Card removed.');
      });
    });
  }

  function cardBrand(num) {
    var n = String(num || '').replace(/\D/g, '');
    if (/^4/.test(n)) return 'Visa';
    if (/^5[1-5]/.test(n)) return 'Mastercard';
    if (/^3[47]/.test(n)) return 'Amex';
    if (/^6/.test(n)) return 'Discover';
    return 'Card';
  }

  function buildAccountPayload() {
    var p = getProfile();
    return {
      profile: {
        firstName: p.firstName || '',
        lastName: p.lastName || '',
        phone: p.phone || '',
        city: getCity(),
        region: getRegion(),
        defaultDateFilter: getDefaultDate(),
        emailUpdates: getPrefs().emailUpdates !== false
      },
      addresses: getAddresses(),
      cards: getCards()
    };
  }

  async function pullAccountFromServer() {
    var tok = authToken();
    var base = apiBase();
    if (!tok || !base) return;
    try {
      var r = await fetch(base + '/api/shop/account?token=' + encodeURIComponent(tok), { cache: 'no-store' });
      var data = await r.json();
      if (!data.ok) return;
      if (data.profile) {
        writeJson(PROFILE_KEY, {
          firstName: data.profile.firstName || '',
          lastName: data.profile.lastName || '',
          phone: data.profile.phone || ''
        });
        if (data.profile.city || data.profile.region) {
          saveCity(data.profile.city || '', data.profile.region || '');
        }
        if (data.profile.defaultDateFilter) {
          try { localStorage.setItem(DATE_KEY, data.profile.defaultDateFilter); } catch (e) {}
        }
        writeJson(PREFS_KEY, { emailUpdates: data.profile.emailUpdates !== false });
      }
      if (Array.isArray(data.addresses)) writeJson(ADDR_KEY, data.addresses);
      if (Array.isArray(data.cards)) writeJson(CARDS_KEY, data.cards);
      refreshLabels();
    } catch (e) {}
  }

  async function pushAccountToServer() {
    var tok = authToken();
    var base = apiBase();
    if (!tok || !base) return false;
    try {
      var r = await fetch(base + '/api/shop/account?token=' + encodeURIComponent(tok), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildAccountPayload())
      });
      var data = await r.json();
      return !!(data && data.ok);
    } catch (e) {
      return false;
    }
  }

  function recordOrder(order) {
    if (!order || !order.event_name) return;
    var list = getLocalOrders();
    list.unshift({
      at: order.at || new Date().toISOString(),
      listing_id: order.listing_id || '',
      event_name: order.event_name,
      price_usd: order.price_usd,
      link: order.link || ''
    });
    if (list.length > 80) list = list.slice(0, 80);
    writeJson(ORDERS_KEY, list);
  }

  function openModal() {
    var m = el('tixx-settings-modal');
    if (!m) return;
    refreshLabels();
    pullAccountFromServer().finally(function () {
      refreshLabels();
      switchTab(activeTab || 'account');
    });
    m.hidden = false;
    document.body.style.overflow = 'hidden';
  }
  function closeModal() {
    var m = el('tixx-settings-modal');
    if (!m) return;
    m.hidden = true;
    document.body.style.overflow = '';
    setStatus('');
  }

  function injectModal() {
    if (el('tixx-settings-modal')) return;
    var wrap = document.createElement('div');
    wrap.innerHTML =
      '<div id="tixx-settings-modal" class="tixx-settings-modal" hidden role="dialog" aria-labelledby="tixx-settings-title">' +
      '<div class="tixx-settings-backdrop" data-close="1"></div>' +
      '<div class="tixx-settings-panel">' +
      '<div class="tixx-settings-head"><h2 id="tixx-settings-title">Account</h2>' +
      '<button type="button" class="tixx-settings-close" data-close="1" aria-label="Close">&times;</button></div>' +
      '<div class="tixx-settings-layout">' +
      '<nav class="tixx-settings-nav" aria-label="Account sections">' +
      '<button type="button" class="tixx-settings-tab is-active" data-tab="account">Profile</button>' +
      '<button type="button" class="tixx-settings-tab" data-tab="orders">Orders</button>' +
      '<button type="button" class="tixx-settings-tab" data-tab="addresses">Addresses</button>' +
      '<button type="button" class="tixx-settings-tab" data-tab="cards">Payment</button>' +
      '<button type="button" class="tixx-settings-tab" data-tab="preferences">Preferences</button>' +
      '</nav>' +
      '<div class="tixx-settings-body">' +

      '<div class="tixx-settings-pane" data-pane="account">' +
      '<h3 class="tixx-settings-pane-title">Profile &amp; name</h3>' +
      '<p class="tixx-settings-lead">Used at checkout and on your tickets. Stored on this device only.</p>' +
      '<div class="tixx-settings-field"><label for="tixx-settings-first">First name</label>' +
      '<input type="text" id="tixx-settings-first" autocomplete="given-name" placeholder="First name"/></div>' +
      '<div class="tixx-settings-field"><label for="tixx-settings-last">Last name</label>' +
      '<input type="text" id="tixx-settings-last" autocomplete="family-name" placeholder="Last name"/></div>' +
      '<div class="tixx-settings-field"><label for="tixx-settings-phone">Phone</label>' +
      '<input type="tel" id="tixx-settings-phone" autocomplete="tel" placeholder="Optional"/></div>' +
      '<div class="tixx-settings-field"><label>Email</label>' +
      '<p class="tixx-settings-readonly" id="tixx-settings-email-display">Not signed in</p>' +
      '<p class="tixx-settings-hint"><a href="/login">Sign in</a> to link orders and tickets to your email.</p></div>' +
      '<button type="button" class="tixx-settings-btn tixx-settings-btn--primary" id="tixx-settings-save-profile">Save profile</button>' +
      '</div>' +

      '<div class="tixx-settings-pane" data-pane="orders" hidden>' +
      '<h3 class="tixx-settings-pane-title">Order history</h3>' +
      '<p class="tixx-settings-lead">Purchases on Tixx. Signed-in users see orders tied to their email.</p>' +
      '<div id="tixx-settings-orders"></div></div>' +

      '<div class="tixx-settings-pane" data-pane="addresses" hidden>' +
      '<h3 class="tixx-settings-pane-title">Saved addresses</h3>' +
      '<div id="tixx-settings-addresses"></div>' +
      '<details class="tixx-settings-add-form"><summary>Add address</summary>' +
      '<div class="tixx-settings-field"><label>Label</label><input type="text" id="tixx-addr-label" placeholder="Home, Work…"/></div>' +
      '<div class="tixx-settings-field"><label>Street</label><input type="text" id="tixx-addr-line1" autocomplete="address-line1"/></div>' +
      '<div class="tixx-settings-field"><label>Apt / suite</label><input type="text" id="tixx-addr-line2" autocomplete="address-line2"/></div>' +
      '<div class="tixx-settings-row2">' +
      '<div class="tixx-settings-field"><label>City</label><input type="text" id="tixx-addr-city" autocomplete="address-level2"/></div>' +
      '<div class="tixx-settings-field"><label>State</label><input type="text" id="tixx-addr-state" autocomplete="address-level1"/></div></div>' +
      '<div class="tixx-settings-field"><label>ZIP</label><input type="text" id="tixx-addr-zip" autocomplete="postal-code"/></div>' +
      '<label class="tixx-settings-check"><input type="checkbox" id="tixx-addr-default"/> Default address</label>' +
      '<button type="button" class="tixx-settings-btn tixx-settings-btn--primary" id="tixx-addr-save">Save address</button>' +
      '</details></div>' +

      '<div class="tixx-settings-pane" data-pane="cards" hidden>' +
      '<h3 class="tixx-settings-pane-title">Payment methods</h3>' +
      '<p class="tixx-settings-lead">We only store the last 4 digits and expiry — never your full card number.</p>' +
      '<div id="tixx-settings-cards"></div>' +
      '<details class="tixx-settings-add-form"><summary>Add card</summary>' +
      '<div class="tixx-settings-field"><label>Name on card</label><input type="text" id="tixx-card-name" autocomplete="cc-name"/></div>' +
      '<div class="tixx-settings-field"><label>Card number</label><input type="text" id="tixx-card-num" inputmode="numeric" autocomplete="cc-number" placeholder="1234 5678 9012 3456" maxlength="19"/></div>' +
      '<div class="tixx-settings-row2">' +
      '<div class="tixx-settings-field"><label>Exp month</label><input type="text" id="tixx-card-mm" placeholder="MM" maxlength="2" inputmode="numeric"/></div>' +
      '<div class="tixx-settings-field"><label>Exp year</label><input type="text" id="tixx-card-yy" placeholder="YY" maxlength="4" inputmode="numeric"/></div></div>' +
      '<label class="tixx-settings-check"><input type="checkbox" id="tixx-card-default"/> Default payment method</label>' +
      '<button type="button" class="tixx-settings-btn tixx-settings-btn--primary" id="tixx-card-save">Save card</button>' +
      '</details></div>' +

      '<div class="tixx-settings-pane" data-pane="preferences" hidden>' +
      '<h3 class="tixx-settings-pane-title">Preferences</h3>' +
      '<p class="tixx-settings-lead tixx-settings-privacy">We never access GPS or device location. Enter a city below if you want localized event results — that&rsquo;s it.</p>' +
      '<div class="tixx-settings-field"><label for="tixx-settings-loc-input">Your city</label>' +
      '<input type="text" id="tixx-settings-loc-input" placeholder="e.g. Nashville" autocomplete="address-level2"/>' +
      '<p class="tixx-settings-hint" id="tixx-settings-loc-display">Optional</p></div>' +
      '<div class="tixx-settings-field"><label for="tixx-settings-region-input">State / region</label>' +
      '<input type="text" id="tixx-settings-region-input" placeholder="e.g. TN" autocomplete="address-level1"/></div>' +
      '<div class="tixx-settings-actions-row">' +
      '<button type="button" class="tixx-settings-btn tixx-settings-btn--primary" id="tixx-settings-save-loc">Save location</button>' +
      '<button type="button" class="tixx-settings-btn" id="tixx-settings-clear">Clear</button></div>' +
      '<div class="tixx-settings-field"><label for="tixx-settings-date">Default date filter</label>' +
      '<select id="tixx-settings-date"><option value="all">All dates</option><option value="week">Next 7 days</option>' +
      '<option value="month">Next 30 days</option><option value="future">Upcoming only</option></select></div>' +
      '<label class="tixx-settings-check"><input type="checkbox" id="tixx-settings-email-updates"/> Email me about order updates</label>' +
      '<div class="tixx-settings-links">' +
      '<a href="/shop.html">Shop</a> · <a href="/my-tickets">My tickets</a> · ' +
      '<a href="https://securetixx.com" target="_blank" rel="noopener noreferrer">Instagram</a></div>' +
      '</div>' +

      '</div></div>' +
      '<p id="tixx-settings-status" class="tixx-settings-status" role="status"></p>' +
      '</div></div>';
    document.body.appendChild(wrap.firstElementChild);

    document.querySelectorAll('[data-close="1"]').forEach(function (n) {
      n.addEventListener('click', closeModal);
    });
    document.querySelectorAll('.tixx-settings-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        switchTab(btn.getAttribute('data-tab'));
      });
    });

    el('tixx-settings-save-profile').addEventListener('click', function () {
      writeJson(PROFILE_KEY, {
        firstName: (el('tixx-settings-first').value || '').trim(),
        lastName: (el('tixx-settings-last').value || '').trim(),
        phone: (el('tixx-settings-phone').value || '').trim()
      });
      pushAccountToServer().then(function (ok) {
        setStatus(ok ? 'Profile saved to your account.' : 'Profile saved on this device.');
      });
    });

    el('tixx-settings-save-loc').addEventListener('click', function () {
      var city = (el('tixx-settings-loc-input').value || '').trim();
      var region = (el('tixx-settings-region-input').value || '').trim();
      saveCity(city, region);
      pushAccountToServer();
      setStatus(city ? 'Location preference saved.' : 'Location cleared.');
    });
    el('tixx-settings-clear').addEventListener('click', function () {
      saveCity('', '');
      if (el('tixx-settings-region-input')) el('tixx-settings-region-input').value = '';
      setStatus('Location cleared.');
    });
    el('tixx-settings-date').addEventListener('change', function () {
      try { localStorage.setItem(DATE_KEY, this.value); } catch (e) {}
      var homeDate = el('home-date');
      var shopDate = el('f-date');
      if (homeDate) homeDate.value = this.value;
      if (shopDate) shopDate.value = this.value;
      window.dispatchEvent(new CustomEvent('tixx:date', { detail: { date: this.value } }));
      setStatus('Date preference saved.');
    });
    el('tixx-settings-email-updates').addEventListener('change', function () {
      writeJson(PREFS_KEY, { emailUpdates: !!this.checked });
      setStatus('Preference saved.');
    });

    el('tixx-addr-save').addEventListener('click', function () {
      var line1 = (el('tixx-addr-line1').value || '').trim();
      if (!line1) { setStatus('Street address is required.', true); return; }
      var isDef = !!el('tixx-addr-default').checked;
      var list = getAddresses();
      if (isDef) list.forEach(function (a) { a.isDefault = false; });
      list.push({
        id: uid(),
        label: (el('tixx-addr-label').value || '').trim() || 'Address',
        line1: line1,
        line2: (el('tixx-addr-line2').value || '').trim(),
        city: (el('tixx-addr-city').value || '').trim(),
        state: (el('tixx-addr-state').value || '').trim(),
        zip: (el('tixx-addr-zip').value || '').trim(),
        isDefault: isDef
      });
      writeJson(ADDR_KEY, list);
      ['tixx-addr-label', 'tixx-addr-line1', 'tixx-addr-line2', 'tixx-addr-city', 'tixx-addr-state', 'tixx-addr-zip'].forEach(function (id) {
        var inp = el(id);
        if (inp) inp.value = '';
      });
      if (el('tixx-addr-default')) el('tixx-addr-default').checked = false;
      renderAddresses();
      pushAccountToServer();
      setStatus('Address saved.');
    });

    el('tixx-card-save').addEventListener('click', function () {
      var num = (el('tixx-card-num').value || '').replace(/\D/g, '');
      if (num.length < 13) { setStatus('Enter a valid card number.', true); return; }
      var last4 = num.slice(-4);
      var isDef = !!el('tixx-card-default').checked;
      var list = getCards();
      if (isDef) list.forEach(function (c) { c.isDefault = false; });
      list.push({
        id: uid(),
        brand: cardBrand(num),
        last4: last4,
        expMonth: (el('tixx-card-mm').value || '').trim(),
        expYear: (el('tixx-card-yy').value || '').trim(),
        name: (el('tixx-card-name').value || '').trim(),
        isDefault: isDef
      });
      writeJson(CARDS_KEY, list);
      ['tixx-card-name', 'tixx-card-num', 'tixx-card-mm', 'tixx-card-yy'].forEach(function (id) {
        var inp = el(id);
        if (inp) inp.value = '';
      });
      if (el('tixx-card-default')) el('tixx-card-default').checked = false;
      renderCards();
      pushAccountToServer();
      setStatus('Card saved (last 4 digits only).');
    });
  }

  function injectStyles() {
    if (document.getElementById('tixx-settings-css')) return;
    var s = document.createElement('style');
    s.id = 'tixx-settings-css';
    s.textContent =
      '.tixx-settings-btn-nav{background:transparent;border:1px solid rgba(255,255,255,.25);color:#fff;' +
      'border-radius:8px;padding:.4rem .55rem;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}' +
      '.tixx-settings-btn-nav:hover{background:rgba(255,255,255,.1)}' +
      '.tixx-settings-btn-nav svg{width:18px;height:18px}' +
      '.tixx-settings-modal{position:fixed;inset:0;z-index:200;display:flex;align-items:center;justify-content:center;padding:1rem}' +
      '.tixx-settings-modal[hidden]{display:none!important}' +
      '.tixx-settings-backdrop{position:absolute;inset:0;background:rgba(15,23,42,.55);backdrop-filter:blur(4px)}' +
      '.tixx-settings-panel{position:relative;background:#fff;border-radius:16px;max-width:720px;width:100%;' +
      'max-height:min(90vh,720px);overflow:hidden;display:flex;flex-direction:column;box-shadow:0 24px 60px rgba(0,0,0,.22)}' +
      '.tixx-settings-head{display:flex;align-items:center;justify-content:space-between;padding:1.1rem 1.25rem;border-bottom:1px solid #e2e8f0;flex-shrink:0}' +
      '.tixx-settings-head h2{margin:0;font-size:1.15rem;font-weight:800}' +
      '.tixx-settings-close{border:0;background:#f1f5f9;width:32px;height:32px;border-radius:8px;font-size:1.25rem;cursor:pointer}' +
      '.tixx-settings-layout{display:flex;min-height:0;flex:1;overflow:hidden}' +
      '.tixx-settings-nav{display:flex;flex-direction:column;gap:.15rem;padding:.75rem;border-right:1px solid #e2e8f0;min-width:128px;background:#f8fafc;flex-shrink:0}' +
      '.tixx-settings-tab{border:0;background:transparent;text-align:left;padding:.55rem .75rem;border-radius:8px;' +
      'font:inherit;font-size:.8125rem;font-weight:600;color:#475569;cursor:pointer}' +
      '.tixx-settings-tab:hover{background:#e2e8f0;color:#0f172a}' +
      '.tixx-settings-tab.is-active{background:#fff;color:#059669;box-shadow:0 1px 4px rgba(0,0,0,.06)}' +
      '.tixx-settings-body{flex:1;overflow-y:auto;padding:1.1rem 1.25rem 1.25rem}' +
      '.tixx-settings-pane-title{margin:0 0 .35rem;font-size:1rem;font-weight:800;color:#0f172a}' +
      '.tixx-settings-lead{font-size:.8125rem;color:#64748b;line-height:1.45;margin:0 0 1rem}' +
      '.tixx-settings-privacy{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:.65rem .75rem;color:#166534}' +
      '.tixx-settings-field{margin-bottom:.85rem}' +
      '.tixx-settings-field label{display:block;font-size:.8125rem;font-weight:600;margin-bottom:.35rem;color:#334155}' +
      '.tixx-settings-field input,.tixx-settings-field select{width:100%;padding:.6rem .75rem;border:1px solid #e2e8f0;border-radius:8px;font:inherit;box-sizing:border-box}' +
      '.tixx-settings-readonly{margin:0;font-size:.875rem;font-weight:600;color:#0f172a}' +
      '.tixx-settings-hint{font-size:.75rem;color:#94a3b8;margin:.35rem 0 0}' +
      '.tixx-settings-hint a{color:#059669;font-weight:600}' +
      '.tixx-settings-row2{display:grid;grid-template-columns:1fr 1fr;gap:.65rem}' +
      '.tixx-settings-actions-row{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}' +
      '.tixx-settings-btn{border:1px solid #e2e8f0;background:#fff;border-radius:8px;padding:.5rem .85rem;font:inherit;font-weight:600;cursor:pointer;font-size:.8125rem}' +
      '.tixx-settings-btn--primary{background:#059669;color:#fff;border-color:#059669}' +
      '.tixx-settings-check{display:flex;align-items:center;gap:.5rem;font-size:.8125rem;margin:.75rem 0;cursor:pointer}' +
      '.tixx-settings-links{font-size:.8125rem;margin-top:1rem;padding-top:.75rem;border-top:1px solid #e2e8f0}' +
      '.tixx-settings-links a{color:#059669;text-decoration:none;font-weight:600}' +
      '.tixx-settings-status{font-size:.8125rem;color:#059669;min-height:1.2em;margin:0;padding:.65rem 1.25rem;border-top:1px solid #e2e8f0;flex-shrink:0}' +
      '.tixx-settings-status--err{color:#dc2626}' +
      '.tixx-settings-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.5rem}' +
      '.tixx-settings-order,.tixx-settings-card-item{display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem;' +
      'padding:.75rem;border:1px solid #e2e8f0;border-radius:10px;background:#fafbfc}' +
      '.tixx-settings-order-main{display:flex;flex-direction:column;gap:.2rem}' +
      '.tixx-settings-order-meta{font-size:.75rem;color:#64748b;font-weight:500}' +
      '.tixx-settings-order-link{font-size:.75rem;font-weight:700;color:#059669;text-decoration:none;white-space:nowrap}' +
      '.tixx-settings-item-meta{font-size:.75rem;color:#64748b;margin:.25rem 0 0;line-height:1.4}' +
      '.tixx-settings-tag{font-size:.625rem;font-weight:800;text-transform:uppercase;color:#059669;background:rgba(5,150,105,.12);padding:.1rem .35rem;border-radius:4px;margin-left:.25rem}' +
      '.tixx-settings-icon-btn{border:0;background:#fee2e2;color:#b91c1c;width:28px;height:28px;border-radius:6px;cursor:pointer;font-size:1.1rem;line-height:1;flex-shrink:0}' +
      '.tixx-settings-empty{font-size:.8125rem;color:#64748b;margin:0}' +
      '.tixx-settings-empty a{color:#059669;font-weight:600}' +
      '.tixx-settings-loading{font-size:.8125rem;color:#94a3b8;margin:0}' +
      '.tixx-settings-add-form{margin-top:1rem;border:1px dashed #cbd5e1;border-radius:10px;padding:.65rem .85rem}' +
      '.tixx-settings-add-form summary{cursor:pointer;font-weight:700;font-size:.8125rem;color:#059669}' +
      '.tixx-settings-add-form[open]{padding-bottom:1rem}' +
      '@media(max-width:640px){.tixx-settings-layout{flex-direction:column}.tixx-settings-nav{flex-direction:row;flex-wrap:wrap;border-right:0;border-bottom:1px solid #e2e8f0;min-width:0}.tixx-settings-panel{max-height:92vh}}';
    document.head.appendChild(s);
  }

  /** No-op — we never request GPS (privacy). Kept for older shop code paths. */
  function detectLocation() {}

  window.TixxSettings = {
    getCity: getCity,
    getRegion: getRegion,
    getDefaultDate: getDefaultDate,
    getProfile: getProfile,
    getFullName: fullName,
    getDefaultAddress: function () {
      var list = getAddresses();
      return list.find(function (a) { return a.isDefault; }) || list[0] || null;
    },
    getDefaultCard: function () {
      var list = getCards();
      return list.find(function (c) { return c.isDefault; }) || list[0] || null;
    },
    saveCity: saveCity,
    detectLocation: detectLocation,
    recordOrder: recordOrder,
    open: openModal,
    refresh: refreshLabels
  };

  function init() {
    injectStyles();
    injectModal();
    refreshLabels();
    document.querySelectorAll('[data-tixx-settings]').forEach(function (b) {
      b.addEventListener('click', function (e) {
        e.preventDefault();
        openModal();
      });
    });
    var homeDate = el('home-date');
    if (homeDate) homeDate.value = getDefaultDate();
    var city = getCity();
    if (city) {
      var homeLoc = el('home-loc');
      if (homeLoc && !homeLoc.value.trim()) homeLoc.value = city;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
