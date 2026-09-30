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
  st.builtFor = null;
  const acctSel = h('select#acct-sel', { 'aria-label': 'Account', style: { width: 'auto', minWidth: '220px' }, onchange: (e) => { st.account = e.target.value; renderAccount(); loadEquity(); loadTrades(); } });
  view.append(
    autopilotPanel(),
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
  loadBuilder();
  st.timers.push(setInterval(() => { loadEquity(); loadTrades(); }, 30000), setInterval(loadCandles, 20000));
}

export function unmount() {
  st.timers.forEach(clearInterval); st.unsub.forEach(f => f());
  st.charts.forEach(c => c.destroy()); st.charts = [];
  if (st.price) { st.price.destroy(); st.price = null; }
}

// ---------------------------------------------------------------- AUTOPILOT: the one button
function autopilotPanel() {
  return h('section.panel.autopilot#autopilot',
    h('div.ap-grid',
      h('div.ap-left',
        h('div.row', h('span.ap-title', 'AI AUTOPILOT'), h('span#ap-badge'), h('span#ap-state.note')),
        h('div#ap-button', { style: { margin: '12px 0' } }),
        h('p.note#ap-explain')),
      h('div.tiles#ap-tiles')));
}

async function loadAutopilot() {
  if (!$('#autopilot')) return;
  try { st.ap = await api('/api/autopilot'); renderAutopilot(); } catch (e) { /* shown on the next poll */ }
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
    h('div.tile', h('div.k', 'AI account (simulated)'),
      h('div.v', acct.equity === undefined || acct.equity === null ? '—' : money(acct.equity, acct.currency, 0)),
      h('div.s', acct.open_positions !== undefined ? `${acct.open_positions} open · exposure ${pct(acct.exposure_pct, 0)} · ` : '',
        h('a', { href: '#', onclick: (e) => { e.preventDefault(); changeBalance('paper-research'); } }, '✎ change balance'))),
    t('Research jobs', a.research && a.research.done_today !== undefined ? `${a.research.done_today} today` : '—', `${rq.queued || 0} queued · ${rq.running || 0} running`));
}

function changeBalance(cid) {
  const a = (S.overview && S.overview.accounts || []).find(x => x.connection_id === cid);
  if (!a) { toast('That account is not ready yet', 'bad'); return; }
  if (!a.simulated) { toast('Broker balances are what the broker reports: add funds on the broker\'s site (Connections)', 'bad'); return; }
  const ap = cid === 'paper-research' && st.ap && st.ap.account && st.ap.account.equity !== undefined ? st.ap.account : null;
  balanceDialog({ ...a, equity: ap ? ap.equity : a.equity, currency: a.currency || (ap && ap.currency) }, () => { loadAutopilot(); setTimeout(() => { loadEquity(); renderAccount(); }, 800); });
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
  for (const [f, rows] of Object.entries(fams).sort()) strat.append(h('optgroup', { label: f.replace(/_/g, ' ') },
    rows.map(s => h('option', { value: s.id }, `${s.name} (${s.tf})`))));
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
      : [h('option', { value: '' }, env === 'live' ? 'no live account connected (Connections)' : 'no account')]);
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
        + 'authorisation (Connections) and an explicit confirmation of account, strategy, allocation and limits.')));
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
    h('div.note', 'Kept apart from your accounts: its results are labelled PAPER · RESEARCH.'),
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
