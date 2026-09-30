// PAGE 2 - CONNECTIONS & FUNDING: every account connection (simulated paper, Alpaca paper/live, Kraken, NDAX) with its
// identity, environment, status, permissions, buying power and last sync; connect / test / sync / reconnect /
// disconnect; "Add funds" opens the provider's own site (never a simulated deposit); the separate live-trading
// authorisation; the AI research assistant's key and budget; news feeds.
import { S, h, $, api, replace, toast, errorToast, modal, confirmBox, modeBadge, money, time, ago, checklist, kvList, balanceDialog } from './core.js';

const st = { data: null, timers: [] };

export function mount(view) {
  st.timers = [];
  view.append(
    h('section.panel.hot', h('h2', 'Accounts and connections', h('span.right#conn-actions')),
      h('p.note#conn-note'), h('div.cards#conn-cards', h('div.empty', 'Loading…'))),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('section.panel#add-conn', h('h2', 'Connect an account'), h('div#add-body')),
      h('section.panel#live-auth', h('h2', 'Live trading authorisation'), h('div#live-body'))),
    h('div.grid.g-2', { style: { marginTop: '12px' } },
      h('section.panel#assistant', h('h2', 'AI research assistant'), h('div#asst-body')),
      h('section.panel#news', h('h2', 'News feeds', h('span.right.note', 'external, unverified')), h('div#news-body'))));
  load();
  st.timers.push(setInterval(load, 30000));
}

export function unmount() { st.timers.forEach(clearInterval); }

async function load() {
  try {
    st.data = await api('/api/connections');
    render();
  } catch (e) { if (e.status !== 401) errorToast(e); }
}

function render() {
  const d = st.data;
  if (!d || !$('#conn-cards')) return;
  const demo = S.overview && S.overview.workspace && S.overview.workspace.demo;
  replace($('#conn-note'),
    `Credentials are encrypted on this computer (${d.secret_store}) and are never shown again, sent to the page, or written to logs. `,
    'Jarvus asks only for trading and read permissions, never withdrawal. Balances are what the provider reports, with the time they were read.');
  replace($('#conn-cards'), d.connections.map(card));
  if (demo) {
    replace($('#add-body'), h('div.banner.demo', 'This is the DEMO workspace: a synthetic market and simulated money only. Switch to your main workspace (top bar) to connect a real paper or live account.'));
    replace($('#live-body'), h('p.note', 'Live trading is not available in the demo workspace.'));
  } else {
    if (!$('#add-body').dataset.built) addForm();
    liveAuth();
  }
  assistant();
  newsPanel();
}

// ---------------------------------------------------------------- connection cards
const STATUS_DOT = { connected: 'on', untested: 'warn', needs_credentials: 'warn', error: 'bad', disconnected: '' };

function envMode(c) { return c.environment === 'live' ? 'live' : c.environment === 'demo' ? 'demo' : 'paper'; }

