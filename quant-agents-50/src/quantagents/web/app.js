// QuantAgents local web app. Every button calls the app on this computer only, with the
// page's own key; the app runs an ordinary quantagents command and shows what it printed.
"use strict";

const KEY = document.querySelector('meta[name="qa-key"]').content;
const $ = (id) => document.getElementById(id);
let state = null;
let pollingJob = null;
let showTable = false;

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function svg(tag, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  return node;
}

async function api(path, body) {
  const options = { headers: { "X-QuantAgents-Key": KEY } };
  if (body !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const reply = await fetch(path, options);
  let data = {};
  try { data = await reply.json(); } catch (e) { data = { error: "no answer from the app" }; }
  if (!reply.ok && !data.error) data.error = `the app said ${reply.status}`;
  return data;
}

const money = (x, cur) =>
  x === null || x === undefined ? "-" :
  x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (cur ? " " + cur : "");
const pct = (x, digits = 2) =>
  x === null || x === undefined ? "-" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x * 100).toFixed(digits) + "%";
const pctPoints = (x) =>
  x === null || x === undefined ? "-" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(2) + "%";

function toast(text, bad) {
  const box = $("toast");
  box.textContent = text;
  box.className = "toast" + (bad ? " bad" : "");
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, bad ? 15000 : 8000);
}

function pill(text, kind) {
  return el("span", { class: "pill " + (kind || "") }, el("span", { class: "dot" }), text);
}

// ---- rendering ---------------------------------------------------------------------------

function render(s) {
  state = s;
  const name = s.folder.split(/[\\/]/).filter(Boolean).pop() || s.folder;
  $("folder").textContent = `version ${s.version} · folder ${name}`;
  $("folder").title = s.folder;
  const pills = $("pills");
  pills.replaceChildren(
    pill(s.live.on ? (s.live.armed ? "REAL MONEY armed" : "Real money set up, not armed") : "Paper trading (practice money)",
      s.live.armed ? "bad" : "ok"),
    pill(s.kill.engaged ? "Trading STOPPED" : "Trading allowed", s.kill.engaged ? "bad" : "ok"),
    pill(`Automatic run ${s.schedule.on ? "ON" : "OFF"}`, s.schedule.on ? "ok" : ""),
    pill(`Paper days ${s.paper_days} of ${s.days_needed}`, s.paper_days >= s.days_needed ? "ok" : ""),
  );

  const banners = $("banners");
  banners.replaceChildren();
  for (const err of s.errors) banners.append(el("div", { class: "banner bad" }, err));
  if (s.kill.engaged)
    banners.append(el("div", { class: "banner bad" },
      el("strong", { text: "Trading is stopped. " }),
      `Reason: ${s.kill.reason || "unknown"} (by ${s.kill.by || "?"}, ${s.kill.at || "?"}). `,
      "Find out why (the Today box and runs/daily.log), then resume in the Stop or resume box."));
  if (s.synthetic)
    banners.append(el("div", { class: "banner warn" },
      "Your settings still use the demo symbols (SYN_A...). Choose real symbols in the Your symbols box."));
  if (s.watchdog && s.watchdog.length)
    banners.append(el("div", { class: "banner warn" }, "Watchdog: " + s.watchdog.join("; ")));

  renderToday(s);
  renderAccount(s);
  renderDecision(s);
  renderControls(s);
  renderMoney(s);
  if (s.job && !pollingJob) watchJob(s.job.id);
  setBusy(Boolean(s.job));
}

function renderToday(s) {
  const last = s.last_daily || [];
  $("last-run").textContent = last.length ? `Last run ${last[0].replace("T", " ").slice(0, 16)} UTC: ${last.slice(1).join(", ")}` : "No daily run yet.";
  $("today-note").textContent = s.last_cycle ? `Prices up to ${s.last_cycle.as_of}` : "";
}

function tile(label, value, sub) {
  return el("div", { class: "tile" },
    el("div", { class: "label", text: label }),
    el("div", { class: "value", text: value }),
    sub ? el("div", { class: "sub", text: sub }) : null);
}

