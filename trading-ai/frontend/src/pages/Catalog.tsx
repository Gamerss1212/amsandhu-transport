import { useMemo, useState } from "react";
import { fmt } from "../api";
import { Badge, Card, Drawer, Empty, Tabs } from "../components/ui";
import { usePoll } from "../store";
import { ExperimentDrawer, Verdict } from "./StrategyLab";

// The owner's strategy registry, read-only: every card, its published evidence, what blocks it here, the owner's own
// batch results and this installation's automatic research. Nothing on this panel starts a test or a bot.

const STATE_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  documented: "", specified: "", implemented: "info", evaluated: "info", paper_eligible: "good", live_eligible: "good",
  suspended: "bad",
};
const STATE_LABEL: Record<string, string> = {
  documented: "documented", specified: "specified (blocked)", implemented: "implemented", evaluated: "evaluated",
  paper_eligible: "paper-eligible", live_eligible: "live-eligible", suspended: "suspended",
};
const RSTATE_KIND: Record<string, "good" | "warn" | "bad" | "info" | ""> = {
  DISCOVERED: "", RULES_INCOMPLETE: "warn", DATA_BLOCKED: "", IMPLEMENTED_RESEARCH_ONLY: "info", TEST_COMPLETE: "warn",
  REJECTED_UNDER_TEST: "bad", VALIDATION_PENDING: "good",
};
const EV_KIND: Record<string, "good" | "info" | "warn"> = { R: "good", C: "info", H: "warn" };

export function CatalogCard() {
  const [cat] = usePoll<any>("/api/catalog", 30000);
  const [open, setOpen] = useState(false);
  if (!cat) return <Card title="Strategy catalog"><Empty>Loading…</Empty></Card>;
  const r = cat.research_states;
  return (
    <Card title="Strategy catalog" sub={`${cat.cards.length} templates and ${cat.index.length} research-index entries from your specification`}
      right={<button className="btn sm" onClick={() => setOpen(true)}>Open catalog</button>}>
      <div className="col" style={{ gap: 8 }}>
        <div className="row wrap">
          <Badge kind={cat.qualifying.count ? "good" : "warn"}>{cat.qualifying.count} qualifying</Badge>
          {["VALIDATION_PENDING", "TEST_COMPLETE", "REJECTED_UNDER_TEST", "IMPLEMENTED_RESEARCH_ONLY", "RULES_INCOMPLETE", "DATA_BLOCKED"].map((k) => r[k] ? (
            <Badge key={k} kind={RSTATE_KIND[k]}>{r[k]} {k.toLowerCase().replace(/_/g, " ")}</Badge>
          ) : null)}
        </div>
        <div className="note">{cat.qualifying.count === 0
          ? "No strategy qualifies yet, so no trade is opened: the system watches the markets, keeps testing by itself and stays in cash. "
          : `${cat.qualifying.count} strategy configuration(s) qualify. `}
          Published evidence (R research-supported, C documented construction, H hypothesis) is kept separate from your own batch results and from this
          installation's tests. Cards that need options, bonds, order books, funding, on-chain access or fundamentals show the reason code that blocks them.</div>
      </div>
      {open && <CatalogDrawer cat={cat} onClose={() => setOpen(false)} />}
    </Card>
  );
}

