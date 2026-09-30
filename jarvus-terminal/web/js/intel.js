// PAGE 3 - LIVE INTELLIGENCE: what every bot is doing and why. Decision feed (live, from the audit log) with the full
// lifecycle of each decision, scanner with watchlists, bot status, orders / fills / positions / exposure, side-by-side
// comparison, searchable history with export, research jobs and model registry, and service health.
import { S, h, $, api, replace, clear, toast, errorToast, modal, drawer, confirmBox, on, modeBadge, stateChip,
         money, signed, pct, num, r, cls, time, ago, checklist, kvList, table, debounce } from './core.js';
import { aiText } from './connections.js';

const TABS = [
  ['feed', 'Decision feed'], ['scanner', 'Scanner'], ['bots', 'Bot status'], ['orders', 'Orders & positions'],
  ['compare', 'Compare'], ['history', 'History'], ['research', 'Research & models'], ['health', 'Health'],
];
const LIFECYCLE = ['market_update', 'signal', 'brain', 'risk_approved', 'risk_rejected', 'order_submitted', 'broker_ack',
  'partially_filled', 'fill', 'filled', 'position_opened', 'stop_placed', 'exit', 'position_closed'];
const st = { tab: 'feed', timers: [], unsub: [], feed: [], seen: new Set(), paused: false, filt: { group: 'decisions', sev: 'info', text: '' },
             scanner: [], watchlists: [], wl: '', cmp: [] };

export function mount(view) {
  st.timers = []; st.unsub = [];
  if (st.ws !== S.workspace) { st.ws = S.workspace; st.feed = []; st.seen = new Set(); st.scanner = []; st.watchlists = []; st.wl = ''; st.cmp = []; }
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  if (q.get('tab') && TABS.find(t => t[0] === q.get('tab'))) st.tab = q.get('tab');
  view.append(
    h('div.tabs', { role: 'tablist' }, TABS.map(([k, label]) => h('button', { role: 'tab', class: k === st.tab ? 'on' : null, dataset: { tab: k }, onclick: () => show(k) }, label))),
    h('div#intel-body'));
  st.unsub.push(on('audit', onAudit), on('state', onState));
  show(st.tab);
}

export function unmount() { stopTimers(); st.unsub.forEach(f => f()); }
function stopTimers() { st.timers.forEach(clearInterval); st.timers = []; }

function show(k) {
  st.tab = k;
  stopTimers();
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === k));
  const body = $('#intel-body');
  clear(body);
  ({ feed: feedTab, scanner: scannerTab, bots: botsTab, orders: ordersTab, compare: compareTab, history: historyTab,
     research: researchTab, health: healthTab })[k](body);
}
function every(ms, fn) { st.timers.push(setInterval(fn, ms)); }

// ================================================================ decision feed
const GROUPS = {
  decisions: { label: 'Decisions (signals → exits)', kinds: ['signal', 'brain', 'risk', 'order', 'fill', 'position', 'exit', 'control'] },
  all: { label: 'Everything', kinds: null },
  orders: { label: 'Orders & fills', kinds: ['order', 'fill', 'position', 'exit'] },
  risk: { label: 'Risk decisions', kinds: ['risk', 'brain'] },
  control: { label: 'Controls & connections', kinds: ['control', 'connection'] },
  market: { label: 'Market updates', kinds: ['market_update', 'data'] },
  research: { label: 'Research & models', kinds: ['research'] },
};
const SEV = { debug: 0, info: 1, warning: 2, error: 3, critical: 4 };
const TF_SEC = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 };
// stale = the next bar should have closed well over a minute ago (a 1h series is normally up to an hour old)
function stale(ageS, tf) { return ageS !== null && ageS !== undefined && ageS > (TF_SEC[tf] || 300) + 120; }

function feedTab(body) {
  const grp = h('select', { 'aria-label': 'Event group', onchange: (e) => { st.filt.group = e.target.value; renderFeed(); } },
    Object.entries(GROUPS).map(([k, g]) => h('option', { value: k, selected: k === st.filt.group }, g.label)));
  const sev = h('select', { 'aria-label': 'Minimum severity', style: { width: 'auto' }, onchange: (e) => { st.filt.sev = e.target.value; renderFeed(); } },
    ['debug', 'info', 'warning', 'error'].map(s => h('option', { value: s, selected: s === st.filt.sev }, s === 'debug' ? 'incl. no-trade' : s + '+')));
  const txt = h('input', { placeholder: 'filter: bot, symbol, words…', value: st.filt.text, oninput: debounce((e) => { st.filt.text = e.target.value.toLowerCase(); renderFeed(); }, 200) });
  const pause = h('button.btn.small.ghost', { onclick: () => { st.paused = !st.paused; pause.textContent = st.paused ? 'Resume' : 'Pause'; if (!st.paused) renderFeed(); } }, st.paused ? 'Resume' : 'Pause');
  body.append(h('div.grid.g-li',
    h('section.panel.hot', h('h2', 'Decision feed', h('span.right', h('span.note#feed-count'), pause)),
      h('div.row', { style: { marginBottom: '8px' } }, grp, sev, txt),
      h('p.note', 'Every event is recorded before it is shown. Click an event to see the whole decision: market update → signal → risk → order → broker → fill → position → exit.'),
      h('div.feed.scroll.tall#feed')),
    h('div.stack',
      h('section.panel', h('h2', 'Bots right now', h('span.right.note', 'live')), h('div#now-bots')),
      h('section.panel', h('h2', 'Aggregate exposure'), h('div#now-exp')),
      h('section.panel', h('h2', 'Summarise with AI'), aiSummary()))));
  loadFeed();
  renderNow();
  loadExposure($('#now-exp'), true);
  every(20000, () => loadExposure($('#now-exp'), true));
}

async function loadFeed() {
  try {
    const rows = await api('/api/events?limit=300&severity=debug');
    for (const e of rows.reverse()) addEvent(e, false);
    renderFeed();
  } catch (e) { errorToast(e); }
}
function addEvent(e, live) {
  if (st.seen.has(e.id)) return false;
  st.seen.add(e.id);
  e._new = live;
  st.feed.push(e);
  if (st.feed.length > 1500) { const drop = st.feed.splice(0, 300); drop.forEach(x => st.seen.delete(x.id)); }
  return true;
}
function passes(e) {
  const g = GROUPS[st.filt.group];
  if (g.kinds && !g.kinds.includes(e.kind)) return false;
  if ((SEV[e.severity] ?? 1) < SEV[st.filt.sev]) return false;
  if (st.filt.text) {
    const hay = `${e.summary} ${e.bot_id || ''} ${e.symbol || ''} ${e.stage || ''} ${e.deployment_id || ''} ${e.connection_id || ''}`.toLowerCase();
    if (!hay.includes(st.filt.text)) return false;
  }
  return true;
}
function evRow(e) {
  return h(`div.ev.sev-${e.severity}${e._new ? '.new' : ''}`, { onclick: () => openEvent(e), title: 'Open the full decision' },
    h('span.t', time(e.ts)),
    h(`span.k.${e.kind}`, (e.stage || e.kind).replace(/_/g, ' ')),
    h('span.s', e.mode ? [modeBadge(e.mode), ' '] : null, e.summary));
}
function renderFeed() {
  const box = $('#feed');
  if (!box) return;
  const rows = st.feed.filter(passes).slice(-250).reverse();
  replace(box, rows.length ? rows.map(evRow) : h('div.empty', 'No events match. Events appear here as the bots evaluate markets.'));
  const c = $('#feed-count');
  if (c) c.textContent = `${rows.length} shown`;
  st.feed.forEach(e => { e._new = false; });
}
function onAudit(e) {
  const added = addEvent(e, true);
  if (!added || st.tab !== 'feed' || st.paused || !passes(e)) return;
  const box = $('#feed');
  if (!box) return;
  const empty = box.querySelector('.empty');
  if (empty) empty.remove();
  box.prepend(evRow(e));
  e._new = false;
  while (box.childElementCount > 250) box.lastChild.remove();
}
function onState() { if (st.tab === 'feed') renderNow(); if (st.tab === 'bots') renderBotGrid(); }