function renderAccount(s) {
  const a = s.account;
  const tiles = $("tiles");
  if (!a.exists) {
    tiles.replaceChildren(el("p", { class: "empty", text: "No paper account yet. Press “Run today's paper day” to start it (10,000 practice money)." }));
    $("scoreboard").textContent = "";
    $("positions").replaceChildren();
    renderChart([]);
    return;
  }
  tiles.replaceChildren(
    tile("Paper equity", money(a.equity, s.currency), `started at ${money(a.start, s.currency)}`),
    tile("Since the start", pct(a.return), "after fees"),
    tile("Drawdown", pct(a.drawdown), "below the highest point"),
    tile("Fees paid", money(a.fees, s.currency), `${a.fills} fills · ${a.pending} waiting`),
  );
  $("scoreboard").textContent = a.scoreboard || "";
  $("account-note").textContent = `cash ${money(a.cash, s.currency)}`;
  const pos = a.positions || [];
  $("positions").replaceChildren(pos.length ?
    el("div", { class: "table-scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "Symbol" }), el("th", { class: "num", text: "Units" }),
        el("th", { class: "num", text: "Value" }), el("th", { class: "num", text: "Share of account" }))),
      el("tbody", {}, ...pos.map((p) => el("tr", {},
        el("td", { text: p.symbol }), el("td", { class: "num", text: p.qty.toLocaleString(undefined, { maximumFractionDigits: 6 }) }),
        el("td", { class: "num", text: money(p.value, s.currency) }), el("td", { class: "num", text: pct(p.weight, 1) })))))) :
    el("p", { class: "empty", text: "No open positions: the account is all cash." }));
  renderChart(s.series || []);
}

function renderChart(series) {
  const box = $("chart");
  const table = $("chart-table");
  const points = series.filter((p) => p.paper !== null);
  table.replaceChildren(el("div", { class: "table-scroll" }, el("table", {},
    el("thead", {}, el("tr", {}, el("th", { text: "Day" }), el("th", { class: "num", text: "Paper" }), el("th", { class: "num", text: "Holding" }))),
    el("tbody", {}, ...series.map((p) => el("tr", {}, el("td", { text: p.date }),
      el("td", { class: "num", text: pctPoints(p.paper) }), el("td", { class: "num", text: pctPoints(p.hold) })))))));
  table.hidden = !showTable;
  box.hidden = showTable;
  if (points.length < 2) {
    box.replaceChildren(el("p", { class: "empty", text: "The chart appears after 2 paper days." }));
    return;
  }
  const W = Math.max(320, Math.round(box.clientWidth || box.parentElement.clientWidth || 760));
  const H = 240, L = 56, R = 120, T = 12, B = 28;
  const values = points.flatMap((p) => [p.paper, p.hold]).filter((v) => v !== null);
  let lo = Math.min(0, ...values), hi = Math.max(0, ...values);
  if (hi - lo < 0.5) { hi += 0.25; lo -= 0.25; }
  const pad = (hi - lo) * 0.1; lo -= pad; hi += pad;
  const x = (i) => L + (i * (W - L - R)) / (points.length - 1);
  const y = (v) => T + ((hi - v) * (H - T - B)) / (hi - lo);
  const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
    "aria-label": "Paper account and holding the same symbols, percent since the first paper day" });
  const step = niceStep((hi - lo) / 4);
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    chart.append(svg("line", { class: Math.abs(v) < 1e-9 ? "zero" : "grid", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
    const t = svg("text", { class: "tick", x: L - 6, y: y(v) + 4, "text-anchor": "end" });
    t.textContent = pctPoints(Math.abs(v) < 1e-9 ? 0 : v);
    chart.append(t);
  }
  for (const [i, anchor] of [[0, "start"], [points.length - 1, "end"]]) {
    const t = svg("text", { class: "tick", x: x(i), y: H - 8, "text-anchor": anchor });
    t.textContent = points[i].date;
    chart.append(t);
  }
  const line = (key, cls) => {
    const d = points.map((p, i) => (p[key] === null ? null : `${x(i)},${y(p[key])}`)).filter(Boolean);
    if (d.length > 1) chart.append(svg("polyline", { class: `line ${cls}`, points: d.join(" ") }));
  };
  line("hold", "s2");
  line("paper", "s1");
  const lastP = points[points.length - 1];
  const ends = [["paper", "Paper", lastP.paper], ["hold", "Holding", lastP.hold]].filter((e) => e[2] !== null);
  const ys = ends.map((e) => y(e[2]));
  if (ys.length === 2 && Math.abs(ys[0] - ys[1]) < 14) { const mid = (ys[0] + ys[1]) / 2; ys[0] = mid - 7; ys[1] = mid + 7; if (ends[0][2] < ends[1][2]) ys.reverse(); }
  ends.forEach((e, i) => {
    const t = svg("text", { class: "end", x: W - R + 8, y: ys[i] + 4 });
    t.textContent = `${e[1]} ${pctPoints(e[2])}`;
    chart.append(t);
  });
  const cross = svg("line", { class: "cross", y1: T, y2: H - B, visibility: "hidden" });
  const m1 = svg("circle", { class: "m1", r: 4, visibility: "hidden" });
  const m2 = svg("circle", { class: "m2", r: 4, visibility: "hidden" });
  chart.append(cross, m2, m1);
  const tip = el("div", { class: "tip", hidden: "" });
  const hit = svg("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" });
  chart.append(hit);
  const move = (event) => {
    const rect = chart.getBoundingClientRect();
    const px = ((event.clientX - rect.left) * W) / rect.width;
    const i = Math.max(0, Math.min(points.length - 1, Math.round(((px - L) * (points.length - 1)) / (W - L - R))));
    const p = points[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    m1.setAttribute("cx", x(i)); m1.setAttribute("cy", y(p.paper)); m1.setAttribute("visibility", "visible");
    if (p.hold !== null) { m2.setAttribute("cx", x(i)); m2.setAttribute("cy", y(p.hold)); m2.setAttribute("visibility", "visible"); }
    tip.replaceChildren(el("strong", { text: p.date }), el("br"),
      el("span", { class: "key s1" }), `Paper ${pctPoints(p.paper)}`, el("br"),
      el("span", { class: "key s2" }), `Holding ${pctPoints(p.hold)}`);
    tip.hidden = false;
    const left = (x(i) / W) * rect.width;
    tip.style.left = `${Math.min(left + 12, rect.width - 160)}px`;
    const legendBox = box.querySelector(".legend");
    tip.style.top = `${(legendBox ? legendBox.offsetHeight : 0) + 12}px`;  // below the legend, inside the plot
  };
  hit.addEventListener("mousemove", move);
  hit.addEventListener("mouseleave", () => {
    tip.hidden = true;
    for (const n of [cross, m1, m2]) n.setAttribute("visibility", "hidden");
  });
  const legend = el("div", { class: "legend" },
    el("span", {}, el("span", { class: "key s1" }), "Paper account"),
    el("span", {}, el("span", { class: "key s2" }), "Holding the same symbols in equal parts (no fees)"));
  box.replaceChildren(legend, chart, tip);
}

function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 2.5, 5, 10]) if (raw <= m * p) return m * p;
  return 10 * p;
}

