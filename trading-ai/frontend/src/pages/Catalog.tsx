import { useMemo, useState } from "react";
import { api, fmt } from "../api";
import { Badge, Card, Drawer, Empty } from "../components/ui";
import { useLive, usePoll } from "../store";
import { ExperimentDrawer, Verdict } from "./StrategyLab";

const STATE_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  documented: "", specified: "", implemented: "info", evaluated: "info", paper_eligible: "good", live_eligible: "good",
  suspended: "bad",
};
const STATE_LABEL: Record<string, string> = {
  documented: "documented", specified: "specified (blocked)", implemented: "implemented", evaluated: "evaluated",
  paper_eligible: "paper-eligible", live_eligible: "live-eligible", suspended: "suspended",
};
const EV_KIND: Record<string, "good" | "info" | "warn"> = { R: "good", C: "info", H: "warn" };

export function CatalogCard() {
  const [cat] = usePoll<any>("/api/catalog", 30000);
  const [open, setOpen] = useState(false);
  if (!cat) return <Card title="Strategy catalog"><Empty>Loading…</Empty></Card>;
  const s = cat.states;
  return (
    <Card title="Strategy catalog" sub="80 templates from your specification (ST001-ST080)" right={<button className="btn sm" onClick={() => setOpen(true)}>Open catalog</button>}>
      <div className="col" style={{ gap: 8 }}>
        <div className="row wrap">
          {["paper_eligible", "evaluated", "implemented", "specified", "documented", "suspended"].map((k) => s[k] ? (
            <Badge key={k} kind={STATE_KIND[k]}>{s[k]} {STATE_LABEL[k]}</Badge>
          ) : null)}
        </div>
        <div className="note">Published evidence (R research-supported, C documented construction, H hypothesis) is shown separately from this
          installation's own backtests. Templates that need options, bonds, order books, funding or fundamentals are listed with the reason code
          that blocks them, never faked.</div>
      </div>
      {open && <CatalogDrawer cat={cat} onClose={() => setOpen(false)} />}
    </Card>
  );
}