function renderNow() {
  const box = $('#now-bots');
  if (!box) return;
  const deps = (S.live && S.live.deployments) || (S.overview && S.overview.deployments) || [];
  const active = deps.filter(d => d.state !== 'stopped');
  replace(box, active.length ? h('div.stack', active.map(d => h('div.row.between',
    h('div', h('b', d.bot_id), ' ', modeBadge(d.mode), d.last_decision ? h('div.note', String(d.last_decision)) : null,
      d.blocked ? h('div.note.down', d.blocked) : null),
    stateChip(d.activity || d.state)))) : h('div.empty', 'No bot is deployed. Start one on Command Center.'));
}

function aiSummary() {
  const hours = h('select', { style: { width: 'auto' } }, [1, 6, 24].map(x => h('option', { value: x, selected: x === 6 }, `last ${x}h`)));
  const focus = h('input', { placeholder: 'optional focus, e.g. why were entries refused?' });
  const out = h('div');
  return h('div.stack', h('p.note', 'Sends the recent log (no credentials; secrets are stripped before anything is stored) to the assistant. It cites event ids; check them.'),
    h('div.row', hours, h('button.btn.small', { onclick: async () => {
      replace(out, h('p.note', 'Asking the assistant…'));
      try { replace(out, aiText(await api('/api/assistant/summarize', { hours: Number(hours.value), focus: focus.value }))); }
      catch (e) { replace(out); errorToast(e); }
    } }, 'Summarise')), focus, out);
}

// ---------------------------------------------------------------- one event / one decision
async function openEvent(e) {
  if (!e.correlation_id) {
    drawer(`${e.kind} · ${time(e.ts, true)}`, h('div.stack', eventHead(e), evidence(e), rawPayload(e)));
    return;
  }
  openLifecycle(e.correlation_id, e);
}
export async function openLifecycle(corr, first) {
  let rows = [];
  try { rows = await api('/api/lifecycle/' + encodeURIComponent(corr)); } catch (err) { errorToast(err); return; }
  if (!rows.length && first) rows = [first];
  const stages = new Set(rows.map(x => x.stage));
  const have = LIFECYCLE.filter(s => stages.has(s));
  const out = h('div');
  const head = rows[0] || {};
  drawer(`Decision ${corr.slice(0, 12)}`, h('div.stack',
    h('div.row', head.mode ? modeBadge(head.mode) : null, head.bot_id ? h('b', head.bot_id) : null, head.symbol ? h('span.note', head.symbol) : null,
      h('span.note', `${rows.length} events · stages: ${have.map(s => s.replace(/_/g, ' ')).join(' → ') || '—'}`)),
    h('ul.timeline', rows.map(x => h('li', h('div.row.between', h('span.stage', (x.stage || x.kind).replace(/_/g, ' ')), h('span.note', time(x.ts, true))),
      h('div', x.summary), evidence(x), rawPayload(x)))),
    h('div.row', h('button.btn.small', { onclick: async () => {
      replace(out, h('p.note', 'Asking the assistant…'));
      try { replace(out, aiText(await api('/api/assistant/explain', { correlation_id: corr }))); } catch (err) { replace(out); errorToast(err); }
    } }, 'Explain with AI'), h('a.btn.small.ghost', { href: `/api/events/export?correlation=${encodeURIComponent(corr)}&format=json`, download: '' }, 'Export JSON')),
    out));
}
function eventHead(e) {
  return kvList([['Kind', e.kind], ['Stage', e.stage || '—'], ['Severity', e.severity], ['Mode', e.mode || '—'], ['Bot', e.bot_id || '—'],
    ['Deployment', e.deployment_id || '—'], ['Market', e.symbol ? `${e.venue ? e.venue + ':' : ''}${e.symbol}` : '—'],
    ['Account', e.connection_id || '—'], ['Order', e.order_id || '—'], ['Recorded', time(e.ts, true)], ['Event id', `#${e.id}`]]);
}
function rawPayload(e) {
  if (e.payload === null || e.payload === undefined) return null;
  return h('details', h('summary.note', 'raw evidence (JSON)'), h('pre.payload', JSON.stringify(e.payload, null, 1)));
}
// structured evidence for the stages that carry it: data source and freshness, rule conditions, model versions, risk checks
function evidence(e) {
  const p = e.payload || {};
  const parts = [];
  if (e.stage === 'market_update') {
    parts.push(kvList([['Source', p.source || e.venue], ['Series', p.series], ['Bar', `${time(p.bar_open, true)} → ${time(p.bar_end)}`],
      ['Close', num(p.close)], ['Received', p.received ? time(p.received, true) : '—'], ['Age at decision', p.age_s !== undefined ? `${p.age_s}s after bar end` : '—'],
      ['Series status', p.status, p.status === 'ok' ? '' : 'down']]));
  }
  if (e.stage === 'signal') {
    parts.push(kvList([['Action', (p.action || '').replace(/_/g, ' ')], ['Bar', time(p.bar_time, true)], ['Decided', time(p.decision_time, true)],
      ['Data age', p.data_age_s !== undefined ? `${p.data_age_s}s` : '—', p.data_age_s > 120 ? 'down' : ''], ['Series', p.series_status],
      ['Strategy', `${p.strategy_id || ''} · version ${String(p.strategy_version || '').slice(0, 10)}`],
      ['Brain', p.brain_version || '—'], ['Volatility gate', p.volgate_version || 'not loaded']]));
    if ((p.rules || []).length) {
      parts.push(h('ul.checks', p.rules.map(x => h(`li.${x.passed === true ? 'pass' : x.passed === false ? 'fail' : 'skip'}`,
        h('span.i', x.passed === true ? '✓' : x.passed === false ? '✕' : '·'), h('div', h('span.mono', x.rule), h('div.d', `${x.group}${x.detail ? ' · ' + x.detail : ''}`))))));
    }
  }
  if (e.stage === 'brain') {
    parts.push(kvList([['Decision', p.action], ['Expected edge', p.edge !== undefined ? `${r(p.edge)} ± ${Number(p.sd || 0).toFixed(2)}` : '—'],
      ['Evidence', p.evidence !== undefined ? `${Math.round(p.evidence)} trades` : '—'], ['Regime', p.regime || '—'],
      ['Cost', p.cost_r !== undefined && p.cost_r !== null ? `${Number(p.cost_r).toFixed(2)}R` : '—'],
      ['Volatility gate', p.gate ? (typeof p.gate === 'object' ? JSON.stringify(p.gate) : String(p.gate)) : '—'],
      ['Win probability', p.p_win !== null && p.p_win !== undefined ? pct(p.p_win * 100, 1) + ' (calibrated)' : (p.p_win_note || 'not shown (not calibrated)')]]));
  }
  if (e.stage === 'risk_approved' || e.stage === 'risk_rejected') {
    const checks = p.checks || p.risk_checks;
    if (Array.isArray(checks)) parts.push(checklist(checks.map(c => ({ status: c.status || (c.ok ? 'pass' : 'fail'), label: c.label || c.name || c.id, detail: c.detail || c.reason || '' }))));
    else parts.push(kvList(Object.entries(p).filter(([, v]) => v === null || typeof v !== 'object').slice(0, 14).map(([k, v]) => [k.replace(/_/g, ' '), String(v)])));
  }
  if (e.kind === 'order' || e.kind === 'fill') {
    parts.push(kvList([p.client_order_id ? ['Client order id', p.client_order_id] : null, p.broker_order_id ? ['Provider order id', p.broker_order_id] : null,
      p.side ? ['Side', p.side] : null, p.qty !== undefined ? ['Quantity', num(p.qty, 6)] : null, p.limit_price ? ['Limit', num(p.limit_price)] : null,
      p.stop_price ? ['Stop', num(p.stop_price)] : null, p.price ? ['Price', num(p.price)] : null, p.filled_qty !== undefined ? ['Filled', num(p.filled_qty, 6)] : null,
      p.fee !== undefined ? ['Fee', `${num(p.fee, 6)} ${p.fee_currency || ''}`] : null, p.slippage_bps !== undefined && p.slippage_bps !== null ? ['Slippage', `${Number(p.slippage_bps).toFixed(1)} bps`] : null,
      p.reason ? ['Reason', p.reason] : null, p.state ? ['State', p.state] : null]));
  }
  return parts.length ? h('div', parts) : null;
}

