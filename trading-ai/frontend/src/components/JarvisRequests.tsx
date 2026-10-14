import { api } from "../api";
import { useLive, usePoll } from "../store";
import { Badge, Card } from "./ui";

/** Requests from the JARVIS voice assistant that wait for the owner. Only a click here (the dashboard's own session
 *  token) can approve one; JARVIS holds a token that can ask, never approve. Shown only while something is waiting. */
export function JarvisRequests() {
  const live = useLive();
  const [v, reload] = usePoll<any>("/api/jarvis/pending", 3000);
  const pending: any[] = v?.pending ?? [];
  if (!pending.length) return null;
  const act = async (id: string, what: "approve" | "reject") => {
    try {
      await api.post(`/api/jarvis/pending/${encodeURIComponent(id)}/${what}`);
      live.toast(what === "approve" ? "Approved and done." : "Rejected. Nothing was changed.", what === "approve" ? "ok" : "warn");
    } catch (e: any) {
      live.toast(e.message, "error");
    }
    reload();
  };
  return (
    <Card title="JARVIS is asking you" sub="Nothing happens until you press Approve" right={<Badge kind="warn" dot>{pending.length} waiting</Badge>}>
      <div className="col" style={{ gap: 8 }}>
        {pending.map((p) => (
          <div key={p.id} className="spread" style={{ gap: 12, flexWrap: "wrap" }}>
            <div>
              <b>{p.what}</b>
              {p.args?.minutes ? <span className="muted"> · {p.args.minutes} min</span> : null}
              {p.args?.amount ? <span className="muted"> · {p.args.amount}</span> : null}
              {p.reason ? <div className="tiny muted">JARVIS says: {p.reason}</div> : null}
            </div>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn" onClick={() => act(p.id, "approve")}>Approve</button>
              <button className="btn ghost" onClick={() => act(p.id, "reject")}>Reject</button>
            </div>
          </div>
        ))}
        <div className="tiny muted">JARVIS can never place orders, change risk limits, turn on live trading or reach your accounts.</div>
      </div>
    </Card>
  );
}