function card(c) {
  const spec = st.data.providers[c.provider] || {};
  const lt = c.latest || {};
  const perms = c.permissions || {};
  const caps = c.capabilities || {};
  const acct = c.account || {};
  const permText = Object.keys(perms).length ? Object.entries(perms).map(([k, v]) => `${k}: ${v ? 'yes' : 'no'}`).join(', ')
    : (c.provider === 'jarvus_paper' ? 'simulated' : 'not reported by the provider');
  const ot = caps.order_types ? caps.order_types.join(', ') : null;
  const last = c.last_test && c.last_test.checks ? c.last_test : null;
  const buttons = [
    h('button.btn.small', { onclick: () => test(c) }, 'Test'),
    c.enabled !== 0 ? h('button.btn.small', { onclick: () => sync(c) }, 'Sync') : null,
    c.provider !== 'jarvus_paper' && (c.status === 'disconnected' || c.status === 'error' || c.enabled === 0)
      ? h('button.btn.small', { onclick: () => reconnect(c) }, 'Reconnect') : null,
    c.auth_method === 'oauth' && c.status === 'needs_credentials' ? h('button.btn.small.primary', { onclick: () => oauthGo(c.connection_id, c.environment) }, 'Sign in with Alpaca') : null,
    h('button.btn.small.primary', { onclick: () => addFunds(c) }, c.simulated ? 'Set simulated balance' : 'Add funds ↗'),
    c.provider !== 'jarvus_paper' && c.enabled !== 0 ? h('button.btn.small.warn', { onclick: () => disconnect(c) }, 'Disconnect') : null,
    c.provider !== 'jarvus_paper' ? h('button.btn.small.ghost', { onclick: () => removeConn(c) }, 'Remove') : null,
  ];
  return h(`div.card${c.real_money ? '.live' : ''}`, { dataset: { conn: c.connection_id } },
    h('div.row.between', h('div', h('div.title', c.label), h('div.sub', `${c.provider_label} · ${c.connection_id}`)),
      h('div.chips', modeBadge(envMode(c)), h('span.pill', h(`span.dot${STATUS_DOT[c.status] ? '.' + STATUS_DOT[c.status] : ''}`), c.status.replace(/_/g, ' ')))),
    c.real_money ? h('div.banner.live', { style: { marginTop: '8px' } }, 'REAL MONEY account. Orders here are real only after you authorise live trading and confirm each live bot.') : null,
    kvList([
      ['Account', acct.account_id ? `${acct.account_id}${acct.status ? ' (' + acct.status + ')' : ''}` : (c.simulated ? 'simulated inside Jarvus' : '—')],
      ['Environment', c.environment.toUpperCase()],
      ['Sign-in', c.auth_method === 'none' ? 'none needed' : c.auth_method === 'oauth' ? 'OAuth' : 'API key'],
      c.provider !== 'jarvus_paper' ? ['Credentials', c.has_credentials ? `stored encrypted (${c.secret_store})` : 'missing', c.has_credentials ? '' : 'down'] : null,
      ['Equity', lt.equity !== undefined && lt.equity !== null ? money(lt.equity, lt.currency) : '—'],
      ['Buying power', lt.buying_power !== undefined && lt.buying_power !== null ? money(lt.buying_power, lt.currency) : '—'],
      ['Last sync', c.last_sync ? `${ago(c.last_sync)} (${time(c.last_sync, true)})` : 'never'],
      lt.latency_ms ? ['Round trip', `${Math.round(lt.latency_ms)} ms`] : null,
      ['Permissions', permText],
      ['Assets', (spec.asset_classes || []).join(', ') || '—'],
      ot ? ['Order types', ot] : null,
      caps.protective_stop_by_class ? ['Protective stops', Object.entries(caps.protective_stop_by_class).map(([k, v]) => `${k}: ${v}`).join(', ')] : null,
      c.last_error ? ['Last error', c.last_error, 'down'] : null,
    ]),
    last ? h('details', h('summary.note', `Last test ${last.ok ? 'passed' : 'FAILED'} · ${ago(last.time)}${last.latency_ms ? ` · ${Math.round(last.latency_ms)} ms` : ''}`), checklist(last.checks)) : null,
    h('div.row', { style: { marginTop: '8px' } }, buttons));
}

async function test(c) {
  try {
    const r = await api('/api/connections/test', { connection_id: c.connection_id });
    modal(`Connection test: ${c.label}`, h('div.stack', h('p', r.ok ? 'All required checks passed.' : 'Some required checks FAILED.'), checklist(r.checks),
      r.latency_ms ? h('p.note', `Authentication round trip ${Math.round(r.latency_ms)} ms.`) : null));
    load();
  } catch (e) { errorToast(e); }
}
async function sync(c) {
  try { await api('/api/connections/sync', { connection_id: c.connection_id }); toast(`${c.label}: balances read from the provider`, 'good'); load(); }
  catch (e) { errorToast(e); }
}
async function reconnect(c) {
  try { const r = await api('/api/connections/reconnect', { connection_id: c.connection_id }); toast(`${c.label}: ${r.ok ? 'reconnected' : 'test failed'}`, r.ok ? 'good' : 'bad'); load(); }
  catch (e) { errorToast(e); }
}
async function disconnect(c) {
  const ok = await confirmBox(`Disconnect ${c.label}?`, 'Its credentials are deleted from the vault. Bots cannot use it until you connect again with new credentials. Running bots on it must be stopped first.', { okLabel: 'Disconnect' });
  if (!ok) return;
  try { await api('/api/connections/disconnect', { connection_id: c.connection_id, forget: true }); toast(`${c.label} disconnected`, 'good'); load(); }
  catch (e) { errorToast(e); }
}
async function removeConn(c) {
  const ok = await confirmBox(`Remove ${c.label}?`, 'The connection and its stored credentials are deleted. Past orders and trades stay in the history.', { okLabel: 'Remove' });
  if (!ok) return;
  try { await api('/api/connections/remove', { connection_id: c.connection_id }); toast(`${c.label} removed`, 'good'); load(); }
  catch (e) { errorToast(e); }
}