// ================================================================ scanner
function scannerTab(body) {
  const wl = h('select', { 'aria-label': 'Watchlist', style: { width: 'auto' }, onchange: (e) => { st.wl = e.target.value; renderScanner(); } });
  const asset = h('select', { style: { width: 'auto' }, onchange: renderScanner }, h('option', { value: '' }, 'all assets'), h('option', { value: 'crypto' }, 'crypto'), h('option', { value: 'stock' }, 'stocks'));
  const only = h('select', { style: { width: 'auto' }, onchange: renderScanner },
    h('option', { value: 'opps' }, 'opportunities'), h('option', { value: 'all' }, 'every bot'), h('option', { value: 'signals' }, 'entry signals only'));
  const gate = h('select', { style: { width: 'auto' }, onchange: renderScanner }, h('option', { value: '' }, 'any volatility'), ['LOUD', 'NORMAL', 'QUIET'].map(x => h('option', { value: x }, x)));
  const txt = h('input', { placeholder: 'search strategy / market', oninput: debounce(renderScanner, 200) });
  st.scanCtl = { wl, asset, only, gate, txt };
  body.append(
    h('section.panel.hot', h('h2', 'Scanner', h('span.right', h('button.btn.small.ghost', { onclick: editWatchlist }, 'Edit watchlists'))),
      h('div.row', { style: { marginBottom: '8px' } }, wl, asset, only, gate, txt),
      h('p.note', 'Each row is one bot\'s latest closed-bar evaluation. "Opportunities" = an entry signal now, or at least 75% of its entry conditions holding. Brain edge is the learned expected result in R with its spread and the number of trades behind it: it is not a probability. The volatility gate says how much a market is likely to move, never which way.'),
      h('div#scan-table', h('div.empty', 'Loading…'))));
  loadScanner();
  every(10000, loadScanner);
}
async function loadScanner() {
  try {
    const [rows, wls] = await Promise.all([api('/api/scanner'), st.watchlists.length ? Promise.resolve(st.watchlists) : api('/api/watchlists')]);
    st.scanner = rows || []; st.watchlists = wls || [];
    const sel = st.scanCtl && st.scanCtl.wl;
    if (sel && sel.options.length !== st.watchlists.length + 1) {
      replace(sel, h('option', { value: '' }, 'all markets'), st.watchlists.map(w => h('option', { value: w.name, selected: w.name === st.wl }, `${w.name} (${w.symbols.length})`)));
    }
    renderScanner();
  } catch (e) { if ($('#scan-table')) replace($('#scan-table'), h('div.empty', e.message)); }
}
function renderScanner() {
  const box = $('#scan-table');
  if (!box) return;
  if (!S.overview || !S.overview.engine || !S.overview.engine.running) {
    if (!st.scanner.length) { replace(box, h('div.empty', 'The bot engine is stopped: start it (top bar) to scan markets.')); return; }
  }
  const c = st.scanCtl;
  const w = st.watchlists.find(x => x.name === st.wl);
  const syms = w ? new Set(w.symbols.map(s => s.toUpperCase())) : null;
  const t = c.txt.value.toLowerCase();
  let rows = st.scanner.filter(x => (!syms || syms.has(String(x.symbol).toUpperCase())) && (!c.asset.value || x.asset === c.asset.value)
    && (!c.gate.value || (x.gate && x.gate.state === c.gate.value))
    && (!t || `${x.strategy} ${x.symbol} ${x.name} ${x.family}`.toLowerCase().includes(t)));
  const ratio = (x) => x.conditions && x.conditions.total ? x.conditions.passed / x.conditions.total : 0;
  const entry = (x) => String(x.action || '').startsWith('enter');
  if (c.only.value === 'opps') rows = rows.filter(x => entry(x) || ratio(x) >= 0.75);
  if (c.only.value === 'signals') rows = rows.filter(entry);
  rows.sort((a, b) => (entry(b) - entry(a)) || (ratio(b) - ratio(a)) || ((b.brain ? b.brain.edge_r : -9) - (a.brain ? a.brain.edge_r : -9)));
  replace(box, table([
    { label: 'Market', v: x => h('span', h('b', x.symbol), h('div.note', x.venue)) },
    { label: 'Strategy', v: x => h('span', x.strategy || x.strategy_id, h('div.note', `${x.family || ''} · ${x.bot_id}`)) },
    { label: 'TF', v: x => x.tf },
    { label: 'Mode', v: x => x.deployed ? modeBadge(x.mode) : (x.user ? h('span.note', 'not deployed') : modeBadge(S.overview && S.overview.workspace.demo ? 'demo' : 'research')) },
    { label: 'Signal', v: x => h('span', h(`b${entry(x) ? '.up' : ''}`, String(x.action || '—').replace(/_/g, ' ')), x.reason ? h('div.note', x.reason) : null) },
    { label: 'Conditions', n: true, v: x => x.conditions && x.conditions.total ? `${x.conditions.passed}/${x.conditions.total}` : '—', cls: x => ratio(x) >= 0.75 ? 'up' : '' },
    { label: 'Brain edge (R)', n: true, v: x => x.brain ? h('span', { title: `${x.brain.evidence_trades} trades of evidence` }, `${r(x.brain.edge_r)} ± ${Number(x.brain.sd_r).toFixed(2)}`, h('div.note', `${x.brain.evidence_trades} trades`)) : '—', cls: x => x.brain ? cls(x.brain.edge_r) : '' },
    { label: 'Vol gate', v: x => x.gate ? h('span', { title: gateTitle(x.gate) }, x.gate.state || '—') : h('span.note', 'none') },
    { label: 'Data age', n: true, v: x => x.data_age_s === null || x.data_age_s === undefined ? '—' : `${Math.round(x.data_age_s)}s`, cls: x => stale(x.data_age_s, x.tf) ? 'down' : '' },
    { label: 'State', v: x => h('span', x.state, x.position ? h('div.note.up', 'in position') : null, x.benched ? h('div.note', 'benched by brain') : null) },
  ], rows.slice(0, 400), { empty: 'Nothing matches these filters.', onRow: (x) => botDrawer(x.bot_id) }));
}
function gateTitle(g) {
  const ev = g.evidence;
  if (!ev) return 'no held-out evidence recorded for this reading';
  return typeof ev === 'object' ? Object.entries(ev).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join('\n') : String(ev);
}
function editWatchlist() {
  const name = h('input', { placeholder: 'name', maxLength: 40 });
  const syms = h('textarea', { rows: 3, placeholder: 'BTC-USD, ETH-USD, SPY …' });
  const pick = h('select', { onchange: () => { const w = st.watchlists.find(x => x.name === pick.value); if (w) { name.value = w.name; syms.value = w.symbols.join(', '); } } },
    h('option', { value: '' }, 'new watchlist'), st.watchlists.map(w => h('option', { value: w.name }, w.name)));
  const save = async (del) => {
    try {
      st.watchlists = await api('/api/watchlists', { name: name.value, symbols: syms.value.split(/[\s,]+/).filter(Boolean), delete: del }).then(x => x.watchlists);
      m.close(); toast(del ? 'Watchlist deleted' : 'Watchlist saved', 'good'); if ($('#scan-table')) { replace(st.scanCtl.wl); loadScanner(); }
    } catch (e) { errorToast(e); }
  };
  const m = modal('Watchlists', h('div.stack', h('label.f', 'Edit', pick), h('label.f', 'Name', name), h('label.f', 'Symbols (as the bots name them)', syms),
    h('div.row', h('button.btn.primary', { onclick: () => save(false) }, 'Save'), h('button.btn.ghost', { onclick: () => save(true) }, 'Delete'))));
}
async function botDrawer(bid) {
  let d;
  try { d = await api('/api/bot/' + encodeURIComponent(bid)); } catch (e) { errorToast(e); return; }
  if (d.error) { toast(d.error, 'bad'); return; }
  const sig = d.last_signal || d.signal || {};
  drawer(`${bid}`, h('div.stack',
    kvList(Object.entries(d).filter(([k, v]) => v === null || typeof v !== 'object').slice(0, 24).map(([k, v]) => [k.replace(/_/g, ' '), String(v)])),
    (sig.rules || []).length ? h('div', h('h3', 'Latest rule evaluation'), h('ul.checks', sig.rules.map(x => h(`li.${x.passed ? 'pass' : x.passed === false ? 'fail' : 'skip'}`,
      h('span.i', x.passed ? '✓' : x.passed === false ? '✕' : '·'), h('div', h('span.mono', x.rule), h('div.d', `${x.group} · ${x.detail || ''}`)))))) : null,
    h('details', h('summary.note', 'raw state (JSON)'), h('pre.payload', JSON.stringify(d, null, 1)))));
}

