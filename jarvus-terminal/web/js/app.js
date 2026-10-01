// Jarvus app shell: sign-in, the top bar (three destinations, workspace, engine, live status, EMERGENCY STOP),
// the router and the live stream. Pages live in command.js, connections.js and intel.js.
import { S, h, $, api, replace, clear, toast, errorToast, modal, confirmBox, on, emit, startStream, stopStream,
         modeBadge, time, ago } from './core.js';
import * as command from './command.js';
import * as connections from './connections.js';
import * as intel from './intel.js';

const PAGES = {
  command: { title: 'Command Center', mod: command },
  connections: { title: 'Connections', mod: connections },
  intel: { title: 'Live Intelligence', mod: intel },
};
let current = null;
let overviewTimer = null;

// ---------------------------------------------------------------- sign-in
async function boot() {
  let st;
  try { st = await api('/api/auth/state', undefined, { allow401: true }); } catch (e) { return fatal(e); }
  if (!st.signed_in) return authScreen(st.needs_setup);
  S.csrf = st.csrf; S.user = st.user; S.workspace = st.workspace; S.workspaces = st.workspaces;
  shell();
}

function fatal(e) {
  replace($('#root'), h('div.auth', h('div.panel.box', h('h1', 'JARVUS'), h('p', e.message || String(e)),
    h('button.btn', { onclick: () => location.reload() }, 'Try again'))));
}

function authScreen(setup) {
  stopStream();
  const user = h('input', { autocomplete: 'username', required: true, maxLength: 40 });
  const pass = h('input', { type: 'password', autocomplete: setup ? 'new-password' : 'current-password', required: true });
  const pass2 = setup ? h('input', { type: 'password', autocomplete: 'new-password', required: true }) : null;
  const msg = h('div.note');
  const form = h('form.stack', {
    onsubmit: async (ev) => {
      ev.preventDefault();
      if (setup && pass.value !== pass2.value) { msg.textContent = 'The two passwords differ.'; return; }
      try {
        const r = await api(setup ? '/api/auth/setup' : '/api/auth/login', { username: user.value, password: pass.value }, { allow401: true });
        S.csrf = r.csrf;
        boot();
      } catch (e) { msg.textContent = e.message; }
    }
  },
  h('label.f', 'Username', user), h('label.f', 'Password', pass), setup ? h('label.f', 'Repeat password', pass2) : null,
  h('button.btn.primary', { type: 'submit' }, setup ? 'Create owner account' : 'Sign in'), msg);
  replace($('#root'), h('div.auth', h('div.panel.box.hot',
    h('div.brand', h('div.logo'), h('div', 'JARVUS', h('small', 'trading research terminal'))), h('div.sep'),
    h('p.dim', setup ? 'First run: create the owner account for this computer. Your password is stored only as a salted '
      + 'scrypt hash. Every account gets its own workspaces, bots and credentials.' : 'Sign in to your workspace.'),
    form,
    h('p.note', 'Educational research and paper-trading software, not financial advice. Nothing here promises profits.'))));
  setTimeout(() => user.focus(), 50);
}

on('signed-out', () => { stopStream(); clearInterval(overviewTimer); setTimeout(boot, 500); });   // reopen, no sign-in page

// ---------------------------------------------------------------- shell
function shell() {
  const ws = S.workspaces.find(w => w.workspace_id === S.workspace) || {};
  const nav = h('nav.nav', { 'aria-label': 'Main' }, Object.entries(PAGES).map(([k, p]) => h('a', { href: `#/${k}`, dataset: { page: k } }, p.title)));
  const bottom = h('nav.bottomnav', { 'aria-label': 'Main' }, Object.entries(PAGES).map(([k, p]) => h('a', { href: `#/${k}`, dataset: { page: k } }, p.title)));
  const wsSel = h('select', { 'aria-label': 'Workspace', style: { width: 'auto' }, onchange: switchWorkspace },
    S.workspaces.map(w => h('option', { value: w.workspace_id, selected: w.workspace_id === S.workspace },
      w.kind === 'demo' ? 'Demo workspace' : 'Main workspace')));
  const eng = h('span.pill#engine-pill', h('span.dot'), 'engine …');
  const live = h('span.pill.hide-sm#live-pill', 'live: …');
  const ap = h('a.pill#ap-pill', { href: '#/command', title: 'AUTOPILOT: every research bot trading simulated money by itself' }, 'autopilot …');
  const streamPill = h('span.pill.hide-sm#stream-pill', { title: 'Live event stream' }, h('span.dot'), 'stream');
  const emergency = h('button.btn.emergency#emergency-btn', { onclick: emergencyFlow, title: 'Block every new entry now' }, '⏻ EMERGENCY STOP');
  const userBtn = h('button.btn.ghost.small', { onclick: userMenu, 'aria-label': 'Account' }, S.user.username);
  replace($('#root'),
    h('header.topbar',
      h('div.brand', h('div.logo'), h('div', 'JARVUS', h('small', 'research · paper · live'))),
      nav, h('div.spacer'),
      h('span.row', ws.kind === 'demo' ? modeBadge('demo') : null, wsSel),
      ap, streamPill, live, eng, emergency),
    h('div#banners'),
    h('main#view'),
    bottom);
  if (!S._streamHooked) {
    S._streamHooked = true;
    on('stream-state', (st) => {
      const p = $('#stream-pill');
      if (!p) return;
      replace(p, h(`span.dot${st === 'live' ? '.on' : '.warn'}`), st === 'live' ? 'live stream' : st);
    });
  }
  window.onhashchange = route;
  startStream();
  refreshOverview();
  clearInterval(overviewTimer);
  overviewTimer = setInterval(refreshOverview, 15000);
  if (!S._stateHooked) {
    S._stateHooked = true;
    on('state', (d) => { if (S.overview) { S.overview.emergency = d.emergency; S.overview.engine.running = d.engine; renderStatus(); } });
  }
  route();
}

