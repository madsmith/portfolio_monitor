import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Asset, type DailyClose, type PortfolioDetail } from "../../api/client";
import { fmtMoney, fmtPct } from "../../lib/formatters";
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

function daysAgoDate(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

/**
 * Mean close over the `windowDays` trailing calendar days ending at (and including) anchorDate.
 * Falls back to the single closest close if no days fall within the window.
 */
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

type PeriodPrices = Record<PeriodKey, number | null>;

type AssetPerf = {
  asset: Asset;
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


function SparklineView({ assetPerfs }: { assetPerfs: AssetPerf[] }) {
  return (
    <div className="border border-[#404868] rounded-md overflow-hidden">
      {assetPerfs.map(({ asset, days, prices, error }) => {
        const yr = prices ? pctChange(asset.current_price, prices["1y"]) : null;
        return (
          <div
            key={`${asset.ticker}:${asset.asset_type}`}
            className="flex items-center gap-3 px-3 py-2.5 border-b border-[#2a2d3a] last:border-b-0"
          >
            <div className="w-24 shrink-0">
              <span className="font-semibold text-sm text-slate-100">{asset.ticker}</span>
              <span className="hidden sm:inline ml-1.5 text-[0.65rem] text-slate-600 uppercase">
                {asset.asset_type}
              </span>
            </div>
            <div className="hidden sm:block w-20 shrink-0 text-right tabular-nums text-slate-300 text-sm">
              {fmtMoney(asset.current_value)}
            </div>
            <div className="w-16 shrink-0 text-right">
              {error ? (
                <span className="text-slate-600 text-xs">unavailable</span>
              ) : prices === null ? (
                <span className="text-slate-600 text-xs">loading…</span>
              ) : (
                <PctBadge pct={yr} />
              )}
            </div>
            <div className="flex-1 min-w-0">
              {!error && days !== null && (
                <Sparkline id={`${asset.ticker}-${asset.asset_type}`} values={days.map((d) => d.close)} height={40} />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

type SortCol = "ticker" | "value" | PeriodKey;

function PerformanceTable({ assetPerfs }: { assetPerfs: AssetPerf[] }) {
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

  function getSortValue(ap: AssetPerf): string | number {
    if (sortCol === "ticker") return ap.asset.ticker;
    if (sortCol === "value") return ap.asset.current_value ?? 0;
    const pct = ap.prices ? pctChange(ap.asset.current_price, ap.prices[sortCol!]) : null;
    return pct ?? (sortDir === "asc" ? Infinity : -Infinity);
  }

  const sorted = sortCol === null ? assetPerfs : [...assetPerfs].sort((a, b) => {
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
            <th
              onClick={() => handleSort("ticker", "asc")}
              className={`text-left text-slate-500 ${thBase}`}
            >
              <span className="inline-flex items-center">Asset {sortIndicator("ticker")}</span>
            </th>
            <th
              onClick={() => handleSort("value")}
              className={`text-right text-slate-500 ${thBase} hidden sm:table-cell`}
            >
              <span className="inline-flex items-center justify-end">Value {sortIndicator("value")}</span>
            </th>
            {PERIODS.map((p) => (
              <th
                key={p.key}
                onClick={() => handleSort(p.key)}
                className={`text-right text-slate-500 ${thBase} px-1.5`}
              >
                <span className="inline-flex items-center justify-end">{p.label} {sortIndicator(p.key)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(({ asset, prices, error }) => (
            <tr
              key={`${asset.ticker}:${asset.asset_type}`}
              className="border-b border-[#2a2d3a] last:border-b-0"
            >
              <td className="px-3 py-2 font-semibold text-slate-100">
                {asset.ticker}
                <span className="hidden sm:inline ml-1.5 text-[0.65rem] text-slate-600 uppercase">
                  {asset.asset_type}
                </span>
              </td>
              <td className="hidden sm:table-cell px-3 py-2 text-right tabular-nums text-slate-300">
                {fmtMoney(asset.current_value)}
              </td>
              {error ? (
                <td colSpan={PERIODS.length} className="px-3 py-2 text-right text-xs text-slate-600">
                  unavailable
                </td>
              ) : prices === null ? (
                <td colSpan={PERIODS.length} className="px-3 py-2 text-right text-xs text-slate-600">
                  loading…
                </td>
              ) : (
                PERIODS.map((p) => (
                  <PerfCell key={p.key} pct={pctChange(asset.current_price, prices[p.key])} />
                ))
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PortfolioPerformancePane({
  detail,
  loading,
  error,
}: {
  detail: PortfolioDetail | null;
  loading: boolean;
  error: string | null;
}) {
  const navigate = useNavigate();
  const [assetPerfs, setAssetPerfs] = useState<AssetPerf[]>([]);
  const [viewMode, setViewMode] = useState<"table" | "charts">("table");

  useEffect(() => {
    if (!detail) return;
    const assets = [...detail.stocks, ...detail.currencies, ...detail.crypto];
    setAssetPerfs(assets.map((a) => ({ asset: a, prices: null, days: null, error: false })));

    const maxLookback = Math.max(...PERIODS.map((p) => p.days + p.window));
    const fromDate = daysAgoDate(maxLookback);

    for (const asset of assets) {
      api
        .getDailyRange(asset.asset_type, asset.ticker, fromDate)
        .then(({ days }) => {
          const prices = Object.fromEntries(
            PERIODS.map((p) => [p.key, smoothedClose(days, daysAgoDate(p.days), p.window)])
          ) as PeriodPrices;
          setAssetPerfs((prev) =>
            prev.map((p) =>
              p.asset.ticker === asset.ticker && p.asset.asset_type === asset.asset_type
                ? { ...p, prices, days }
                : p
            )
          );
        })
        .catch(() => {
          setAssetPerfs((prev) =>
            prev.map((p) =>
              p.asset.ticker === asset.ticker && p.asset.asset_type === asset.asset_type
                ? { ...p, error: true }
                : p
            )
          );
        });
    }
  }, [detail?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 py-2 text-sm">{error}</p>;
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
            <button onClick={() => setViewMode("table")} className={btnClass(viewMode === "table")}>
              Table
            </button>
            <button onClick={() => setViewMode("charts")} className={btnClass(viewMode === "charts")}>
              Charts
            </button>
          </div>
          <button
            onClick={() => navigate(`/portfolio/${detail.id}`)}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
          >
            ← Back to portfolio
          </button>
        </div>
      </div>
      {assetPerfs.length === 0 ? (
        <p className="text-slate-500 text-sm">No assets.</p>
      ) : viewMode === "table" ? (
        <PerformanceTable assetPerfs={assetPerfs} />
      ) : (
        <SparklineView assetPerfs={assetPerfs} />
      )}
    </div>
  );
}