// ================================================================ bot status
function botsTab(body) {
  body.append(
    h('section.panel.hot', h('h2', 'Deployed bots', h('span.right.note', 'your bots, by mode')), h('div.cards#bot-grid')),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('section.panel', h('h2', 'Research fleet', h('span.right', modeBadge('research'))), h('div#fleet-states'), h('div.scroll#fleet-list')),
      h('section.panel', h('h2', 'Aggregate exposure'), h('div#bots-exp'))));
  renderBotGrid();
  loadFleet();
  loadExposure($('#bots-exp'));
  every(10000, () => { loadFleet(); loadExposure($('#bots-exp')); });
}
async function renderBotGrid() {
  const box = $('#bot-grid');
  if (!box) return;
  let deps = [];
  try { deps = await api('/api/deployments') || []; } catch { deps = (S.overview && S.overview.deployments) || []; }
  const live = new Map(((S.live && S.live.deployments) || []).map(d => [d.deployment_id, d]));
  const act = deps.filter(d => d.state !== 'stopped');
  replace(box, act.length ? act.map(d => {
    const l = live.get(d.deployment_id) || {};
    const b = d.bot || {};
    const pf = d.performance || {};
    return h(`div.card${d.mode === 'live' ? '.live' : ''}${d.state === 'running' ? '.running' : ''}`,
      h('div.row.between', h('div', h('div.title', b.name || d.bot_id), h('div.sub', `${b.strategy || ''} · ${b.symbol || ''} ${b.tf || ''}`)),
        h('div.chips', modeBadge(d.mode), stateChip(l.activity || d.activity || d.state))),
      kvList([['Deployment', d.deployment_id], ['Account', d.connection_id], ['Allocation', money(d.allocation)],
        ['Position', d.position ? `${num(d.position.qty, 6)} @ ${num(d.position.avg_price)}` : 'flat'],
        ['Stop', d.position && (d.position.stop_price || d.position.stop) ? num(d.position.stop_price || d.position.stop) : '—'],
        ['Unrealized', signed(l.unrealized ?? d.unrealized), cls(l.unrealized ?? d.unrealized)],
        ['Trades', `${pf.trades || 0} · after fees ${signed(pf.pnl_after_fees)}`, cls(pf.pnl_after_fees)],
        ['Working orders', String((d.working_orders || []).length)],
        d.blocked ? ['Blocked', d.blocked, 'down'] : null,
        b.last_decision ? ['Last decision', String(b.last_decision)] : null]),
      h('div.row', h('button.btn.small.ghost', { onclick: () => { st.cmp = [d.bot_id]; show('compare'); } }, 'Compare'),
        h('button.btn.small.ghost', { onclick: () => { st.histPreset = { deployment: d.deployment_id }; show('history'); } }, 'History')));
  }) : h('div.empty', 'No deployed bots. Start one on Command Center.'));
}
function researchActivity(x) {
  if (x.position) return 'managing_position';
  if (['degraded', 'disabled'].includes(x.state)) return 'error';
  if (['warming', 'data_unavailable'].includes(x.state)) return 'waiting';
  return 'watching';
}
async function loadFleet() {
  try {
    const rows = (await api('/api/scanner') || []).filter(x => !x.user);
    const counts = {};
    rows.forEach(x => { const a = researchActivity(x); counts[a] = (counts[a] || 0) + 1; });
    const auto = S.overview ? S.overview.research_autopilot : null;
    replace($('#fleet-states'), h('div.chips', Object.entries(counts).map(([k, v]) => h('span', stateChip(k), ` ${v}`)),
      h('span.note', auto === false ? ' · autopilot OFF: watching only' : ' · research paper account only')));
    replace($('#fleet-list'), table([
      { label: 'Bot', v: x => h('span', h('b', x.name || x.bot_id), h('div.note', x.strategy)) },
      { label: 'Market', v: x => `${x.symbol} ${x.tf}` },
      { label: 'Now', v: x => stateChip(researchActivity(x)) },
      { label: 'Signal', v: x => String(x.action || '—').replace(/_/g, ' ') },
    ], rows, { empty: 'Research fleet not loaded (engine stopped?).', onRow: (x) => botDrawer(x.bot_id) }));
  } catch (e) { /* engine stopped */ }
}
async function loadExposure(box, compact = false) {
  if (!box) return;
  try {
    const x = await api('/api/exposure');
    replace(box,
      table([{ label: 'Account', v: a => h('span', a.label || a.connection_id, ' ', modeBadge(a.mode)) },
        { label: 'Exposure', n: true, v: a => money(a.exposure, a.currency) }, { label: '% equity', n: true, v: a => a.exposure_pct === null || a.exposure_pct === undefined ? '—' : pct(a.exposure_pct, 1) }],
      x.by_account, { empty: 'No accounts.' }),
      compact ? null : h('h3', { style: { marginTop: '10px' } }, 'By market'),
      compact ? null : table([{ label: 'Market', v: s => s.symbol }, { label: 'Mode', v: s => modeBadge(s.mode) },
        { label: 'Net qty', n: true, v: s => num(s.qty, 6) }, { label: 'Cost', n: true, v: s => money(s.cost) }, { label: 'Positions', n: true, v: s => s.positions }],
      x.by_symbol, { empty: 'No open positions.' }),
      h('p.note', x.note));
  } catch (e) { replace(box, h('div.empty', e.message)); }
}