function CatalogDrawer({ cat, onClose }: { cat: any; onClose: () => void }) {
  const [tab, setTab] = useState<"cards" | "index" | "owner">("cards");
  const [group, setGroup] = useState("");
  const [rstate, setRstate] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [exp, setExp] = useState<string | null>(null);
  const cards = useMemo(() => cat.cards.filter((c: any) => (!group || c.group === group) && (!rstate || c.research_state === rstate) &&
    (!q || (c.id + " " + c.name + " " + c.card).toLowerCase().includes(q.toLowerCase()))), [cat, group, rstate, q]);
  const index = useMemo(() => cat.index.filter((r: any) => !q || (r.id + " " + r.key + " " + r.category + " " + r.authors).toLowerCase().includes(q.toLowerCase())), [cat, q]);
  const c = cat.cards.find((x: any) => x.id === sel);
  return (
    <Drawer title={`Strategy catalog · ${cat.cards.length} templates`} onClose={onClose}>
      <div className="note">{cat.note} Source: {cat.spec}. Qualifying list: {cat.qualifying.document} ({cat.qualifying.count}).</div>
      <Tabs tabs={[["cards", `Templates (${cat.cards.length})`], ["index", `Research index (${cat.index.length})`], ["owner", "Your batches"]]} on={tab} set={(t: any) => { setTab(t); setSel(null); }} />
      {tab === "cards" && !c && (
        <>
          <div className="row wrap">
            <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Group">
              <option value="">All groups</option>
              {Object.entries(cat.groups).map(([k, v]) => <option key={k} value={k}>{k}. {String(v)}</option>)}
            </select>
            <select value={rstate} onChange={(e) => setRstate(e.target.value)} aria-label="Research state">
              <option value="">All research states</option>
              {Object.keys(cat.research_state_labels).map((k) => <option key={k} value={k}>{k} ({cat.research_states[k] ?? 0})</option>)}
            </select>
            <input placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="scroll" style={{ maxHeight: "70vh" }}>
            <table className="t small">
              <thead><tr><th>ID</th><th>Template</th><th>Evidence</th><th>Research state</th><th>Results</th></tr></thead>
              <tbody>{cards.map((x: any) => (
                <tr key={x.id} className="click" onClick={() => setSel(x.id)}>
                  <td className="mono">{x.id}</td>
                  <td><b>{x.name}</b><div className="tiny muted">{cat.groups[x.group]}</div></td>
                  <td>{x.evidence_labels.map((e: string) => <Badge key={e} kind={EV_KIND[e]}>{e}</Badge>)}</td>
                  <td><Badge kind={RSTATE_KIND[x.research_state]}>{x.research_state}</Badge>{x.blocked && <div className="tiny muted">{x.blocked}</div>}</td>
                  <td className="tiny">{x.runs ? Object.entries(x.verdicts).map(([k, v]) => `${v} ${k}`).join(" · ") : <span className="muted">{x.blocked ? "—" : "not tested yet"}</span>}
                    {x.owner_evidence.length > 0 && <div className="muted">your batches: {x.owner_evidence.length} rejected model(s)</div>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
      {tab === "cards" && c && (
        <div className="col">
          <div className="row"><button className="btn sm" onClick={() => setSel(null)}>← All templates</button><span className="grow" />
            <Badge kind={RSTATE_KIND[c.research_state]}>{c.research_state}</Badge> <Badge kind={STATE_KIND[c.state]}>{STATE_LABEL[c.state]}</Badge></div>
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
          {c.owner_evidence.length > 0 && (
            <Card title="Your own batches" sub="from your specification's research appendix; run outside this software">
              <div className="scroll"><table className="t small">
                <thead><tr><th>Batch</th><th>Model</th><th>Market</th><th className="num">Median net</th><th className="num">Positive assets</th><th>Status</th></tr></thead>
                <tbody>{c.owner_evidence.map((o: any, i: number) => (
                  <tr key={i}><td>{o.batch}</td><td className="mono tiny">{o.model}</td><td className="tiny">{o.market}</td>
                    <td className="num mono">{o.median_net_pct !== undefined ? `${fmt.num(o.median_net_pct, 2)}%` : "—"}</td>
                    <td className="num mono">{o.positive_assets ?? "—"}</td><td><Badge kind="bad">{o.status}</Badge></td></tr>
                ))}</tbody>
              </table></div>
            </Card>
          )}
          <Card title="In this software">
            <div className="kv small">
              <div>Implemented by</div><div className="mono">{c.implementations.length ? c.implementations.join(", ") : "—"}</div>
              <div>Blocked by</div><div>{c.blocked ? <><Badge kind="warn">{c.blocked}</Badge> <span className="dim">{cat.reason_codes[c.blocked]}</span></> : "nothing"}</div>
              <div>Research state</div><div>{c.research_state}: <span className="dim">{cat.research_state_labels[c.research_state]}</span></div>
              <div>Notes</div><div className="dim">{c.mapping_note}</div>
              <div>Templates</div><div>{c.templates} single-market template(s){c.portfolio.length ? ` + portfolio ${c.portfolio.join(", ")}` : ""}</div>
              <div>Tested here</div><div>{c.runs ? Object.entries(c.verdicts).map(([k, v]) => `${v} ${k}`).join(" · ") : "not yet (the agents test it by themselves)"}</div>
              {c.best && <><div>Best result</div><div><Verdict v={c.best.verdict} /> <span className="mono tiny">{c.best.strategy_id} · {c.best.instrument} {c.best.tf}</span> <span className="dim">quality {fmt.num(c.best.quality, 0)} · {fmt.datetime(c.best.created)}</span>{" "}
                <button className="btn sm ghost" onClick={() => setExp(c.best.experiment_id)}>Open</button></div></>}
            </div>
          </Card>
        </div>
      )}
      {tab === "index" && (
        <>
          <div className="note">Published equity signals (Open Source Asset Pricing metadata, Predictor records). These are discovery entries, not
            strategies or tested systems: each needs its full method, point-in-time stock data with delistings, and an automatic evaluation first.
            Every entry is DATA_BLOCKED here because that stock data is not connected.</div>
          <input placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="scroll" style={{ maxHeight: "65vh" }}>
            <table className="t small">
              <thead><tr><th>ID</th><th>Source key</th><th>Category</th><th>Authors</th><th>Catalog relationship</th></tr></thead>
              <tbody>{index.map((r: any) => (
                <tr key={r.id}><td className="mono">{r.id}</td><td className="mono">{r.key}</td><td>{r.category}</td><td className="tiny">{r.authors}</td><td className="tiny">{r.relation}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
      {tab === "owner" && (
        <div className="col">
          <div className="note">{cat.owner_research.note}</div>
          <div className="callout small"><b>Qualifying strategies: {cat.owner_research.qualifying_count}.</b> {cat.owner_research.qualifying_note}</div>
          {cat.owner_research.batches.map((b: any) => (
            <Card key={b.id} title={b.id} sub={`${b.configurations} configurations · ${b.positive_full_year_after_costs} positive after costs`}
              right={<Badge kind="bad">{b.status}</Badge>}>
              <div className="kv small">
                <div>Market</div><div>{b.market}</div>
                <div>Period</div><div>{b.period}</div>
                <div>Bars</div><div>{b.bars}</div>
                <div>Costs</div><div>{b.costs}</div>
                <div>Result</div><div>{b.result}</div>
                <div>Validation</div><div>{b.validation}</div>
                <div>Models</div><div className="mono tiny">{b.models.map((m: any) => `${m.model} (${m.cards.join(", ")})`).join(" · ")}</div>
              </div>
            </Card>
          ))}
        </div>
      )}
      {exp && <ExperimentDrawer eid={exp} onClose={() => setExp(null)} />}
    </Drawer>
  );
}
