// In dev (Vite), API calls use /ctl prefix which is proxied to the control panel
// server port with the prefix stripped. In production the HTML is served directly
// from the control panel server so no prefix is needed.
const BASE = import.meta.env.DEV ? "/ctl" : "";

export type SymbolData = { ticker: string; asset_type: string; price: number };

export type StateResponse = {
  symbols: SymbolData[];
  detectors: string[];
  suppressed_detectors: string[];
  tick_interval: number;
  paused: boolean;
};

async function post<T = { ok: boolean }>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

export function sseUrl(path: string): string {
  return `${BASE}${path}`;
}

export const api = {
  getState: (): Promise<StateResponse> =>
    fetch(`${BASE}/api/state`).then((r) => r.json()),
  togglePause: () => post<{ ok: boolean; paused: boolean }>("/api/pause"),
  setRegime: (regime: string) =>
    post<{ ok: boolean; regime: string }>("/api/regime", { regime }),
  setTickInterval: (interval: number) => post("/api/tick-interval", { interval }),
  setBias: (ticker: string, bias_pct: number) =>
    post("/api/bias", { ticker, bias_pct }),
  toggleDetector: (name: string) =>
    post<{ ok: boolean; enabled: boolean }>(
      `/api/detector/${encodeURIComponent(name)}/toggle`
    ),
  reset: () => post<{ ok: boolean; primed_aggregates: number }>("/api/reset"),
  clearAlerts: () => post("/api/clear-alerts"),
  stopServer: () => post("/api/stop"),
};