// ================================================================ orders, fills, positions
const OPEN_STATES = 'NEW,SUBMITTING,ACKED,PARTIALLY_FILLED,CANCEL_REQUESTED,UNKNOWN';
function ordersTab(body) {
  body.append(
    h('section.panel.hot', h('h2', 'Working orders', h('span.right.note', 'at the provider or being confirmed')), h('div#ord-open')),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('section.panel', h('h2', 'Open positions'), h('div.scroll#ord-pos')),
      h('section.panel', h('h2', 'Exposure'), h('div#ord-exp'))),
    h('section.panel', { style: { marginTop: '12px' } }, h('h2', 'Order history', h('span.right.note', 'every order, with its state and the provider\'s answer')), h('div.scroll.tall#ord-all')),
    h('section.panel', { style: { marginTop: '12px' } }, h('h2', 'Fills', h('span.right.note', 'fees and slippage against the price at decision')), h('div.scroll.tall#ord-fills')));
  loadOrders();
  every(8000, loadOrders);
}
function orderCols() {
  return [
    { label: 'Time', v: o => time(o.created, true) },
    { label: 'Mode', v: o => modeBadge(o.mode) },
    { label: 'Bot', v: o => o.bot_id || '—' },
    { label: 'Purpose', v: o => (o.purpose || '').replace(/_/g, ' ') },
    { label: 'Market', v: o => String(o.symbol || '').split(':').pop() },
    { label: 'Side', v: o => o.side, cls: o => o.side === 'buy' ? 'up' : 'down' },
    { label: 'Type', v: o => `${o.order_type}${o.tif ? ' ' + o.tif : ''}` },
    { label: 'Qty', n: true, v: o => num(o.qty, 6) },
    { label: 'Price', n: true, v: o => o.limit_price ? num(o.limit_price) : o.stop_price ? `stop ${num(o.stop_price)}` : 'market' },
    { label: 'State', v: o => h(`span.mono${['REJECTED', 'LOST', 'UNKNOWN', 'NOT_SENT'].includes(o.state) ? '.down' : o.state === 'FILLED' ? '.up' : ''}`, o.state) },
    { label: 'Filled', n: true, v: o => o.filled_qty ? `${num(o.filled_qty, 6)} @ ${num(o.avg_price)}` : '—' },
    { label: 'Fees', n: true, v: o => o.fees ? `${num(o.fees, 6)} ${o.fee_currency || ''}` : '—' },
    { label: 'Note', v: o => o.reason || '' },
  ];
}
async function loadOrders() {
  try {
    const [open, all, fills, pos] = await Promise.all([api(`/api/orders?states=${OPEN_STATES}&limit=100`), api('/api/orders?limit=200'),
      api('/api/fills?limit=200'), api('/api/positions')]);
    const openLc = (o) => o.correlation_id ? openLifecycle(o.correlation_id) : null;
    if ($('#ord-open')) replace($('#ord-open'), table(orderCols(), open, { empty: 'No working orders.', onRow: openLc }));
    if ($('#ord-all')) replace($('#ord-all'), table(orderCols(), all, { empty: 'No orders yet.', onRow: openLc }));
    if ($('#ord-fills')) replace($('#ord-fills'), table([
      { label: 'Time', v: f => time(f.ts, true) }, { label: 'Mode', v: f => h('span', modeBadge(f.mode), f.simulated ? h('span.note', ' sim') : null) },
      { label: 'Bot', v: f => f.bot_id || '—' }, { label: 'Market', v: f => String(f.symbol || '').split(':').pop() },
      { label: 'Side', v: f => f.side, cls: f => f.side === 'buy' ? 'up' : 'down' }, { label: 'Qty', n: true, v: f => num(f.qty, 6) },
      { label: 'Price', n: true, v: f => num(f.price) }, { label: 'Fee', n: true, v: f => `${num(f.fee, 6)} ${f.fee_currency || ''}` },
      { label: 'Liquidity', v: f => f.liquidity || '—' },
      { label: 'Slippage', n: true, v: f => f.slippage_bps === null || f.slippage_bps === undefined ? '—' : `${Number(f.slippage_bps).toFixed(1)} bps`, cls: f => f.slippage_bps > 0 ? 'down' : f.slippage_bps < 0 ? 'up' : '' },
    ], fills, { empty: 'No fills yet.' }));
    if ($('#ord-pos')) replace($('#ord-pos'), table([
      { label: 'Bot', v: p => h('span', p.bot_id, h('div.note', p.source)) }, { label: 'Mode', v: p => modeBadge(p.mode) },
      { label: 'Market', v: p => String(p.symbol || '').split(':').pop() }, { label: 'Qty', n: true, v: p => num(p.qty, 6) },
      { label: 'Avg price', n: true, v: p => num(p.avg_price) },
      { label: 'Stop', n: true, v: p => p.stop_price ? num(p.stop_price) : '—' },
      { label: 'Protection', v: p => p.stop_order ? h('span.up', 'stop at provider') : p.mode === 'research' ? 'managed by the bot' : p.simulated ? 'simulated' : h('span.down', 'no stop order') },
      { label: 'Opened', v: p => time(p.opened, true) },
    ], pos, { empty: 'No open positions.' }));
    loadExposure($('#ord-exp'));
  } catch (e) { errorToast(e); }
}

// ================================================================ compare
async function compareTab(body) {
  const pick = h('div.row#cmp-pick');
  body.append(h('section.panel.hot', h('h2', 'Compare bots side by side', h('span.right.note', 'up to 4')),
    h('p.note', 'Backtest, research-fleet paper, paper, demo and live results are measured separately and are never added together. A backtest is history; the others are what actually happened, each in its own mode.'),
    pick, h('div#cmp-out')));
  let bots = [];
  try {
    const [scan, ub] = await Promise.all([api('/api/scanner').catch(() => []), api('/api/user_bots').catch(() => [])]);
    const seen = new Set();
    for (const b of (ub || [])) { seen.add(b.bot_id); bots.push({ id: b.bot_id, label: `${b.name || b.bot_id} (your bot)` }); }
    for (const x of (scan || [])) if (!seen.has(x.bot_id)) bots.push({ id: x.bot_id, label: `${x.name || x.bot_id} · ${x.symbol}` });
  } catch { /* ignore */ }
  const sels = [0, 1, 2, 3].map(i => h('select', { style: { width: 'auto', maxWidth: '260px' }, onchange: runCompare },
    h('option', { value: '' }, '—'), bots.map(b => h('option', { value: b.id, selected: st.cmp[i] === b.id }, b.label))));
  replace(pick, sels);
  st.cmpSels = sels;
  runCompare();
}
async function runCompare() {
  const ids = (st.cmpSels || []).map(s => s.value).filter(Boolean);
  st.cmp = ids;
  const out = $('#cmp-out');
  if (!out) return;
  if (!ids.length) { replace(out, h('div.empty', 'Choose bots above.')); return; }
  try {
    const d = await api('/api/compare?bots=' + encodeURIComponent(ids.join(',')));
    const block = (label, badge, s) => h('div', h('div.row', modeBadge(badge), h('span.note', label)),
      s && s.trades ? kvList([['Trades', String(s.trades)], ['After fees', signed(s.pnl_after_fees), cls(s.pnl_after_fees)], ['Fees', money(s.fees)],
        ['Win rate', pct(s.win_rate * 100, 1)], ['Avg R', r(s.avg_r)], ['Max drawdown', money(s.max_drawdown_money)]]) : h('p.note', 'no trades in this mode'));
    replace(out, h('div.grid', { style: { gridTemplateColumns: `repeat(${d.bots.length}, minmax(240px, 1fr))`, overflowX: 'auto' } }, d.bots.map(b => {
      const bt = b.backtest;
      return h('div.card', h('div.title', b.name || b.bot_id), h('div.sub', `${b.strategy_id || ''} · ${b.symbol || ''}`),
        h('div.stack', { style: { marginTop: '8px' } },
          h('div', h('div.row', modeBadge('backtest'), h('span.note', 'measured on history, after costs')),
            bt && bt.available ? kvList(Object.entries(bt).filter(([k, v]) => !['available', 'note'].includes(k) && (v === null || typeof v !== 'object')).slice(0, 8)
              .map(([k, v]) => [k.replace(/_/g, ' '), typeof v === 'number' ? num(v) : String(v)])) : h('p.note', (bt && bt.note) || 'no backtest on record')),
          block('research fleet (simulated)', 'research', b.results.research),
          block('your paper bots', 'paper', b.results.paper),
          block('demo market', 'demo', b.results.demo),
          block('real money', 'live', b.results.live),
          kvList([['Avg slippage', b.avg_slippage_bps === null || b.avg_slippage_bps === undefined ? '—' : `${Number(b.avg_slippage_bps).toFixed(1)} bps (${b.fills_measured} fills)`],
            ['Brain estimate', b.brain ? `${r(b.brain.edge_r)} ± ${Number(b.brain.sd_r).toFixed(2)} (${b.brain.evidence_trades} trades)` : '—']])));
    })), h('p.note', d.note));
  } catch (e) { replace(out, h('div.empty', e.message)); }
}