export async function refreshOverview() {
  try {
    S.overview = await api('/api/overview');
    renderStatus();
    emit('overview', S.overview);
  } catch (e) { if (e.status !== 401) console.warn(e); }
}

function renderStatus() {
  const o = S.overview;
  if (!o) return;
  const eng = $('#engine-pill');
  if (eng) {
    const run = o.engine.running;
    replace(eng, h(`span.dot${run ? '.on' : '.bad'}`), run ? 'engine running' : 'engine stopped',
      h('button.btn.small.ghost', {
        onclick: async () => {
          try {
            if (run) {
              if (!await confirmBox('Stop the bot engine?', 'The AI stops trading and every bot stops evaluating, and it stays off, even after Jarvus restarts, until you press Start. Open positions keep their protective orders on the broker (simulated positions are not managed while stopped).', { danger: true, okLabel: 'Stop engine' })) return;
              await api('/api/engine/stop', {});
            } else await api('/api/engine/start', {});
            toast(run ? 'Engine stopping: the AI is off until you press Start' : 'Starting: the AI trades again once the bots have loaded their data (about a minute)');
            setTimeout(refreshOverview, 2500);
          } catch (e) { errorToast(e); }
        }
      }, run ? 'Stop' : 'Start'));
  }
  const app = $('#ap-pill');
  if (app) replace(app, h(`span.dot${o.autopilot ? '.on' : ''}`), o.autopilot ? 'AUTOPILOT ON' : 'autopilot off');
  const lp = $('#live-pill');
  if (lp) {
    const a = o.live_authorization;
    replace(lp, a.authorized ? modeBadge('live') : h('span.badge.sim', 'LIVE OFF'), a.authorized ? 'authorised' : 'not authorised');
    lp.title = a.authorized ? `Live trading authorised on ${a.connections.join(', ')}` : 'Real-money orders are disabled until you authorise them under Connections';
  }
  const b = $('#banners');
  if (b) {
    clear(b);
    if (o.workspace.demo) b.append(h('div.banner.demo', modeBadge('demo'), 'Demo workspace: synthetic markets and simulated money. Nothing here is real or comparable to real results.'));
    if (o.emergency) b.append(h('div.banner.emergency', '⏻ EMERGENCY STOP is on since ' + time(o.emergency.time, true) + ': ' + o.emergency.reason
      + '. No new entries are sent. Exits and protective orders still work.',
      h('button.btn.small.danger', { onclick: closeAllFlow }, 'Close all positions…'),
      h('button.btn.small', { onclick: async () => { if (await confirmBox('Clear the emergency stop?', 'Running bots may enter new trades again.', { danger: false, okLabel: 'Clear' })) { try { await api('/api/emergency/clear', {}); toast('Emergency stop cleared'); refreshOverview(); } catch (e) { errorToast(e); } } } }, 'Clear emergency stop')));
    if (o.live_authorization.authorized) b.append(h('div.banner.live', modeBadge('live'), 'Real-money trading is authorised on ' + o.live_authorization.connections.join(', ') + '. Live bots trade real money within your limits.'));
  }
}

async function switchWorkspace(ev) {
  try {
    const r = await api('/api/auth/workspace', { workspace_id: ev.target.value });
    if (r.warning) toast(r.warning, 'bad');
    const st = await api('/api/auth/state');
    S.workspace = st.workspace; S.csrf = st.csrf;
    S.overview = null; S.live = null;                  // nothing from the previous workspace may show in this one
    shell();
  } catch (e) { errorToast(e); }
}

