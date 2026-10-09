import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, connectLive, type BusEvent } from "./api";

export type Overview = {
  version: string;
  state: { state: string; since: number; trading: boolean; history: { ts: number; from: string; to: string; reason: string }[] };
  mode: "paper" | "shadow" | "live";
  live: { armed: boolean; connection_id?: string; max_capital?: string; daily_loss?: string };
  risk: any;
  bots: Bot[];
  library: any;
  features: any;
  agents: any;
  brokers: any;
  live_ack: string;
  offline: boolean;
  vault?: string;
  autopilot?: { enabled: boolean; doing: string };
  autostart?: { supported: boolean; enabled: boolean; reason?: string };
};

export type Bot = {
  bot_id: string; instrument_id: string; tf: string; strategy_id: string; signal_mode: string; risk_profile: string;
  max_trades_per_day: number; state: string; trades_today: number; last_bar_ts: number | null; created: number;
  managed_by?: string; tier?: string | null; experiment_id?: string | null; note?: string;
};

type Live = {
  overview: Overview | null;
  account: any | null;
  events: BusEvent[];
  decisions: any[];
  ws: "live" | "reconnecting" | "offline" | "connecting";
  refresh: () => Promise<void>;
  toast: (msg: string, kind?: "ok" | "error" | "warn") => void;
  toasts: { id: number; msg: string; kind: string }[];
};

const Ctx = createContext<Live | null>(null);

export function LiveProvider({ children }: { children: ReactNode }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [account, setAccount] = useState<any | null>(null);
  const [events, setEvents] = useState<BusEvent[]>([]);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [ws, setWs] = useState<Live["ws"]>("connecting");
  const [toasts, setToasts] = useState<{ id: number; msg: string; kind: string }[]>([]);
  const tid = useRef(1);

  const toast = useCallback((msg: string, kind: "ok" | "error" | "warn" = "ok") => {
    const id = tid.current++;
    setToasts((t) => [...t, { id, msg, kind }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 9000 : 4500);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [o, a] = await Promise.all([api.get<Overview>("/api/overview"), api.get("/api/account")]);
      setOverview(o);
      setAccount(a);
    } catch (e: any) {
      if (e?.status === 401) toast("Session expired: reload the page", "error");
    }
  }, [toast]);

  useEffect(() => {
    refresh();
    api.get("/api/decisions?limit=60").then(setDecisions).catch(() => undefined);
    const t = window.setInterval(refresh, 10000);
    const stop = connectLive((ev) => {
      if (ev.topic === "hello") {
        setOverview(ev.data.overview);
        setAccount(ev.data.account);
        return;
      }
      setEvents((prev) => (prev.length > 600 ? [...prev.slice(-500), ev] : [...prev, ev]));
      if (ev.topic === "account") setAccount(ev.data);
      if (ev.topic === "decision") setDecisions((d) => [ev.data, ...d].slice(0, 200));
      if (["state", "kill_switch", "risk.locked", "order.update"].includes(ev.topic)) refresh();
      if (ev.topic === "kill_switch") toast("STOP ALL TRADING engaged", "error");
      if (ev.topic === "risk.locked") toast("Trading locked by a loss breaker", "error");
    }, (s) => setWs(s));
    return () => {
      window.clearInterval(t);
      stop();
    };
  }, [refresh, toast]);

  return (
    <Ctx.Provider value={{ overview, account, events, decisions, ws, refresh, toast, toasts }}>
      {children}
    </Ctx.Provider>
  );
}

export function useLive(): Live {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLive outside LiveProvider");
  return v;
}

// Small helper for polling an endpoint while a component is on screen.
export function usePoll<T>(path: string | null, ms = 5000, deps: unknown[] = []): [T | null, () => void, string | null] {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => {
    if (!path) return;
    api.get<T>(path).then((d) => {
      setData(d);
      setErr(null);
    }).catch((e) => setErr(String(e.message ?? e)));
  }, [path]);
  useEffect(() => {
    load();
    if (!ms) return;
    const t = window.setInterval(load, ms);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, ms, ...deps]);
  return [data, load, err];
}