// ---------------------------------------------------------------- funding
async function addFunds(c) {
  if (c.simulated) return simBalance(c.connection_id, c.label, envMode(c));
  try {
    const f = await api('/api/funding/' + encodeURIComponent(c.connection_id));
    if (!f.url) { modal('Add funds', h('p', f.note || 'This provider has no funding page Jarvus can open.')); return; }
    modal(f.label || 'Add funds', h('div.stack',
      h('p', f.note || ''),
      h('p.note', 'Jarvus never moves money and never asks for withdrawal permission. The balance here changes only after the provider reports it.'),
      h('div.row', h('a.btn.primary', { href: f.url, target: '_blank', rel: 'noopener noreferrer' }, `Open ${new URL(f.url).hostname} ↗`))));
  } catch (e) { errorToast(e); }
}

export function simBalance(cid, label, mode) {
  const c = (st.data && st.data.connections || []).find(x => x.connection_id === cid) || {};
  const lt = c.latest || {};
  const a = (S.overview && S.overview.accounts || []).find(x => x.connection_id === cid) || {};
  balanceDialog({ connection_id: cid, label, mode: cid === 'paper-research' ? 'research' : mode,
    equity: a.equity ?? lt.equity, currency: a.currency || lt.currency }, () => load());
}

// ---------------------------------------------------------------- add a connection
function addForm() {
  const box = $('#add-body');
  box.dataset.built = '1';
  const P = st.data.providers;
  const provSel = h('select', Object.entries(P).filter(([k]) => k !== 'jarvus_paper').map(([k, v]) => h('option', { value: k }, v.label)));
  const envSel = h('select');
  const authSel = h('select');
  const fieldsBox = h('div.stack');
  const info = h('div.stack');
  const out = h('div');
  const label = h('input', { placeholder: 'optional name', maxLength: 60, autocomplete: 'off' });
  let inputs = {};
  const redraw = () => {
    const p = P[provSel.value];
    const env = envSel.value;
    replace(envSel, p.environments.map(e => h('option', { value: e, selected: e === env }, e === 'live' ? 'LIVE (real money)' : 'PAPER (the provider\'s simulated account)')));
    const au = authSel.value;
    replace(authSel, p.auth.map(a => h('option', { value: a, selected: a === au }, a === 'oauth' ? 'OAuth (your own Alpaca OAuth app)' : 'API key')));
    inputs = {};
    const opts = Object.entries(p.options || {}).map(([k, vals]) => { inputs['opt:' + k] = h('select', vals.map(v => h('option', { value: v }, v))); return h('label.f', k === 'feed' ? 'Stock data feed' : k === 'quote' ? 'Quote currency' : k, inputs['opt:' + k]); });
    if (authSel.value === 'oauth') {
      const app = st.data.oauth_app;
      const cidIn = h('input', { autocomplete: 'off', placeholder: app && app.client_id ? app.client_id : 'client id' });
      const csIn = h('input', { type: 'password', autocomplete: 'off', placeholder: app && app.configured ? 'stored (enter to replace)' : 'client secret' });
      replace(fieldsBox,
        h('p.note', 'OAuth signs you in on Alpaca\'s own site. Jarvus does not ship an OAuth app: register one with Alpaca (Connect API) and use this redirect URI:'),
        h('code.mono', st.data.redirect_uri),
        h('div.fgrid', h('label.f', 'OAuth client id', cidIn), h('label.f', 'OAuth client secret', csIn)),
        h('button.btn.small', { type: 'button', onclick: async () => {
          try { await api('/api/oauth/app', { client_id: cidIn.value, client_secret: csIn.value }); csIn.value = ''; toast('OAuth app saved (encrypted)', 'good'); await load(); }
          catch (e) { errorToast(e); }
        } }, 'Save OAuth app'),
        opts.length ? h('div.fgrid', opts) : null);
    } else {
      const flds = p.fields.map(f => {
        inputs[f] = h('input', { type: f === 'user_id' ? 'text' : 'password', autocomplete: 'off', spellcheck: false, placeholder: f === 'key' ? 'API key' : f === 'secret' ? 'API secret' : 'User ID' });
        return h('label.f', f === 'key' ? 'API key' : f === 'secret' ? 'API secret' : 'User ID', inputs[f]);
      });
      replace(fieldsBox, h('div.fgrid', flds, opts));
    }
    replace(info,
      h('p', p.summary),
      p.key_help ? h('p.note', h('b', 'Creating a key: '), p.key_help) : null,
      h('p.note', h('b', 'Eligibility: '), p.eligibility),
      p.docs ? h('p.note', 'Provider API documentation: ', h('a', { href: p.docs, target: '_blank', rel: 'noopener noreferrer' }, p.docs)) : null,
      envSel.value === 'live' ? h('div.banner.live', 'A LIVE connection can see and trade real money. Adding it does not enable trading: live orders stay off until you authorise live trading (right) and confirm each live bot.') : null);
  };
  provSel.addEventListener('change', () => { envSel.value = ''; authSel.value = ''; redraw(); });
  envSel.addEventListener('change', redraw);
  authSel.addEventListener('change', redraw);
  const go = h('button.btn.primary', { type: 'submit' }, 'Connect and test');
  const form = h('form.stack', {
    onsubmit: async (e) => {
      e.preventDefault();
      const p = provSel.value;
      const options = {};
      for (const [k, el] of Object.entries(inputs)) if (k.startsWith('opt:')) options[k.slice(4)] = el.value;
      if (authSel.value === 'oauth') { oauthGo(null, envSel.value); return; }
      const credentials = {};
      for (const f of P[p].fields) credentials[f] = inputs[f].value;
      go.disabled = true;
      try {
        const r = await api('/api/connections/create', { provider: p, environment: envSel.value, credentials, options, label: label.value || undefined });
        for (const f of P[p].fields) inputs[f].value = '';
        replace(out, h('div.stack', h('p', `${r.connection.label} added as ${r.connection.connection_id}. Test ${r.test.ok ? 'passed' : 'FAILED'}:`), checklist(r.test.checks)));
        load();
      } catch (err) { errorToast(err); }
      finally { go.disabled = false; for (const f of P[p].fields) if (inputs[f]) inputs[f].value = ''; }
    }
  }, h('div.fgrid3', h('label.f', 'Provider', provSel), h('label.f', 'Environment', envSel), h('label.f', 'Sign-in', authSel)),
  fieldsBox, h('label.f', 'Name', label), info, go, out);
  replace(box, form);
  redraw();
}

