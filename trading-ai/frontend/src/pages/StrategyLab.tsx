import { useState } from "react";
import { api, fmt, tone } from "../api";
import { EquityChart } from "../components/charts";
import { Badge, Card, Check, Drawer, Empty, Tabs } from "../components/ui";
import { useLive, usePoll } from "../store";
import { InstrumentSelect, StrategyPicker, type Instrument } from "./CommandCenter";

const VERDICT_KIND: Record<string, "good" | "warn" | "bad" | ""> = { "PAPER TEST": "good", "RESEARCH FURTHER": "warn", REJECT: "bad" };

export function Verdict({ v }: { v?: string | null }) {
  if (!v) return <Badge>—</Badge>;
  return <Badge kind={VERDICT_KIND[v] ?? ""}>{v}</Badge>;
}

export default function StrategyLab({ instruments, defaultInstrument }: { instruments: Instrument[]; defaultInstrument: string }) {
  const live = useLive();
  const [iid, setIid] = useState(defaultInstrument);
  const inst = instruments.find((i) => i.instrument_id === iid);
  const [tf, setTf] = useState("1h");
  const [sid, setSid] = useState("");
  const [profile, setProfile] = useState("STANDARD");
  const [lookback, setLookback] = useState(5000);
  const [jobs, reloadJobs] = usePoll<any[]>("/api/research/jobs", 2500);
  const [exps, reloadExps] = usePoll<any>("/api/research/experiments?limit=60", 8000);
  const [open, setOpen] = useState<string | null>(null);
  const running = (jobs ?? []).filter((j) => j.state === "running" || j.state === "queued");

  return (
    <Card title="Strategy lab · backtesting" sub="chronological train / validation / test, walk-forward, Monte Carlo, cost stress, deflated Sharpe">
      <div className="col">
        <div className="grid g-3" style={{ gap: 10 }}>
          <label className="field">Instrument<InstrumentSelect value={iid} onChange={setIid} list={instruments} /></label>
          <label className="field">Timeframe
            <select value={tf} onChange={(e) => setTf(e.target.value)}>
              {["5m", "15m", "30m", "1h", "4h", "1d"].filter((t) => inst?.timeframes.includes(t)).map((t) => <option key={t}>{t}</option>)}
            </select>
          </label>
          <div className="row">
            <label className="field grow">Depth
              <select value={profile} onChange={(e) => setProfile(e.target.value)}>
                <option value="FAST">FAST (1 parameter set)</option>
                <option value="STANDARD">STANDARD (9 sets, 200 Monte Carlo)</option>
                <option value="DEEP">DEEP (27 sets, 1000 MC, capacity)</option>
              </select>
            </label>
            <label className="field" style={{ width: 96 }}>Bars<input type="number" min={400} max={20000} step={100} value={lookback} onChange={(e) => setLookback(Number(e.target.value))} /></label>
          </div>
        </div>
        {inst && <label className="field">Strategy template<StrategyPicker market={inst.market} value={sid} onChange={setSid} /></label>}
        <div className="row wrap">
          <button className="btn primary" disabled={!sid} onClick={async () => {
            try {
              await api.post("/api/research", { strategy_id: sid, instrument_id: iid, tf, profile, lookback });
              live.toast("Research job queued", "ok");
              reloadJobs();
            } catch (e: any) {
              live.toast(e.message, "error");
            }
          }}>Run backtest</button>
          <span className="note">Every run is recorded in the research ledger and counts as a trial for multiple-testing correction. A backtest can recommend PAPER TEST at most, never live trading.</span>
        </div>

        {running.length > 0 && (
          <div className="col" style={{ gap: 6 }}>
            {running.map((j) => (
              <div key={j.job_id} className="col" style={{ gap: 4 }}>
                <div className="spread small"><span>{j.title}</span><span className="dim">{j.stage} · {Math.round(j.progress * 100)}%</span></div>
                <div className="row">
                  <div className="bar grow"><i style={{ width: `${j.progress * 100}%` }} /></div>
                  <button className="btn sm ghost" onClick={() => api.post(`/api/research/jobs/${j.job_id}/cancel`).then(reloadJobs)}>Cancel</button>
                </div>
              </div>
            ))}
          </div>
        )}
        {(jobs ?? []).filter((j) => j.state === "failed").slice(0, 3).map((j) => (
          <div key={j.job_id} className="callout bad small">{j.title}: {j.error}</div>
        ))}

        <div className="scroll" style={{ maxHeight: 340 }}>
          {!exps?.experiments?.length ? <Empty>No backtests yet.</Empty> : (
            <table className="t">
              <thead><tr><th>When</th><th>Strategy</th><th>Data</th><th>Depth</th><th>Verdict</th><th className="num">Quality</th><th className="num">Trials</th></tr></thead>
              <tbody>
                {exps.experiments.map((e: any) => (
                  <tr key={e.experiment_id} className="click" onClick={() => setOpen(e.experiment_id)}>
                    <td className="nowrap small">{fmt.datetime(e.created)}</td>
                    <td className="mono small" style={{ wordBreak: "break-all" }}>{e.strategy_id}</td>
                    <td className="small">{e.dataset?.instrument} {e.dataset?.tf} {e.dataset?.simulated && <Badge kind="sim">sim</Badge>}</td>
                    <td className="small">{e.profile}</td>
                    <td>{e.status === "RUNNING" ? <Badge kind="info">running</Badge> : e.verdict ? <Verdict v={e.verdict} /> : <Badge kind="bad">{e.status}</Badge>}</td>
                    <td className="num mono">{e.quality !== null && e.quality !== undefined ? fmt.num(e.quality, 0) : "—"}</td>
                    <td className="num mono">{e.trials_at_run ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        {exps?.counts && <div className="tiny muted">{exps.counts.experiments} experiment(s) in the ledger · {Object.entries(exps.counts.by_status ?? {}).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>}
      </div>
      {open && <ExperimentDrawer eid={open} onClose={() => { setOpen(null); reloadExps(); }} />}
    </Card>
  );
}

const METRICS: [string, string, (v: any) => string][] = [
  ["total_return", "Net return", fmt.pct], ["cagr", "CAGR", fmt.pct], ["max_drawdown", "Max drawdown", fmt.pct],
  ["sharpe", "Sharpe", (v) => fmt.num(v, 2)], ["sortino", "Sortino", (v) => fmt.num(v, 2)],
  ["trades", "Trades", String], ["win_rate", "Win rate", fmt.pct], ["profit_factor", "Profit factor", (v) => fmt.num(v, 2)],
  ["payoff_ratio", "Payoff ratio", (v) => fmt.num(v, 2)], ["expectancy", "Expectancy / trade", (v) => fmt.money(v)],
  ["expectancy_r", "Expectancy (R)", (v) => fmt.num(v, 3)], ["avg_hold_bars", "Avg hold (bars)", (v) => fmt.num(v, 1)],
  ["exposure", "Time in market", fmt.pct], ["net_pnl", "Net P&L", (v) => fmt.money(v)], ["gross_pnl", "Gross P&L", (v) => fmt.money(v)],
];

export function ExperimentDrawer({ eid, onClose }: { eid: string; onClose: () => void }) {
  const [e] = usePoll<any>(`/api/research/experiments/${eid}`, 0, [eid]);
  const [tab, setTab] = useState<"summary" | "robust" | "trades" | "compare">("summary");
  const r = e?.results;
  const [cmp] = usePoll<any>(e ? `/api/research/compare?strategy_id=${encodeURIComponent(e.strategy_id)}&instrument=${encodeURIComponent(e.dataset?.instrument ?? "")}` : null, 0, [e?.experiment_id]);
  return (
    <Drawer title={e ? e.strategy_id : "Loading…"} onClose={onClose} right={r && <Verdict v={r.verdict} />}>
      {!e && <Empty>Loading…</Empty>}
      {e && !r && <div className="callout bad">This run did not finish: {e.status} {e.reason}</div>}
      {e && r && r.status !== "ok" && <div className="callout warn">Result: {r.status} {r.bars ? `(${r.bars} bars, need ${r.needed})` : ""}</div>}
      {e && r && r.status === "ok" && r.kind === "portfolio" && <PortfolioResult r={r} />}
      {e && r && r.status === "ok" && r.kind !== "portfolio" && (
        <>
          <div className="row wrap small">
            <Badge kind={r.reproducibility?.simulated_data ? "sim" : "info"}>{r.reproducibility?.simulated_data ? "SIMULATED DATA" : "REAL HISTORICAL DATA"}</Badge>
            <span className="dim">{e.dataset?.instrument} {e.dataset?.tf} · {r.reproducibility?.bars} bars · {fmt.datetime(r.reproducibility?.start)} → {fmt.datetime(r.reproducibility?.end)}</span>
            <span className="dim">· {r.profile} · {r.runtime_s}s · seed {r.reproducibility?.seed}</span>
          </div>
          <div className="callout small">
            Quality score <b>{fmt.num(r.quality?.score, 0)}/100</b> · trials charged <b>{r.statistics?.trials_charged}</b> · chosen parameters <span className="mono">{JSON.stringify(r.params_chosen)}</span>
            <div className="note" style={{ marginTop: 4 }}>{r.language_note}</div>
          </div>
          <Tabs tabs={[["summary", "Summary"], ["robust", "Robustness"], ["trades", "Test trades"], ["compare", "Backtest vs paper"]]} on={tab} set={setTab} />
          {tab === "summary" && (
            <>
              <Card title="Equity (full history, net of modelled costs)" flush>
                <EquityChart points={r.equity_curve ?? []} start={r.full?.start_equity} />
              </Card>
              <Card title="Train / validation / test (chronological)" sub="parameters chosen on train only; test is untouched" flush>
                <div className="scroll">
                  <table className="t">
                    <thead><tr><th>Metric</th><th className="num">Train</th><th className="num">Validation</th><th className="num">Test (OOS)</th><th className="num">Full</th></tr></thead>
                    <tbody>
                      {METRICS.map(([k, label, f]) => (
                        <tr key={k}><td className="dim">{label}</td>
                          {(["train", "validation", "test", "full"] as const).map((seg) => {
                            const v = r[seg]?.[k];
                            return <td key={seg} className={`num mono ${["total_return", "net_pnl", "expectancy"].includes(k) ? tone(v) : ""}`}>{v === null || v === undefined ? "—" : f(v)}</td>;
                          })}
                        </tr>
                      ))}
                      <tr><td className="dim">Costs (fees+spread+slippage)</td>
                        {(["train", "validation", "test", "full"] as const).map((seg) => <td key={seg} className="num mono">{fmt.money(r[seg]?.costs?.total)}</td>)}</tr>
                    </tbody>
                  </table>
                </div>
              </Card>
              {[r.train, r.validation, r.test].some((x: any) => x?.annualized_note) && (
                <div className="note">CAGR on a segment shorter than a year extrapolates a short period to a full year and can look extreme; read net return and drawdown first.</div>
              )}
              <Card title="Gates">
                {(r.checks ?? []).map((c: any) => (
                  <Check key={c.name} ok={c.passed} name={<>{c.name} {!c.required && <span className="muted tiny">(advisory)</span>}</>}
                    detail={`value ${c.value === null || c.value === undefined ? "—" : typeof c.value === "number" ? fmt.num(c.value, 3) : String(c.value)} · need ${c.need}`} />
                ))}
              </Card>
              <div className="note">Cost model: {(r.reproducibility?.cost_model?.labels ?? []).join("; ")} — {r.reproducibility?.cost_model?.note}</div>
            </>
          )}
          {tab === "robust" && <Robustness r={r} />}
          {tab === "trades" && <TradesTable trades={r.test_trades ?? []} />}
          {tab === "compare" && <Compare c={cmp} />}
        </>
      )}
    </Drawer>
  );
}

function Robustness({ r }: { r: any }) {
  const mc = r.monte_carlo?.trade_reshuffle;
  const st = r.statistics ?? {};
  return (
    <div className="grid g-2">
      <Card title="Walk-forward" sub={`${r.walk_forward?.folds?.length ?? 0} folds`}>
        <div className="kv">
          <div>OOS Sharpe (stitched)</div><div className="mono">{fmt.num(r.walk_forward?.oos_sharpe, 3)}</div>
          <div>OOS / in-sample ratio</div><div className="mono">{fmt.num(r.walk_forward?.oos_is_ratio, 3)}</div>
        </div>
        <table className="t small" style={{ marginTop: 8 }}>
          <thead><tr><th>Fold</th><th className="num">IS Sharpe</th><th className="num">OOS Sharpe</th></tr></thead>
          <tbody>{(r.walk_forward?.folds ?? []).map((f: any, i: number) => (
            <tr key={i}><td>{i + 1}</td><td className="num mono">{fmt.num(f.is_sharpe, 2)}</td><td className="num mono">{fmt.num(f.oos_sharpe, 2)}</td></tr>
          ))}</tbody>
        </table>
      </Card>
      <Card title="Statistics" sub="test segment">
        <div className="kv">
          <div>Probabilistic Sharpe</div><div className="mono">{fmt.num(st.psr, 3)}</div>
          <div>Deflated Sharpe</div><div className="mono">{fmt.num(st.dsr, 3)} <span className="muted tiny">({st.trials_charged} trials)</span></div>
          <div>Newey-West t</div><div className="mono">{fmt.num(st.newey_west_t, 2)}</div>
          <div>Sharpe 95% interval</div><div className="mono">{st.sharpe_ci95 ? `${fmt.num(st.sharpe_ci95[0], 2)} … ${fmt.num(st.sharpe_ci95[1], 2)}` : "—"}</div>
          <div>PBO</div><div className="mono">{st.pbo === null || st.pbo === undefined ? (st.pbo_note ?? "—") : fmt.num(st.pbo, 3)}</div>
          {st.error && <><div>Note</div><div className="neg">{st.error}</div></>}
        </div>
      </Card>
      <Card title="Monte Carlo" sub={`${r.monte_carlo?.runs ?? 0} runs`}>
        {!mc ? <Empty>Not run at this depth (or fewer than 5 trades).</Empty> : (
          <div className="kv">
            <div>Max drawdown p50 / p95</div><div className="mono">{fmt.pct(mc.max_drawdown_p50)} / {fmt.pct(mc.max_drawdown_p95)}</div>
            <div>Final return p5 / p50</div><div className="mono">{fmt.pct(mc.final_return_p5)} / {fmt.pct(mc.final_return_p50)}</div>
            <div>Losing streak p95</div><div className="mono">{fmt.num(mc.losing_streak_p95, 0)}</div>
            <div>Risk of a 50% drawdown</div><div className="mono">{fmt.pct(mc.risk_of_ruin_50pct_dd)}</div>
            <div>Bootstrap Sharpe p5 … p95</div><div className="mono">{fmt.num(r.monte_carlo.bootstrap_sharpe_p5_p95?.[0], 2)} … {fmt.num(r.monte_carlo.bootstrap_sharpe_p5_p95?.[1], 2)}</div>
            <div>Worst Sharpe under cost shocks</div><div className="mono">{fmt.num(r.monte_carlo.cost_shock_sharpe_min, 2)}</div>
            <div>Sharpe with 10% missed fills</div><div className="mono">{fmt.num(r.monte_carlo.missed_10pct_fills_sharpe, 2)}</div>
          </div>
        )}
      </Card>
      <Card title="Cost stress & stability">
        <table className="t small">
          <thead><tr><th>Costs</th><th className="num">Sharpe</th><th className="num">Net return</th></tr></thead>
          <tbody>{Object.entries(r.cost_stress ?? {}).map(([k, v]: any) => (
            <tr key={k}><td>{k}</td><td className="num mono">{fmt.num(v.sharpe, 2)}</td><td className={`num mono ${tone(v.net_return)}`}>{fmt.pct(v.net_return)}</td></tr>
          ))}</tbody>
        </table>
        <div className="kv" style={{ marginTop: 8 }}>
          <div>Parameter stability</div><div className="mono">{r.param_stability === null ? "— (one parameter set)" : fmt.num(r.param_stability, 2)}</div>
          <div>Capacity</div><div className="mono">{r.capacity ? (r.capacity.estimate_usd ? fmt.money(r.capacity.estimate_usd, "USD", 0) : r.capacity.note ?? "below $10,000") : "— (DEEP only)"}</div>
          <div>Net after removing best trades</div><div className="mono small">{Object.entries(r.robustness?.remove_best_trades ?? {}).map(([k, v]) => `${k}: ${fmt.money(v as number)}`).join(" · ") || "—"}</div>
          <div>Placebo percentile</div><div className="mono">{r.robustness?.placebo?.percentile_vs_shifted !== undefined ? `${r.robustness.placebo.percentile_vs_shifted} vs shifted · ${r.robustness.placebo.percentile_vs_random} vs random` : "—"}</div>
        </div>
      </Card>
    </div>
  );
}

function TradesTable({ trades }: { trades: any[] }) {
  if (!trades.length) return <Empty>No trades in the test segment.</Empty>;
  return (
    <div className="scroll" style={{ maxHeight: 520 }}>
      <table className="t small">
        <thead><tr><th>Entry</th><th>Exit</th><th>Side</th><th className="num">Entry px</th><th className="num">Exit px</th><th className="num">Net</th><th className="num">Fees</th><th className="num">R</th><th className="num">Bars</th><th>Exit reason</th></tr></thead>
        <tbody>{trades.slice().reverse().map((t, i) => (
          <tr key={i}>
            <td className="nowrap">{fmt.datetime(t.entry_ts)}</td><td className="nowrap">{fmt.datetime(t.exit_ts)}</td>
            <td>{t.side > 0 ? "long" : "short"}</td>
            <td className="num mono">{fmt.num(t.entry, 6)}</td><td className="num mono">{fmt.num(t.exit, 6)}</td>
            <td className={`num mono ${tone(t.net)}`}>{fmt.signed(t.net)}</td><td className="num mono">{fmt.money(t.fees)}</td>
            <td className="num mono">{fmt.num(t.r, 2)}</td><td className="num mono">{t.bars}</td><td className="small">{t.exit_reason}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Compare({ c }: { c: any }) {
  if (!c) return <Empty>Loading…</Empty>;
  const cols = ["backtest", "paper", "shadow", "live"];
  return (
    <div className="col">
      <table className="t">
        <thead><tr><th></th>{cols.map((k) => <th key={k} className="num">{k}</th>)}</tr></thead>
        <tbody>
          {[["trades", "Trades", String], ["win_rate", "Win rate", fmt.pct], ["expectancy", "Mean return / trade", (v: any) => fmt.pct(v, 3)], ["profit_factor", "Profit factor", (v: any) => fmt.num(v, 2)]].map(([k, label, f]: any) => (
            <tr key={k}><td className="dim">{label}</td>{cols.map((col) => {
              const v = c.columns?.[col]?.[k];
              return <td key={col} className="num mono">{v === null || v === undefined ? "—" : f(v)}</td>;
            })}</tr>
          ))}
        </tbody>
      </table>
      <div className="kv small">
        <div>Backtest mean 95% interval</div><div className="mono">{c.backtest_mean_ci95 ? `${fmt.pct(c.backtest_mean_ci95[0], 3)} … ${fmt.pct(c.backtest_mean_ci95[1], 3)}` : "— (too few trades)"}</div>
        <div>Reality gap</div><div className="mono">{c.reality_gap ?? "—"}</div>
        <div>Flags</div><div>{c.flags?.length ? c.flags.join(", ") : "none"}</div>
        <div>Live candidate</div><div>{c.live_candidate ? <Badge kind="good">yes</Badge> : <Badge>no</Badge>}</div>
      </div>
      <div className="note">{c.rule}. {c.note}</div>
    </div>
  );
}

function PortfolioResult({ r }: { r: any }) {
  const rows: [string, string, (v: any) => string][] = [["total_return", "Net return", fmt.pct], ["cagr", "CAGR", fmt.pct],
    ["vol", "Volatility", fmt.pct], ["sharpe", "Sharpe", (v) => fmt.num(v, 2)], ["max_drawdown", "Max drawdown", fmt.pct], ["years", "Years", (v) => fmt.num(v, 1)]];
  return (
    <>
      <div className="callout small"><b>{r.name}</b> · rebalance {r.rebalance === "M" ? "monthly" : "weekly"} · {r.universe.length} instruments · chosen parameters <span className="mono">{JSON.stringify(r.params_chosen)}</span>
        <div className="note" style={{ marginTop: 4 }}>{r.note}. {r.reproducibility.execution}. {r.language_note}</div></div>
      {r.limitations?.length > 0 && <div className="callout warn small">Limitations: {r.limitations.join("; ")}</div>}
      {r.reason_codes?.length > 0 && <div className="row wrap">{r.reason_codes.map((c: string) => <Badge key={c} kind="warn">{c}</Badge>)}</div>}
      <Card title="Equity (full history, net of costs) vs equal-weight holding" flush>
        <EquityChart points={r.equity_curve ?? []} start={1} />
      </Card>
      <Card title="Held-out period vs benchmark" sub={`held out from ${fmt.datetime(r.split_day)}`} flush>
        <table className="t small"><thead><tr><th>Metric</th><th className="num">Strategy (held out)</th><th className="num">Equal weight (held out)</th><th className="num">Strategy, 2x costs</th><th className="num">Strategy (full)</th></tr></thead>
          <tbody>{rows.map(([k, label, f]) => (
            <tr key={k}><td className="dim">{label}</td>{[r.test, r.benchmark_test, r.cost_2x_test, r.full].map((m: any, i: number) => <td key={i} className="num mono">{m?.[k] === null || m?.[k] === undefined ? "—" : f(m[k])}</td>)}</tr>
          ))}
            <tr><td className="dim">Turnover / year</td><td className="num mono">{fmt.num(r.turnover_per_year, 2)}</td><td /><td /><td /></tr>
          </tbody></table>
      </Card>
      <Card title="Gates">{r.checks.map((c: any) => <Check key={c.name} ok={c.passed} name={<>{c.name} {!c.required && <span className="muted tiny">(advisory)</span>}</>}
        detail={`value ${c.value === null || c.value === undefined ? "—" : typeof c.value === "number" ? fmt.num(c.value, 3) : String(c.value)} · need ${c.need}${c.code ? " · " + c.code : ""}`} />)}</Card>
      <Card title="Statistics (held-out daily returns)"><div className="kv small">
        <div>Probabilistic Sharpe</div><div className="mono">{fmt.num(r.statistics.psr, 3)}</div>
        <div>Deflated Sharpe</div><div className="mono">{fmt.num(r.statistics.dsr, 3)} ({r.statistics.trials_charged} trials)</div>
        <div>Sharpe 95% interval</div><div className="mono">{r.statistics.sharpe_ci95 ? `${fmt.num(r.statistics.sharpe_ci95[0], 2)} … ${fmt.num(r.statistics.sharpe_ci95[1], 2)}` : "—"}</div>
        <div>Weights now</div><div className="mono tiny">{r.weights_now ? Object.entries(r.weights_now.weights).map(([k, v]) => `${k.split(":")[1]} ${fmt.pct(v as number, 0)}`).join(", ") || "cash" : "—"}</div>
      </div></Card>
    </>
  );
}
