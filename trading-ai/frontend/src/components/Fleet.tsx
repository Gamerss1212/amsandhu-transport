import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { fmt, tone } from "../api";
import { usePoll } from "../store";
import { Badge, Card, Drawer, Empty, Tabs } from "./ui";

// The trading fleet A001... and the Supercomputer Brain (specification revision 13, page 2). Every number here comes
// from /api/fleet; nothing is animated unless the server reported a change.

type Agent = {
  id: string; group: string; partition: string[]; runtime: string; job: string; detail: string; venue: string | null;
  market: string | null; consumed_version: number | null; last_input_ts: number | null; last_price: string | null;
  heartbeat: number | null; job_ms: number | null; eligible: number; errors: number; assignment_version: number;
  budget: string; next_action: string | null; fresh: boolean; strategies?: string[]; position?: string | null; unrealized?: string | null;
  realized?: string | null; fees?: string | null; open_orders?: number; last_decision?: { ts: number; outcome: string; reason: string } | null;
};

const RUNTIME_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  available: "good", degraded: "warn", blocked: "", stopped: "", starting: "info",
};
const DOT: Record<string, string> = {
  available: "var(--good)", degraded: "var(--warn)", blocked: "#33445f", stopped: "#33445f", starting: "var(--accent)",
};
const GROUP_LABEL: Record<string, string> = {
  equities: "Equities", crypto: "Crypto", fx: "FX", futures: "Futures", options: "Options", rates: "Rates",
  specialty: "Specialty", overflow: "Overflow",
};

export function FleetPanel() {
  const [f] = usePoll<any>("/api/fleet", 5000);
  const [tab, setTab] = useState<"network" | "grid" | "caps">("network");
  const [open, setOpen] = useState<string | null>(null);
  const pulses = usePulses(f?.agents);
  if (!f) return <Card title="Supercomputer Brain"><Empty>Loading the fleet…</Empty></Card>;
  const c = f.counts;
  const b = f.brain;
  return (
    <Card title="Supercomputer Brain and trading fleet" sub={`${b.kind} · ${b.model}`} flush>
      <div className="brain-row">
        <BrainCore plan={b.plan_version} owned={b.owned_instruments} />
        <div className="col" style={{ gap: 8, minWidth: 0, flex: 1 }}>
          <div className="small"><b>Plan:</b> <span className="dim">{b.plan}</span></div>
          <div className="kv small">
            <div>Plan version</div><div className="mono">{b.plan_version}</div>
            <div>Market-state version</div><div className="mono">{b.market_state_version ?? "— (discovery off)"}</div>
            <div>Last fleet cycle</div><div className="mono">{b.metrics.last_cycle_ms !== null ? `${b.metrics.last_cycle_ms} ms` : "—"} · {fmt.ago(b.metrics.last_cycle)} · {b.metrics.cycles} cycles</div>
            <div>Missed deadlines</div><div className="mono">{b.metrics.missed_deadlines}</div>
          </div>
        </div>
      </div>
      <div className="stats" style={{ margin: "0 14px 12px" }}>
        <Num k="Configured" v={c.configured} s={`target ${c.target} · ${c.registered} registered`} />
        <Num k="Assigned a market" v={c.assigned} s="one distinct instrument each" />
        <Num k="Fresh data now" v={c.data_ready} s={`${c.market_closed} more in closed markets`} />
        <Num k="Qualified strategy" v={c.execution_eligible} s="may trade (paper)" />
        <Num k="Holding positions" v={c.with_positions} s="managed by their owner" />
        <Num k="Blocked" v={c.blocked} s="no distinct market: see reason" />
      </div>
      <Tabs tabs={[["network", "Network"], ["grid", `Agent grid (${f.agents.length})`], ["caps", "Support services C01–C50"]]} on={tab} set={setTab} />
      {tab === "network" && <><MarketMap m={f.market_map} /><Network groups={f.groups} agents={f.agents} pulses={pulses} onOpen={setOpen} /></>}
      {tab === "grid" && <AgentGrid agents={f.agents} groups={f.groups} onOpen={setOpen} />}
      {tab === "caps" && <Capabilities />}
      {open && <AgentDrawer id={open} onClose={() => setOpen(null)} />}
    </Card>
  );
}

