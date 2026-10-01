// Shared helpers: DOM building (text is always set as text, never parsed as HTML), formatting, the API client,
// the live event stream, toasts, modals and drawers, and the mode badges.

export const S = { csrf: null, user: null, workspace: null, workspaces: [], overview: null, stream: null, listeners: {} };

export function on(evt, fn) { (S.listeners[evt] = S.listeners[evt] || []).push(fn); return () => off(evt, fn); }
export function off(evt, fn) { S.listeners[evt] = (S.listeners[evt] || []).filter(f => f !== fn); }
export function emit(evt, data) { for (const f of S.listeners[evt] || []) { try { f(data); } catch (e) { console.error(e); } } }

// h('div.panel#id', {onclick, title, ...}, children...)
export function h(tag, attrs, ...kids) {
  const m = /^([a-z0-9]+)?((?:[.#][\w-]+)*)$/i.exec(tag) || [];
  const el = document.createElement(m[1] || 'div');
  for (const part of (m[2] || '').match(/[.#][\w-]+/g) || []) {
    if (part[0] === '.') el.classList.add(part.slice(1)); else el.id = part.slice(1);
  }
  if (attrs !== null && attrs !== undefined && (typeof attrs !== 'object' || attrs instanceof Node || Array.isArray(attrs))) { kids.unshift(attrs); attrs = null; }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className += ' ' + v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k in el && k !== 'list' && k !== 'form') { try { el[k] = v; } catch { el.setAttribute(k, v); } }
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, kids);
  return el;
}
function append(el, kids) {
  for (const k of kids) {
    if (k === null || k === undefined || k === false) continue;
    if (Array.isArray(k)) append(el, k);
    else el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}
export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
export function replace(el, ...kids) { clear(el); append(el, kids); return el; }
export const $ = (sel, root = document) => root.querySelector(sel);

// ---------------------------------------------------------------- formatting
export function money(x, cur, dp = 2) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const v = Number(x);
  const s = Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
  return (v < 0 ? '-' : '') + s + (cur ? ' ' + cur : '');
}
export function signed(x, dp = 2) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const v = Number(x);
  return (v > 0 ? '+' : v < 0 ? '-' : '') + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
}
export function pct(x, dp = 2) { return x === null || x === undefined || Number.isNaN(x) ? '—' : `${Number(x).toFixed(dp)}%`; }
export function num(x, dp = 4) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const v = Number(x);
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Math.abs(v) >= 1) return v.toFixed(Math.min(dp, 4));
  return v.toPrecision(Math.max(2, dp));
}
export function r(x) { return x === null || x === undefined ? '—' : `${Number(x) >= 0 ? '+' : ''}${Number(x).toFixed(2)}R`; }
export function cls(x) { return x > 0 ? 'up' : x < 0 ? 'down' : ''; }
export function time(ms, withDate = false) {
  if (!ms) return '—';
  const d = new Date(ms);
  const t = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  return withDate ? `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${t}` : t;
}
export function ago(ms) {
  if (!ms) return 'never';
  const s = (Date.now() - ms) / 1000;
  if (s < 60) return `${Math.max(0, Math.round(s))}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

// ---------------------------------------------------------------- badges
export function modeBadge(mode) {
  const m = String(mode || '').toLowerCase();
  if (m === 'live') return h('span.badge.live', { title: 'LIVE: real money' }, 'LIVE');
  if (m === 'demo') return h('span.badge.demo', { title: 'DEMO: synthetic market, simulated money' }, 'DEMO');
  if (m === 'research') return h('span.badge.research', { title: 'Research fleet: simulated paper money' }, 'PAPER · RESEARCH');
  if (m === 'backtest') return h('span.badge.backtest', { title: 'Measured on history, not traded' }, 'BACKTEST');
  if (m === 'paper') return h('span.badge.paper', { title: 'PAPER: simulated money' }, 'PAPER');
  return h('span.badge.sim', m ? m.toUpperCase() : '—');
}
export function stateChip(state) {
  const s = String(state || 'stopped');
  return h(`span.state.${s.replace(/[^a-z_]/g, '')}`, h('span.dot' + (['managing_position', 'watching', 'evaluating'].includes(s) ? '.on' : s === 'error' ? '.bad' : ['paused', 'partially_filled', 'exiting', 'submitting'].includes(s) ? '.warn' : '')), s.replace(/_/g, ' '));
}

// ---------------------------------------------------------------- API
export class ApiError extends Error { constructor(status, msg, body) { super(msg); this.status = status; this.body = body; } }

export async function api(path, body, opts = {}) {
  const init = { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Jarvus': '1' }, credentials: 'same-origin' };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    if (S.csrf) init.headers['X-CSRF-Token'] = S.csrf;
    init.body = JSON.stringify(body);
  }
  let res;
  try { res = await fetch(path, init); } catch (e) { throw new ApiError(0, 'Jarvus is not reachable. Is the Jarvus window still open?'); }
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = { error: text.slice(0, 200) }; }
  if (res.status === 401 && !opts.allow401) { emit('signed-out'); throw new ApiError(401, 'signed out'); }
  if (!res.ok) throw new ApiError(res.status, (data && data.error) || `HTTP ${res.status}`, data);
  return data;
}

// ---------------------------------------------------------------- live stream (Server-Sent Events)
export function startStream() {
  stopStream();
  const es = new EventSource('/api/stream?severity=debug');
  S.stream = es;
  S.streamState = 'connecting';
  emit('stream-state', 'connecting');
  es.addEventListener('hello', () => { S.streamState = 'live'; emit('stream-state', 'live'); });
  es.addEventListener('audit', (e) => { try { emit('audit', JSON.parse(e.data)); } catch { /* ignore */ } });
  es.addEventListener('state', (e) => { try { const d = JSON.parse(e.data); S.live = d; emit('state', d); } catch { /* ignore */ } });
  es.onerror = () => { S.streamState = 'reconnecting'; emit('stream-state', 'reconnecting'); };
}
export function stopStream() { if (S.stream) { S.stream.close(); S.stream = null; } }

// ---------------------------------------------------------------- toasts, modals, drawers
export function toast(msg, kind = '') {
  const t = h(`div.toast${kind ? '.' + kind : ''}`, msg);
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), kind === 'bad' ? 9000 : 5000);
}
export function errorToast(e) { toast(e && e.message ? e.message : String(e), 'bad'); }

export function modal(title, body, { danger = false, onClose } = {}) {
  const ov = $('#overlay');
  const back = h('div.modal-back');
  const close = () => { back.remove(); box.remove(); document.removeEventListener('keydown', esc); if (onClose) onClose(); };
  const esc = (e) => { if (e.key === 'Escape') close(); };
  const box = h(`div.modal${danger ? '.danger' : ''}`, { role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    h('button.btn.ghost.small.xbtn', { onclick: close, 'aria-label': 'Close' }, '✕'), h('h2', title), body);
  back.addEventListener('click', close);
  document.addEventListener('keydown', esc);
  ov.append(back, box);
  const f = box.querySelector('input, select, textarea, button.btn:not(.xbtn)');
  if (f) setTimeout(() => f.focus(), 30);
  return { close, box };
}
export function drawer(title, body, { onClose } = {}) {
  const ov = $('#overlay');
  const back = h('div.drawer-back');
  const close = () => { back.remove(); box.remove(); document.removeEventListener('keydown', esc); if (onClose) onClose(); };
  const esc = (e) => { if (e.key === 'Escape') close(); };
  const box = h('div.drawer', { role: 'dialog', 'aria-label': title },
    h('button.btn.ghost.small.xbtn', { onclick: close, 'aria-label': 'Close' }, '✕'), h('h2', title), body);
  back.addEventListener('click', close);
  document.addEventListener('keydown', esc);
  ov.append(back, box);
  return { close, box };
}
export function confirmBox(title, text, { typed, danger = true, okLabel = 'Confirm' } = {}) {
  return new Promise((resolve) => {
    const inp = typed ? h('input', { placeholder: typed, autocomplete: 'off', spellcheck: false }) : null;
    let done = false;
    const ok = h(`button.btn${danger ? '.danger' : '.primary'}`, okLabel);
    const m = modal(title, h('div.stack', h('p', text), typed ? h('label.f', `Type ${typed} to confirm`, inp) : null,
      h('div.row', ok, h('button.btn.ghost', { onclick: () => m.close() }, 'Cancel'))), { danger, onClose: () => { if (!done) resolve(false); } });
    ok.addEventListener('click', () => {
      if (typed && inp.value.trim().toUpperCase() !== typed) { inp.focus(); toast(`Type exactly: ${typed}`, 'bad'); return; }
      done = true; m.close(); resolve(typed ? inp.value.trim() : true);
    });
  });
}

// checklist of readiness / test results
export function checklist(checks) {
  const icon = { pass: '✓', fail: '✕', warn: '!', waived: '~', skip: '·' };
  return h('ul.checks', (checks || []).map(c => h(`li.${c.status}`, h('span.i', icon[c.status] || '?'),
    h('div', h('div', c.label), c.detail ? h('div.d', c.detail) : null))));
}

export function kvList(pairs) {
  return h('div.kv', pairs.filter(Boolean).flatMap(([k, v, c]) => [h('span', k), h(`span${c ? '.' + c : ''}`, v)]));
}

export function table(cols, rows, { onRow, empty = 'Nothing yet.' } = {}) {
  if (!rows || !rows.length) return h('div.empty', empty);
  return h('div.tablewrap', h('table',
    h('thead', h('tr', cols.map(c => h(`th${c.n ? '.n' : ''}`, c.label)))),
    h('tbody', rows.map(row => h(`tr${onRow ? '.click' : ''}`, onRow ? { onclick: () => onRow(row) } : null,
      cols.map(c => { const v = c.v(row); return h(`td${c.n ? '.n' : ''}`, { class: c.cls ? c.cls(row) : null }, v); }))))));
}

export function debounce(fn, ms = 250) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ---------------------------------------------------------------- simulated balance (any simulated account, any time)
export function balanceDialog(acct, onDone) {
  const cur = acct.currency || 'USD';
  const amt = h('input', { type: 'number', min: '1', step: 'any', inputMode: 'decimal', value: String(Math.round(acct.equity || 100000)) });
  const kind = h('select', h('option', { value: 'set_balance' }, 'Set the balance to'), h('option', { value: 'deposit' }, 'Add'), h('option', { value: 'withdraw' }, 'Remove'));
  const preview = h('div.note');
  const warn = h('div.down');
  const upd = () => {
    const v = Number(amt.value), eq = Number(acct.equity || 0), inv = Number(acct.invested ?? acct.exposure ?? 0);
    warn.textContent = '';
    if (!(v > 0)) { preview.textContent = 'Enter an amount above 0.'; return; }
    const after = kind.value === 'set_balance' ? v : kind.value === 'deposit' ? eq + v : eq - v;
    preview.textContent = acct.equity === null || acct.equity === undefined ? `New balance: ${money(after, cur)}`
      : `Now ${money(eq, cur)} → after: ${money(after, cur)}`;
    if (inv > 0 && after < inv) warn.textContent = `Heads up: ${money(inv, cur)} is in open trades. A balance below that leaves cash negative until those trades close, and the AI opens no new trades meanwhile. The open trades are not closed for you.`;
  };
  amt.addEventListener('input', upd); kind.addEventListener('change', upd);
  const presets = h('div.row', [1000, 10000, 25000, 50000, 100000, 250000, 1000000].map(v =>
    h('button.btn.small.ghost', { type: 'button', onclick: () => { kind.value = 'set_balance'; amt.value = String(v); upd(); } },
      v >= 1e6 ? `${v / 1e6}M` : `${v / 1000}k`)));
  const go = h('button.btn.primary', { type: 'submit' }, 'Apply');
  const m = modal(`Change balance: ${acct.label || acct.connection_id}`, h('form.stack', {
    onsubmit: async (e) => {
      e.preventDefault();
      go.disabled = true;
      try {
        const r = await api('/api/paper_balance', { connection_id: acct.connection_id, kind: kind.value, amount: Number(amt.value) });
        m.close();
        toast(`Balance now ${money(r.equity_after, cur)} (simulated money)`, 'good');
        if (S.refreshOverview) S.refreshOverview();
        if (onDone) onDone(r);
      } catch (err) { errorToast(err); go.disabled = false; }
    }
  }, h('div.chips', modeBadge(acct.mode || 'paper'), h('span.note', 'simulated money · never a deposit')),
  presets, h('div.fgrid', h('label.f', 'Action', kind), h('label.f', `Amount (${cur})`, amt)), preview, warn,
  h('p.note', 'Works any time, with the bots running or stopped. Open positions stay open. The drawdown limit restarts from the new balance, and balance changes are never counted as profit or loss.'),
  go));
  upd();
  return m;
}