// ================================================================ history
function historyTab(body) {
  const f = {
    text: h('input', { placeholder: 'words in the summary' }),
    kinds: h('select', h('option', { value: '' }, 'any kind'), ['signal', 'brain', 'risk', 'order', 'fill', 'position', 'exit', 'control', 'connection', 'research', 'market_update', 'data'].map(k => h('option', { value: k }, k.replace('_', ' ')))),
    mode: h('select', h('option', { value: '' }, 'any mode'), ['live', 'paper', 'demo', 'research'].map(k => h('option', { value: k }, k.toUpperCase()))),
    severity: h('select', ['debug', 'info', 'warning', 'error'].map(k => h('option', { value: k, selected: k === 'info' }, k + '+'))),
    bot: h('input', { placeholder: 'bot id' }), symbol: h('input', { placeholder: 'symbol' }),
    deployment: h('input', { placeholder: 'deployment id' }), correlation: h('input', { placeholder: 'decision (correlation) id' }),
    since: h('input', { type: 'datetime-local' }), until: h('input', { type: 'datetime-local' }),
  };
  if (st.histPreset) { for (const [k, v] of Object.entries(st.histPreset)) if (f[k]) f[k].value = v; st.histPreset = null; }
  const params = (extra = {}) => {
    const p = new URLSearchParams();
    for (const [k, el] of Object.entries(f)) {
      if (!el.value) continue;
      if (k === 'since' || k === 'until') p.set(k, String(new Date(el.value).getTime())); else p.set(k, el.value);
    }
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return p;
  };
  const res = h('div');
  let rows = [];
  const draw = () => replace(res, h('p.note', `${rows.length} events`), table([
    { label: '#', n: true, v: e => e.id }, { label: 'Time', v: e => time(e.ts, true) },
    { label: 'Kind', v: e => h(`span.k.${e.kind}`, (e.stage || e.kind).replace(/_/g, ' ')) },
    { label: 'Mode', v: e => e.mode ? modeBadge(e.mode) : '' }, { label: 'Bot', v: e => e.bot_id || '' },
    { label: 'Summary', v: e => e.summary }, { label: 'Sev', v: e => e.severity, cls: e => e.severity === 'warning' ? 'dim' : ['error', 'critical'].includes(e.severity) ? 'down' : '' },
  ], rows, { empty: 'No events match.', onRow: openEvent }),
  rows.length >= 200 ? h('button.btn.small', { onclick: async () => { const more = await api('/api/events?' + params({ before: rows[rows.length - 1].id, limit: 200 })); rows = rows.concat(more); draw(); } }, 'Load older') : null);
  const search = async () => { try { rows = await api('/api/events?' + params({ limit: 200 })); draw(); } catch (e) { errorToast(e); } };
  const exp = (fmt) => { const a = h('a', { href: '/api/events/export?' + params({ format: fmt, limit: 5000 }), download: '' }); document.body.append(a); a.click(); a.remove(); };
  body.append(h('section.panel.hot', h('h2', 'Event history', h('span.right', h('button.btn.small', { onclick: () => exp('csv') }, 'Export CSV'), h('button.btn.small', { onclick: () => exp('json') }, 'Export JSON'))),
    h('form', { onsubmit: (e) => { e.preventDefault(); search(); } },
      h('div.grid', { style: { gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: '8px' } },
        h('label.f', 'Text', f.text), h('label.f', 'Kind', f.kinds), h('label.f', 'Mode', f.mode), h('label.f', 'Severity', f.severity),
        h('label.f', 'Bot', f.bot), h('label.f', 'Symbol', f.symbol), h('label.f', 'Deployment', f.deployment), h('label.f', 'Decision id', f.correlation),
        h('label.f', 'From', f.since), h('label.f', 'To', f.until)),
      h('div.row', { style: { marginTop: '8px' } }, h('button.btn.primary', { type: 'submit' }, 'Search'), h('span.note', 'Exports use the same filters (up to 5,000 events). Credentials never appear in the log.'))),
    h('div.sep'), res));
  search();
}

