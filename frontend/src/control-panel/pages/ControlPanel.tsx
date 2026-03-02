import { Fragment, useState, useEffect, useRef } from "react";
import { api, sseUrl, type SymbolData } from "../api/client";

// --- Types ---

type DetectorState = { name: string; enabled: boolean };
type AlertEntry = { at: string; ticker: string; kind: string; message: string };

// --- Constants ---

const MAX_HISTORY = 60;
const BIAS_STEPS = [-10, -5, -2, -1, 1, 2, 5, 10] as const;

// --- Helpers ---

function formatPrice(p: number): string {
  if (p >= 1000) return p.toFixed(0);
  if (p >= 1) return p.toFixed(2);
  return p.toFixed(4);
}

// --- Sub-components ---

function Sparkline({ prices }: { prices: number[] }) {
  if (prices.length < 2) return <svg className="block w-full" height="40" />;
  const W = 400;
  const H = 40;
  const pad = 2;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const pts = prices
    .map((p, i) => {
      const x = (i / (MAX_HISTORY - 1)) * W;
      const y = pad + ((max - p) / range) * (H - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const color = prices[prices.length - 1] >= prices[0] ? "#3fb950" : "#f85149";
  return (
    <svg
      className="block w-full"
      height="40"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
    >
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function Panel({
  header,
  headerRight,
  children,
}: {
  header: string;
  headerRight?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded border border-[#30363d] bg-[#161b22] overflow-hidden">
      <div className="bg-[#1c2128] border-b border-[#30363d] px-3 py-2 text-[0.7rem] font-semibold uppercase tracking-wider text-[#8b949e] flex items-center">
        {header}
        {headerRight && <span className="ml-auto">{headerRight}</span>}
      </div>
      {children}
    </div>
  );
}

function Btn({
  children,
  onClick,
  active = false,
  danger = false,
  disabled = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active?: boolean;
  danger?: boolean;
  disabled?: boolean;
}) {
  const base =
    "px-3 py-1 text-[0.8rem] rounded border cursor-pointer font-[inherit] transition-colors disabled:opacity-50";
  const variant = active
    ? "bg-[#1f6feb] border-[#58a6ff] text-white"
    : danger
      ? "bg-[#21262d] border-[#f85149] text-[#f85149] hover:bg-[#f8514922]"
      : "bg-[#21262d] border-[#30363d] text-[#c9d1d9] hover:bg-[#30363d]";
  return (
    <button className={`${base} ${variant}`} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

// --- Main component ---

export default function ControlPanel() {
  const [loaded, setLoaded] = useState(false);
  const [stopped, setStopped] = useState(false);

  const [symbols, setSymbols] = useState<SymbolData[]>([]);
  const [symbolPrices, setSymbolPrices] = useState<Record<string, number>>({});
  const [symbolChanges, setSymbolChanges] = useState<Record<string, number | null>>({});
  const [priceHistory, setPriceHistory] = useState<Record<string, number[]>>({});

  const [paused, setPaused] = useState(false);
  const [tickInterval, setTickInterval] = useState(5.0);
  const [regime, setRegime] = useState<"CALM" | "VOLATILE">("CALM");
  const [tickCount, setTickCount] = useState(0);

  const [detectors, setDetectors] = useState<DetectorState[]>([]);
  const [alerts, setAlerts] = useState<AlertEntry[]>([]);
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set());

  // Refs for tick-bar animation (avoids state-driven re-renders)
  const tickBarRef = useRef<HTMLDivElement>(null);
  const lastTickTimeRef = useRef<number | null>(null);
  const tickIntervalRef = useRef(5.0);
  const pausedRef = useRef(false);
  const rafRef = useRef(0);
  const tickDebounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Load initial state
  useEffect(() => {
    api.getState().then((state) => {
      setSymbols(state.symbols);
      const prices: Record<string, number> = {};
      for (const s of state.symbols) prices[s.ticker] = s.price;
      setSymbolPrices(prices);
      setDetectors(
        state.detectors.map((name) => ({
          name,
          enabled: !state.suppressed_detectors.includes(name),
        }))
      );
      setPaused(state.paused);
      pausedRef.current = state.paused;
      setTickInterval(state.tick_interval);
      tickIntervalRef.current = state.tick_interval;
      setLoaded(true);
    });
  }, []);

  // SSE: prices
  useEffect(() => {
    const sse = new EventSource(sseUrl("/sse/prices"));
    sse.onmessage = (e) => {
      const d = JSON.parse(e.data) as { ticker: string; price: number };
      setSymbolPrices((prev) => {
        const prevPrice = prev[d.ticker];
        if (prevPrice !== undefined) {
          const pct = ((d.price - prevPrice) / prevPrice) * 100;
          setSymbolChanges((ch) => ({ ...ch, [d.ticker]: pct }));
        }
        return { ...prev, [d.ticker]: d.price };
      });
      setPriceHistory((hist) => ({
        ...hist,
        [d.ticker]: [...(hist[d.ticker] ?? []), d.price].slice(-MAX_HISTORY),
      }));
    };
    return () => sse.close();
  }, []);

  // SSE: alerts
  useEffect(() => {
    const sse = new EventSource(sseUrl("/sse/alerts"));
    sse.onmessage = (e) => {
      setAlerts((prev) => [JSON.parse(e.data) as AlertEntry, ...prev].slice(0, 200));
    };
    return () => sse.close();
  }, []);

  // SSE: tick progress + bar animation
  useEffect(() => {
    function animateBar() {
      cancelAnimationFrame(rafRef.current);
      const step = () => {
        if (!lastTickTimeRef.current || pausedRef.current) return;
        const pct = Math.min(
          100,
          ((Date.now() - lastTickTimeRef.current) / (tickIntervalRef.current * 1000)) * 100
        );
        if (tickBarRef.current) tickBarRef.current.style.width = `${pct}%`;
        if (pct < 100) rafRef.current = requestAnimationFrame(step);
      };
      rafRef.current = requestAnimationFrame(step);
    }

    const sse = new EventSource(sseUrl("/sse/tick-progress"));
    sse.onmessage = (e) => {
      const d = JSON.parse(e.data);
      setTickCount(d.tick_count);
      tickIntervalRef.current = d.tick_interval;
      pausedRef.current = d.paused;
      setPaused(d.paused);
      if (d.paused) {
        cancelAnimationFrame(rafRef.current);
        if (tickBarRef.current) tickBarRef.current.style.width = "0%";
      } else if (d.last_tick) {
        lastTickTimeRef.current = new Date(d.last_tick).getTime();
        animateBar();
      }
    };
    return () => {
      sse.close();
      cancelAnimationFrame(rafRef.current);
    };
  }, []);

  // --- Handlers ---

  async function handleTogglePause() {
    const r = await api.togglePause();
    setPaused(r.paused);
    pausedRef.current = r.paused;
  }

  async function handleSetRegime(r: "CALM" | "VOLATILE") {
    await api.setRegime(r);
    setRegime(r);
  }

  function handleTickIntervalInput(val: number) {
    setTickInterval(val);
    tickIntervalRef.current = val;
    clearTimeout(tickDebounceRef.current);
    tickDebounceRef.current = setTimeout(() => api.setTickInterval(val), 250);
  }

  async function handleReset() {
    const r = await api.reset();
    setAlerts([
      {
        at: new Date().toISOString(),
        ticker: "—",
        kind: "SYSTEM",
        message: `Engine reset — primed with ${r.primed_aggregates} aggregates`,
      },
    ]);
  }

  async function handleClearAlerts() {
    await api.clearAlerts();
    setAlerts([]);
  }

  async function handleStopServer() {
    if (!confirm("Stop the dev server?")) return;
    await api.stopServer();
    setStopped(true);
  }

  async function handleToggleDetector(name: string) {
    const r = await api.toggleDetector(name);
    setDetectors((prev) =>
      prev.map((d) => (d.name === name ? { ...d, enabled: r.enabled } : d))
    );
  }

  function toggleExpanded(ticker: string) {
    setExpandedTickers((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  function toggleAllExpanded() {
    if (expandedTickers.size === symbols.length) {
      setExpandedTickers(new Set());
    } else {
      setExpandedTickers(new Set(symbols.map((s) => s.ticker)));
    }
  }

  // --- Render ---

  if (stopped) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#0d1117] text-[#8b949e] text-xl">
        Server stopped.
      </div>
    );
  }

  if (!loaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#0d1117] text-[#8b949e]">
        Loading…
      </div>
    );
  }

  const allExpanded = symbols.length > 0 && expandedTickers.size === symbols.length;

  return (
    <div className="bg-[#0d1117] text-[#c9d1d9] text-sm min-h-screen">
      {/* Tick progress bar */}
      <div
        ref={tickBarRef}
        style={{ width: "0%", transition: "width 0.1s linear" }}
        className="fixed top-0 left-0 h-[3px] bg-[#58a6ff] z-50"
      />

      {/* Header */}
      <header className="bg-[#161b22] border-b border-[#30363d] px-6 py-3 flex justify-between items-center mt-[3px]">
        <h1 className="text-base font-semibold text-[#58a6ff]">
          Portfolio Monitor — Dev Mode
        </h1>
        <div className="text-xs text-[#8b949e]">
          Tick <span className="text-[#58a6ff]">{tickCount}</span>
          {" · "}
          <span>{regime}</span>
          {" · "}
          <span>{paused ? "Paused" : "Running"}</span>
        </div>
      </header>

      {/* Main grid: content | sidebar */}
      <div
        className="grid gap-[1px] bg-[#30363d]"
        style={{ gridTemplateColumns: "1fr 320px", minHeight: "calc(100vh - 43px)" }}
      >
        {/* Left column */}
        <div className="bg-[#0d1117] p-4 flex flex-col gap-4">
          {/* Controls */}
          <Panel header="Controls">
            <div className="flex flex-wrap gap-2 items-center p-3">
              <Btn active={paused} onClick={handleTogglePause}>
                {paused ? "Resume" : "Pause"}
              </Btn>

              <label className="flex items-center gap-2 text-xs text-[#8b949e] flex-1 min-w-0">
                Tick
                <input
                  type="range"
                  min="0.5"
                  max="300"
                  step="0.5"
                  value={tickInterval}
                  onChange={(e) => handleTickIntervalInput(parseFloat(e.target.value))}
                  className="flex-1 min-w-0 accent-[#58a6ff]"
                />
                <span className="text-[#58a6ff] min-w-[3em] tabular-nums">
                  {tickInterval}s
                </span>
              </label>

              <Btn active={regime === "CALM"} onClick={() => handleSetRegime("CALM")}>
                Calm
              </Btn>
              <Btn
                active={regime === "VOLATILE"}
                onClick={() => handleSetRegime("VOLATILE")}
              >
                Volatile
              </Btn>

              <span className="ml-auto flex gap-2">
                <Btn danger onClick={handleReset}>
                  Reset
                </Btn>
                <Btn danger onClick={handleStopServer}>
                  Stop Server
                </Btn>
              </span>
            </div>
          </Panel>

          {/* Securities table */}
          <Panel
            header="Securities"
            headerRight={
              <button
                className="text-3xl text-[#484f58] hover:text-[#c9d1d9] transition-colors -my-3 py-1"
                onClick={toggleAllExpanded}
                title="Expand/Collapse all"
              >
                {allExpanded ? "▾" : "▸"}
              </button>
            }
          >
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {(
                    [
                      ["Symbol", "text-left"],
                      ["Type", "text-left"],
                      ["Price", "text-right"],
                      ["Change", "text-right"],
                      ["Bias", "text-left"],
                      ["", "text-right"],
                    ] as [string, string][]
                  ).map(([label, align]) => (
                    <th
                      key={label}
                      className={`${align} text-[0.8rem] uppercase tracking-wide text-[#8b949e] font-semibold px-2 py-1.5 border-b border-[#30363d]`}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {symbols.map((s) => {
                  const price = symbolPrices[s.ticker] ?? s.price;
                  const change = symbolChanges[s.ticker] ?? null;
                  const expanded = expandedTickers.has(s.ticker);
                  return (
                    <Fragment key={s.ticker}>
                      <tr
                        className="bg-[#131920] hover:bg-[#161b22] cursor-pointer border-b border-[#21262d]"
                        onClick={() => toggleExpanded(s.ticker)}
                      >
                        <td className="px-2 py-1.5 font-semibold text-[#58a6ff]">
                          {s.ticker}
                        </td>
                        <td className="px-2 py-1.5">
                          <span className="text-[0.8rem] px-1.5 py-0.5 rounded bg-[#21262d] text-[#8b949e]">
                            {s.asset_type}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-right tabular-nums">
                          {formatPrice(price)}
                        </td>
                        <td
                          className={`px-2 py-1.5 text-right tabular-nums ${
                            change === null
                              ? ""
                              : change >= 0
                                ? "text-[#3fb950]"
                                : "text-[#f85149]"
                          }`}
                        >
                          {change === null
                            ? "—"
                            : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                        </td>
                        <td
                          className="px-2 py-1.5"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex gap-0.5">
                            {BIAS_STEPS.map((step) => (
                              <button
                                key={step}
                                onClick={() => api.setBias(s.ticker, step)}
                                className={`text-[0.8rem] px-1 py-0.5 rounded border border-[#30363d] bg-[#21262d] cursor-pointer font-[inherit] ${
                                  step < 0
                                    ? "text-[#f85149] hover:bg-[#f8514922]"
                                    : "text-[#3fb950] hover:bg-[#3fb95022]"
                                }`}
                              >
                                {step > 0 ? "+" : ""}
                                {step}%
                              </button>
                            ))}
                          </div>
                        </td>
                        <td className="w-6 text-center text-[#484f58] text-3xl pr-2">
                          {expanded ? "▾" : "▸"}
                        </td>
                      </tr>
                      {expanded && (
                        <tr className="border-b border-[#30363d]">
                          <td colSpan={6} className="px-2 py-1 bg-[#090d12]">
                            <Sparkline prices={priceHistory[s.ticker] ?? []} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </Panel>
        </div>

        {/* Right sidebar */}
        <div className="bg-[#0d1117] p-4 flex flex-col gap-4">
          {/* Detectors */}
          <Panel header="Detectors">
            {detectors.map((d) => (
              <div
                key={d.name}
                className="flex justify-between items-center px-3 py-1.5 border-b border-[#21262d] last:border-b-0"
              >
                <span className="text-sm">{d.name}</span>
                <button
                  role="switch"
                  aria-checked={d.enabled}
                  onClick={() => handleToggleDetector(d.name)}
                  className={`relative w-9 h-5 rounded-full cursor-pointer transition-colors ${
                    d.enabled ? "bg-[#238636]" : "bg-[#30363d]"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 bg-[#c9d1d9] rounded-full transition-transform ${
                      d.enabled ? "translate-x-4" : ""
                    }`}
                  />
                </button>
              </div>
            ))}
          </Panel>

          {/* Alert log */}
          <div className="flex-1 flex flex-col rounded border border-[#30363d] bg-[#161b22] overflow-hidden min-h-0">
            <div className="bg-[#1c2128] border-b border-[#30363d] px-3 py-2 text-[0.7rem] font-semibold uppercase tracking-wider text-[#8b949e] flex items-center gap-2 shrink-0">
              Alerts
              <span className="text-[#58a6ff]">{alerts.length}</span>
              <button
                className="ml-auto font-normal normal-case tracking-normal text-[#484f58] hover:text-[#c9d1d9] transition-colors"
                onClick={handleClearAlerts}
              >
                clear
              </button>
            </div>
            <div className="overflow-y-auto flex-1">
              {alerts.length === 0 ? (
                <div className="p-4 text-center text-[#484f58] italic text-xs">
                  Waiting for alerts…
                </div>
              ) : (
                alerts.map((a, i) => (
                  <div
                    key={i}
                    className="px-3 py-1.5 border-b border-[#21262d] text-xs last:border-b-0"
                  >
                    <span className="text-[#8b949e] mr-2">
                      {new Date(a.at).toLocaleTimeString()}
                    </span>
                    <span className="text-[#58a6ff] font-semibold mr-1">{a.ticker}</span>
                    <span className="text-[0.65rem] bg-[#f8514933] text-[#f85149] px-1.5 py-0.5 rounded mr-1">
                      {a.kind}
                    </span>
                    <span>{a.message}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
