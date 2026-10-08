// The only way the dashboard talks to the local server. The session token comes from the page itself (the server
// writes it into index.html), so nothing is typed or stored by the owner.

const meta = document.querySelector('meta[name="ta-token"]') as HTMLMetaElement | null;
export const TOKEN = meta?.content ?? "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: { "X-TA-Token": TOKEN, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: text };
  }
  if (!r.ok) {
    const msg = data?.error ?? (Array.isArray(data?.detail) ? data.detail.map((d: any) => d.msg).join("; ") : data?.detail)
      ?? `HTTP ${r.status}`;
    throw new ApiError(String(msg), r.status);
  }
  return data as T;
}

export const api = {
  get: <T = any>(path: string) => request<T>("GET", path),
  post: <T = any>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  del: <T = any>(path: string) => request<T>("DELETE", path),
};

export type BusEvent = { id: number; ts: number; topic: string; severity: string; correlation_id: string | null; data: any };

// One WebSocket for the whole page, reconnecting with back-off and asking for what it missed.
export function connectLive(onEvent: (e: BusEvent) => void, onStatus: (s: "live" | "reconnecting" | "offline") => void) {
  let last = 0;
  let ws: WebSocket | null = null;
  let tries = 0;
  let closed = false;
  let pingTimer: number | undefined;

  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(TOKEN)}&since=${last}`);
    ws.onopen = () => {
      tries = 0;
      onStatus("live");
      pingTimer = window.setInterval(() => ws?.readyState === 1 && ws.send("ping"), 20000);
    };
    ws.onmessage = (m) => {
      const ev = JSON.parse(m.data);
      if (ev.topic === "hello") {
        for (const missed of ev.data.missed ?? []) {
          last = Math.max(last, missed.id);
          onEvent(missed);
        }
        onEvent({ id: 0, ts: Date.now(), topic: "hello", severity: "info", correlation_id: null, data: ev.data });
        return;
      }
      last = Math.max(last, ev.id ?? 0);
      onEvent(ev);
    };
    ws.onclose = () => {
      window.clearInterval(pingTimer);
      if (closed) return;
      tries += 1;
      onStatus(tries > 5 ? "offline" : "reconnecting");
      window.setTimeout(open, Math.min(10000, 500 * 2 ** Math.min(tries, 5)));
    };
  };
  open();
  return () => {
    closed = true;
    ws?.close();
  };
}

// ---------------------------------------------------------------- formatting (never invents a value: null shows "—")
export const fmt = {
  money(v: string | number | null | undefined, ccy = "USD", dp = 2) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    return n.toLocaleString(undefined, { style: "currency", currency: ccy, minimumFractionDigits: dp, maximumFractionDigits: dp });
  },
  num(v: string | number | null | undefined, dp = 2) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: dp, minimumFractionDigits: 0 }) : "—";
  },
  pct(v: string | number | null | undefined, dp = 2) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    return Number.isFinite(n) ? `${(n * 100).toFixed(dp)}%` : "—";
  },
  signed(v: string | number | null | undefined, ccy = "USD") {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    return (n > 0 ? "+" : "") + fmt.money(n, ccy);
  },
  time(ms: number | null | undefined) {
    if (!ms) return "—";
    return new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  },
  datetime(ms: number | null | undefined) {
    if (!ms) return "—";
    return new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  },
  ago(ms: number | null | undefined) {
    if (!ms) return "—";
    const s = Math.max(0, (Date.now() - ms) / 1000);
    if (s < 60) return `${Math.round(s)}s ago`;
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
  },
};

export function tone(v: string | number | null | undefined): "pos" | "neg" | "" {
  const n = Number(v);
  if (v === null || v === undefined || !Number.isFinite(n) || n === 0) return "";
  return n > 0 ? "pos" : "neg";
}