async function oauthGo(cid, environment) {
  try {
    const r = await api('/api/oauth/start', { connection_id: cid || undefined, environment });
    location.href = r.url;                      // Alpaca's own sign-in page; it returns to /oauth/callback
  } catch (e) { errorToast(e); load(); }
}

// ---------------------------------------------------------------- live authorisation
function liveAuth() {
  const d = st.data;
  const la = d.live_authorization || {};
  const box = $('#live-body');
  const live = d.connections.filter(c => c.environment === 'live' && c.enabled !== 0);
  const intro = h('p.note', 'Real-money orders are OFF by default. This switch lets live bots place real orders on the accounts you tick, within the caps you set. Each live bot still needs its own readiness checks and a typed START LIVE confirmation. Revoking pauses every live bot at once.');
  if (la.authorized) {
    replace(box, intro,
      h('div.banner.live', h('b', 'LIVE TRADING AUTHORISED'), ` since ${time(la.time, true)}`),
      kvList([['Accounts', (la.connections || []).join(', ')], ['Total allocation cap', money(la.max_total_allocation)],
        ['Daily loss limit (all live bots)', money(la.daily_loss_limit)], ['Paper-record requirement', la.waive_eligibility ? 'WAIVED by you' : 'required']]),
      h('button.btn.danger', { onclick: revoke }, 'Revoke live authorisation (pauses live bots)'));
    return;
  }
  if (!live.length) {
    replace(box, intro, h('p', 'No live account is connected. Connect one on the left first (Alpaca Live, Kraken Pro or NDAX).'),
      la.revoked ? h('p.note', `Last revoked ${time(la.revoked, true)} (${la.revoke_reason || 'owner'}).`) : null);
    return;
  }
  const boxes = live.map(c => ({ c, el: h('input', { type: 'checkbox', disabled: c.status !== 'connected' }) }));
  const cap = h('input', { type: 'number', min: '0', step: '10', placeholder: 'e.g. 500' });
  const loss = h('input', { type: 'number', min: '0', step: '5', placeholder: 'e.g. 25' });
  const waive = h('input', { type: 'checkbox' });
  const ack = h('input', { placeholder: d.live_ack, autocomplete: 'off', spellcheck: false });
  replace(box, intro,
    h('div.stack', boxes.map(({ c, el }) => h('label.check', el, modeBadge('live'), ` ${c.label} (${c.connection_id})`, c.status !== 'connected' ? h('span.down', ' - test it first') : null))),
    h('div.fgrid', h('label.f', 'Max total allocation across live bots', cap), h('label.f', 'Daily loss limit across live bots', loss)),
    h('label.check', waive, 'Waive the paper-record requirement (a strategy normally needs a paper/demo record on the same market before it may go live)'),
    h('label.f', `Type ${d.live_ack}`, ack),
    h('button.btn.danger', { onclick: async () => {
      const conns = boxes.filter(b => b.el.checked).map(b => b.c.connection_id);
      try {
        await api('/api/live/authorize', { ack: ack.value, connections: conns, max_total_allocation: Number(cap.value), daily_loss_limit: Number(loss.value), waive_eligibility: waive.checked });
        toast('Live trading authorised within your caps', 'good');
        if (S.refreshOverview) S.refreshOverview();
        load();
      } catch (e) { errorToast(e); }
    } }, 'Authorise live trading'),
    h('p.note', 'Needs the bot engine running. Nothing trades until you start a live bot on Command Center.'));
}