function renderDecision(s) {
  const c = s.last_cycle;
  if (!c) {
    $("decision-note").textContent = "";
    $("decisions").replaceChildren(el("p", { class: "empty", text: "No decision yet. Run today's paper day." }));
    return;
  }
  $("decision-note").textContent = `as of ${c.as_of} · risk level ${c.level} · data health ${c.health} · ${c.intents} order(s)`;
  const rows = c.decisions.flatMap((d) => {
    const main = el("tr", { class: d.go ? "" : "has-why" },
      el("td", { text: d.symbol }),
      el("td", {}, d.go ? el("span", { class: "tag go" }, "✓ GO") : el("span", { class: "tag" }, "– no trade")),
      el("td", { text: d.direction || "-" }),
      el("td", { class: "num", text: d.p_up === null || d.p_up === undefined ? "-" : d.p_up.toFixed(3) }));
    if (d.go || !d.why) return [main];
    return [main, el("tr", { class: "why" }, el("td", { colspan: "4", text: `Why not: ${d.why}` }))];
  });
  $("decisions").replaceChildren(rows.length ?
    el("table", {},
      el("thead", {}, el("tr", {}, el("th", { text: "Symbol" }), el("th", { text: "Decision" }), el("th", { text: "Leaning" }),
        el("th", { class: "num", text: "Chance up" }))),
      el("tbody", {}, ...rows)) :
    el("p", { class: "empty", text: "No symbols were decided on." }));
}

