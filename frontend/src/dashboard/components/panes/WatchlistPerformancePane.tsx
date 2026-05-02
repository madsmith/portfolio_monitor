import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type DailyClose, type WatchlistDetail } from "../../api/client";
import { fmtPct } from "../../lib/formatters";
import { Sparkline } from "../Sparkline";

type PeriodKey = "1d" | "1w" | "1m" | "3m" | "6m" | "1y";

const PERIODS: { key: PeriodKey; label: string; days: number; window: number }[] = [
  { key: "1d", label: "1D",  days:   1, window:  1 },
  { key: "1w", label: "1W",  days:   7, window:  3 },
  { key: "1m", label: "1M",  days:  30, window:  7 },
  { key: "3m", label: "3M",  days:  90, window:  7 },
  { key: "6m", label: "6M",  days: 180, window: 14 },
  { key: "1y", label: "1Y",  days: 365, window: 30 },
];

type MomentumWindow = 3 | 5 | 7;
type MomentumMode = { kind: "momentum"; window: MomentumWindow };
type ViewMode = "table" | "return" | MomentumMode;

function daysAgoDate(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function smoothedClose(days: DailyClose[], anchorDate: string, windowDays: number): number | null {
  const anchor = new Date(anchorDate);
  const windowStart = new Date(anchor);
  windowStart.setUTCDate(windowStart.getUTCDate() - (windowDays - 1));
  const windowStartStr = windowStart.toISOString().slice(0, 10);

  const windowCloses: number[] = [];
  let fallback: number | null = null;
  for (const day of days) {
    if (day.date > anchorDate) break;
    if (day.date <= anchorDate) fallback = day.close;
    if (day.date >= windowStartStr) windowCloses.push(day.close);
  }

  if (windowCloses.length === 0) return fallback;
  return windowCloses.reduce((sum, c) => sum + c, 0) / windowCloses.length;
}

function pctChange(current: number | null, historic: number | null): number | null {
  if (current === null || historic === null || historic === 0) return null;
  return ((current - historic) / historic) * 100;
}

// Rolling average of daily returns over `windowSize` days.
// Returns values already in % units (no further normalization needed).
function momentumSeries(days: DailyClose[], windowSize: number): { values: number[]; labels: string[] } {
  const values: number[] = [];
  const labels: string[] = [];
  for (let i = windowSize; i < days.length; i++) {
    let sum = 0;
    for (let j = i - windowSize + 1; j <= i; j++) {
      sum += (days[j].close / days[j - 1].close) - 1;
    }
    values.push((sum / windowSize) * 100);
    labels.push(days[i].date);
  }
  return { values, labels };
}

type PeriodPrices = Record<PeriodKey, number | null>;

type EntryPerf = {
  ticker: string;
  asset_type: string;
  current_price: number | null;
  prices: PeriodPrices | null;
  days: DailyClose[] | null;
  error: boolean;
};

function PctBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-slate-600 text-xs">—</span>;
  const positive = pct > 0;
  const zero = pct === 0;
  const bg = zero ? "bg-[#1e2130]" : positive ? "bg-[#152618]" : "bg-[#2c1414]";
  const text = zero ? "text-slate-400" : positive ? "text-[#3fb950]" : "text-[#f85149]";
  return (
    <span className={`inline-block ${bg} ${text} rounded px-1.5 py-0.5 text-xs tabular-nums font-medium`}>
      {fmtPct(pct)}
    </span>
  );
}

function PerfCell({ pct }: { pct: number | null }) {
  return (
    <td className={pct === null ? "px-1.5 py-2 text-right" : "px-1.5 py-1.5 text-right"}>
      <PctBadge pct={pct} />
    </td>
  );
}

type SortCol = "ticker" | PeriodKey;