async function revoke() {
  const ok = await confirmBox('Revoke live trading?', 'Every running live bot is paused (no new entries). Open positions keep their protective orders.', { okLabel: 'Revoke' });
  if (!ok) return;
  try { const r = await api('/api/live/revoke', {}); toast(`Live authorisation revoked; ${(r.paused || []).length} live bot(s) paused`, 'good'); if (S.refreshOverview) S.refreshOverview(); load(); }
  catch (e) { errorToast(e); }
}

// ---------------------------------------------------------------- AI assistant
function assistant() {
  const a = st.data.assistant;
  const box = $('#asst-body');
  if (!box || box.contains(document.activeElement)) return;     // don't redraw under the cursor
  const key = h('input', { type: 'password', autocomplete: 'off', spellcheck: false, placeholder: a.has_key ? 'stored (enter a new key to replace)' : 'sk-ant-…' });
  const b = a.budget || {};
  const req = h('input', { type: 'number', min: '0', value: b.max_requests_per_day });
  const tin = h('input', { type: 'number', min: '0', step: '1000', value: b.max_input_tokens_per_day });
  const tout = h('input', { type: 'number', min: '0', step: '1000', value: b.max_output_tokens_per_day });
  const en = h('input', { type: 'checkbox', checked: a.enabled });
  const u = a.usage_today || {};
  replace(box,
    h('div.row', h('span.pill', h(`span.dot${a.available ? '.on' : '.warn'}`), a.available ? 'ready' : 'not available'), h('span.note', a.why_not || '')),
    kvList([['Model', a.model], ['Python SDK', a.sdk ? 'installed' : 'not installed'], ['API key', a.has_key ? 'stored encrypted' : 'none'],
      ['Used today', `${u.requests || 0} requests · ${(u.input_tokens || 0).toLocaleString()} in · ${(u.output_tokens || 0).toLocaleString()} out tokens`],
      ['Refusals', a.fallback], ['Runs', a.runs], ['Can trade', 'no - it cannot place, change or cancel orders']]),
    h('p.note', 'It summarises the log, explains a decision, drafts strategy ideas for testing (they are compiled and registered as research versions, never traded) and summarises headlines. Everything it reads from logs or feeds is treated as data, never as instructions.'),
    h('form.stack', {
      onsubmit: async (e) => {
        e.preventDefault();
        try {
          st.data.assistant = await api('/api/assistant/config', { api_key: key.value || undefined, enabled: en.checked,
            budget: { max_requests_per_day: req.value, max_input_tokens_per_day: tin.value, max_output_tokens_per_day: tout.value } });
          key.value = ''; toast('Assistant settings saved', 'good'); document.activeElement && document.activeElement.blur(); assistant();
        } catch (err) { key.value = ''; errorToast(err); }
      }
    }, h('label.f', 'Anthropic API key', key),
    h('div.fgrid3', h('label.f', 'Requests / day', req), h('label.f', 'Input tokens / day', tin), h('label.f', 'Output tokens / day', tout)),
    h('label.check', en, 'Enabled'),
    h('div.row', h('button.btn.primary', { type: 'submit' }, 'Save'),
      a.has_key ? h('button.btn.ghost', { type: 'button', onclick: async () => { try { st.data.assistant = await api('/api/assistant/forget', {}); toast('Key deleted from the vault', 'good'); assistant(); } catch (e) { errorToast(e); } } }, 'Delete key') : null)));
}