function renderControls(s) {
  $("schedule-state").textContent = s.schedule.on ? "ON: it runs by itself." : "OFF: nothing runs by itself.";
  $("schedule-words").textContent = `When on: ${s.schedule.words}.`;
  $("kill-state").textContent = s.kill.engaged ? `STOPPED: ${s.kill.reason}` : "Trading is allowed.";
  $("reset-phrase").textContent = s.reset_phrase;
  $("symbols-now").textContent = s.symbols.join(", ") || "(none)";
  const presets = $("presets");
  if (!presets.childElementCount) {
    for (const [key, label] of Object.entries(s.presets)) {
      const b = el("button", { type: "button", "data-action": "symbols", "data-preset": key }, `Use: ${label}`);
      presets.append(b);
    }
  }
}

function renderMoney(s) {
  const l = s.live;
  const open = l.gates.filter((g) => g.ok).length;
  $("money-state").textContent = l.armed ? `ARMED: the daily run copies the paper portfolio to Kraken, up to ${l.budget}.` :
    `OFF: ${open} of ${l.gates.length} safety gates open. Nothing real can be bought.`;
  $("money-mirror").textContent = l.mirror || "";
  $("gates").replaceChildren(...l.gates.map((g) => el("li", { class: g.ok ? "open" : "closed" },
    el("span", { class: "mark", text: g.ok ? "✓" : "✗" }), el("strong", { text: g.name }), `: ${g.detail}`)));
}

// ---- actions and jobs --------------------------------------------------------------------

function setBusy(busy) {
  for (const b of document.querySelectorAll("button[data-action]")) {
    const always = ["stop", "resume", "quit"].includes(b.dataset.action);
    b.disabled = busy && !always;
  }
}

async function refresh() {
  const s = await api("/api/status");
  if (s.error) { toast(`Could not read the account: ${s.error}`, true); return; }
  render(s);
}

async function watchJob(id) {
  pollingJob = id;
  $("job").hidden = false;
  setBusy(true);
  while (pollingJob === id) {
    const j = await api(`/api/job/${id}`);
    if (j.error) { toast(j.error, true); break; }
    $("job-label").textContent = j.label;
    $("job-time").textContent = j.done ? (j.code === 0 ? `finished in ${j.seconds}s` : `finished with problems (code ${j.code})`) : `running… ${j.seconds}s`;
    const out = $("job-output");
    const atEnd = out.scrollTop + out.clientHeight >= out.scrollHeight - 8;
    out.textContent = j.output || "(starting)";
    if (atEnd) out.scrollTop = out.scrollHeight;
    if (j.done) {
      toast(j.code === 0 ? `${j.label}: done.` : `${j.label}: finished with problems. Read the output in the Today box.`, j.code !== 0);
      break;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  pollingJob = null;
  await refresh();
}

async function act(button) {
  const action = button.dataset.action;
  const body = { action };
  if (action === "resume") body.phrase = $("phrase").value;
  if (action === "symbols") {
    if (button.dataset.preset) body.preset = button.dataset.preset;
    else body.symbols = $("symbols").value;
  }
  if (action === "live_test_order") body.confirm = $("confirm").value.trim();
  if (action === "import") body.path = $("old-folder").value;
  if (action === "quit" && !confirm("Close the app? The automatic daily run keeps working without it.")) return;
  if (action === "stop" && !confirm("Stop all trading now? Only you can resume it, with the phrase.")) return;
  button.disabled = true;
  const reply = await api("/api/action", body);
  button.disabled = false;
  if (reply.error) { toast(reply.error, true); await refresh(); return; }
  if (reply.job) { watchJob(reply.job); return; }
  if (reply.message) toast(reply.message, false);
  if (action === "resume") $("phrase").value = "";
  if (action === "live_test_order") $("confirm").value = "";
  if (action === "quit") { document.body.replaceChildren(el("main", {}, el("section", { class: "card wide" }, el("h2", { text: "QuantAgents is closed." }), el("p", { text: "You can close this tab. Double-click QuantAgents.bat to open it again." })))); return; }
  await refresh();
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (button) act(button);
});
$("chart-toggle").addEventListener("click", () => {
  showTable = !showTable;
  $("chart-toggle").textContent = showTable ? "Show as chart" : "Show as table";
  if (state) renderChart(state.series || []);
});
let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (state) renderChart(state.series || []); }, 150);
});
refresh();
setInterval(() => { if (!pollingJob && document.visibilityState === "visible") refresh(); }, 15000);