function CatalogDrawer({ cat, onClose }: { cat: any; onClose: () => void }) {
  const live = useLive();
  const [group, setGroup] = useState("");
  const [state, setState] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [exp, setExp] = useState<string | null>(null);
  const cards = useMemo(() => cat.cards.filter((c: any) => (!group || c.group === group) && (!state || c.state === state) &&
    (!q || (c.id + " " + c.name + " " + c.card).toLowerCase().includes(q.toLowerCase()))), [cat, group, state, q]);
  const c = cat.cards.find((x: any) => x.id === sel);
  return (
    <Drawer title="Strategy catalog · 80 templates" onClose={onClose}>
      <div className="note">{cat.note} Source: {cat.spec}.</div>
      <div className="row wrap">
        <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Group">
          <option value="">All groups</option>
          {Object.entries(cat.groups).map(([k, v]) => <option key={k} value={k}>{k}. {String(v)}</option>)}
        </select>
        <select value={state} onChange={(e) => setState(e.target.value)} aria-label="State">
          <option value="">All states</option>
          {Object.keys(STATE_LABEL).map((k) => <option key={k} value={k}>{STATE_LABEL[k]} ({cat.states[k] ?? 0})</option>)}
        </select>
        <input placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {!c ? (
        <div className="scroll" style={{ maxHeight: "70vh" }}>
          <table className="t small">
            <thead><tr><th>ID</th><th>Template</th><th>Evidence</th><th>State</th><th>This installation</th></tr></thead>
            <tbody>{cards.map((x: any) => (
              <tr key={x.id} className="click" onClick={() => setSel(x.id)}>
                <td className="mono">{x.id}</td>
                <td><b>{x.name}</b><div className="tiny muted">{x.groupName ?? cat.groups[x.group]}</div></td>
                <td>{x.evidence_labels.map((e: string) => <Badge key={e} kind={EV_KIND[e]}>{e}</Badge>)}</td>
                <td><Badge kind={STATE_KIND[x.state]}>{STATE_LABEL[x.state]}</Badge>{x.blocked && <div className="tiny muted">{x.blocked}</div>}</td>
                <td className="tiny">{x.runs ? Object.entries(x.verdicts).map(([k, v]) => `${v} ${k}`).join(" · ") : <span className="muted">{x.blocked ? "—" : "not tested yet"}</span>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : (
        <div className="col">
          <div className="row"><button className="btn sm" onClick={() => setSel(null)}>← All templates</button><span className="grow" />
            <Badge kind={STATE_KIND[c.state]}>{STATE_LABEL[c.state]}</Badge></div>
          <h3 style={{ margin: 0 }}>{c.id} — {c.name}</h3>
          <div className="row wrap small">{c.evidence_labels.map((e: string) => <Badge key={e} kind={EV_KIND[e]}>{e}: {cat.evidence_labels[e]}</Badge>)}</div>
          <Card title="Specification card (your document)"><div className="small" style={{ whiteSpace: "pre-wrap" }}>{c.card}</div></Card>
          <Card title="Sources" sub="access labels are the specification's; this software has not replicated the studies">
            {c.sources.length === 0 ? <Empty>No source cited: a hypothesis.</Empty> : c.sources.map((sid: string) => {
              const s = cat.sources[sid];
              return s ? (
                <div key={sid} className="check"><span className="ic mono tiny">{sid}</span>
                  <div className="grow"><a href={s.url} target="_blank" rel="noreferrer noopener">{s.title}</a>
                    <div className="note">access {s.access}: {cat.access_labels[s.access] ?? s.access} · {s.scope}</div></div></div>
              ) : <div key={sid} className="tiny muted">{sid}: not in the register</div>;
            })}
          </Card>
          <Card title="In this software">
            <div className="kv small">
              <div>Implemented by</div><div className="mono">{c.implementations.length ? c.implementations.join(", ") : "—"}</div>
              <div>Blocked by</div><div>{c.blocked ? <><Badge kind="warn">{c.blocked}</Badge> <span className="dim">{cat.reason_codes[c.blocked]}</span></> : "nothing"}</div>
              <div>Notes</div><div className="dim">{c.mapping_note}</div>
              <div>Templates</div><div>{c.templates} single-market template(s){c.portfolio.length ? ` + portfolio ${c.portfolio.join(", ")}` : ""}</div>
              <div>Backtests here</div><div>{c.runs ? Object.entries(c.verdicts).map(([k, v]) => `${v} ${k}`).join(" · ") : "none yet"}</div>
              {c.best && <><div>Best result</div><div><Verdict v={c.best.verdict} /> <span className="mono tiny">{c.best.strategy_id} · {c.best.instrument} {c.best.tf}</span> <span className="dim">quality {fmt.num(c.best.quality, 0)} · {fmt.datetime(c.best.created)}</span>{" "}
                <button className="btn sm ghost" onClick={() => setExp(c.best.experiment_id)}>Open</button></div></>}
            </div>
            {c.portfolio.length > 0 && (
              <div className="row wrap" style={{ marginTop: 10 }}>
                {c.portfolio.map((p: string) => (
                  <span key={p} className="row">
                    <button className="btn sm" onClick={async () => {
                      try { await api.post(`/api/catalog/${p}/research`); live.toast(`${p} portfolio backtest queued`, "ok"); } catch (e: any) { live.toast(e.message, "error"); }
                    }}>Backtest {p}</button>
                    <button className="btn sm" onClick={async () => {
                      try { await api.post("/api/portfolio-bots", { strategy_id: p, allocation: 0.15 }); live.toast(`${p} paper portfolio bot added (stopped)`, "ok"); await live.refresh(); } catch (e: any) { live.toast(e.message, "error"); }
                    }}>Add paper bot (15%)</button>
                  </span>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
      {exp && <ExperimentDrawer eid={exp} onClose={() => setExp(null)} />}
    </Drawer>
  );
}
