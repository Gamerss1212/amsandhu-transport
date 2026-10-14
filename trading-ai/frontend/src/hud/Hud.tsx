import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmt } from "../api";
import { JarvisRequests } from "../components/JarvisRequests";
import { useLive, usePoll } from "../store";
import { Reactor } from "./Reactor";

/* Page 1: the JARVIS trading HUD. Every figure is read from the backend; when a value does not exist yet the panel
   says so instead of showing a made-up number. The rings, sweeps and glows are decoration and carry no data. */

const n = (v: any): number | null => (v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));

/** Eases a displayed number towards its new value (a count-up), without ever showing a value that was not measured. */
function useTween(target: number | null, ms = 900): number | null {
  const [v, setV] = useState<number | null>(target);
  const from = useRef<number | null>(target);
  useEffect(() => {
    if (target === null) { setV(null); from.current = null; return; }
    const start = from.current ?? target;
    if (start === target || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { setV(target); from.current = target; return; }
    const t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      setV(start + (target - start) * e);
      if (k < 1) raf = requestAnimationFrame(step); else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

function Bar({ pct, kind }: { pct: number | null; kind?: "warn" | "bad" }) {
  return <div className={`hud-bar ${kind ?? ""}`}><span style={{ width: `${pct === null ? 0 : Math.max(0, Math.min(100, pct))}%` }} /></div>;
}

function Row({ k, v, pct, kind }: { k: string; v: string; pct?: number | null; kind?: "warn" | "bad" }) {
  return (
    <div className="hud-row">
      <span className="k">{k}</span><span className="v">{v}</span>
      {pct !== undefined && <Bar pct={pct} kind={kind} />}
    </div>
  );
}

function uptime(s: number | null): string {
  if (s === null) return "—";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = Math.floor(s % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}`;
}

function sym(iid: string): string {
  const s = iid.includes(":") ? iid.split(":")[1] : iid;
  return s.replace(/-USD$/, "");
}

function Spark({ values, height = 54 }: { values: number[]; height?: number }) {
  if (values.length < 2) return <div className="hud-empty">Not enough history yet.</div>;
  const w = 260, lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, height - 4 - ((v - lo) / span) * (height - 10)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="hud-spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#39c6ff" stopOpacity="0.35" /><stop offset="1" stopColor="#39c6ff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path className="area" d={`${d} L${w} ${height} L0 ${height} Z`} />
      <path className="line" d={d} />
    </svg>
  );
}

// ---------------------------------------------------------------- left column
function System({ health, thermal, ws }: { health: any; thermal: any; ws: string }) {
  const checks: any[] = health?.startup_checks ?? [];
  const ok = checks.filter((c) => c.ok).length;
  const pct = checks.length ? Math.round((ok / checks.length) * 100) : null;
  const shown = useTween(pct);
  const r = thermal?.reading ?? {};
  const load = n(r.cpu_load_pct), temp = n(r.max_temp_c), ram = n(health?.system?.ram_used_pct);
  const R = 30, C = 2 * Math.PI * R;
  return (
    <section className="hp" style={{ animationDelay: "0.05s" }}>
      <h3>System <small>{ws === "live" ? "online" : ws}</small></h3>
      <div className="gauge">
        <svg viewBox="0 0 74 74" aria-hidden>
          <circle cx="37" cy="37" r={R} fill="none" stroke="rgba(57,198,255,.15)" strokeWidth="6" />
          <circle cx="37" cy="37" r={R} fill="none" stroke={pct === 100 ? "#39c6ff" : "#ffc861"} strokeWidth="6" strokeLinecap="round"
            strokeDasharray={`${((shown ?? 0) / 100) * C} ${C}`} transform="rotate(-90 37 37)" style={{ filter: "drop-shadow(0 0 4px #39c6ff)" }} />
          <g className="spin"><circle cx="37" cy="37" r="20" fill="none" stroke="#39c6ff" strokeOpacity=".5" strokeDasharray="3 5" /></g>
        </svg>
        <div>
          <div className="big">{shown === null ? "—" : `${Math.round(shown)}%`}</div>
          <div className="lbl">Health</div>
        </div>
      </div>
      <Row k="CPU" v={load === null ? "—" : `${load.toFixed(0)}%`} pct={load} kind={load !== null && load > 90 ? "warn" : undefined} />
      <Row k="RAM" v={ram === null ? "—" : `${ram.toFixed(0)}%`} pct={ram} />
      {temp !== null && <Row k="Temp" v={`${temp.toFixed(0)} °C`} pct={temp} kind={temp >= 85 ? "bad" : undefined} />}
    </section>
  );
}

function MarketWatch({ strip }: { strip: any }) {
  const items: any[] = (strip?.items ?? []).slice(0, 7);
  return (
    <section className="hp" style={{ animationDelay: "0.25s" }}>
      <h3>Markets</h3>
      {!items.length ? <div className="hud-empty">Waiting for prices.</div> : items.map((it) => {
        const c = n(it.change);
        return (
          <div className="mw-row" key={it.instrument_id} title={`${it.source ?? ""} · ${it.basis ?? ""}`}>
            <span className="s">{it.label}{it.simulated ? <span className="tiny-h"> · sim</span> : null}</span>
            <span className="p">{fmt.price(it.price)}</span>
            <span className={`c ${c === null ? "" : c >= 0 ? "up" : "down"}`}>{c === null ? "—" : `${c >= 0 ? "▲" : "▼"}${Math.abs(c * 100).toFixed(2)}%`}</span>
          </div>
        );
      })}
    </section>
  );
}

// ---------------------------------------------------------------- right column
function Positions({ account, owners }: { account: any; owners: Record<string, any> }) {
  const eq = n(account?.account?.equity);
  const rows = (account?.positions ?? []).map((p: any) => {
    const px = n(p.price) ?? n(p.avg_price) ?? 0;
    const value = Math.abs((n(p.qty) ?? 0) * px * (n(p.multiplier) ?? 1));
    return { ...p, value, share: eq ? (value / eq) * 100 : null };
  }).filter((p: any) => Number(p.qty) !== 0).sort((a: any, b: any) => b.value - a.value);
  return (
    <section className="hp" style={{ animationDelay: "0.05s" }}>
      <h3>Positions <small>{rows.length ? `${rows.length} open` : ""}</small></h3>
      {!rows.length ? (
        <div className="hud-empty">No open positions.</div>
      ) : rows.slice(0, 7).map((p: any) => {
        const o = owners[p.instrument_id];
        const kind = o?.meme ? "meme" : p.market_type === "stock" ? "stock" : "";
        const u = n(p.unrealized);
        return (
          <div className="pos-row" key={p.instrument_id}>
            <span className={`pos-ico ${kind}`}>{sym(p.instrument_id).slice(0, 3)}</span>
            <div>
              <div className="pos-name">{sym(p.instrument_id)} <span className="tiny-h">× {fmt.num(p.qty, 6)}</span></div>
              <div className="pos-sub">{kind === "meme" ? "meme" : p.market_type === "stock" ? "stock" : "crypto"} · avg {fmt.price(p.avg_price)}</div>
              <Bar pct={p.share} />
            </div>
            <div className="pos-val">{fmt.money(p.value)}<div className={u === null ? "dimh" : u >= 0 ? "up" : "down"} style={{ fontSize: 11 }}>{u === null ? "—" : fmt.signed(u)}</div></div>
          </div>
        );
      })}
    </section>
  );
}

const GROUPS: [string, string, string[]][] = [
  ["crypto", "Crypto", ["crypto_major", "crypto_trend", "crypto_reversion"]],
  ["meme", "Meme coins", ["meme_momentum", "meme_reversion"]],
  ["stock", "US stocks", ["stock_breakout", "stock_reversion", "stock_intraday"]],
];

function Fleet({ fleet }: { fleet: any }) {
  const groups: any[] = fleet?.groups ?? [];
  const c = fleet?.counts ?? {};
  const agg = GROUPS.map(([key, label, roles]) => {
    const gs = groups.filter((g) => roles.includes(g.group));
    const sum = (k: string) => gs.reduce((s, g) => s + (Number(g[k]) || 0), 0);
    return { key, label, target: sum("target"), assigned: sum("assigned"), ready: sum("ready"), validated: sum("validated") };
  });
  const allUp = c.target && c.running === c.target && !c.blocked;
  const node = (x: number, y: number, frac: number, label: string) => (
    <g>
      <circle cx={x} cy={y} r={12} fill="#02101f" stroke="#39c6ff" strokeWidth="1.3" />
      <circle cx={x} cy={y} r={3 + 7 * frac} fill="#39c6ff" fillOpacity={0.25 + 0.6 * frac} className="n-pulse" />
      <text x={x} y={y + 24} textAnchor="middle" fontSize="8" fill="#7fcff5" letterSpacing="1">{label}</text>
    </g>
  );
  return (
    <section className="hp" style={{ animationDelay: "0.1s" }}>
      <h3>Agents <small>{c.target ? `${c.running ?? 0}/${c.target}` : ""}</small></h3>
      <div className="fleet-wrap">
        <svg viewBox="0 0 112 132" aria-hidden>
          {[[20, 96], [56, 108], [92, 96]].map(([x, y], i) => (
            <line key={i} x1="56" y1="36" x2={x} y2={y} stroke="#39c6ff" strokeOpacity=".6" className="r-flow" />
          ))}
          <circle cx="56" cy="36" r="20" fill="#021426" stroke="#39c6ff" strokeWidth="1.6" style={{ filter: "drop-shadow(0 0 6px #39c6ff)" }} />
          <circle cx="56" cy="36" r="9" fill="#bff1ff" className="n-pulse" />
          <text x="56" y="70" textAnchor="middle" fontSize="7.5" fill="#bfefff" letterSpacing="1.2">BRAIN</text>
          {agg.map((g, i) => node([20, 56, 92][i], [96, 108, 96][i], g.target ? g.assigned / g.target : 0, g.label.split(" ")[0].toUpperCase()))}
        </svg>
        <div>
          {agg.map((g) => (
            <div className="fl-row" key={g.key}>
              <div className="t"><span>{g.label}</span><b>{g.assigned} / {g.target}</b></div>
              <Bar pct={g.target ? (g.assigned / g.target) * 100 : null} />
              <div className="s">{g.validated} cleared to trade</div>
            </div>
          ))}
        </div>
      </div>
      <div className={`foot ${allUp ? "ok" : "wait"}`}>
        {allUp ? "All agents operational" : c.target ? `${c.execution_eligible ?? 0} cleared to trade` : "Starting"}
      </div>
    </section>
  );
}

function hash(s: string): number {
  let h = 0;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h;
}

function Trades({ account }: { account: any }) {
  const fills: any[] = account?.fills ?? [];
  const now = Date.now();
  const recent = fills.filter((f) => now - Number(f.ts) < 6 * 3600 * 1000).slice(0, 12);
  return (
    <section className="hp" style={{ animationDelay: "0.15s" }}>
      <h3>Trades <small>{account?.trades_today ?? 0} today</small></h3>
      <div className="radar-wrap">
        <div className="radar" aria-hidden>
          <div className="sweep" />
          {recent.map((f, i) => {
            const a = (hash(f.instrument_id) % 360) * (Math.PI / 180);
            const age = Math.min(1, (now - Number(f.ts)) / (6 * 3600 * 1000));
            const r = 14 + age * 38;
            return <span key={i} className={`blip ${f.side === "sell" ? "sell" : ""}`} style={{ left: 56 + Math.cos(a) * r, top: 56 + Math.sin(a) * r }} />;
          })}
        </div>
        <div>
          <Row k="Earned" v={fmt.signed(account?.realized)} />
          <Row k="Open P&L" v={fmt.signed(account?.unrealized)} />
          <Row k="Fees paid" v={fmt.money(account?.fees)} />
        </div>
      </div>
      <div style={{ marginTop: 8 }}>
        {!fills.length ? <div className="hud-empty">No trades yet.</div>
          : fills.slice(0, 6).map((f, i) => (
            <div className="fill-row" key={f.fill_id ?? i}>
              <span className={`side ${f.side}`}>{String(f.side).toUpperCase()}</span>
              <span className="pos-name" style={{ fontSize: 11.5 }}>{sym(f.instrument_id)} <span className="tiny-h">{fmt.num(f.qty, 6)} @ {fmt.price(f.price)}</span></span>
              <span className="tiny-h">{fmt.time(Number(f.ts))}</span>
            </div>
          ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- centre
function status(o: any, fleet: any, ws: string): { level: "ok" | "wait" | "bad"; say: string; why: string } {
  const r = o?.risk ?? {};
  if (ws === "offline") return { level: "bad", say: "Server unreachable", why: "Start START_TRADING_AI.exe again." };
  if (r.kill_switch) return { level: "bad", say: "Emergency stop engaged", why: `${r.kill_switch.reason ?? ""}. No new orders can be sent until you re-arm.` };
  if (r.trading_locked) return { level: "bad", say: "Trading locked", why: `${r.trading_locked.reason ?? ""}. Only exits are allowed.` };
  if (!o?.autopilot?.enabled) return { level: "wait", say: "System stopped", why: "Press Start." };
  if (r.entries_paused) return { level: "wait", say: "New entries paused", why: "Open positions are still managed." };
  const c = fleet?.counts ?? {};
  if (!c.execution_eligible) return { level: "wait", say: "Standing by", why: "No strategy has qualified yet, so JARVIS stays in cash." };
  return { level: "ok", say: "All systems operational", why: `${c.execution_eligible} agent${c.execution_eligible === 1 ? "" : "s"} cleared to trade` };
}

export default function Hud() {
  const live = useLive();
  const o: any = live.overview;
  const a: any = live.account;
  const [health] = usePoll<any>("/health", 5000);
  const [thermal] = usePoll<any>("/api/system/thermal", 5000);
  const [fleet, reloadFleet] = usePoll<any>("/api/fleet/summary", 5000);
  const [agents] = usePoll<any>("/api/fleet", 15000);
  const [eq] = usePoll<any>("/api/equity?hours=24", 30000);
  const [strip] = usePoll<any>("/api/market/strip", 10000);
  const [busy, setBusy] = useState(false);

  const owners = useMemo(() => {
    const m: Record<string, any> = {};
    for (const c of agents?.agents ?? []) for (const iid of c.partition ?? []) m[iid] = { id: c.id, meme: c.meme };
    return m;
  }, [agents]);

  const equity = n(a?.account?.equity);
  const shownEq = useTween(equity);
  const day = n(a?.day_pnl);
  const exposure = useMemo(() => {
    if (!a?.positions?.length || !equity) return a?.positions ? 0 : null;
    const v = a.positions.reduce((s: number, p: any) => s + Math.abs((n(p.qty) ?? 0) * (n(p.price) ?? n(p.avg_price) ?? 0) * (n(p.multiplier) ?? 1)), 0);
    return (v / equity) * 100;
  }, [a, equity]);
  const st = status(o, fleet, live.ws);
  const c = fleet?.counts ?? {};
  const lit = c.target ? Math.round(((c.running ?? 0) / c.target) * 24) : 0;
  const curve: number[] = (eq?.equity ?? []).map((p: any) => Number(p[1]));

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try { await fn(); live.toast(ok, "ok"); } catch (e: any) { live.toast(e.message, "error"); }
    setBusy(false);
    await live.refresh();
    reloadFleet();
  };
  const paused = !!o?.risk?.entries_paused;

  return (
    <div className="hud-main">
      <div className="hud-col">
        <System health={health} thermal={thermal} ws={live.ws} />
        <MarketWatch strip={strip} />
      </div>

      <div className="hud-center">
        <JarvisRequests />
        <div className="hud-stage">
          <div className="hud-side">
            <section className="hp"><div className="lbl">Today's P&amp;L</div>
              <div className={`mid ${day === null ? "" : day >= 0 ? "up" : "down"}`}>{fmt.signed(day)}</div>
</section>
            <section className="hp"><div className="lbl">Invested now</div>
              <div className="mid">{exposure === null ? "—" : `${exposure.toFixed(1)}%`}</div>
              <Bar pct={exposure} /></section>
            <section className="hp"><div className="lbl">Cash</div>
              <div className="mid">{fmt.money(a?.account?.cash)}</div></section>
          </div>
          <Reactor level={st.level}>{/* animation only: the numbers below are measured */}
            <div className="lbl">{a?.mode === "live" ? "Live equity" : "Paper equity"}</div>
            <div className="eq">{shownEq === null ? "—" : fmt.money(shownEq)}</div>
            <div className={`pnl ${day === null ? "" : day >= 0 ? "up" : "down"}`}>{day === null ? "" : `${fmt.signed(day)} today`}</div>
          </Reactor>
          <div className="hud-side">
            <section className="hp"><div className="lbl">Uptime</div>
              <div className="mid">{uptime(n(health?.components?.backend?.uptime_s))}</div></section>
            <section className="hp"><div className="lbl">Agents running</div>
              <div className="mid">{c.target ? `${c.running ?? 0}` : "—"}<span className="tiny-h"> / {c.target ?? "—"}</span></div></section>
          </div>
        </div>

        <section className="hp hud-status">
          <div className="lbl">System status</div>
          <div className={`say ${st.level === "ok" ? "" : st.level}`}>{st.say}</div>
          <div className="why">{st.why}</div>
          <div className={`hud-ticks ${o?.autopilot?.enabled ? "run" : ""}`} title={`${c.running ?? 0} of ${c.target ?? 0} agents running`}>
            {Array.from({ length: 24 }, (_, i) => <span key={i} className={i < lit ? "on" : ""} style={{ animationDelay: `${i * 0.06}s` }} />)}
          </div>
          <div className="hud-controls">
            <button className={`hud-btn ${o?.autopilot?.enabled ? "on" : ""}`} disabled={busy || !!o?.risk?.kill_switch}
              onClick={() => act(() => api.post("/api/bot/start"), "System started")}>{o?.autopilot?.enabled ? "System running" : "Start system"}</button>
            <button className={`hud-btn ${paused ? "warn" : ""}`} disabled={busy}
              onClick={() => act(() => api.post("/api/controls/pause-entries", { paused: !paused, reason: "owner" }), paused ? "New entries allowed" : "New entries paused: exits keep running")}>
              {paused ? "Resume entries" : "Pause entries"}</button>
            <button className="hud-btn" disabled={busy || !o?.autopilot?.enabled}
              onClick={() => act(() => api.post("/api/bot/stop"), "System stopped")}>Stop</button>
          </div>
        </section>

        <section className="hp">
          <h3>Equity · 24h</h3>
          <Spark values={curve} height={70} />
        </section>
      </div>

      <div className="hud-col">
        <Positions account={a} owners={owners} />
        <Fleet fleet={fleet} />
        <Trades account={a} />
      </div>
    </div>
  );
}