function PerformanceTable({ entryPerfs }: { entryPerfs: EntryPerf[] }) {
  const [sortCol, setSortCol] = useState<SortCol | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function handleSort(col: SortCol, defaultDir: "asc" | "desc" = "desc") {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir(defaultDir);
    }
  }

  function getSortValue(ep: EntryPerf): string | number {
    if (sortCol === "ticker") return ep.ticker;
    const pct = ep.prices ? pctChange(ep.current_price, ep.prices[sortCol!]) : null;
    return pct ?? (sortDir === "asc" ? Infinity : -Infinity);
  }

  const sorted = sortCol === null ? entryPerfs : [...entryPerfs].sort((a, b) => {
    const av = getSortValue(a);
    const bv = getSortValue(b);
    const cmp = typeof av === "string" && typeof bv === "string"
      ? av.localeCompare(bv)
      : (av as number) - (bv as number);
    return sortDir === "asc" ? cmp : -cmp;
  });

  function sortIndicator(col: SortCol) {
    if (sortCol === col) return <span className="text-slate-300 ml-0.5">{sortDir === "asc" ? "↑" : "↓"}</span>;
    return <span className="text-slate-700 ml-0.5">⇅</span>;
  }

  const thBase = "text-[0.65rem] uppercase tracking-wide font-semibold px-3 py-2 cursor-pointer select-none hover:text-slate-300 transition-colors";

  return (
    <div className="border border-[#404868] rounded-md overflow-hidden overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-[#404868]">
            <th onClick={() => handleSort("ticker", "asc")} className={`text-left text-slate-500 ${thBase}`}>
              <span className="inline-flex items-center">Asset {sortIndicator("ticker")}</span>
            </th>
            {PERIODS.map((p) => (
              <th key={p.key} onClick={() => handleSort(p.key)} className={`text-right text-slate-500 ${thBase} px-1.5`}>
                <span className="inline-flex items-center justify-end">{p.label} {sortIndicator(p.key)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(({ ticker, asset_type, current_price, prices, error }) => (
            <tr key={`${ticker}:${asset_type}`} className="border-b border-[#2a2d3a] last:border-b-0">
              <td className="px-3 py-2 font-semibold text-slate-100">
                {ticker}
                <span className="hidden sm:inline ml-1.5 text-[0.65rem] text-slate-600 uppercase">{asset_type}</span>
              </td>
              {error ? (
                <td colSpan={PERIODS.length} className="px-3 py-2 text-right text-xs text-slate-600">unavailable</td>
              ) : prices === null ? (
                <td colSpan={PERIODS.length} className="px-3 py-2 text-right text-xs text-slate-600">loading…</td>
              ) : (
                PERIODS.map((p) => (
                  <PerfCell key={p.key} pct={pctChange(current_price, prices[p.key])} />
                ))
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SparklineView({ entryPerfs }: { entryPerfs: EntryPerf[] }) {
  const [hoverFraction, setHoverFraction] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  function handleHover(id: string, fraction: number | null) {
    setHoverFraction(fraction);
    setHoveredId(fraction !== null ? id : null);
  }

  return (
    <div className="border border-[#404868] rounded-md overflow-hidden">
      {entryPerfs.map(({ ticker, asset_type, current_price, prices, days, error }) => {
        const id = `${ticker}-${asset_type}`;
        const yr = prices ? pctChange(current_price, prices["1y"]) : null;

        const hoverPct = (hoverFraction !== null && days !== null && days.length >= 2)
          ? (() => {
              const idx = Math.round(hoverFraction * (days.length - 1));
              return ((days[idx].close - days[0].close) / days[0].close) * 100;
            })()
          : null;

        const displayPct = hoverPct !== null ? hoverPct : yr;

        return (
          <div
            key={`${ticker}:${asset_type}`}
            className="flex items-center gap-3 px-3 py-2.5 border-b border-[#2a2d3a] last:border-b-0"
          >
            <div className="w-24 shrink-0">
              <span className="font-semibold text-sm text-slate-100">{ticker}</span>
              <span className="hidden sm:inline ml-1.5 text-[0.65rem] text-slate-600 uppercase">{asset_type}</span>
            </div>
            <div className="w-16 shrink-0 text-right">
              {error ? (
                <span className="text-slate-600 text-xs">unavailable</span>
              ) : prices === null ? (
                <span className="text-slate-600 text-xs">loading…</span>
              ) : (
                <PctBadge pct={displayPct} />
              )}
            </div>
            <div className="flex-1 min-w-0 pt-3">
              {!error && days !== null && (
                <Sparkline
                  id={id}
                  values={days.map((d) => d.close)}
                  labels={days.map((d) => d.date)}
                  height={40}
                  hoverFraction={hoverFraction}
                  onHoverFraction={(f) => handleHover(id, f)}
                  showTooltip={hoveredId === id}
                />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MomentumView({ entryPerfs, windowSize }: { entryPerfs: EntryPerf[]; windowSize: MomentumWindow }) {
  const [hoverFraction, setHoverFraction] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  function handleHover(id: string, fraction: number | null) {
    setHoverFraction(fraction);
    setHoveredId(fraction !== null ? id : null);
  }

  return (
    <div className="border border-[#404868] rounded-md overflow-hidden">
      {entryPerfs.map(({ ticker, asset_type, days, error }) => {
        const id = `${ticker}-${asset_type}-mom`;
        const series = days !== null ? momentumSeries(days, windowSize) : null;
        const currentMom = series && series.values.length > 0
          ? series.values[series.values.length - 1]
          : null;

        const hoverMom = (hoverFraction !== null && series !== null && series.values.length >= 2)
          ? series.values[Math.round(hoverFraction * (series.values.length - 1))]
          : null;

        const displayPct = hoverMom !== null ? hoverMom : currentMom;

        return (
          <div
            key={`${ticker}:${asset_type}`}
            className="flex items-center gap-3 px-3 py-2.5 border-b border-[#2a2d3a] last:border-b-0"
          >
            <div className="w-24 shrink-0">
              <span className="font-semibold text-sm text-slate-100">{ticker}</span>
              <span className="hidden sm:inline ml-1.5 text-[0.65rem] text-slate-600 uppercase">{asset_type}</span>
            </div>
            <div className="w-16 shrink-0 text-right">
              {error ? (
                <span className="text-slate-600 text-xs">unavailable</span>
              ) : days === null ? (
                <span className="text-slate-600 text-xs">loading…</span>
              ) : (
                <PctBadge pct={displayPct} />
              )}
            </div>
            <div className="flex-1 min-w-0 pt-3">
              {!error && series !== null && series.values.length > 1 && (
                <Sparkline
                  id={id}
                  values={series.values}
                  labels={series.labels}
                  height={40}
                  normalize={false}
                  hoverFraction={hoverFraction}
                  onHoverFraction={(f) => handleHover(id, f)}
                  showTooltip={hoveredId === id}
                />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ChartsDropdown({ viewMode, setViewMode }: {
  viewMode: ViewMode;
  setViewMode: (v: ViewMode) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const isChart = viewMode !== "table";
  const label = !isChart ? "Charts"
    : viewMode === "return" ? "Return"
    : `Momentum ${(viewMode as MomentumMode).window}D`;

  const options: { label: string; mode: ViewMode }[] = [
    { label: "Return",         mode: "return" },
    { label: "Momentum · 3D",  mode: { kind: "momentum", window: 3 } },
    { label: "Momentum · 5D",  mode: { kind: "momentum", window: 5 } },
    { label: "Momentum · 7D",  mode: { kind: "momentum", window: 7 } },
  ];

  function modeKey(m: ViewMode): string {
    if (m === "table" || m === "return") return m;
    return `momentum-${(m as MomentumMode).window}`;
  }

  function isActive(m: ViewMode): boolean {
    if (typeof m === "string") return viewMode === m;
    if (typeof viewMode === "object") return (viewMode as MomentumMode).window === (m as MomentumMode).window;
    return false;
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`px-2 py-0.5 rounded text-xs font-medium transition-colors cursor-pointer flex items-center gap-0.5 ${
          isChart ? "bg-[#404868] text-slate-100" : "text-slate-500 hover:text-slate-300"
        }`}
      >
        {label}
        <span className="opacity-50 text-[0.55rem] ml-0.5">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 bg-[#1e2130] border border-[#404868] rounded-md shadow-lg z-10 min-w-[148px] py-1">
          {options.map((opt) => (
            <button
              key={modeKey(opt.mode)}
              onClick={() => { setViewMode(opt.mode); setOpen(false); }}
              className={`block w-full text-left px-3 py-1.5 text-xs transition-colors cursor-pointer ${
                isActive(opt.mode)
                  ? "text-slate-100 bg-[#2a2d3a]"
                  : "text-slate-400 hover:text-slate-100 hover:bg-[#2a2d3a]"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function WatchlistPerformancePane({ id }: { id: string }) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<WatchlistDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [entryPerfs, setEntryPerfs] = useState<EntryPerf[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("table");

  useEffect(() => {
    let active = true;
    setDetailLoading(true);
    setDetailError(null);
    api.getWatchlist(id)
      .then((d) => { if (active) setDetail(d); })
      .catch(() => { if (active) setDetailError("Failed to load watchlist"); })
      .finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; };
  }, [id]);

  useEffect(() => {
    if (!detail) return;
    setEntryPerfs(detail.entries.map((e) => ({
      ticker: e.ticker,
      asset_type: e.asset_type,
      current_price: e.current_price,
      prices: null,
      days: null,
      error: false,
    })));

    const maxLookback = Math.max(...PERIODS.map((p) => p.days + p.window));
    const fromDate = daysAgoDate(maxLookback);

    for (const entry of detail.entries) {
      api.getDailyRange(entry.asset_type, entry.ticker, fromDate)
        .then(({ days }) => {
          const prices = Object.fromEntries(
            PERIODS.map((p) => [p.key, smoothedClose(days, daysAgoDate(p.days), p.window)])
          ) as PeriodPrices;
          setEntryPerfs((prev) =>
            prev.map((p) =>
              p.ticker === entry.ticker && p.asset_type === entry.asset_type
                ? { ...p, prices, days }
                : p
            )
          );
        })
        .catch(() => {
          setEntryPerfs((prev) =>
            prev.map((p) =>
              p.ticker === entry.ticker && p.asset_type === entry.asset_type
                ? { ...p, error: true }
                : p
            )
          );
        });
    }
  }, [detail?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (detailLoading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (detailError) return <p className="text-red-400 py-2 text-sm">{detailError}</p>;
  if (!detail) return null;

  const btnClass = (active: boolean) =>
    `px-2 py-0.5 rounded text-xs font-medium transition-colors cursor-pointer ${
      active ? "bg-[#404868] text-slate-100" : "text-slate-500 hover:text-slate-300"
    }`;

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-base font-semibold text-slate-100">{detail.name} — Performance</h2>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            <button onClick={() => setViewMode("table")} className={btnClass(viewMode === "table")}>Table</button>
            <ChartsDropdown viewMode={viewMode} setViewMode={setViewMode} />
          </div>
          <button
            onClick={() => navigate("/watchlist")}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
          >
            ← Back to watchlist
          </button>
        </div>
      </div>
      {entryPerfs.length === 0 ? (
        <p className="text-slate-500 text-sm">No entries.</p>
      ) : viewMode === "table" ? (
        <PerformanceTable entryPerfs={entryPerfs} />
      ) : viewMode === "return" ? (
        <SparklineView entryPerfs={entryPerfs} />
      ) : (
        <MomentumView entryPerfs={entryPerfs} windowSize={(viewMode as MomentumMode).window} />
      )}
    </div>
  );
}