// ---------------------------------------------------------------- news feeds
function newsPanel() {
  const n = st.data.news || {};
  const box = $('#news-body');
  if (!box || box.contains(document.activeElement)) return;
  const ta = h('textarea', { rows: 3, placeholder: 'https://… one RSS or Atom feed per line (https only, up to 12)' });
  ta.value = (n.feeds || []).join('\n');
  const out = h('div');
  replace(box,
    h('p.note', n.note || ''),
    h('label.f', 'Feeds', ta),
    h('div.row',
      h('button.btn.small', { onclick: async () => { try { await api('/api/news/feeds', { feeds: ta.value.split('\n').map(x => x.trim()).filter(Boolean) }); toast('Feeds saved', 'good'); load(); } catch (e) { errorToast(e); } } }, 'Save feeds'),
      h('button.btn.small', { onclick: async () => { try { const r = await api('/api/news/refresh', {}); toast(`Read ${r.items ? r.items.length : 0} headlines`, 'good'); load(); } catch (e) { errorToast(e); } } }, 'Refresh now'),
      h('button.btn.small', { onclick: async () => {
        replace(out, h('p.note', 'Asking the assistant…'));
        try { const r = await api('/api/assistant/news', {}); replace(out, aiText(r)); } catch (e) { replace(out); errorToast(e); }
      } }, 'Summarise with AI'),
      n.fetched ? h('span.note', `fetched ${ago(n.fetched)}`) : null),
    Object.keys(n.errors || {}).length ? h('div.note.down', Object.entries(n.errors).map(([u, e]) => h('div', `${u}: ${e}`))) : null,
    out,
    (n.items || []).length ? h('ul.checks', n.items.slice(0, 20).map(x => h('li.skip', h('span.i', '·'),
      h('div', x.link && /^https:\/\//.test(x.link) ? h('a', { href: x.link, target: '_blank', rel: 'noopener noreferrer' }, x.title) : x.title,
        h('div.d', `${x.source || ''}${x.published ? ' · ' + time(x.published, true) : ''}`))))) : h('div.empty', 'No headlines. Add a feed above.'));
}

export function aiText(r) {
  if (r.refused) return h('div.banner', 'The model declined this request.' + (r.category ? ` (${r.category})` : ''));
  const v = r.validation || {};
  return h('div.stack',
    h('div.row', h('span.badge.backtest', 'AI-GENERATED'), h('span.note', r.label || ''), r.model ? h('span.note', r.model) : null),
    v.unknown_citations && v.unknown_citations.length ? h('div.banner', `Cites events that were not supplied: ${v.unknown_citations.join(', ')}. Treat those statements as unverified.`) : null,
    h('pre.payload', { style: { whiteSpace: 'pre-wrap' } }, r.text || ''));
}
