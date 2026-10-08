// PAGE 1 - COMMAND CENTER: account figures, the market chart with real entries/exits, building and starting a bot
// (readiness checks first), bot cards with PAUSE NEW ENTRIES / STOP, equity and drawdown, recent trades, alerts.
import { S, h, $, api, replace, clear, toast, errorToast, modal, drawer, confirmBox, on, off, modeBadge, stateChip,
         money, signed, pct, num, r, cls, time, ago, checklist, kvList, table, debounce, balanceDialog } from './core.js';
import { PriceChart, LineChart, available as chartsAvailable } from './charts.js';

const st = { account: null, market: null, tf: '5m', ind: { ema21: true, ema50: false, vwap: true, bb: false }, markers: true,
             strategies: null, markets: null, charts: [], timers: [], unsub: [] };

export function mount(view) {
  st.charts = []; st.timers = []; st.unsub = [];
  st.markets = null; st.market = null; st.account = null; st.price = null;   // per workspace: never reuse another's
  st.sinceDone = false; st.moneyLine = null; st.moneyChartLoaded = false; st.lastEquity = undefined; st.fillsPrimed = false; st.seenFills = new Set();
  st.builtFor = null;
  const acctSel = h('select#acct-sel', { 'aria-label': 'Account', style: { width: 'auto', minWidth: '220px' }, onchange: (e) => { st.account = e.target.value; renderAccount(); loadEquity(); loadTrades(); } });
  view.append(
    moneyPanel(),
    ultronPanel(),
    analysisPanel(),
    autopilotPanel(),
    goalPanel(),
    h('section.panel.hot', { style: { marginTop: '12px' } }, h('h2', 'Account', h('span.right', acctSel,
      h('button.btn.small.primary#acct-balance', { onclick: () => changeBalance(st.account) }, '✎ Change balance'), h('span.note#acct-src'))), h('div.tiles#acct-tiles')),
    h('div.grid.g-cc-top', { style: { marginTop: '12px' } },
      chartPanel(),
      h('section.panel.hot#builder', h('h2', 'Start a bot', h('span.right', h('span.note', 'readiness checks run first'))), h('div#builder-body', h('div.empty', 'Loading strategies…')))),
    h('section.panel', { style: { marginTop: '12px' } }, h('h2', 'Bots', h('span.right#bots-actions')), h('div.cards#bot-cards', h('div.empty', 'Loading…'))),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('section.panel', h('h2', 'Equity', h('span.right.note#eq-note')), h('div.chartbox.small#eq-chart'), h('h3', { style: { marginTop: '10px' } }, 'Drawdown'), h('div.chartbox.xs#dd-chart')),
      h('div.stack',
        h('section.panel', h('h2', 'Recent trades', h('span.right.note', 'after fees')), h('div.scroll#trades')),
        h('section.panel', h('h2', 'Active alerts', h('span.right.note', 'last 24 hours')), h('div.scroll#alerts')))));
  if (chartsAvailable()) {
    st.eq = new LineChart($('#eq-chart'), { color: '#a855f7' });
    st.dd = new LineChart($('#dd-chart'), { baseline: true, percent: true });
    st.charts.push(st.eq, st.dd);
  }
  const onOverview = () => {
    renderAccountSelector(); renderAccount(); renderBots(); renderAlerts();
    if (st.strategies && st.markets && st.builtFor !== S.overview.workspace.id) renderBuilder();   // first overview, or another workspace
  };
  st.unsub.push(on('overview', onOverview), on('state', liveState), on('audit', onAudit));
  if (S.overview) onOverview();
  loadAutopilot();
  st.timers.push(setInterval(loadAutopilot, 5000));
  loadMoney();
  st.timers.push(setInterval(loadMoney, 15000));                 // the stream updates it every couple of seconds; this is the fallback
  st.anaAll = false;
  loadAnalysis();
  st.timers.push(setInterval(() => { if (!document.hidden) loadAnalysis(); }, 10000));
  loadUltron();
  st.timers.push(setInterval(() => { if (!document.hidden) loadUltron(); }, 15000));
  st.unsub.push(on('state', (d) => { if (d.money) renderMoney(d.money); }));
  loadBuilder();
  st.timers.push(setInterval(() => { loadEquity(); loadTrades(); }, 30000), setInterval(loadCandles, 20000));
}

export function unmount() {
  st.timers.forEach(clearInterval); st.unsub.forEach(f => f());
  st.charts.forEach(c => c.destroy()); st.charts = [];
  if (st.price) { st.price.destroy(); st.price = null; }
}

// ---------------------------------------------------------------- YOUR MONEY: the account the AI trades, moving with the market
function moneyPanel() {
  return h('section.panel.money#money',
    h('h2', 'Your money', h('span.right', h('span.live-dot#money-live'), h('button.btn.small.primary', { onclick: () => changeBalance('paper-research') }, '✎ Change balance'))),
    h('div.money-grid',
      h('div',
        h('div.money-title#money-title', 'PAPER ACCOUNT'),
        h('div.money-big#money-big', '—'),
        h('div.money-change#money-change'),
        h('div.money-sub#money-sub'),
        h('p.note#money-note'),
        h('div#money-since'),
        h('div#money-decisions')),
      h('div.money-chart#money-chart')),
    h('h3', { style: { marginTop: '12px' } }, 'Open trades right now', h('span.right.note', 'valued at the market price, updating live')),
    h('div.scroll#money-positions'),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('div', h('h3', 'Latest buys and sells'), h('div#money-fills')),
      h('div', h('h3', 'Latest closed trades'), h('div.scroll#money-closed'))));
}

const LS = 'jv_last_seen';
function lastSeen() { try { return Number(localStorage.getItem(LS)) || 0; } catch { return 0; } }
function markSeen() { try { localStorage.setItem(LS, String(Date.now())); } catch { /* private window: no summary next time */ } }

async function loadMoney() {
  if (!$('#money')) return;
  try {
    const m = await api('/api/money');
    renderMoney(m);
    if (!st.moneyChartLoaded) loadMoneyChart();
    if (!st.sinceDone) { st.sinceDone = true; showSince(); }
  } catch { /* next poll */ }
}

// what the AI did while you were away: closed trades since the page was last open (realized, after fees)
async function showSince() {
  const since = lastSeen();
  markSeen();
  st.timers.push(setInterval(markSeen, 60000));
  if (!since || Date.now() - since < 10 * 60000) return;
  try {
    const rows = (await api('/api/trades?connection=paper-research&limit=500')).filter(t => t.exit_time >= since);
    const pnl = rows.reduce((a, t) => a + (t.pnl || 0), 0), wins = rows.filter(t => t.pnl > 0).length;
    replace($('#money-since'), h('div.banner' + (rows.length ? '' : '.demo'), { style: { marginTop: '10px' } },
      h('b', `Since you last looked (${ago(since)}): `),
      rows.length ? [`${rows.length} trade${rows.length === 1 ? '' : 's'} closed, ${wins} won, `, h('b', { class: cls(pnl) }, `${signed(pnl)} after fees`), ' (simulated).']
                  : 'no trades closed. The AI skips most signals because fees would eat the move, so quiet periods are normal.'));
  } catch { /* the summary is optional */ }
}

async function loadMoneyChart() {
  if (!$('#money-chart') || !chartsAvailable()) return;
  try {
    const d = await api('/api/equity?connection=paper-research&since=' + (Date.now() - 24 * 3600 * 1000));
    if (!st.moneyLine) { st.moneyLine = new LineChart($('#money-chart'), { color: '#22d3ee' }); st.charts.push(st.moneyLine); }
    st.moneyLine.set(d.equity, 'equity');
    st.moneyChartLoaded = true;
  } catch { /* chart is optional */ }
}