function route() {
  const key = (location.hash.replace(/^#\/?/, '').split('?')[0] || 'command');
  const page = PAGES[key] ? key : 'command';
  document.querySelectorAll('.nav a, .bottomnav a').forEach(a => a.classList.toggle('active', a.dataset.page === page));
  if (current && current.mod.unmount) current.mod.unmount();
  current = PAGES[page];
  document.title = `${current.title} · Jarvus`;
  const view = $('#view');
  clear(view);
  current.mod.mount(view);
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  if (q.get('oauth')) toast('Alpaca: ' + q.get('oauth'), q.get('oauth').startsWith('error') ? 'bad' : 'good');
}

// ---------------------------------------------------------------- emergency controls
async function emergencyFlow() {
  const reason = h('input', { value: 'owner pressed EMERGENCY STOP', maxLength: 200 });
  const out = h('div');
  const go = h('button.btn.emergency', 'Block new entries and cancel entry orders now');
  const m = modal('EMERGENCY STOP', h('div.stack',
    h('p', 'This blocks every new entry in this workspace at once and tries to cancel every working entry order. ',
      h('b', 'It does not close positions'), ': they keep their protective orders. Closing them is a separate step below.'),
    h('label.f', 'Reason (recorded in the log)', reason), go, out), { danger: true });
  go.addEventListener('click', async () => {
    go.disabled = true;
    try {
      const r = await api('/api/emergency', { reason: reason.value });
      const rows = (r.entry_orders || []);
      replace(out, h('div.stack',
        h('div.banner.emergency', `New entries blocked. ${rows.filter(x => x.ok).length} of ${rows.length} working entry orders confirmed canceled.`
          + (r.engine_running === false ? ' (The engine was stopped, so nothing was working.)' : '')),
        rows.length ? h('ul.checks', rows.map(x => h(`li.${x.ok ? 'pass' : 'fail'}`, h('span.i', x.ok ? '✓' : '✕'),
          h('div', `${x.order}: ${x.state}` + (x.filled_qty ? ` (filled ${x.filled_qty} before the cancel)` : '') + (x.error ? ` - ${x.error}` : ''))))) : null,
        r.failed && r.failed.length ? h('p.down', `${r.failed.length} cancel(s) NOT confirmed. Check them on the broker.`) : null,
        h('div.sep'),
        h('p', 'Optional, separately confirmed:'),
        h('button.btn.danger', { onclick: () => { m.close(); closeAllFlow(); } }, 'Close all positions…')));
      refreshOverview();
    } catch (e) { errorToast(e); go.disabled = false; }
  });
}

async function closeAllFlow() {
  const typed = await confirmBox('Close ALL positions?', 'Every open position in this workspace (paper, demo and live, and the research fleet) is sold with market orders. Protective stops are canceled first. Failures and unfilled amounts are reported.', { typed: 'CLOSE ALL', okLabel: 'Close everything' });
  if (!typed) return;
  try {
    const r = await api('/api/close_all', { confirm: typed });
    const res = r.results || [];
    modal('Close-all results', h('div.stack',
      h('p', `${res.length - (r.not_completed || []).length} of ${res.length} deployment positions closed; ${r.research_closed} research-fleet positions closed.`),
      res.length ? h('ul.checks', res.map(x => h(`li.${x.status === 'filled' ? 'pass' : 'fail'}`, h('span.i', x.status === 'filled' ? '✓' : '✕'),
        h('div', `${x.bot_id} `, modeBadge(x.mode), ` ${x.status || ''}`, x.reason ? h('div.d', x.reason) : null,
          x.left ? h('div.d.down', `${x.left} still open`) : null)))) : h('p.muted', 'No deployment positions were open.')), { danger: true });
    refreshOverview();
  } catch (e) { errorToast(e); }
}

// ---------------------------------------------------------------- account menu
function userMenu() {
  const m = modal(`Signed in as ${S.user.username}`, h('div.stack',
    h('p.note', `Role: ${S.user.role}. Workspace: ${S.workspace}.`),
    h('button.btn', { onclick: () => { m.close(); passwordForm(); } }, 'Change password'),
    S.user.role === 'owner' ? h('button.btn', { onclick: () => { m.close(); addUserForm(); } }, 'Add an account (separate workspaces)') : null,
    h('button.btn.warn', { onclick: async () => { try { await api('/api/auth/logout', {}); } catch { /* ignore */ } m.close(); emit('signed-out'); } }, 'Sign out')));
}
function passwordForm() {
  const o = h('input', { type: 'password', autocomplete: 'current-password' });
  const n = h('input', { type: 'password', autocomplete: 'new-password' });
  const m = modal('Change password', h('form.stack', {
    onsubmit: async (e) => { e.preventDefault(); try { await api('/api/auth/password', { old: o.value, new: n.value }); m.close(); toast('Password changed; sign in again', 'good'); emit('signed-out'); } catch (err) { errorToast(err); } }
  }, h('label.f', 'Current password', o), h('label.f', 'New password (8+ characters)', n), h('button.btn.primary', { type: 'submit' }, 'Change')));
}
function addUserForm() {
  const u = h('input', { autocomplete: 'off' });
  const p = h('input', { type: 'password', autocomplete: 'new-password' });
  const m = modal('Add an account', h('form.stack', {
    onsubmit: async (e) => { e.preventDefault(); try { await api('/api/auth/users', { username: u.value, password: p.value }); m.close(); toast('Account added: it has its own Main and Demo workspaces', 'good'); } catch (err) { errorToast(err); } }
  }, h('p.note', 'The new account gets its own workspaces, bots, database and credentials. It cannot see yours.'),
  h('label.f', 'Username', u), h('label.f', 'Password', p), h('button.btn.primary', { type: 'submit' }, 'Add account')));
}

S.refreshOverview = refreshOverview;
S.closeAllFlow = closeAllFlow;
S.emergencyFlow = emergencyFlow;
boot();
