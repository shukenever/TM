/** User-facing copy only — no backend paths, env vars, or internal error codes. */
(function (global) {
  'use strict';

  var MSG = {
    emptyEvents: 'Check back soon — new events are added regularly.',
    loadFail: 'Unable to load events right now. Please refresh or try again in a moment.',
    shopUnavailable: 'The shop is temporarily unavailable. Please try again shortly.',
    ticketsLoading: 'Loading tickets…',
    categoryEmpty: 'Nothing here yet — try another category or search below.',
    loginFail: 'Sign-in is temporarily unavailable. Please try again in a moment.',
    loginNetwork: 'Connection problem. Check your internet and try again.',
    purchaseFail: 'Purchase could not be completed. Please try again or contact support.'
  };

  function fromApi(data) {
    if (data && typeof data.message === 'string' && data.message.trim()) {
      return data.message.trim();
    }
    return MSG.loadFail;
  }

  global.TixxPublic = {
    MSG: MSG,
    fromApi: fromApi,
    shopError: function () { return MSG.shopUnavailable; },
    loginError: function (code) {
      var c = String(code || '').toLowerCase();
      if (c === 'rate_limit') return 'Please wait before requesting another code.';
      if (c === 'bad_code') return 'Incorrect code. Try again.';
      if (c === 'code_expired') return 'Code expired. Request a new one.';
      if (c === 'too_many_attempts') return 'Too many attempts. Request a new code.';
      if (c === 'send_failed') return 'Could not send email. Try again later.';
      if (c === 'invalid_credentials') return 'Incorrect email or password.';
      if (c === 'account_exists') return 'An account with this email already exists.';
      if (c === 'account_not_found') return 'No account found for that email.';
      if (c === 'password_too_short') return 'Password must be at least 6 characters.';
      return MSG.loginFail;
    }
  };
})(typeof window !== 'undefined' ? window : globalThis);
