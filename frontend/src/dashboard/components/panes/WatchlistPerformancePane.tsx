import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type DailyClose, type WatchlistDetail } from "../../api/client";
import { fmtPrice } from "../../lib/formatters";
import { type ChartSettings, loadChartSettings, saveChartSettings, chartLabel } from "../../lib/chartSettings";
import { PERIODS, type PeriodKey, type PeriodPrices, daysAgoDate, smoothedClose, pctChange } from "../../lib/perfUtils";
import { PerfCell } from "../perf/PctBadge";
import { type PerfRow, SparklineView, MomentumView, VolumeView } from "../perf/PerfChartViews";
import { IntradayView } from "../perf/IntradayView";
import { ChartControlsButton } from "../ChartControls";

type EntryPerf = {
  ticker: string;
  asset_type: string;
  current_price: number | null;
  prices: PeriodPrices | null;
  days: DailyClose[] | null;
  error: boolean;
};

function entryToRow(ep: EntryPerf): PerfRow {
  return {
    id: `${ep.ticker}-${ep.asset_type}`,
    ticker: ep.ticker,
    asset_type: ep.asset_type,
    sublabel: fmtPrice(ep.current_price, ep.asset_type, ep.ticker),
    current_price: ep.current_price,
    prices: ep.prices,
    days: ep.days,
    error: ep.error,
  };
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

export function WatchlistPerformancePane({ id }: { id: string }) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<WatchlistDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [entryPerfs, setEntryPerfs] = useState<EntryPerf[]>([]);
  const [isChart, setIsChart] = useState(false);
  const [settings, setSettings] = useState<ChartSettings>(loadChartSettings);

  function handleSettings(s: ChartSettings) {
    setSettings(s);
    saveChartSettings(s);
    setIsChart(true);
  }

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

  const rows = entryPerfs.map(entryToRow);

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-base font-semibold text-slate-100">{detail.name} — {isChart ? chartLabel(settings) : "Performance"}</h2>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            <button onClick={() => setIsChart(false)} className={btnClass(!isChart)}>Table</button>
            <ChartControlsButton
              isChart={isChart}
              onToggle={() => setIsChart(true)}
              settings={settings}
              onSettings={handleSettings}
            />
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
      ) : !isChart ? (
        <PerformanceTable entryPerfs={entryPerfs} />
      ) : settings.chartType === "return" ? (
        <SparklineView rows={rows} chartDays={settings.chartRange} />
      ) : settings.chartType === "volume" ? (
        <VolumeView rows={rows} chartDays={settings.chartRange} />
      ) : settings.chartType === "intraday" ? (
        <IntradayView rows={rows} window={settings.intradayWindow} />
      ) : (
        <MomentumView rows={rows} windowSize={settings.momentumWindow} chartDays={settings.chartRange} />
      )}
    </div>
  );
}
