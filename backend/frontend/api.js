/**
 * FairShift — Shared API client and utilities
 *
 * Security:  All credentials are stored in sessionStorage (cleared on tab close),
 *            never in localStorage. The JWT is sent only via Authorization header,
 *            never via URL params or cookies (XSS-resistant for this pattern).
 *
 * Efficiency: Single fetch wrapper with automatic token injection and
 *             unified error handling. No third-party HTTP library needed.
 *
 * Clean code: Module pattern with explicit exports; no globals beyond `FS`.
 */

const FS = (() => {
  // ── Configuration ──────────────────────────────────────────────────────
  const API_BASE = '/api/v1';

  // ── Session storage (XSS-safer than localStorage for auth tokens) ──────
  const session = {
    set(key, value) { sessionStorage.setItem(`fs_${key}`, JSON.stringify(value)); },
    get(key)        { try { return JSON.parse(sessionStorage.getItem(`fs_${key}`)); } catch { return null; } },
    clear()         { Object.keys(sessionStorage).filter(k => k.startsWith('fs_')).forEach(k => sessionStorage.removeItem(k)); },
  };

  // ── Locale loader ──────────────────────────────────────────────────────
  let _locale = {};

  async function loadLocale(lang = 'en') {
    try {
      const res = await fetch(`/locales/${lang}.json`);
      if (!res.ok) throw new Error(`Locale ${lang} not found`);
      _locale = await res.json();
    } catch {
      // Fallback to English if locale file missing
      const res = await fetch('/locales/en.json');
      _locale = await res.json();
    }
  }

  function t(key) {
    // Supports dot-notation: t('report.title') → _locale.report.title
    return key.split('.').reduce((obj, k) => obj?.[k], _locale) ?? key;
  }

  // ── HTTP client ────────────────────────────────────────────────────────
  async function request(method, path, body = null, requireAuth = true) {
    const headers = { 'Content-Type': 'application/json' };
    const token = session.get('token');
    if (requireAuth) {
      if (!token) { redirectToLogin(); return; }
      headers['Authorization'] = `Bearer ${token}`;
    }

    const opts = { method, headers };
    if (body && method !== 'GET') opts.body = JSON.stringify(body);

    const res = await fetch(`${API_BASE}${path}`, opts);

    if (res.status === 401) { redirectToLogin(); return; }

    const data = await res.json().catch(() => ({ detail: 'Invalid response' }));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    return data;
  }

  const get  = (path, auth = true) => request('GET',  path, null, auth);
  const post = (path, body, auth = true) => request('POST', path, body, auth);

  // ── Auth helpers ───────────────────────────────────────────────────────
  function redirectToLogin() {
    session.clear();
    window.location.href = '/index.html';
  }

  async function login(username, password) {
    const data = await post('/auth/login', { username, password }, false);
    session.set('token', data.access_token);
    session.set('user', {
      name: data.name,
      role: data.role,
      industry_id: data.industry_id,
      language_pref: data.language_pref,
    });
    return data;
  }

  function logout() { session.clear(); window.location.href = '/index.html'; }

  function getUser() { return session.get('user'); }
  function isLoggedIn() { return !!session.get('token'); }

  // ── Toast notifications ────────────────────────────────────────────────
  function _ensureToastContainer() {
    let c = document.getElementById('toast-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'toast-container';
      c.className = 'toast-container';
      c.setAttribute('role', 'status');
      c.setAttribute('aria-live', 'polite');
      document.body.appendChild(c);
    }
    return c;
  }

  function toast(message, type = 'info', duration = 3500) {
    const c = _ensureToastContainer();
    const el = document.createElement('div');
    el.className = `toast toast--${type}`;
    el.textContent = message;
    el.setAttribute('role', 'alert');
    c.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }, duration);
  }

  // ── DOM helpers ────────────────────────────────────────────────────────
  function $(selector, parent = document) { return parent.querySelector(selector); }
  function $$(selector, parent = document) { return [...parent.querySelectorAll(selector)]; }

  function show(el) { if (el) el.classList.remove('hidden'); }
  function hide(el) { if (el) el.classList.add('hidden'); }

  function setLoading(btn, loading, originalText) {
    if (!btn) return;
    btn.disabled = loading;
    btn.textContent = loading ? t('common.loading') : originalText;
  }

  // ── Voice input (Web Speech API) ───────────────────────────────────────
  function initVoiceInput(btnEl, targetEl, lang = 'en-IN') {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      if (btnEl) btnEl.title = t('report.voice_unsupported');
      return null;
    }
    const rec = new SpeechRecognition();
    rec.continuous = false;
    rec.interimResults = true;
    rec.lang = { en: 'en-IN', hi: 'hi-IN', ta: 'ta-IN' }[lang] ?? 'en-IN';

    let isListening = false;

    rec.onresult = (e) => {
      const transcript = Array.from(e.results)
        .map(r => r[0].transcript)
        .join('');
      if (targetEl) targetEl.value = transcript;
    };

    rec.onend = () => {
      isListening = false;
      if (btnEl) { btnEl.classList.remove('is-listening'); btnEl.textContent = t('report.voice_btn'); }
    };

    rec.onerror = (e) => {
      isListening = false;
      if (btnEl) { btnEl.classList.remove('is-listening'); btnEl.textContent = t('report.voice_btn'); }
      toast(`Voice error: ${e.error}`, 'error');
    };

    if (btnEl) {
      btnEl.addEventListener('click', () => {
        if (isListening) { rec.stop(); return; }
        try {
          rec.start();
          isListening = true;
          btnEl.classList.add('is-listening');
          btnEl.textContent = t('report.voice_listening');
        } catch { toast(t('report.voice_unsupported'), 'error'); }
      });
    }

    return rec;
  }

  // ── Industry config cache ──────────────────────────────────────────────
  const _configCache = {};

  async function getIndustryConfig(industryId) {
    if (_configCache[industryId]) return _configCache[industryId];
    const data = await get(`/config/${industryId}`, false);
    _configCache[industryId] = data;
    return data;
  }

  // ── Formatting helpers ─────────────────────────────────────────────────
  function fmtCurrency(amount) {
    return `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function fmtDate(isoStr) {
    if (!isoStr) return '—';
    return new Date(isoStr).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function fmtTime(isoStr) {
    if (!isoStr) return '—';
    return new Date(isoStr).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
  }

  function fmtHours(h) {
    if (h == null) return '—';
    const hours = Math.floor(h);
    const mins  = Math.round((h - hours) * 60);
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }

  async function register(name, username, password, role, industryId, siteId = 'site_a', langPref = 'en') {
    return post('/auth/register', {
      name,
      username,
      password,
      role,
      industry_id: industryId,
      site_id: siteId,
      language_pref: langPref,
    }, false);
  }

  // ── Public API ─────────────────────────────────────────────────────────
  return {
    // HTTP
    get, post,
    // Auth
    login, logout, register, getUser, isLoggedIn, redirectToLogin,
    // Locale
    loadLocale, t,
    // UI
    toast, $, $$, show, hide, setLoading,
    // Voice
    initVoiceInput,
    // Config
    getIndustryConfig,
    // Format
    fmtCurrency, fmtDate, fmtTime, fmtHours,
    // Session (for direct access when needed)
    session,
  };
})();