function Num({ k, v, s }: { k: string; v: number; s: string }) {
  return <div className="stat"><div className="k">{k}</div><div className="v">{v}</div><div className="s">{s}</div></div>;
}

function BrainCore({ plan, owned }: { plan: number; owned: number }) {
  return (
    <svg className="brain-core" viewBox="0 0 120 120" role="img" aria-label={`Brain plan version ${plan}, ${owned} instruments owned`}>
      <defs>
        <radialGradient id="bc" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#a78bfa" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="60" cy="60" r="56" fill="url(#bc)" />
      <g className="ring"><circle cx="60" cy="60" r="44" fill="none" stroke="#3dd9ff" strokeOpacity="0.5" strokeDasharray="4 7" /></g>
      <circle cx="60" cy="60" r="32" fill="#101a2b" stroke="#a78bfa" strokeWidth="2" />
      <text x="60" y="60" textAnchor="middle" fontSize="18" fontWeight="700" fill="#f2f6ff">{owned}</text>
      <text x="60" y="73" textAnchor="middle" fontSize="8" fill="#a9b8ce">owned</text>
    </svg>
  );
}

// An agent pulses once when the server reports that it received new market data since the previous refresh.
function usePulses(agents: Agent[] | undefined): Set<string> {
  const prev = useRef<Map<string, number | null>>(new Map());
  const [on, setOn] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!agents) return;
    const next = new Set<string>();
    for (const a of agents) {
      const p = prev.current.get(a.id);
      if (p !== undefined && a.last_input_ts && a.last_input_ts !== p) next.add(a.id);
      prev.current.set(a.id, a.last_input_ts);
    }
    setOn(next);
    if (!next.size) return;
    const t = window.setTimeout(() => setOn(new Set()), 1600);
    return () => window.clearTimeout(t);
  }, [agents]);
  return on;
}