// ================================================================ research & models
function researchTab(body) {
  body.append(
    h('div.grid.g-2',
      h('section.panel.hot', h('h2', 'Research jobs', h('span.right.note#job-counts')), h('div#job-form'), h('div.scroll#job-list')),
      h('section.panel', h('h2', 'AI strategy ideas', h('span.right', h('span.badge.backtest', 'UNTESTED'))), aiCandidates())),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('section.panel', h('h2', 'Strategy versions'), h('div.scroll#reg-strat')),
      h('section.panel', h('h2', 'Brain versions', h('span.right', h('button.btn.small', { onclick: snapshot }, 'Snapshot learning brain'))), h('div#reg-models'))),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('section.panel', h('h2', 'Drift', h('span.right', h('button.btn.small', { onclick: driftCheck }, 'Check now'))), h('div.scroll#drift')),
      h('section.panel', h('h2', 'Promotions', h('span.right.note', 'every approval, recorded')), h('div.scroll#promos'))));
  jobForm();
  loadJobs(); loadModels();
  every(4000, loadJobs);
  every(30000, loadModels);
}
function jobForm() {
  const kind = h('select', h('option', { value: 'walk_forward' }, 'Walk-forward evaluation of a strategy'), h('option', { value: 'gate_drift' }, 'Volatility-gate drift check'), h('option', { value: 'brain_eval' }, 'Brain candidate vs champion'));
  const strat = h('input', { placeholder: 'strategy id (e.g. from the library)' });
  const market = h('input', { placeholder: 'venue:instrument e.g. coinbase:BTC-USD' });
  const days = h('input', { type: 'number', min: '7', max: '2000', value: '90' });
  const cand = h('input', { placeholder: 'candidate brain version' });
  const fields = h('div.fgrid');
  const redraw = () => replace(fields, kind.value === 'walk_forward' ? [h('label.f', 'Strategy', strat), h('label.f', 'Market', market), h('label.f', 'Days of history', days)]
    : kind.value === 'gate_drift' ? [h('label.f', 'Market', market)] : [h('label.f', 'Candidate version', cand)]);
  kind.addEventListener('change', redraw);
  redraw();
  const go = async () => {
    const [venue, instrument] = market.value.includes(':') ? market.value.split(':') : ['coinbase', market.value];
    const spec = kind.value === 'walk_forward' ? { strategy_id: strat.value.trim(), venue, instrument, days: Number(days.value), draws: 100, fee_profile: 'venue' }
      : kind.value === 'gate_drift' ? { venue, instrument } : { candidate: cand.value.trim() };
    try { const j = await api('/api/research/submit', { kind: kind.value, spec }); toast(`Job ${j.job_id} queued`, 'good'); loadJobs(); } catch (e) { errorToast(e); }
  };
  replace($('#job-form'), h('div.stack', h('label.f', 'Job', kind), fields, h('div.row', h('button.btn.primary', { onclick: go }, 'Queue job'),
    h('span.note', 'Jobs run in separate worker processes with time and memory limits; results are cached by question + data.'))));
}
async function loadJobs() {
  try {
    const d = await api('/api/research/jobs?limit=40');
    const c = d.counts || {};
    if ($('#job-counts')) $('#job-counts').textContent = Object.entries(c).map(([k, v]) => `${k} ${v}`).join(' · ') || 'no jobs yet';
    if ($('#job-list')) replace($('#job-list'), table([
      { label: 'Job', v: j => h('span.mono', j.job_id) }, { label: 'Kind', v: j => j.kind.replace('_', ' ') },
      { label: 'State', v: j => h(`span${j.state === 'failed' ? '.down' : j.state === 'done' ? '.up' : ''}`, j.state) },
      { label: 'Progress', v: j => j.state === 'running' ? `${Math.round((j.progress || 0) * 100)}% ${j.message || ''}` : (j.message || '') },
      { label: 'Result', v: j => j.result ? (j.result.summary || j.result.verdict || j.result.recommendation || j.result.status || '') : (j.error || '') },
      { label: '', v: j => ['queued', 'running'].includes(j.state) ? h('button.btn.small.ghost', { onclick: async (ev) => { ev.stopPropagation(); try { await api('/api/research/cancel', { job_id: j.job_id }); loadJobs(); } catch (e) { errorToast(e); } } }, 'Cancel') : '' },
    ], d.jobs, { empty: 'No research jobs yet.', onRow: (j) => jobDrawer(j.job_id) }));
  } catch (e) { /* ignore transient */ }
}
async function jobDrawer(jid) {
  let j;
  try { j = await api('/api/research/job/' + jid); } catch (e) { errorToast(e); return; }
  const res = j.result || {};
  const segs = res.segments || {};
  const segRow = (name, s) => s ? [name, `${s.trades} trades · ${r(s.expectancy_r)}${s.ci95 ? ` (95% CI ${r(s.ci95[0])} to ${r(s.ci95[1])})` : ''}`, cls(s.expectancy_r)] : null;
  const checks = res.checks ? Object.entries(res.checks).map(([k, v]) => ({ status: v ? 'pass' : 'fail', label: k.replace(/_/g, ' ') })) : null;
  drawer(`Job ${jid}`, h('div.stack',
    kvList([['Kind', j.kind], ['State', j.state], ['Queued', time(j.created, true)], ['By', j.requested_by || '—'], ['Message', j.message || '—'], j.error ? ['Error', j.error, 'down'] : null]),
    res.verdict ? h('div.banner', h('b', 'Verdict: '), res.verdict) : null,
    Object.keys(segs).length ? h('div', h('h3', 'Chronological segments (after costs)'), kvList([segRow('Train', segs.train), segRow('Validation', segs.validation), segRow('Test (untouched)', segs.test),
      segRow('Test at 2x costs', res.test_double_costs), segRow('Test gross (no costs)', res.test_gross),
      res.baselines && res.baselines.random_entries ? ['Random entries p95', r(res.baselines.random_entries.p95)] : null,
      ['Positive folds', `${res.positive_folds ?? '—'} of ${res.k_folds ?? '—'}`]])) : null,
    checks ? h('div', h('h3', 'Checks'), checklist(checks)) : null,
    res.assumptions ? h('div', h('h3', 'Assumptions'), kvList(Object.entries(res.assumptions).map(([k, v]) => [k, String(v)]))) : null,
    j.kind === 'walk_forward' && j.state === 'done' && res.strategy_id ? h('button.btn.warn', { onclick: () => approveFlow(res.strategy_id, res.strategy_version, jid, res.passes) }, 'Approve this version for live use…') : null,
    j.kind === 'brain_eval' && j.state === 'done' ? h('button.btn.warn', { onclick: () => promoteFlow(j.spec && j.spec.candidate, jid, res.passes || res.recommendation === 'promote') }, 'Promote this brain for live bots…') : null,
    h('details', h('summary.note', 'full result (JSON)'), h('pre.payload', JSON.stringify(j, null, 1)))));
}
async function approveFlow(sid, version, jid, passed) {
  const typed = passed ? await confirmBox('Approve for live use?', `Strategy ${sid} version ${String(version).slice(0, 10)} passed every check of evaluation ${jid}. Approval lets live bots use this exact version; it does not start anything.`, { okLabel: 'Approve', danger: false })
    : await confirmBox('Approve despite failed checks?', `Evaluation ${jid} did NOT pass every check. Approving anyway is recorded with your name.`, { typed: 'I ACCEPT THE FAILED CHECKS', okLabel: 'Approve anyway' });
  if (!typed) return;
  try { await api('/api/models/strategy_approve', { strategy_id: sid, version, job_id: jid, accept: typeof typed === 'string' ? typed : '' }); toast('Approved for live use', 'good'); loadModels(); }
  catch (e) { errorToast(e); }
}
async function promoteFlow(version, jid, passed) {
  const typed = passed ? await confirmBox('Promote this brain?', `Live bots will score entries with brain ${version}. The learning brain keeps learning on paper.`, { okLabel: 'Promote', danger: false })
    : await confirmBox('Promote despite the evaluation?', 'The candidate did not beat the current brain on the forward comparison.', { typed: 'I ACCEPT THE FAILED CHECKS', okLabel: 'Promote anyway' });
  if (!typed) return;
  try { await api('/api/models/promote', { version, job_id: jid, accept: typeof typed === 'string' ? typed : '' }); toast('Brain promoted for live bots', 'good'); loadModels(); }
  catch (e) { errorToast(e); }
}
async function loadModels() {
  try {
    const d = await api('/api/models');
    if ($('#reg-strat')) replace($('#reg-strat'), table([
      { label: 'Strategy', v: s => h('span', s.strategy_id, h('div.note.mono', String(s.version_hash).slice(0, 12))) },
      { label: 'Source', v: s => s.source }, { label: 'Status', v: s => h(`span${s.status === 'live_approved' ? '.up' : s.status === 'retired' ? '.muted' : ''}`, s.status.replace('_', ' ')) },
      { label: 'Evaluation', v: s => s.evaluation_job || '—' }, { label: 'Approved', v: s => s.approved ? `${time(s.approved, true)} by ${s.approved_by}` : '—' },
      { label: '', v: s => s.status === 'live_approved' ? h('button.btn.small.ghost', { onclick: async (ev) => { ev.stopPropagation(); if (!await confirmBox('Retire this version?', 'Live bots can no longer start with it.', { okLabel: 'Retire' })) return; try { await api('/api/models/strategy_retire', { strategy_id: s.strategy_id, version: s.version_hash }); loadModels(); } catch (e) { errorToast(e); } } }, 'Retire') : '' },
    ], d.strategies, { empty: 'No strategy versions registered yet. Running a bot or an evaluation registers its exact version.' }));
    if ($('#reg-models')) replace($('#reg-models'), h('p.note', d.note), h('p.note', `${d.brain_samples} closed trades recorded for brain evaluation.`), table([
      { label: 'Version', v: m => h('span.mono', m.version) }, { label: 'Status', v: m => h(`span${m.status === 'champion' ? '.up' : ''}`, m.status) },
      { label: 'Created', v: m => time(m.created, true) },
      { label: 'Learned from', n: true, v: m => m.metrics && m.metrics.trades_learned !== undefined ? `${m.metrics.trades_learned} trades` : '—' },
      { label: '', v: m => m.status === 'candidate' ? h('button.btn.small', { onclick: async (ev) => { ev.stopPropagation(); try { const j = await api('/api/research/submit', { kind: 'brain_eval', spec: { candidate: m.version } }); toast(`Evaluation ${j.job_id} queued`, 'good'); loadJobs(); } catch (e) { errorToast(e); } } }, 'Evaluate') : '' },
    ], d.models.filter(m => m.model === 'brain'), { empty: 'No brain snapshots yet.' }));
    if ($('#drift')) replace($('#drift'), table([
      { label: 'Subject', v: x => x.subject }, { label: 'Metric', v: x => x.metric },
      { label: 'Status', v: x => h(`span${x.status === 'drift' || x.status === 'alert' ? '.down' : x.status === 'ok' ? '.up' : ''}`, x.status || '—') },
      { label: 'Value', n: true, v: x => x.value === null || x.value === undefined ? '—' : `${num(x.value)}${x.threshold !== null && x.threshold !== undefined ? ' vs ' + num(x.threshold) : ''}` },
      { label: 'Detail', v: x => (x.body && (x.body.note || x.body.summary)) || '' }, { label: 'When', v: x => ago(x.ts) },
    ], d.drift, { empty: 'No drift reports yet.' }));
    if ($('#promos')) replace($('#promos'), table([
      { label: 'When', v: p => time(p.ts, true) }, { label: 'What', v: p => `${p.object} ${p.object_id}` },
      { label: 'Change', v: p => `${p.from_status} → ${p.to_status}` }, { label: 'By', v: p => p.approved_by }, { label: 'Note', v: p => p.note || '' },
    ], d.promotions, { empty: 'Nothing has been promoted.' }));
  } catch (e) { /* ignore */ }
}
async function snapshot() {
  try { const r2 = await api('/api/models/snapshot', { note: 'from Live Intelligence' }); toast(`Snapshot ${r2.version} saved as a candidate`, 'good'); loadModels(); }
  catch (e) { errorToast(e); }
}
async function driftCheck() {
  try { await api('/api/models/drift_check', {}); toast('Drift check done', 'good'); loadModels(); } catch (e) { errorToast(e); }
}
function aiCandidates() {
  const brief = h('textarea', { rows: 3, placeholder: 'e.g. long-only swing ideas for BTC-USD on 1h that survive 0.5% round-trip costs' });
  const out = h('div');
  return h('div.stack', h('p.note', 'The assistant drafts rule-language strategies. Each is compiled and checked; valid ones are registered as untested research versions. None is traded: evaluate first, then approve.'),
    brief, h('button.btn.small', { onclick: async () => {
      replace(out, h('p.note', 'Asking the assistant…'));
      try {
        const res = await api('/api/assistant/candidates', { brief: brief.value, n: 3 });
        if (res.refused) { replace(out, aiText(res)); return; }
        replace(out, h('div.stack', (res.candidates || []).map(c => h('div.card',
          h('div.row.between', h('div.title', c.name || c.strategy_id), h('span.badge' + (c.valid ? '.ok' : '.bad'), c.valid ? 'COMPILES' : 'INVALID')),
          c.rationale ? h('p', c.rationale) : null, c.how_it_fails ? h('p.note', 'How it fails: ', c.how_it_fails) : null,
          (c.problems || []).length ? h('ul.checks', c.problems.map(p => h('li.fail', h('span.i', '✕'), h('div', p)))) : null,
          c.valid ? h('button.btn.small', { onclick: () => evalCandidate(c) }, 'Evaluate (walk-forward)') : null))));
      } catch (e) { replace(out); errorToast(e); }
    } }, 'Draft ideas'), out);
}