function renderMoney(m) {
  const box = $('#money');
  if (!box) return;
  const demo = S.overview && S.overview.workspace && S.overview.workspace.demo;
  replace($('#money-title'), modeBadge(demo ? 'demo' : 'research'), ' ', demo ? 'DEMO ACCOUNT · SIMULATED' : 'PAPER ACCOUNT · SIMULATED MONEY');
  const cur = m.currency || 'USD';
  st.money = m;
  if (m.equity === null || m.equity === undefined) {
    replace($('#money-big'), '—'); replace($('#money-change')); replace($('#money-sub'));
    replace($('#money-note'), m.note || 'Waiting for the bot engine to open the account…');
    return;
  }
  const big = $('#money-big');
  const prev = st.lastEquity;
  big.textContent = money(m.equity, cur);
  if (prev !== undefined && Math.abs(m.equity - prev) > 1e-9) {
    big.classList.remove('flash-up', 'flash-down'); void big.offsetWidth;
    big.classList.add(m.equity > prev ? 'flash-up' : 'flash-down');
  }
  st.lastEquity = m.equity;
  if (st.moneyLine && m.engine && m.time) st.moneyLine.append(m.time, m.equity);
  const ch = m.change_today, chp = m.change_today_pct;
  replace($('#money-change'), ch === null || ch === undefined ? null :
    h('span', { class: cls(ch) }, `${ch >= 0 ? '▲' : '▼'} ${signed(ch)} ${cur}  (${chp >= 0 ? '+' : ''}${(chp || 0).toFixed(2)}%)  today`));
  replace($('#money-sub'),
    h('span', 'Cash ', h('b', money(m.cash, cur))), h('span', 'In trades ', h('b', money(m.invested, cur))),
    h('span', 'Open P&L ', h('b', { class: cls(m.unrealized) }, signed(m.unrealized))),
    h('span', 'Closed today ', h('b', { class: cls(m.realized_today) }, signed(m.realized_today)), ` (${m.trades_today || 0} trades, fees ${money(m.fees_today || 0, cur)})`));
  replace($('#money-note'), m.engine === false ? 'The bot engine is stopped: this is the last saved state.' :
    `Every open trade is priced from the live market every few seconds, so this number moves like a real account. Simulated money: nothing here is real. ${m.slots_in_use ? m.slots_in_use + ' capital slots in use.' : ''}`);
  const d = m.decisions;
  const WHY = { cost: 'fees too high for the move', learned: 'expected result negative', quiet: 'market too quiet', benched: 'strategy benched (keeps losing)' };
  replace($('#money-decisions'), d ? h('div', { style: { marginTop: '10px' } },
    h('div.k.note', { style: { letterSpacing: '0.1em', textTransform: 'uppercase' } }, `What the AI decided in the last ${d.minutes} minutes`),
    h('p', { style: { margin: '4px 0' } }, d.signals
      ? [h('b', String(d.signals)), ` entry signals: `, h('b.up', String(d.approved)), ' taken, ', h('b', String(d.refused)), ' refused',
         d.refused ? [' (', Object.entries(d.refused_by).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${WHY[k] || k}`).join(' · '), ')'] : null, '.']
      : 'No entry signals. The AI only acts when a strategy fires and the costs are worth it, so quiet stretches are normal.'),
    (d.latest || []).length ? h('ul.fills', d.latest.map(x => h('li', h('span.t', time(x.time)), h(`span.${x.action === 'veto' ? 'sell' : 'buy'}`, x.action === 'veto' ? 'SKIP' : 'TAKE'),
      h('span', `${x.symbol || ''}`, h('span.note', ` · ${x.action === 'veto' ? (WHY[x.kind] || x.kind) : 'approved by the brain'}`)), h('span.note', x.bot_id || '')))) : null,
    h('a', { href: '#/intel' }, 'See every decision and its evidence →')) : null);
  replace($('#money-live'), h(`span.dot${m.engine === false ? '.warn' : '.on'}`), m.engine === false ? 'engine stopped' : `live · ${time(m.time)}`);
  replace($('#money-positions'), table([
    { label: 'Market', v: p => h('span', h('b', p.symbol), h('div.note', `${p.venue} · ${p.bot_id}`)) },
    { label: 'Side', v: p => p.side, cls: p => p.side === 'long' ? 'up' : 'down' },
    { label: 'Size', n: true, v: p => num(p.qty, 6), },
    { label: 'Bought at', n: true, v: p => num(p.entry) },
    { label: 'Price now', n: true, v: p => h('span', { title: `${p.price_source || ''}${p.price_time ? ' · ' + time(p.price_time) : ''}` }, num(p.price)) },
    { label: 'Worth now', n: true, v: p => money(p.value, cur) },
    { label: 'Profit / loss', n: true, v: p => h('span', { class: `pnl-pill ${cls(p.pnl)}` }, `${signed(p.pnl)}${p.pnl_pct === null || p.pnl_pct === undefined ? '' : `  ${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct.toFixed(2)}%`}`) },
    { label: 'Stop', n: true, v: p => p.stop ? num(p.stop) : '—' },
    { label: 'Target', n: true, v: p => p.target ? num(p.target) : '—' },
    { label: 'Held', v: p => ago(p.opened).replace(' ago', '') },
  ], m.positions || [], { empty: m.engine === false ? 'No open trades in the saved state.' : 'No open trades yet. The AI enters when a strategy fires and the costs are worth it; it skips most signals on purpose.' }));
  const known = st.seenFills || (st.seenFills = new Set());
  const fresh = [];
  for (const f of (m.recent_fills || [])) { const k = `${f.time}|${f.bot_id}|${f.side}|${f.price}`; if (!known.has(k)) { known.add(k); fresh.push(f); } }
  if (st.fillsPrimed) for (const f of fresh.slice(0, 3)) {
    toast(`${f.side === 'buy' ? 'BOUGHT' : 'SOLD'} ${num(f.qty, 6)} ${f.instrument} @ ${num(f.price)} (simulated)`, f.side === 'buy' ? 'good' : '');
  }
  st.fillsPrimed = true;
  replace($('#money-fills'), (m.recent_fills || []).length ? h('ul.fills', (m.recent_fills || []).map(f => h(`li${fresh.includes(f) && st.fillsPrimed ? '.new' : ''}`,
    h('span.t', time(f.time)), h(`span.${f.side}`, String(f.side).toUpperCase()),
    h('span', `${num(f.qty, 6)} ${f.instrument}`, h('span.note', ` @ ${num(f.price)}`)), h('span.note', `fee ${money(f.fee, cur)}`)))) : h('div.empty', 'No buys or sells yet. They appear here the moment the AI makes them.'));
  replace($('#money-closed'), table([
    { label: 'Closed', v: t => time(t.exit_time) }, { label: 'Market', v: t => t.instrument },
    { label: 'P&L', n: true, v: t => h('span', { class: `pnl-pill ${cls(t.pnl)}` }, signed(t.pnl)) },
    { label: 'Why', v: t => t.exit_reason },
  ], m.recent_trades || [], { empty: 'No closed trades yet.' }));
}

// ---------------------------------------------------------------- ULTRON: the trained councils inside the fleet
function ultronPanel() {
  return h('section.panel.ultron#ultron', { style: { marginTop: '12px' } },
    h('h2', 'ULTRON brain', h('span.right', h('span.note#ul-sum'))),
    h('p.note', 'The trained ULTRON councils (25 agents and a learned brain per timeframe, the same models as the ULTRON ',
      'TradingView indicator) each run a bot per market. A bot buys only when its council approves, then the stop, the 2R ',
      'target and the time limit manage the trade.'),
    h('div#ul-table', h('div.empty', 'Loading ULTRON…')),
    h('h3', { style: { marginTop: '10px' } }, 'Latest ULTRON buys and sells'), h('div#ul-recent'),
    h('p.note#ul-note', { style: { marginTop: '8px' } }));
}

async function loadUltron() {
  try { renderUltron(await api('/api/ultron')); } catch { /* next poll */ }
}

const UL_STATE = { idle_no_signal: 'ready', running: 'in a trade', warming: 'loading data', closed: 'market closed',
                   data_unavailable: 'no data', degraded: 'data issue', paused: 'paused', disabled: 'off', stopped: 'stopped' };
function ulStates(c) {
  const parts = Object.entries(c.states || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${UL_STATE[k] || k}`);
  return parts.length ? parts.join(' · ') : 'engine stopped';
}
function ulTested(t) {
  if (!t) return h('span.note', 'not measured');
  const x = t.test || {};
  return h('span', h(`b.${cls(x.expectancy_r)}`, `${r(x.expectancy_r)} × ${x.trades}`),
    h('div.note', `untouched test · all periods ${r(t.all.expectancy_r)} × ${t.all.trades}`));
}

function renderUltron(u) {
  if (!$('#ultron')) return;
  const cs = u.councils || [];
  const tot = cs.reduce((a, c) => a + c.bots, 0), open = cs.reduce((a, c) => a + c.open.length, 0);
  const ready = cs.reduce((a, c) => a + ((c.states || {}).idle_no_signal || 0) + ((c.states || {}).running || 0), 0);
  replace($('#ul-sum'), u.engine ? `${tot} bots · ${ready} watching · ${open} in a trade` : 'engine stopped');
  replace($('#ul-table'), table([
    { label: 'Council', v: c => h('span', h('b', c.name.replace(/^ULTRON (\w)/, (m, a) => a.toUpperCase())), h('div.note', c.markets.length > 6
      ? `${c.markets.slice(0, 6).map(m => m.replace(/-USD$|=X$/, '')).join(', ')} +${c.markets.length - 6} more`
      : c.markets.map(m => m.replace(/-USD$|=X$/, '')).join(', '))) },
    { label: 'Its bots now', v: c => h('span', ulStates(c), h('div.note', `${c.trades} paper trade${c.trades === 1 ? '' : 's'} so far`)) },
    { label: 'Holding', v: c => c.open.length ? h('span', c.open.map(o => h('div', h('b', o.instrument), ' ', h('span.note', o.position)))) : h('span.dim', 'nothing') },
    { label: 'Tested per trade (your fees)', n: true, v: c => ulTested(c.tested) },
  ], cs, { empty: 'No ULTRON councils found.' }));
  replace($('#ul-recent'), (u.recent || []).length
    ? h('ul.fills', u.recent.map(x => h('li', h('span.t', time(x.decision_time)),
        h(`b.${x.action === 'exit' ? 'down' : 'up'}`, x.action === 'exit' ? 'SELL' : 'BUY'), ' ', h('b', x.instrument), ' ',
        h('span.note', x.reason || ''))))
    : h('div.empty', 'No ULTRON trade yet. It is picky on purpose: about 50 buy signals a month across all its markets.'));
  replace($('#ul-note'), u.note || '');
}

// ---------------------------------------------------------------- WHAT THE AI SEES: its own reading of every market
const WHY_SKIP = { cost: 'fees too high for the move', learned: 'expected result negative', quiet: 'market too quiet', benched: 'strategy benched (keeps losing)' };
function analysisPanel() {
  return h('section.panel#analysis', { style: { marginTop: '12px' } },
    h('h2', 'What the AI sees right now', h('span.right', h('span.note#ana-time'))),
    h('p.note#ana-who'), h('div#ana-table', h('div.empty', 'Loading the AI\'s analysis…')),
    h('div.grid.g-2', { style: { marginTop: '10px' } },
      h('div', h('h3', 'What it has learned so far'), h('div#ana-insights')),
      h('div', h('h3', 'Strategies it trusts most and least'), h('div#ana-learned'))));
}

async function loadAnalysis() {
  try { renderAnalysis(await api('/api/analysis')); } catch { /* next poll */ }
}

function pctTxt(x) { return x === null || x === undefined ? '—' : `${Math.round(x * 100)}%`; }

function volCell(v) {
  if (!v) return h('span.note', 'no forecast yet (needs 200 hours of data)');
  const tag = h(`span.badge.${v.state === 'LOUD' ? 'warn' : v.state === 'QUIET' ? 'sim' : 'paper'}`, v.state);
  const hrs = v.horizon_hours ? `next ${v.horizon_hours} h` : 'next hours';
  let why;
  if (v.state === 'LOUD') why = `${hrs}: a big move followed ${pctTxt(v.big_move_rate)} of readings like this in testing (${(v.big_move_n || 0).toLocaleString()} cases; usually ${pctTxt(v.big_move_base)})`;
  else if (v.state === 'QUIET') why = `${hrs}: a quiet stretch followed ${pctTxt(v.quiet_rate)} of readings like this in testing (${(v.quiet_n || 0).toLocaleString()} cases; usually ${pctTxt(v.quiet_base)}). The AI skips new trades.`;
  else why = `${hrs}: no strong call either way`;
  return h('span', tag, h('div.note', why));
}

function trendCell(t) {
  if (!t) return h('span.note', 'warming up');
  const arrow = t.direction === 'up' ? '▲' : t.direction === 'down' ? '▼' : '↔';
  return h('span', h(`span.${t.direction === 'up' ? 'up' : t.direction === 'down' ? 'down' : 'dim'}`, `${arrow} ${t.text}`),
    h('div.note', t.volatile ? 'moving more than usual' : 'calmer than usual'));
}

function renderAnalysis(a) {
  if (!$('#analysis')) return;
  replace($('#ana-time'), a.engine === false ? 'engine stopped' : `updated ${time(a.time)}`);
  if (a.engine === false) {
    replace($('#ana-who'), a.note || '');
    replace($('#ana-table'), h('div.empty', 'Start the autopilot to see the AI analyse every market.'));
    replace($('#ana-insights')); replace($('#ana-learned'));
    return;
  }
  replace($('#ana-who'), h('b', 'Every decision here is made by the software. '), `How: ${a.decided_by.replace(/^the software: /, '')} `,
    h('br'), h('b', 'Up or down? '), `${a.direction.charAt(0).toUpperCase()}${a.direction.slice(1)}`);
  const rows = a.markets || [];
  const shown = st.anaAll ? rows : rows.slice(0, 10);
  replace($('#ana-table'),
    table([
      { label: 'Market', v: m => h('span', h('b', m.symbol), h('div.note', `${m.venue} · ${m.bots} bot${m.bots === 1 ? '' : 's'} watching`)) },
      { label: 'Price', n: true, v: m => h('span', { title: m.price_source || '' }, num(m.price)) },
      { label: 'Trend (last 20 candles)', v: m => trendCell(m.trend) },
      { label: 'Forecast: how much it will move', v: m => volCell(m.volatility) },
      { label: 'The bots right now', v: m => h('span', m.signals ? h('b.up', `${m.signals} want to enter`) : h('span.dim', 'no entry signal'),
        h('div.note', m.stance.bots ? `entry rules: ${m.stance.long} say buy · ${m.stance.short} say sell · of ${m.stance.bots}` : 'no fresh candles (market closed?)')) },
      { label: 'Best strategy here (learned)', v: m => !m.best ? '—' : h('span', m.best.strategy || m.best.bot_id,
        h('div.note', m.best.evidence_trades >= 8 ? `${r(m.best.edge_r)} per trade expected (${Math.round(m.best.evidence_trades)} trades of evidence)` : 'too little evidence yet')) },
      { label: 'Latest decision', v: m => !m.decision ? h('span.note', 'none yet') : h('span',
        h(`b.${m.decision.action === 'veto' ? 'down' : 'up'}`, m.decision.action === 'veto' ? 'SKIP' : 'TAKE'),
        h('div.note', `${m.decision.action === 'veto' ? (WHY_SKIP[m.decision.kind] || 'refused') : 'approved by the brain'} · ${ago(m.decision.time)}`)) },
      { label: 'AI holds', v: m => !m.position ? '—' : h('span', h('b', m.position.side.toUpperCase()),
        h('div.note', m.position.pnl === null ? '' : h('span', { class: cls(m.position.pnl) }, `${signed(m.position.pnl)} open`))) },
    ], shown, { empty: 'Waiting for the first candles…' }),
    rows.length > 10 ? h('button.btn.small.ghost', { style: { marginTop: '8px' }, onclick: () => { st.anaAll = !st.anaAll; renderAnalysis(a); } },
      st.anaAll ? 'Show fewer' : `Show all ${rows.length} markets`) : null);
  replace($('#ana-insights'), (a.insights || []).length
    ? h('ul.fills', a.insights.map(x => h('li', h('span.t', time(x.time)), h('span', x.text))))
    : h('div.empty', 'Nothing statistically clear yet. The brain only states a lesson once a pattern holds over enough closed trades (t ≥ 2).'));
  const lcols = [
    { label: 'Strategy', v: x => h('span', h('b', x.strategy), h('div.note', x.markets || '')) },
    { label: 'Expected per trade', n: true, v: x => h('span', { class: cls(x.estimate_r) }, r(x.estimate_r)) },
    { label: 'Evidence', n: true, v: x => h('span.note', `${Math.round(x.evidence_trades)} trades (${Math.round(x.own_trades)} its own)`) }];
  replace($('#ana-learned'), (a.learned_best || []).length
    ? h('div', h('p.note', 'Learned from tested history, then updated with every trade the AI closes. R = the amount a trade risks; the brain refuses strategies it expects to lose.'),
      h('div.note', 'Most trusted'), table(lcols, a.learned_best),
      (a.learned_worst || []).length ? [h('div.note', { style: { marginTop: '8px' } }, 'Least trusted'), table(lcols, a.learned_worst)] : null)
    : h('div.empty', 'No closed trades to learn from yet. The brain starts from tested history and updates with every trade the AI closes.'));
}

// ---------------------------------------------------------------- GOAL CALCULATOR: measured, not promised
function goalPanel() {
  const bal = h('input#goal-balance', { type: 'number', min: '1', step: 'any', inputMode: 'decimal', 'aria-label': 'Starting balance' });
  const days = h('select#goal-days', [30, 90, 180, 365].map(d => h('option', { value: d, selected: d === 90 }, `${d} days`)));
  const target = h('input#goal-target', { type: 'number', min: '1', step: 'any', inputMode: 'decimal', 'aria-label': 'Goal' });
  const go = debounce(runGoal, 350);
  [bal, days, target].forEach(el => el.addEventListener('input', go));
  const presets = h('div.row', [['2×', 2], ['10×', 10], ['100×', 100], ['3,000×', 3000]].map(([lab, x]) =>
    h('button.btn.small.ghost', { type: 'button', onclick: () => { target.value = String(Math.round(Number(bal.value || 100) * x)); runGoal(); } }, lab)));
  return h('section.panel#goal', h('details', { ontoggle: (e) => { if (e.target.open) { if (!bal.value) { bal.value = String(Math.round((st.lastEquity || 100000) * 100) / 100); target.value = String(Math.round(Number(bal.value) * 10)); } runGoal(); } } },
    h('summary.dim', { style: { cursor: 'pointer', fontWeight: 700 } }, 'What could my balance become? Goal calculator (measured, not promised)'),
    h('div.stack', { style: { marginTop: '10px' } },
      h('p.note', 'Built from the whole software replayed on recent real market data, window after window, at your exchange\'s fees and your balance. Type a balance and a goal to see what it would take and what the measurements say.'),
      h('p.note', h('b', 'This is only arithmetic for the goal you type. '), 'The AI never sees it or aims for it: it has no profit target and decides trade by trade from its own analysis (above).'),
      h('div.fgrid3', h('label.f', 'Starting balance', bal), h('label.f', 'Time', days), h('label.f', 'Goal (what you want it to become)', target)),
      presets, h('div#goal-out', h('div.empty', 'Open this and choose a balance.')))));
}

async function runGoal() {
  const out = $('#goal-out');
  if (!out) return;
  const b = Number($('#goal-balance').value), t = Number($('#goal-target').value), d = $('#goal-days').value;
  if (!(b >= 1)) { replace(out, h('div.empty', 'Enter a starting balance of at least 1.')); return; }
  try {
    const r = await api(`/api/projection?balance=${b}&days=${d}${t > 0 ? '&target=' + t : ''}`);
    const o = r.outcome, cur = (S.overview && S.overview.accounts || []).find(x => x.connection_id === 'paper-research');
    const c = (cur && cur.currency) || 'USD';
    const m = (x) => money(x, c, x < 1000 ? 2 : 0);
    const g = r.goal;
    replace(out, h('div.stack',
      r.requested_fees && r.requested_fees !== r.fees ? h('p.note.down', `Your selected fee level (${r.requested_fees}) has no measurement bundled yet; showing the nearest measured level (${r.fees}).`) : null,
      h('div', h('b', `${m(r.balance)} over ${r.days} days`), ` (${r.windows} windows of ${r.window_days} days, ${r.fees.replace('_', '-')} fees, measured at the ${m(r.tier)} balance size): `,
        'the middle outcome is ', h('b', m(o.median)), `; 9 in 10 simulated outcomes end between ${m(o.p05)} and ${m(o.p95)}.`),
      table([{ label: 'Worst', n: true, v: () => m(o.worst), cls: () => o.worst < r.balance ? 'down' : 'up' }, { label: '5th %', n: true, v: () => m(o.p05), cls: () => o.p05 < r.balance ? 'down' : 'up' },
        { label: 'Middle', n: true, v: () => m(o.median), cls: () => o.median < r.balance ? 'down' : 'up' }, { label: '95th %', n: true, v: () => m(o.p95), cls: () => o.p95 < r.balance ? 'down' : 'up' },
        { label: 'Best of ' + 5000, n: true, v: () => m(o.best), cls: () => o.best < r.balance ? 'down' : 'up' }], [1]),
      h('p.note', `Ends higher than it started in ${(r.share_ending_up * 100).toFixed(0)}% of simulations; loses 10% or more in ${(r.share_losing_10pct * 100).toFixed(0)}%. Average ${r.mean_window_pct >= 0 ? '+' : ''}${r.mean_window_pct.toFixed(3)}% per ${r.window_days} days; best window ${r.best_window_pct >= 0 ? '+' : ''}${r.best_window_pct.toFixed(2)}%, worst ${r.worst_window_pct.toFixed(2)}%.`),
      g ? h('div.banner' + (g.share_reaching > 0.05 ? '' : '.demo'), h('div',
        h('b', `Your goal: ${m(g.target)} (${g.multiple >= 10 ? g.multiple.toFixed(0) : g.multiple.toFixed(1)}× your balance) in ${r.days} days.`), ' ',
        `It needs about +${g.needed_per_day_pct.toFixed(2)}% EVERY day (+${g.needed_per_window_pct.toFixed(1)}% every ${r.window_days} days). The best ${r.window_days}-day window measured was ${r.best_window_pct >= 0 ? '+' : ''}${r.best_window_pct.toFixed(2)}%. `,
        h('b', `${(g.share_reaching * 100).toFixed(1)}% of ${g.simulations.toLocaleString()} simulated paths reached it.`), ' ',
        `Even repeating the single best window every time ends at ${m(r.even_the_best_window_every_time)}.`)) : null,
      h('p.note', `Based on ${r.sample.windows_measured} random ${r.window_days}-day windows from ${r.sample.period ? r.sample.period.join(' to ') : 'recent history'}. A short sample, not a forecast: markets change, and past windows do not promise future ones. Leverage or all-in bets would raise the spread of outcomes, mostly toward losing everything.`)));
  } catch (e) { replace(out, h('div.empty', e.message)); }
}

// ---------------------------------------------------------------- AUTOPILOT: the one button
function autopilotPanel() {
  return h('section.panel.autopilot#autopilot',
    h('div.ap-grid',
      h('div.ap-left',
        h('div.row', h('span.ap-title', 'AI AUTOPILOT'), h('span#ap-badge'), h('span#ap-state.note')),
        h('div#ap-button', { style: { margin: '12px 0' } }),
        h('label.f', { style: { maxWidth: '420px', marginBottom: '8px' } }, 'Exchange fees the AI pays (pick the one you really trade on)', h('select#ap-fees', { onchange: setFees })),
        h('p.note#ap-fees-note'),
        h('label.check#ap-startup-row.hidden', h('input#ap-startup', { type: 'checkbox', onchange: setStartup }), 'Start Jarvus when Windows starts, so the AI keeps trading without you opening anything'),
        h('p.note#ap-explain')),
      h('div.tiles#ap-tiles')));
}

async function loadAutopilot() {
  if (!$('#autopilot')) return;
  try { st.ap = await api('/api/autopilot'); renderAutopilot(); } catch (e) { /* shown on the next poll */ }
  if (!st.fees || !$('#ap-fees').options.length) loadFees();
  if (st.startup === undefined) loadStartup();
}

async function loadStartup() {
  st.startup = null;
  try {
    st.startup = await api('/api/startup');
    const row = $('#ap-startup-row');
    if (!row || !st.startup.supported) return;                // only the Windows app can do this
    row.classList.remove('hidden');
    $('#ap-startup').checked = !!st.startup.enabled;
    row.title = st.startup.note;
  } catch { /* shown on the next poll */ }
}
async function setStartup(e) {
  try { st.startup = await api('/api/startup', { on: e.target.checked }); toast(st.startup.enabled ? 'Jarvus will start with Windows and keep the AI trading in the background' : 'Jarvus will not start with Windows', 'good'); }
  catch (err) { errorToast(err); e.target.checked = !e.target.checked; }
}

async function loadFees() {
  try {
    st.fees = await api('/api/fees');
    const sel = $('#ap-fees');
    if (!sel) return;
    replace(sel, st.fees.profiles.map(p => h('option', { value: p.name, selected: p.name === st.fees.current }, p.label)));
    showFeeNote();
  } catch { /* shown on the next poll */ }
}
function showFeeNote() {
  const f = st.fees, n = $('#ap-fees-note');
  if (!f || !n) return;
  const p = f.profiles.find(x => x.name === f.current) || {};
  const hi = (p.taker || 0) >= 0.008;
  replace(n, p.taker ? `Crypto trades cost ${(p.taker * 100).toFixed(2)}% per side at market (${(p.maker * 100).toFixed(2)}% with limit orders). ` : 'Each bot pays its own data source\'s fees. ',
    hi ? h('span.down', 'At this level fees are larger than most price moves, so the AI will skip nearly every crypto signal. ') : null,
    'Stocks are commission-free. Fee level changes how the AI sizes and filters trades from the next bar.');
}
async function setFees(e) {
  try { st.fees = await api('/api/fees', { profile: e.target.value }); showFeeNote(); toast('Fee level saved: the AI now judges every trade with these fees', 'good'); }
  catch (err) { errorToast(err); loadFees(); }
}

function renderAutopilot() {
  const a = st.ap;
  const box = $('#autopilot');
  if (!a || !box) return;
  const demo = S.overview && S.overview.workspace && S.overview.workspace.demo;
  const n = a.bots ?? (demo ? 24 : 311);
  box.classList.toggle('on', !!a.on);
  replace($('#ap-badge'), modeBadge(demo ? 'demo' : 'research'));
  replace($('#ap-state'), a.on ? h('span.up', a.since ? `ON since ${time(a.since, true)}` : 'ON: trading by itself') : h('span', 'OFF'),
    a.engine && !a.engine.running ? h('span.down', ' · engine stopped') : null);
  const btn = a.on
    ? h('button.btn.warn.ap-btn', { onclick: stopAutopilot }, '■ STOP AUTOPILOT')
    : h('button.btn.start.ap-btn', { onclick: startAutopilot, disabled: !!a.emergency, title: a.emergency ? 'Clear the emergency stop first' : '' }, `▶ START AUTOPILOT · ${n} BOTS`);
  replace($('#ap-button'), btn, a.emergency ? h('div.down', { style: { marginTop: '6px' } }, 'EMERGENCY STOP is on: clear it (red banner) to start autopilot.') : null);
  replace($('#ap-explain'), a.on
    ? `The AI makes every trade: ${n} bots scan their markets on every closed bar and trade the simulated research account; the brain sizes and vetoes each entry; stops, targets and exits are automatic; a walk-forward evaluation runs every ${(a.research && a.research.every_min) || 20} minutes and the volatility gate and brain are re-checked daily. It restarts with Jarvus. Real money stays off.`
    : `One press starts everything: the bot engine, all ${n} bots scanning their markets and trading the simulated research account by themselves, the brain sizing and vetoing each trade, automatic exits, and scheduled research. It keeps running and restarts when Jarvus opens. Real money stays off: live trading needs its own authorisation.`);
  const t = (k, v, sub, c) => h('div.tile', h('div.k', k), h(`div.v${c ? '.' + c : ''}`, v), sub ? h('div.s', sub) : null);
  const s2 = a.states || {};
  const td = a.today || {};
  const acct = a.account || {};
  const rq = (a.research && a.research.queue) || {};
  replace($('#ap-tiles'),
    t('Bots', a.bots ?? '—', a.bots ? `${s2.watching || 0} watching · ${s2.waiting || 0} waiting${s2.error ? ' · ' + s2.error + ' error' : ''}` : 'engine stopped'),
    t('In a trade', s2.managing_position ?? '—', 'positions being managed'),
    t('Trades today', td.trades ?? '—', td.trades ? `${td.wins} won · fees ${money(td.fees)}` : 'closed trades'),
    t('Today after fees', td.pnl_after_fees === undefined ? '—' : signed(td.pnl_after_fees), 'simulated money', cls(td.pnl_after_fees)),
    h('div.tile', h('div.k', 'Paper account (simulated)'),
      h('div.v', acct.equity === undefined || acct.equity === null ? '—' : money(acct.equity, acct.currency, 0)),
      h('div.s', acct.open_positions !== undefined ? `${acct.open_positions} open · exposure ${pct(acct.exposure_pct, 0)} · ` : '',
        h('a', { href: '#', onclick: (e) => { e.preventDefault(); changeBalance('paper-research'); } }, '✎ change balance'))),
    t('Research jobs', a.research && a.research.done_today !== undefined ? `${a.research.done_today} today` : '—', `${rq.queued || 0} queued · ${rq.running || 0} running`));
}

function changeBalance(cid) {
  const a = (S.overview && S.overview.accounts || []).find(x => x.connection_id === cid);
  if (!a) { toast('That account is not ready yet', 'bad'); return; }
  if (!a.simulated) { toast('Broker balances are what the broker reports: add funds on the broker\'s site (Broker & Money)', 'bad'); return; }
  const ap = cid === 'paper-research' && st.ap && st.ap.account && st.ap.account.equity !== undefined ? st.ap.account : null;
  const live = cid === 'paper-research' ? st.money : null;                       // the account right now, at live prices
  balanceDialog({ ...a, equity: live ? live.equity : (ap ? ap.equity : a.equity), invested: live ? live.invested : a.exposure,
    currency: a.currency || (ap && ap.currency) }, () => { loadAutopilot(); setTimeout(() => { loadEquity(); renderAccount(); }, 800); });
}

async function startAutopilot(e) {
  const b = e.target;
  b.disabled = true;
  b.textContent = 'Starting…';
  try {
    st.ap = await api('/api/autopilot', { on: true });
    toast(st.ap.engine_started ? 'Autopilot ON: the engine is starting and the bots load their market data (about a minute)' : 'Autopilot ON: every bot is trading the simulated research account', 'good');
    st.account = 'paper-research';
    renderAutopilot();
    if (S.refreshOverview) setTimeout(S.refreshOverview, 1500);
  } catch (err) { errorToast(err); loadAutopilot(); }
}
async function stopAutopilot() {
  const ok = await confirmBox('Stop autopilot?', 'The research bots stop opening new trades. Open positions keep being managed until their exits. The engine and any bots you started yourself keep running.', { okLabel: 'Stop autopilot', danger: false });
  if (!ok) return;
  try { st.ap = await api('/api/autopilot', { on: false }); toast('Autopilot OFF'); renderAutopilot(); if (S.refreshOverview) S.refreshOverview(); }
  catch (err) { errorToast(err); }
}

// ---------------------------------------------------------------- account strip
function renderAccountSelector() {
  const sel = $('#acct-sel');
  if (!sel || !S.overview) return;
  const accts = S.overview.accounts;
  if (!st.account || !accts.find(a => a.connection_id === st.account)) {
    const own = (S.overview.deployments || []).some(d => d.state !== 'stopped');
    const pref = S.overview.autopilot && !own ? ['paper-research'] : ['paper-main', 'demo-main'];
    st.account = (accts.find(a => pref.includes(a.connection_id)) || accts[0] || {}).connection_id;
  }
  replace(sel, accts.map(a => h('option', { value: a.connection_id, selected: a.connection_id === st.account },
    `${a.label}  [${modeText(a.mode)}]`)));
  loadEquity(); loadTrades();
}
function modeText(m) { return m === 'research' ? 'PAPER · RESEARCH' : String(m || '').toUpperCase(); }

function renderAccount() {
  const a = (S.overview && S.overview.accounts || []).find(x => x.connection_id === st.account);
  const tiles = $('#acct-tiles');
  if (!tiles) return;
  if (!a) { replace(tiles, h('div.empty', 'No account yet.')); return; }
  const live = S.live && (S.live.accounts || []).find(x => x.connection_id === a.connection_id);
  const x = live ? { ...a, ...Object.fromEntries(Object.entries(live).filter(([, v]) => v !== undefined)) } : a;
  const cur = x.currency || '';
  replace($('#acct-src'), modeBadge(a.mode), ' ', a.simulated ? 'simulated money · ' : '', x.source || '', x.as_of ? ` · ${time(x.as_of)}` : '');
  const bb = $('#acct-balance');
  if (bb) bb.classList.toggle('hidden', !a.simulated);        // broker balances are what the broker reports
  const t = (k, v, s, c) => h('div.tile', h('div.k', k), h(`div.v${c ? '.' + c : ''}`, v), s ? h('div.s', s) : null);
  replace(tiles,
    t('Equity', money(x.equity, cur), a.real_money ? 'real money' : 'simulated'),
    t('Buying power', money(x.buying_power, cur), a.simulated ? 'cash (no margin)' : 'as the broker reports'),
    t('Allocated to bots', money(x.allocated, cur), `${a.active_bots || 0} active bot(s)`),
    t('Realized P&L today', signed(x.realized_today), `${a.trades_today || 0} trades · total ${signed(a.realized_total)}`, cls(x.realized_today)),
    t('Unrealized P&L', signed(x.unrealized), 'open positions', cls(x.unrealized)),
    t('Exposure', x.exposure_pct === null || x.exposure_pct === undefined ? '—' : pct(x.exposure_pct, 1), money(x.exposure, cur)),
    t('Daily drawdown', x.daily_drawdown_pct === undefined || x.daily_drawdown_pct === null ? '—' : pct(-x.daily_drawdown_pct, 2), 'from today\'s peak', x.daily_drawdown_pct > 0 ? 'down' : ''));
  if (a.equity === null && a.simulated) tiles.append(h('div.note', 'The simulated account opens when the bot engine first starts.'));
}

function liveState(d) {
  renderAccount();
  for (const dep of d.deployments || []) {
    const card = document.querySelector(`[data-dep="${dep.deployment_id}"]`);
    if (!card) continue;
    const a = card.querySelector('.activity');
    if (a) replace(a, stateChip(dep.activity || dep.state));
    const u = card.querySelector('.unreal');
    if (u) { u.textContent = signed(dep.unrealized); u.className = 'unreal ' + cls(dep.unrealized); }
    const ld = card.querySelector('.lastdec');
    if (ld && dep.last_decision) ld.textContent = dep.last_decision;
  }
}

// ---------------------------------------------------------------- chart
function chartPanel() {
  const mk = h('select#mkt-sel', { 'aria-label': 'Market', style: { width: 'auto', minWidth: '170px' }, onchange: (e) => { const [v, s] = e.target.value.split('|'); st.market = { venue: v, symbol: s }; loadCandles(true); } });
  const tfs = h('div.seg', ['1m', '5m', '15m', '1h'].map(tf => h('button', { class: tf === st.tf ? 'on' : '', onclick: (e) => { st.tf = tf; e.target.parentNode.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === e.target)); loadCandles(true); } }, tf)));
  const ind = h('div.seg', Object.entries({ ema21: 'EMA21', ema50: 'EMA50', vwap: 'VWAP', bb: 'BB' }).map(([k, lab]) =>
    h('button', { class: st.ind[k] ? 'on' : '', onclick: (e) => { st.ind[k] = !st.ind[k]; e.target.classList.toggle('on', st.ind[k]); if (st.price) st.price.indicators(st.ind); } }, lab)));
  const mkBtn = h('div.seg', h('button', { class: st.markers ? 'on' : '', title: 'Show fills from your bots (paper, demo, live, research)', onclick: (e) => { st.markers = !st.markers; e.target.classList.toggle('on', st.markers); loadMarkers(); } }, 'FILLS'));
  return h('section.panel.hot', h('h2', 'Market', h('span.right', mk, tfs, ind, mkBtn)),
    h('div.chartbox#price-chart', h('div.legend#price-legend')),
    h('div.row.between', h('span.note#chart-src'), h('span.note', 'markers: ', h('span', { style: { color: '#22d3ee' } }, '▲ paper'), ' ',
      h('span', { style: { color: '#f5b301' } }, '▲ demo'), ' ', h('span', { style: { color: '#ff3b5c' } }, '▲ live'), ' ',
      h('span', { style: { color: '#8fb4ff' } }, '▲ research'))));
}

async function loadMarkets() {
  if (!st.markets) {
    try { st.markets = await api('/api/markets'); } catch (e) { st.markets = []; }
  }
  const sel = $('#mkt-sel');
  if (!sel) return;
  if (!st.market && st.markets.length) {
    const pref = st.markets.find(m => ['DEMO-BTC', 'BTC-USD'].includes(m.symbol)) || st.markets[0];
    st.market = { venue: pref.venue, symbol: pref.symbol };
  }
  replace(sel, ['crypto', 'stock'].map(asset => {
    const rows = st.markets.filter(m => m.asset === asset);
    return rows.length ? h('optgroup', { label: asset === 'crypto' ? 'Crypto' : 'Stocks' }, rows.map(m =>
      h('option', { value: `${m.venue}|${m.symbol}`, selected: st.market && m.venue === st.market.venue && m.symbol === st.market.symbol }, `${m.symbol} · ${m.venue}`))) : null;
  }));
  loadCandles(true);
}

async function loadCandles(fit = false) {
  if (!st.market || !$('#price-chart')) return;
  if (!chartsAvailable()) { replace($('#chart-src'), 'Chart library not loaded.'); return; }
  try {
    const d = await api(`/api/candles?venue=${encodeURIComponent(st.market.venue)}&symbol=${encodeURIComponent(st.market.symbol)}&tf=${st.tf}&n=300`);
    if (!d.t || !d.t.length) { replace($('#chart-src'), d.error || 'No bars for this market.'); return; }
    if (!st.price) { st.price = new PriceChart($('#price-chart'), $('#price-legend')); }
    st.price.set(d, { indicators: st.ind, fit });
    const last = d.t[d.t.length - 1];
    replace($('#chart-src'), `${d.symbol} ${d.tf} · source ${d.source} · last bar ${time(last)} · ${d.live ? 'followed live by the bots' : d.status}`);
    loadMarkers();
  } catch (e) { replace($('#chart-src'), e.message); }
}

async function loadMarkers() {
  if (!st.price || !st.market) return;
  try {
    const m = st.markers ? await api(`/api/markers?venue=${encodeURIComponent(st.market.venue)}&symbol=${encodeURIComponent(st.market.symbol)}`) : [];
    st.price.markers(m, st.tf, st.markers);
  } catch { /* markers are optional */ }
}

function onAudit(e) {
  if (e.kind === 'market_update' && st.market && e.symbol === st.market.symbol) loadCandles();
  if ((e.kind === 'fill' || e.kind === 'exit') && st.market && (e.symbol || '').endsWith(st.market.symbol)) { loadMarkers(); loadTrades(); }
  if (['control', 'fill', 'exit', 'position'].includes(e.kind)) debouncedRefresh();
}
const debouncedRefresh = debounce(() => S.refreshOverview && S.refreshOverview(), 800);

// ---------------------------------------------------------------- bot builder (strategy, market, mode, account, allocation, limits)
async function loadBuilder() {
  await loadMarkets();                                     // the builder's market list needs them first
  try { st.strategies = st.strategies || await api('/api/strategies'); } catch (e) { replace($('#builder-body'), h('div.empty', e.message)); return; }
  renderBuilder();
}

function renderBuilder() {
  const body = $('#builder-body');
  if (!body) return;
  const o = S.overview;
  if (!o) { replace(body, h('div.empty', 'Loading…')); return; }
  st.builtFor = o.workspace.id;
  const demo = o.workspace.demo;
  const strat = h('select', { 'aria-label': 'Strategy' });
  const fams = {};
  for (const s of st.strategies.runnable) (fams[s.family] = fams[s.family] || []).push(s);
  // the trained ULTRON councils first, its 1h majors council (best untouched-test result at retail fees) selected
  const famOrder = ([a], [b]) => (a === 'ultron' ? -1 : b === 'ultron' ? 1 : a.localeCompare(b));
  for (const [f, rows] of Object.entries(fams).sort(famOrder)) strat.append(h('optgroup', { label: f === 'ultron' ? 'ULTRON (trained councils)' : f.replace(/_/g, ' ') },
    rows.map(s => h('option', { value: s.id, selected: s.id === 'STRAT-U01' }, `${s.name} (${s.tf})`))));
  const market = h('select', { 'aria-label': 'Market' });
  const fillMarkets = () => replace(market, (st.markets || []).map(m => h('option', { value: `${m.venue}|${m.symbol}`, selected: st.market && m.symbol === st.market.symbol && m.venue === st.market.venue }, `${m.symbol} · ${m.venue}`)));
  fillMarkets();
  const mode = h('select', { 'aria-label': 'Mode' }, demo ? [h('option', { value: 'demo' }, 'DEMO (synthetic market, simulated money)')] :
    [h('option', { value: 'paper' }, 'PAPER (simulated money)'), h('option', { value: 'live' }, 'LIVE (real money)')]);
  const account = h('select', { 'aria-label': 'Account' });
  const fillAccounts = () => {
    const env = mode.value;
    const accts = (o ? o.accounts : []).filter(a => a.environment === env && a.connection_id !== 'paper-research');
    replace(account, accts.length ? accts.map(a => h('option', { value: a.connection_id }, `${a.label}${a.equity !== null ? ' · ' + money(a.equity, a.currency, 0) : ''}`))
      : [h('option', { value: '' }, env === 'live' ? 'no live account connected (Broker & Money)' : 'no account')]);
  };
  fillAccounts();
  mode.addEventListener('change', () => { fillAccounts(); updateBacktest(); });
  const L = (o && o.default_limits) || {};
  const alloc = h('input', { type: 'number', min: 1, step: 'any', value: demo ? 10000 : 5000, 'aria-label': 'Allocation' });
  const lim = {
    risk_per_trade_pct: h('input', { type: 'number', step: 'any', min: 0.01, max: 5, placeholder: "strategy's own" }),
    max_position_pct: h('input', { type: 'number', step: 'any', min: 1, max: 100, value: L.max_position_pct ?? 100 }),
    max_order_notional: h('input', { type: 'number', step: 'any', min: 1, placeholder: 'no extra cap' }),
    daily_loss_limit_pct: h('input', { type: 'number', step: 'any', min: 0.1, max: 50, value: L.daily_loss_limit_pct ?? 3 }),
    max_drawdown_pct: h('input', { type: 'number', step: 'any', min: 1, max: 90, value: L.max_drawdown_pct ?? 15 }),
    max_orders_per_minute: h('input', { type: 'number', step: 1, min: 1, max: 60, value: L.max_orders_per_minute ?? 4 }),
  };
  const bt = h('div.note#bt-summary');
  const result = h('div#ready-result');
  const readyBtn = h('button.btn', 'Check readiness');
  const startBtn = h('button.btn.start', { disabled: true, title: 'Run the readiness checks first' }, '▶ START BOT');
  const evalBtn = h('button.btn.ghost.small', { title: 'Queue a walk-forward evaluation of this strategy on this market' }, 'Evaluate (walk-forward)');
  let lastReady = null, botId = null;

  const spec = () => {
    const limits = {};
    for (const [k, el] of Object.entries(lim)) if (el.value !== '') limits[k] = Number(el.value);
    return { bot_id: botId, mode: mode.value, connection_id: account.value, allocation: Number(alloc.value), limits };
  };
  const invalidate = () => { lastReady = null; startBtn.disabled = true; startBtn.title = 'Run the readiness checks first'; clear(result); };
  [strat, market, mode, account, alloc, ...Object.values(lim)].forEach(el => el.addEventListener('change', invalidate));
  strat.addEventListener('change', updateBacktest);
  market.addEventListener('change', updateBacktest);

  async function ensureBot() {
    const [venue, instrument] = market.value.split('|');
    const bots = await api('/api/user_bots');
    const found = (bots || []).find(b => b.strategy_id === strat.value && b.venue === venue && b.instrument === instrument && !b.archived
      && (!b.deployment || ['stopped'].includes(b.deployment.state) || b.deployment.mode === mode.value));
    if (found) return found.bot_id;
    const b = await api('/api/bots/create', { strategy_id: strat.value, venue, instrument });
    toast(`Bot ${b.bot_id} built: ${b.name}`, 'good');
    return b.bot_id;
  }
  readyBtn.addEventListener('click', async () => {
    readyBtn.disabled = true;
    replace(result, h('div.note', 'Checking… (broker accounts are contacted now)'));
    try {
      botId = await ensureBot();
      await new Promise(r => setTimeout(r, 600));
      lastReady = await api('/api/deploy/readiness', spec());
      showReady(lastReady);
    } catch (e) { replace(result, h('div.down', e.message)); }
    readyBtn.disabled = false;
  });
  function showReady(rep) {
    const failed = rep.checks.filter(c => c.status === 'fail');
    replace(result, h('div', h('div', rep.ok ? h('b.up', 'Ready: every required check passed.') : h('b.down', `Not ready: ${failed.length} required check(s) failed.`)),
      checklist(rep.checks)));
    startBtn.disabled = !rep.ok;
    startBtn.title = rep.ok ? 'Start only this bot, in this mode' : 'Fix the failed checks first';
    startBtn.classList.toggle('danger', mode.value === 'live');
    startBtn.textContent = mode.value === 'live' ? '▶ START LIVE BOT' : '▶ START BOT';
  }
  startBtn.addEventListener('click', async () => {
    if (!lastReady || !lastReady.ok) return;
    startBtn.disabled = true;
    try {
      let res = await api('/api/deploy/start', spec());
      if (res.needs_confirmation) {
        const conf = await liveConfirm(res.confirm);
        if (!conf) { startBtn.disabled = false; return; }
        res = await api('/api/deploy/start', { ...spec(), confirmation: conf });
      }
      if (res.started) { toast(`${res.deployment.bot_id} started in ${res.deployment.mode.toUpperCase()}`, 'good'); invalidate(); S.refreshOverview(); }
      else if (res.readiness) { showReady(res.readiness); toast('START refused: ' + (res.readiness.failed || []).join('; '), 'bad'); }
    } catch (e) { errorToast(e); startBtn.disabled = false; }
  });
  evalBtn.addEventListener('click', async () => {
    const [venue, instrument] = market.value.split('|');
    try {
      const j = await api('/api/research/submit', { kind: 'walk_forward', spec: { strategy_id: strat.value, venue, instrument, days: 90, draws: 100, fee_profile: 'venue' } });
      toast(`Evaluation ${j.job_id} queued: see Live Intelligence → Research`, 'good');
    } catch (e) { errorToast(e); }
  });
  async function updateBacktest() {
    const [venue, instrument] = market.value.split('|');
    try {
      const b = await api(`/api/backtest?strategy=${encodeURIComponent(strat.value)}&symbol=${encodeURIComponent(instrument)}&venue=${encodeURIComponent(venue)}`);
      if (!b.available) { replace(bt, modeBadge('backtest'), ' ', b.note); return; }
      replace(bt, modeBadge('backtest'), ` ${b.same_market ? 'this market' : 'similar markets (' + b.markets.slice(0, 3).join(', ') + ')'}, ${b.cost_level.replace(/_/g, ' ')} costs: `,
        h('span', { class: cls(b.test.expectancy_r) }, `untouched test ${r(b.test.expectancy_r)} over ${b.test.trades} trades`),
        `; full history ${r(b.full.expectancy_r)} (${b.full.trades}). Past, measured, not a promise.`);
    } catch { clear(bt); }
  }
  replace(body,
    h('div.stack',
      h('label.f', 'Strategy', strat), h('label.f', 'Market', market), bt,
      h('div.fgrid', h('label.f', 'Mode', mode), h('label.f', 'Account', account)),
      h('label.f', 'Capital allocated to this bot', alloc),
      h('details', h('summary.dim', 'Risk limits (enforced before every order; nothing can exceed them)'),
        h('div.fgrid', { style: { marginTop: '8px' } },
          h('label.f', 'Risk per trade % of allocation', lim.risk_per_trade_pct), h('label.f', 'Max position % of allocation', lim.max_position_pct),
          h('label.f', 'Max per order (currency)', lim.max_order_notional), h('label.f', 'Daily loss limit %', lim.daily_loss_limit_pct),
          h('label.f', 'Max drawdown % (pauses the bot)', lim.max_drawdown_pct), h('label.f', 'Max orders per minute', lim.max_orders_per_minute))),
      h('div.row', readyBtn, startBtn, evalBtn),
      result,
      h('p.note', 'START runs every check again and starts only this bot, in the mode shown. LIVE also needs your separate live '
        + 'authorisation (Broker & Money) and an explicit confirmation of account, strategy, allocation and limits.')));
  updateBacktest();
}

function liveConfirm(c) {
  return new Promise((resolve) => {
    const inp = h('input', { placeholder: c.ack, autocomplete: 'off', spellcheck: false });
    let done = false;
    const ok = h('button.btn.danger', 'Start with real money');
    const lim = c.limits || {};
    const m = modal('Confirm LIVE start', h('div.stack',
      h('div.banner.live', modeBadge('live'), 'This bot will place real orders with real money.'),
      kvList([['Account', `${c.connection_id} ${(c.account && c.account.account_id) || ''}`], ['Bot', `${c.bot_id} · ${c.strategy}`],
        ['Market', c.market], ['Allocation', money(c.allocation)],
        ['Risk per trade', lim.risk_per_trade_pct ? pct(lim.risk_per_trade_pct) : "strategy's own"], ['Max position', pct(lim.max_position_pct, 0)],
        ['Max per order', lim.max_order_notional ? money(lim.max_order_notional) : 'none extra'], ['Daily loss limit', pct(lim.daily_loss_limit_pct)],
        ['Max drawdown', pct(lim.max_drawdown_pct)], ['Orders per minute', String(lim.max_orders_per_minute)]]),
      h('label.f', `Type ${c.ack} to confirm`, inp), h('div.row', ok, h('button.btn.ghost', { onclick: () => m.close() }, 'Cancel'))),
    { danger: true, onClose: () => { if (!done) resolve(null); } });
    ok.addEventListener('click', () => {
      if (inp.value.trim().toUpperCase() !== c.ack) { toast(`Type exactly: ${c.ack}`, 'bad'); return; }
      done = true; m.close();
      resolve({ ack: c.ack, connection_id: c.connection_id, allocation: c.allocation, bot_id: c.bot_id });
    });
  });
}

// ---------------------------------------------------------------- bot cards
function renderBots() {
  const box = $('#bot-cards');
  if (!box || !S.overview) return;
  const deps = S.overview.deployments || [];
  const acts = $('#bots-actions');
  if (acts) replace(acts, h('span.note', S.overview.autopilot ? 'autopilot is running the research fleet' : 'autopilot is off'));
  const cards = deps.map(botCard);
  cards.push(researchCard());
  replace(box, cards.length ? cards : h('div.empty', 'No bots started yet. Build one on the right: pick a strategy and a market, check readiness, START.'));
}

function botCard(d) {
  const b = d.bot || {};
  const p = d.performance || {};
  const pos = d.position;
  const card = h(`div.card${d.mode === 'live' ? '.live' : ''}${d.state === 'running' ? '.running' : ''}`, { dataset: { dep: d.deployment_id } },
    h('div.row.between', h('div', h('div.title', b.name || d.bot_id), h('div.sub', `${b.strategy || ''} · ${b.symbol || ''} ${b.tf || ''}`)), modeBadge(d.mode)),
    h('div.row', { style: { marginTop: '6px' } }, h('span.activity', stateChip(d.activity || d.state)), d.blocked ? h('span.badge.warn', { title: d.blocked }, 'ENTRIES BLOCKED') : null),
    kvList([
      ['Account', d.connection_id],
      ['Allocation', money(d.allocation)],
      ['Position', pos ? `${num(pos.qty)} @ ${num(pos.avg_price)}` : 'flat'],
      pos ? ['Protective stop', pos.stop_price ? num(pos.stop_price) + (pos.stop_order ? ' (on broker)' : ' (simulated)') : '—'] : null,
      ['Unrealized', h('span.unreal', { class: cls(d.unrealized) }, signed(d.unrealized))],
      [`${(d.mode || '').toUpperCase()} result after fees`, h('span', { class: cls(p.pnl_after_fees) }, `${signed(p.pnl_after_fees)} · ${p.trades || 0} trades${p.avg_r !== null && p.avg_r !== undefined ? ' · ' + r(p.avg_r) : ''}`)],
    ]),
    h('div.note.lastdec', b.last_decision || d.stop_reason || ''),
    h('div.row', { style: { marginTop: '8px' } },
      d.state === 'running' ? h('button.btn.warn.small', { onclick: () => pause(d) }, '⏸ PAUSE NEW ENTRIES') : null,
      d.state === 'paused' ? h('button.btn.small', { onclick: () => resume(d) }, '▶ RESUME') : null,
      ['running', 'paused', 'stopped_retaining', 'error'].includes(d.state) ? h('button.btn.danger.small', { onclick: () => stopFlow(d) }, '■ STOP') : null,
      h('button.btn.ghost.small', { onclick: () => details(d) }, 'Details')));
  return card;
}

function researchCard() {
  const a = (S.overview.accounts || []).find(x => x.connection_id === 'paper-research');
  return h('div.card', h('div.row.between', h('div', h('div.title', 'Research fleet'), h('div.sub', 'the registry\'s bots: always evaluating; their signals feed the scanner and the brain')), modeBadge('research')),
    kvList([['Autopilot', S.overview.autopilot ? 'ON: trading its own simulated account' : 'OFF: watching only'],
      ['Research paper equity', a ? money(a.equity, a.currency) : '—'], ['Realized today', a ? signed(a.realized_today) : '—']]),
    h('div.note', 'This is the account the AI trades (see Your money at the top).'),
    h('a.btn.ghost.small', { href: '#/intel' }, 'See every bot live →'));
}

async function pause(d) {
  try { await api('/api/deploy/pause', { deployment_id: d.deployment_id }); toast(`${d.bot_id}: new entries paused; positions still managed`, 'good'); S.refreshOverview(); } catch (e) { errorToast(e); }
}
async function resume(d) {
  try { await api('/api/deploy/resume', { deployment_id: d.deployment_id }); toast(`${d.bot_id} resumed`, 'good'); S.refreshOverview(); } catch (e) { errorToast(e); }
}

function stopFlow(d) {
  const out = h('div');
  const run = async (positions) => {
    try {
      replace(out, h('div.note', positions === 'close' ? 'Closing the position… (market order; results below)' : 'Stopping…'));
      const r2 = await api('/api/deploy/stop', { deployment_id: d.deployment_id, positions });
      const c = r2.close;
      replace(out, h('div.stack',
        h('div', `Entry orders canceled: ${(r2.entry_orders || []).filter(x => x.ok).length} of ${(r2.entry_orders || []).length}.`),
        c ? h('div', { class: c.status === 'filled' ? 'up' : 'down' }, `Close: ${c.status}${c.qty ? ' · sold ' + num(c.qty) : ''}${c.avg_price ? ' @ ' + num(c.avg_price) : ''}${c.left ? ' · STILL OPEN ' + num(c.left) : ''}${c.reason ? ' · ' + c.reason : ''}`) : null,
        h('div', 'Bot state: ', stateChip(r2.deployment.state))));
      S.refreshOverview();
    } catch (e) { replace(out, h('div.down', e.message)); }
  };
  modal(`STOP ${d.bot_id}`, h('div.stack',
    h('p', 'New entries are blocked at once and working entry orders are canceled. Then choose what happens to an open position:'),
    h('div.grid.g-2',
      h('div.panel', h('h3', 'Retain protective orders'), h('p.note', 'The position stays open with its protective stop (resting on the broker for broker accounts, watched on completed bars for simulated ones). The strategy stops acting. You can close it later.'),
        h('button.btn.warn', { onclick: () => run('retain') }, 'Stop, keep protection')),
      h('div.panel', h('h3', 'Close the position'), h('p.note', 'The protective stop is canceled and the position is sold with market orders. Anything that does not fill is reported and stays protected.'),
        h('button.btn.danger', { onclick: () => run('close') }, 'Stop and close'))),
    out), { danger: d.mode === 'live' });
}

async function details(d) {
  const body = h('div.stack', h('div.empty', 'Loading…'));
  drawer(`${d.bot_id} · ${d.bot ? d.bot.name : ''}`, body);
  try {
    const [orders, trades, bot] = await Promise.all([api(`/api/orders?deployment=${d.deployment_id}&limit=50`),
      api(`/api/trades?deployment=${d.deployment_id}&limit=50`), api(`/api/bot/${encodeURIComponent(d.bot_id)}`)]);
    const L = d.limits || {};
    const inputs = {};
    const limitForm = h('div.fgrid', Object.entries({ risk_per_trade_pct: 'Risk per trade %', max_position_pct: 'Max position %', max_order_notional: 'Max per order',
      daily_loss_limit_pct: 'Daily loss limit %', max_drawdown_pct: 'Max drawdown %', max_orders_per_minute: 'Orders per minute' }).map(([k, lab]) =>
      h('label.f', lab, inputs[k] = h('input', { type: 'number', step: 'any', value: L[k] ?? '' }))));
    const sig = (bot && bot.recent_signals || [])[0];
    replace(body,
      h('div.row', modeBadge(d.mode), stateChip(d.activity || d.state), h('span.note', `started ${time(d.started, true)}`)),
      h('h3', 'Risk limits'), limitForm,
      h('button.btn.small', { onclick: async () => {
        const limits = {};
        for (const [k, el] of Object.entries(inputs)) if (el.value !== '') limits[k] = Number(el.value);
        try { await api('/api/deploy/limits', { deployment_id: d.deployment_id, limits }); toast('Limits saved (they apply to the next order)', 'good'); } catch (e) { errorToast(e); }
      } }, 'Save limits'),
      h('h3', 'Latest rule evaluation'), sig ? h('div', h('div.note', `${time(sig.decision_time, true)} · ${sig.action}: ${sig.reason}`),
        h('ul.checks', (sig.rules || []).map(x => h(`li.${x.passed ? 'pass' : 'fail'}`, h('span.i', x.passed ? '✓' : '✕'), h('div', x.rule, x.detail ? h('div.d', x.detail) : null)))))
        : h('div.note', 'No evaluation yet.'),
      h('h3', 'Orders'), table([{ label: 'Time', v: o => time(o.created) }, { label: 'Purpose', v: o => o.purpose }, { label: 'Side', v: o => o.side },
        { label: 'Type', v: o => `${o.order_type} ${o.tif || ''}` }, { label: 'Qty', n: true, v: o => num(o.qty) }, { label: 'Filled', n: true, v: o => num(o.filled_qty) },
        { label: 'Avg', n: true, v: o => num(o.avg_price) }, { label: 'State', v: o => o.state }], orders, { empty: 'No orders yet.' }),
      h('h3', 'Trades'), table([{ label: 'Exit', v: t => time(t.exit_time, true) }, { label: 'Qty', n: true, v: t => num(t.qty) },
        { label: 'Entry', n: true, v: t => num(t.entry_price) }, { label: 'Exit px', n: true, v: t => num(t.exit_price) },
        { label: 'P&L', n: true, v: t => signed(t.pnl), cls: t => cls(t.pnl) }, { label: 'R', n: true, v: t => r(t.r) }, { label: 'Why', v: t => t.exit_reason }], trades, { empty: 'No closed trades yet.' }));
  } catch (e) { replace(body, h('div.down', e.message)); }
}

// ---------------------------------------------------------------- equity, trades, alerts
async function loadEquity() {
  if (!st.account || !st.eq) return;
  try {
    const d = await api(`/api/equity?connection=${encodeURIComponent(st.account)}`);
    st.eq.set(d.equity, 'equity');
    st.dd.set(d.drawdown, 'drawdown_pct');
    replace($('#eq-note'), `${d.equity.length} points · max drawdown ${pct(d.max_drawdown_pct)}`);
  } catch { /* shown as empty */ }
}

async function loadTrades() {
  if (!st.account) return;
  const box = $('#trades');
  if (!box) return;
  try {
    const rows = await api(`/api/trades?connection=${encodeURIComponent(st.account)}&limit=40`);
    replace(box, table([
      { label: 'Closed', v: t => time(t.exit_time, true) }, { label: 'Mode', v: t => modeBadge(t.deployment_id ? t.mode : 'research') },
      { label: 'Bot', v: t => t.bot_id }, { label: 'Market', v: t => t.instrument }, { label: 'P&L', n: true, v: t => signed(t.pnl), cls: t => cls(t.pnl) },
      { label: 'R', n: true, v: t => r(t.r) }, { label: 'Exit', v: t => t.exit_reason }], rows, { empty: 'No closed trades on this account yet.' }));
  } catch (e) { replace(box, h('div.empty', e.message)); }
}

function renderAlerts() {
  const box = $('#alerts');
  if (!box || !S.overview) return;
  replace(box, table([{ label: 'Time', v: e => time(e.ts) }, { label: 'Level', v: e => h(`span.badge.${e.severity === 'warning' ? 'warn' : 'bad'}`, e.severity) },
    { label: 'What', v: e => e.summary }], S.overview.alerts, { empty: 'No warnings in the last 24 hours.' }));
}