// ---------------------------------------------------------------- market map: sessions, venue health, blind spots
function MarketMap({ m }: { m: any }) {
  if (!m) return null;
  return (
    <div className="grid g-3" style={{ padding: "12px 14px 0" }}>
      <div className="col" style={{ gap: 6 }}>
        <div className="tiny muted">SESSIONS (now)</div>
        {Object.entries(m.sessions).map(([k, s]: any) => (
          <div key={k} className="spread small"><span>{s.label}</span><Badge kind={s.open ? "good" : ""} dot>{s.open ? (s.session ?? "open") : (s.session ?? "closed")}</Badge></div>
        ))}
      </div>
      <div className="col" style={{ gap: 6 }}>
        <div className="tiny muted">CRYPTO VENUES (shared snapshot)</div>
        {m.offline ? <div className="small dim">Offline mode: venue discovery is off.</div> : Object.entries(m.venues).map(([v, x]: any) => (
          <div key={v} className="col" style={{ gap: 2 }}>
            <div className="spread small"><b>{v}</b><Badge kind={x.received && Date.now() - x.received < 150000 ? "good" : "warn"} dot>{x.received ? `snapshot ${fmt.ago(x.received)}` : "no snapshot yet"}</Badge></div>
            <div className="tiny dim">{x.listed} listed · {x.snapshot_fresh} with a fresh price · {x.execution_eligible} paper-tradable · {x.delisted} delisted</div>
          </div>
        ))}
      </div>
      <div className="col" style={{ gap: 6 }}>
        <div className="tiny muted">CANNOT OBSERVE</div>
        {(m.uncovered ?? []).map((u: any) => <div key={u.market} className="tiny"><b>{u.market}</b> <span className="dim">— {u.reason}</span></div>)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- network: the brain and one cluster per group
function Network({ groups, agents, pulses, onOpen }: { groups: any[]; agents: Agent[]; pulses: Set<string>; onOpen: (id: string) => void }) {
  const W = 1000, H = 560, cx = W / 2, cy = H / 2;
  const layout = useMemo(() => {
    const gs = groups.filter((g) => g.target > 0);
    return gs.map((g, i) => {
      const ang = -Math.PI / 2 + (i * 2 * Math.PI) / gs.length;
      const x = cx + Math.cos(ang) * 360, y = cy + Math.sin(ang) * 205;
      const members = agents.filter((a) => a.group === g.group);
      const pts = members.map((a, k) => {
        const r = 6.2 * Math.sqrt(k + 0.5), t = k * 2.39996;          // sunflower packing
        return { a, x: x + Math.cos(t) * r, y: y + Math.sin(t) * r };
      });
      const rad = 6.2 * Math.sqrt(members.length + 0.5) + 8;
      return { g, x, y, pts, rad };
    });
  }, [groups, agents, cx, cy]);
  const blocked = agents.filter((a) => a.runtime === "blocked").length;
  return (
    <div style={{ padding: "8px 14px 12px" }}>
      <svg className="net" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`${agents.length} trading agents in ${layout.length} groups around the brain; ${blocked} blocked. Use the Agent grid tab for a table.`}>
        {layout.map(({ g, x, y }) => (
          <line key={`l-${g.group}`} x1={cx} y1={cy} x2={x} y2={y} stroke="#2a3b55" strokeWidth={g.assigned ? 1.6 : 1} strokeDasharray={g.assigned ? "" : "4 6"} />
        ))}
        <circle cx={cx} cy={cy} r={34} fill="#101a2b" stroke="#a78bfa" strokeWidth={2} />
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize="12" fontWeight="700" fill="#f2f6ff">BRAIN</text>
        <text x={cx} y={cy + 13} textAnchor="middle" fontSize="9.5" fill="#a9b8ce">coordinator</text>
        {layout.map(({ g, x, y, pts, rad }) => (
          <g key={g.group}>
            <circle cx={x} cy={y} r={rad} fill="rgba(23,36,58,0.55)" stroke="#2a3b55" />
            {pts.map(({ a, x: px, y: py }) => (
              <circle key={a.id} cx={px} cy={py} r={pulses.has(a.id) ? 4.2 : 2.6} fill={DOT[a.runtime] ?? "#33445f"}
                stroke={a.position ? "#f2f6ff" : "none"} strokeWidth={a.position ? 1.2 : 0}
                className={`dot-agent ${pulses.has(a.id) ? "pulse" : ""}`} onClick={() => onOpen(a.id)}>
                <title>{`${a.id} · ${a.partition[0] ?? "no market"} · ${a.runtime} · ${a.job}`}</title>
              </circle>
            ))}
            <text x={x} y={y + rad + 15} textAnchor="middle" fontSize="12.5" fontWeight="650" fill="#f2f6ff">{GROUP_LABEL[g.group] ?? g.group} <tspan fill="#a9b8ce" fontWeight="400">{g.assigned}/{g.target}</tspan></text>
            {g.reassigned > 0 && <text x={x} y={y + rad + 29} textAnchor="middle" fontSize="10.5" fill="#f5c76b">{g.reassigned} reassigned to crypto</text>}
          </g>
        ))}
      </svg>
      <div className="row wrap tiny dim" style={{ gap: 14 }}>
        <Legend c="var(--good)" t="available" /><Legend c="var(--warn)" t="degraded (data late)" />
        <Legend c="#33445f" t="blocked (no distinct market)" /><Legend c="var(--accent)" t="starting" />
        <span className="row" style={{ gap: 6 }}><svg width="12" height="12"><circle cx="6" cy="6" r="4" fill="var(--good)" stroke="#f2f6ff" strokeWidth="1.2" /></svg>holds a position</span>
        <span>A dot grows briefly only when that agent received new market data since the last refresh.</span>
      </div>
      <div className="scroll" style={{ marginTop: 10 }}>
        <table className="t small">
          <thead><tr><th>Group</th><th>IDs</th><th className="num">Assigned</th><th className="num">Fresh data</th><th>Coverage gap</th></tr></thead>
          <tbody>{groups.map((g) => (
            <tr key={g.group}><td><b>{GROUP_LABEL[g.group] ?? g.group}</b> <span className="tiny muted">{g.label}</span></td><td className="mono tiny">{g.ids}</td>
              <td className="num mono">{g.assigned}/{g.target}</td><td className="num mono">{g.ready}</td>
              <td className="tiny dim">{g.gap ?? "none"}{g.reassigned ? ` · ${g.reassigned} agent(s) reassigned to other eligible markets` : ""}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

function Legend({ c, t }: { c: string; t: string }) {
  return <span className="row" style={{ gap: 6 }}><span style={{ width: 9, height: 9, borderRadius: 9, background: c, display: "inline-block" }} />{t}</span>;
}

// ---------------------------------------------------------------- agent grid: searchable, filterable, virtualized
const ROW_H = 138, HEAD_H = 34, MIN_W = 260;
type Row = { kind: "head"; label: string; n: number } | { kind: "cards"; items: Agent[] };

function AgentGrid({ agents, groups, onOpen }: { agents: Agent[]; groups: any[]; onOpen: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [state, setState] = useState("");
  const [market, setMarket] = useState("");
  const [by, setBy] = useState<"group" | "market" | "venue" | "job">("group");
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  const [top, setTop] = useState(0);
  const viewH = 600;

  useLayoutEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const markets = useMemo(() => Array.from(new Set(agents.map((a) => a.market).filter(Boolean))).sort() as string[], [agents]);
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return agents.filter((a) => (!group || a.group === group) && (!state || a.runtime === state) && (!market || a.market === market) &&
      (!s || a.id.toLowerCase().includes(s) || a.partition.some((p) => p.toLowerCase().includes(s)) || a.job.includes(s) ||
        (a.strategies ?? []).some((x) => x.toLowerCase().includes(s))));
  }, [agents, q, group, state, market]);

  const cols = Math.max(1, Math.floor(width / MIN_W));
  const rows = useMemo(() => {
    const key = (a: Agent) => by === "group" ? (GROUP_LABEL[a.group] ?? a.group) : by === "market" ? (a.market ?? "no market")
      : by === "venue" ? (a.venue ?? "no venue") : a.job;
    const buckets = new Map<string, Agent[]>();
    for (const a of shown) {
      const k = key(a);
      if (!buckets.has(k)) buckets.set(k, []);
      buckets.get(k)!.push(a);
    }
    const out: Row[] = [];
    for (const [label, items] of buckets) {
      out.push({ kind: "head", label, n: items.length });
      for (let i = 0; i < items.length; i += cols) out.push({ kind: "cards", items: items.slice(i, i + cols) });
    }
    return out;
  }, [shown, by, cols]);

  const offsets = useMemo(() => {
    let y = 0;
    return rows.map((r) => { const o = y; y += r.kind === "head" ? HEAD_H : ROW_H; return o; });
  }, [rows]);
  const total = rows.length ? offsets[offsets.length - 1] + (rows[rows.length - 1].kind === "head" ? HEAD_H : ROW_H) : 0;
  const first = Math.max(0, offsets.findIndex((o, i) => o + (rows[i].kind === "head" ? HEAD_H : ROW_H) >= top) - 2);
  let last = first;
  while (last < rows.length && offsets[last] < top + viewH + ROW_H * 2) last++;

  return (
    <div style={{ padding: "10px 14px 12px" }} className="col">
      <div className="row wrap">
        <input placeholder="Search agent, market or strategy" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search agents" style={{ flex: "1 1 220px" }} />
        <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Coverage group">
          <option value="">All groups</option>{groups.map((g) => <option key={g.group} value={g.group}>{GROUP_LABEL[g.group] ?? g.group}</option>)}
        </select>
        <select value={state} onChange={(e) => setState(e.target.value)} aria-label="State">
          <option value="">All states</option>{["available", "degraded", "blocked", "starting", "stopped"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={market} onChange={(e) => setMarket(e.target.value)} aria-label="Market">
          <option value="">All markets</option>{markets.map((m) => <option key={m}>{m}</option>)}
        </select>
        <select value={by} onChange={(e) => setBy(e.target.value as any)} aria-label="Group by">
          <option value="group">Group by coverage group</option><option value="market">Group by asset class</option>
          <option value="venue">Group by venue</option><option value="job">Group by current job</option>
        </select>
        <span className="tiny muted">{shown.length} of {agents.length}</span>
      </div>
      <div ref={box} className="vgrid" style={{ height: viewH }} onScroll={(e) => setTop((e.target as HTMLDivElement).scrollTop)}>
        {!rows.length ? <Empty>No agent matches.</Empty> : (
          <div style={{ height: total, position: "relative" }}>
            {rows.slice(first, last).map((r, k) => {
              const i = first + k;
              return r.kind === "head"
                ? <div key={`h-${r.label}-${i}`} className="vhead" style={{ top: offsets[i], height: HEAD_H }}>{r.label} <span className="muted">· {r.n}</span></div>
                : <div key={`r-${i}`} className="vrow" style={{ top: offsets[i], height: ROW_H, gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
                  {r.items.map((a) => <AgentCard key={a.id} a={a} onOpen={onOpen} />)}
                </div>;
            })}
          </div>
        )}
      </div>
      <div className="note">Only the visible cards are drawn (the list is virtualized). Blocked agents are configured identities without a distinct market; they are never counted as ready.</div>
    </div>
  );
}

function AgentCard({ a, onOpen }: { a: Agent; onOpen: (id: string) => void }) {
  const iid = a.partition[0];
  const d = a.last_decision;
  return (
    <button className={`agent-card ${a.runtime}`} onClick={() => onOpen(a.id)} title={a.detail}>
      <div className="spread"><span><b className="mono">{a.id}</b> <span className="tiny muted">{GROUP_LABEL[a.group] ?? a.group}</span></span><Badge kind={RUNTIME_KIND[a.runtime] ?? ""}>{a.runtime}</Badge></div>
      <div className="tiny ell">{iid ? <><span className="mono">{iid}</span>{a.last_price && <span className="dim"> · {fmt.price(a.last_price)} · {fmt.ago(a.last_input_ts)}</span>}</> : <span className="muted">no distinct market</span>}</div>
      <div className="tiny ell dim"><b style={{ color: "var(--text)" }}>{a.job}</b>{(a.strategies ?? []).length ? ` · ${a.strategies!.join(", ")}` : ""}</div>
      <div className="tiny ell muted">budget {fmt.money(a.budget)} · pos {a.position ?? "—"} · orders {a.open_orders ?? 0} · fees {a.fees ? fmt.money(a.fees) : "—"}</div>
      <div className="tiny ell muted">{d ? <>last decision <b className="dim">{d.outcome}</b> {fmt.ago(d.ts)}</> : "no decision yet"}{a.unrealized ? <> · <span className={tone(a.unrealized)}>{fmt.signed(a.unrealized)}</span> open</> : null}{a.errors ? <span className="neg"> · {a.errors} error(s)</span> : null}</div>
    </button>
  );
}

// ---------------------------------------------------------------- one agent
function AgentDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const [d, , err] = usePoll<any>(`/api/fleet/${id}`, 5000, [id]);
  const [list, setList] = useState<"" | "implemented_for_market" | "blocked" | "unimplemented">("");
  return (
    <Drawer title={`Trading agent ${id}`} right={d ? <Badge kind={RUNTIME_KIND[d.runtime] ?? ""} dot>{d.runtime}</Badge> : null} onClose={onClose}>
      {err && <div className="callout bad">{err}</div>}
      {!d ? <Empty>Loading…</Empty> : (
        <>
          <div className="grid g-2">
            <Card title="Assignment and state">
              <div className="kv small">
                <div>Group</div><div>{GROUP_LABEL[d.group] ?? d.group}</div>
                <div>Market</div><div className="mono">{d.partition.length ? d.partition.join(", ") : "none (blocked)"}</div>
                <div>Asset class</div><div>{d.market ?? "—"}</div>
                <div>Job</div><div><b>{d.job}</b></div>
                <div>Detail</div><div className="dim">{d.detail}</div>
                <div>Next action</div><div className="dim">{d.next_action ?? "—"}</div>
                <div>Assignment version</div><div className="mono">{d.assignment_version}</div>
                <div>Market-state version used</div><div className="mono">{d.consumed_version ?? "—"}</div>
                <div>Last data</div><div className="mono">{fmt.price(d.last_price)} · {fmt.ago(d.last_input_ts)}{d.fresh ? "" : " (not fresh)"}</div>
                <div>Heartbeat</div><div className="mono">{fmt.ago(d.heartbeat)} · job {d.job_ms ?? "—"} ms</div>
                <div>Virtual budget</div><div className="mono">{fmt.money(d.budget)} <span className="tiny muted">(zero until a strategy qualifies on this market)</span></div>
              </div>
            </Card>
            <Card title="Dependencies and tools">
              <div className="kv small">
                {Object.entries(d.dependencies).map(([k, v]: any) => <Fragment key={k}><div>{k}</div><div>{v === true ? "yes" : v === false ? "no" : v ?? "—"}</div></Fragment>)}
              </div>
              <ul className="small dim" style={{ margin: "10px 0 0", paddingLeft: 18 }}>{d.tools.map((t: string) => <li key={t}>{t}</li>)}</ul>
            </Card>
          </div>
          <Card title="Strategy catalog access" sub="every agent reads the shared 124-card catalog; it may trade only strategies that qualified on its own market">
            <div className="row wrap">
              <Badge kind={d.catalog.eligible.length ? "good" : ""}>{d.catalog.eligible.length} qualified here</Badge>
              <button className="btn sm" onClick={() => setList(list === "implemented_for_market" ? "" : "implemented_for_market")}>{d.catalog.implemented_for_market.length} implemented for this market</button>
              <button className="btn sm" onClick={() => setList(list === "unimplemented" ? "" : "unimplemented")}>{d.catalog.unimplemented.length} not implemented for it</button>
              <button className="btn sm" onClick={() => setList(list === "blocked" ? "" : "blocked")}>{d.catalog.blocked.length} blocked (data or product)</button>
            </div>
            {d.catalog.eligible.length > 0 && <div className="small" style={{ marginTop: 8 }}>Qualified: <span className="mono">{d.catalog.eligible.join(", ")}</span></div>}
            {list && <div className="mono tiny dim" style={{ marginTop: 8, wordBreak: "break-word" }}>{d.catalog[list].join(" · ") || "none"}</div>}
          </Card>
          <Card title="Positions and orders" flush>
            {!d.positions.length ? <Empty>No position. {d.open_orders ? `${d.open_orders} working order(s).` : "No working orders."}</Empty> : (
              <table className="t small"><thead><tr><th>Instrument</th><th className="num">Qty</th><th className="num">Avg</th><th className="num">Unrealized</th><th className="num">Realized</th></tr></thead>
                <tbody>{d.positions.map((p: any) => (
                  <tr key={p.instrument_id}><td className="mono">{p.instrument_id}</td><td className="num mono">{p.qty}</td><td className="num mono">{fmt.num(p.avg_price, 6)}</td>
                    <td className={`num mono ${tone(p.unrealized)}`}>{fmt.signed(p.unrealized)}</td><td className={`num mono ${tone(p.realized)}`}>{fmt.signed(p.realized)}</td></tr>
                ))}</tbody></table>
            )}
          </Card>
          <Card title="Recent decisions on this market" flush>
            {!d.decisions.length ? <Empty>No decision yet: decisions start when a qualified strategy runs here.</Empty> : (
              <table className="t small"><thead><tr><th>Time</th><th>Strategy</th><th>Outcome</th><th>Reason</th></tr></thead>
                <tbody>{d.decisions.map((x: any, i: number) => (
                  <tr key={i}><td className="nowrap">{fmt.datetime(x.ts)}</td><td className="mono tiny">{x.strategy_id}</td><td><Badge>{x.outcome}</Badge></td><td className="tiny dim">{x.reason}</td></tr>
                ))}</tbody></table>
            )}
          </Card>
          <div className="grid g-2">
            <Card title="Errors (isolated to this agent)">
              {!d.errors.length ? <Empty>None.</Empty> : d.errors.map((e: any, i: number) => <div key={i} className="small"><span className="mono muted">{fmt.time(e.ts)}</span> <span className="neg">{e.error}</span></div>)}
            </Card>
            <Card title="Assignment history">
              {!d.history.length ? <Empty>No changes this session.</Empty> : d.history.map((h: any, i: number) => (
                <div key={i} className="small"><span className="mono muted">{fmt.datetime(h.ts)}</span> {h.from.join(", ") || "none"} → <b>{h.to.join(", ") || "none"}</b> <span className="dim">({h.why})</span></div>
              ))}
            </Card>
          </div>
        </>
      )}
    </Drawer>
  );
}

// ---------------------------------------------------------------- shared operational capabilities C01-C50
const CAP_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  running: "good", completed: "info", idle: "", "waiting for data": "warn", paused: "warn", blocked: "bad", degraded: "warn",
  failed: "bad", unavailable: "",
};

function Capabilities() {
  const [r] = usePoll<any>("/api/roles", 5000);
  const [q, setQ] = useState("");
  if (!r) return <Empty>Loading…</Empty>;
  const c = r.counts;
  const s = q.trim().toLowerCase();
  const rows = r.roles.filter((x: any) => !s || `${x.id} ${x.name} ${x.component} ${x.state}`.toLowerCase().includes(s));
  return (
    <div style={{ padding: "10px 14px 12px" }} className="col">
      <div className="note">Support services are not trading agents and are not counted in the fleet. {r.model}.</div>
      <div className="stats">
        <Num k="Capabilities" v={c.configured_roles} s="C01–C50" />
        <Num k="Unavailable" v={c.unavailable} s="need a feed or product not connected" />
        <Num k="Signal agent functions" v={c.agent_functions} s="vote or advise inside decisions" />
        <Num k="Active model calls" v={c.active_model_calls} s="no cloud AI connected" />
      </div>
      <input placeholder="Search capabilities" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search capabilities" />
      <div className="scroll" style={{ maxHeight: 520 }}>
        <table className="t small">
          <thead><tr><th>ID</th><th>Capability</th><th>Implementation</th><th>State</th><th>Latest</th></tr></thead>
          <tbody>{rows.map((x: any) => (
            <tr key={x.id}>
              <td className="mono muted">{x.id}</td>
              <td><b>{x.name}</b><div className="tiny muted">{x.component}</div></td>
              <td className="tiny">{x.implementation}{x.agent_functions ? ` · ${x.agent_functions} functions` : ""}</td>
              <td><Badge kind={CAP_KIND[x.state] ?? ""}>{x.state}</Badge></td>
              <td className="tiny dim">{x.latest}{x.latest_ts ? ` · ${fmt.ago(x.latest_ts)}` : ""}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