function evalCandidate(c) {
  const market = h('input', { value: 'coinbase:BTC-USD', placeholder: 'venue:instrument' });
  const days = h('input', { type: 'number', min: '7', max: '2000', value: '90' });
  const m = modal(`Evaluate ${c.name || c.strategy_id}`, h('form.stack', {
    onsubmit: async (e) => {
      e.preventDefault();
      const [venue, instrument] = market.value.includes(':') ? market.value.split(':') : ['coinbase', market.value];
      try {
        const j = await api('/api/research/submit', { kind: 'walk_forward', spec: { definition: c.definition, venue, instrument, days: Number(days.value), draws: 100, fee_profile: 'venue' } });
        m.close(); toast(`Evaluation ${j.job_id} queued`, 'good'); loadJobs();
      } catch (err) { errorToast(err); }
    }
  }, h('div.fgrid', h('label.f', 'Market (venue:instrument)', market), h('label.f', 'Days of history', days)),
  h('button.btn.primary', { type: 'submit' }, 'Queue walk-forward evaluation')));
}

// ================================================================ health
function healthTab(body) {
  body.append(h('div#health'));
  loadHealth();
  every(5000, loadHealth);
}
async function loadHealth() {
  const box = $('#health');
  if (!box) return;
  let d;
  try { d = await api('/api/health'); } catch (e) { replace(box, h('div.empty', e.message)); return; }
  const f = d.fleet || {};
  const hw = d.hardware || {};
  const pool = (d.research || {}).pool || {};
  const ex = f.execution || {};
  const t = (k, v, s, c) => h('div.tile', h('div.k', k), h(`div.v${c ? '.' + c : ''}`, v), s ? h('div.s', s) : null);
  const ms = (x) => x === null || x === undefined ? '—' : `${Math.round(x)} ms`;
  const series = (f.series_detail || []).slice().sort((a, b) => (b.data_age_s || 0) - (a.data_age_s || 0));
  replace(box,
    h('section.panel.hot', h('h2', 'Engine', h('span.right', h('span.pill', h(`span.dot${f.running === false ? '.bad' : '.on'}`), f.running === false ? 'stopped' : 'running'))),
      h('div.tiles',
        t('Uptime', f.uptime_s ? `${(f.uptime_s / 3600).toFixed(1)} h` : '—'), t('Bots', f.bots ?? '—', f.bot_states ? Object.entries(f.bot_states).filter(([, v]) => v).map(([k, v]) => `${k} ${v}`).join(' · ') : ''),
        t('Queue length', f.queue ?? '—', 'bars waiting to be evaluated', f.queue > 50 ? 'down' : ''),
        t('Evaluation', ms(f.eval_ms_p50), `p95 ${ms(f.eval_ms_p95)}`), t('Bar → decision', ms(f.latency_ms_p50), `p95 ${ms(f.latency_ms_p95)}`),
        t('Completion', f.completion_rate === null || f.completion_rate === undefined ? '—' : pct(f.completion_rate * 100, 1), 'scheduled evaluations done'),
        t('Market data requests', f.requests ?? '—', `${f.http_429 || 0} rate-limited (${pct((f.rate_429 || 0) * 100, 2)})`, f.rate_429 > 0.02 ? 'down' : ''),
        t('Memory', f.rss_mb ? `${Math.round(f.rss_mb)} MB` : '—', `peak ${f.peak_rss_mb ? Math.round(f.peak_rss_mb) : '—'} MB`),
        t('CPU', f.cpu_percent === null || f.cpu_percent === undefined ? '—' : pct(f.cpu_percent, 0), `${hw.cpu_logical_cores || '?'} logical cores`),
        t('Database', d.db_bytes ? `${(d.db_bytes / 1048576).toFixed(1)} MB` : '—'), t('Live stream clients', d.stream_clients ?? '—'))),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('section.panel', h('h2', 'Order execution'), kvList([
        ['Open orders', String(ex.open ?? 0)], ['Broker ack', `${ms(ex.ack_ms_p50)} (p95 ${ms(ex.ack_ms_p95)})`],
        ['Orders by state', Object.entries(ex.orders_by_state || {}).map(([k, v]) => `${k} ${v}`).join(' · ') || 'none'],
        ['Counters', Object.entries(ex.stats || {}).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ') || '—'],
        ['Rate limits', Object.entries(ex.rate_limits || {}).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ') || '—']])),
      h('section.panel', h('h2', 'Connections'), table([
        { label: 'Account', v: c => h('span', c.label, h('div.note', c.connection_id)) }, { label: 'Env', v: c => modeBadge(c.environment === 'live' ? 'live' : c.environment === 'demo' ? 'demo' : 'paper') },
        { label: 'Status', v: c => h(`span${c.status === 'connected' ? '.up' : c.status === 'error' ? '.down' : ''}`, c.status) },
        { label: 'Last sync', v: c => ago(c.last_sync) }, { label: 'Error', v: c => c.last_error || '' },
      ], f.connections || [], { empty: 'Engine stopped.' }))),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('section.panel', h('h2', 'Research workers'), kvList([
        ['Workers busy', `${pool.busy ?? 0} of ${pool.max_workers ?? '—'}`], ['Per-job limits', pool.timeout_s ? `${pool.timeout_s}s, ${pool.max_memory_mb} MB` : '—'],
        ['Finished / failed', `${pool.finished ?? 0} / ${pool.failed ?? 0}`], ['Queue', Object.entries((d.research || {}).queue || {}).map(([k, v]) => `${k} ${v}`).join(' · ') || 'empty']]),
        (pool.running || []).length ? table([{ label: 'Job', v: j => j.job_id }, { label: 'Seconds', n: true, v: j => j.seconds }, { label: 'Peak MB', n: true, v: j => j.peak_mb }], pool.running) : null),
      h('section.panel', h('h2', 'This computer'), kvList([
        ['CPU', `${hw.cpu_logical_cores || '?'} logical cores (${hw.machine || ''})`], ['Memory', hw.memory_total_mb ? `${Math.round(hw.memory_available_mb)} MB free of ${Math.round(hw.memory_total_mb)} MB` : '—'],
        ['OS', hw.os || '—'], ['Python', hw.python || '—'], ['GPU', hw.gpu ? String(hw.gpu) : 'none used'], ['Remote compute', hw.remote_compute ? String(hw.remote_compute) : 'none']]),
        h('p.note', hw.note || ''))),
    h('section.panel', { style: { marginTop: '12px' } }, h('h2', 'Market data series', h('span.right.note', 'age = time since the latest closed bar ended')),
      h('div.scroll', table([
        { label: 'Series', v: s => h('span.mono', s.key) }, { label: 'Status', v: s => h(`span${s.status === 'ok' ? '.up' : '.down'}`, s.status) },
        { label: 'Data age', n: true, v: s => s.data_age_s === undefined ? '—' : `${Math.round(s.data_age_s)}s`, cls: s => stale(s.data_age_s, String(s.key).split('/').pop()) ? 'down' : '' },
        { label: 'Bars', n: true, v: s => s.bars ?? '—' }, { label: 'Bots', n: true, v: s => s.subscribers ?? '—' },
        { label: 'Last problem', v: s => s.last_fetch_error || s.last_issue || '' },
      ], series, { empty: 'Engine stopped: no live series.' }))));
}
