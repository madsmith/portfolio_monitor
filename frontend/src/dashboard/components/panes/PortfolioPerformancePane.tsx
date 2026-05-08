import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Asset, type PortfolioDetail } from "../../api/client";
import { fmtMoney } from "../../lib/formatters";
import { type ChartSettings, loadChartSettings, saveChartSettings, chartLabel } from "../../lib/chartSettings";
import { PERIODS, type PeriodKey, type PeriodPrices, daysAgoDate, smoothedClose, pctChange } from "../../lib/perfUtils";
import { PerfCell } from "../perf/PctBadge";
import { type PerfRow, SparklineView, MomentumView, VolumeView } from "../perf/PerfChartViews";
import { IntradayView } from "../perf/IntradayView";
import { ChartControlsButton } from "../ChartControls";

type AssetPerf = {
  asset: Asset;
  prices: PeriodPrices | null;
  days: import("../../api/client").DailyClose[] | null;
  error: boolean;
};

function assetToRow(ap: AssetPerf): PerfRow {
  return {
    id: `${ap.asset.ticker}-${ap.asset.asset_type}`,
    ticker: ap.asset.ticker,
    asset_type: ap.asset.asset_type,
    sublabel: fmtMoney(ap.asset.current_value),
    current_price: ap.asset.current_price,
    prices: ap.prices,
    days: ap.days,
    error: ap.error,
  };
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
            <th onClick={() => handleSort("ticker", "asc")} className={`text-left text-slate-500 ${thBase}`}>
              <span className="inline-flex items-center">Asset {sortIndicator("ticker")}</span>
            </th>
            <th onClick={() => handleSort("value")} className={`text-right text-slate-500 ${thBase} hidden sm:table-cell`}>
              <span className="inline-flex items-center justify-end">Value {sortIndicator("value")}</span>
            </th>
            {PERIODS.map((p) => (
              <th key={p.key} onClick={() => handleSort(p.key)} className={`text-right text-slate-500 ${thBase} px-1.5`}>
                <span className="inline-flex items-center justify-end">{p.label} {sortIndicator(p.key)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(({ asset, prices, error }) => (
            <tr key={`${asset.ticker}:${asset.asset_type}`} className="border-b border-[#2a2d3a] last:border-b-0">
              <td className="px-3 py-2 font-semibold text-slate-100">
                {asset.ticker}
                <span className="hidden sm:inline ml-1.5 text-[0.65rem] text-slate-600 uppercase">{asset.asset_type}</span>
              </td>
              <td className="hidden sm:table-cell px-3 py-2 text-right tabular-nums text-slate-300">
                {fmtMoney(asset.current_value)}
              </td>
              {error ? (
                <td colSpan={PERIODS.length} className="px-3 py-2 text-right text-xs text-slate-600">unavailable</td>
              ) : prices === null ? (
                <td colSpan={PERIODS.length} className="px-3 py-2 text-right text-xs text-slate-600">loading…</td>
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
  const [isChart, setIsChart] = useState(false);
  const [settings, setSettings] = useState<ChartSettings>(loadChartSettings);

  function handleSettings(s: ChartSettings) {
    setSettings(s);
    saveChartSettings(s);
    setIsChart(true);
  }

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

  const rows = assetPerfs.map(assetToRow);

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-base font-semibold text-slate-100">{detail.name} — {isChart ? chartLabel(settings) : "Performance"}</h2>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            <button onClick={() => setIsChart(false)} className={btnClass(!isChart)}>
              Table
            </button>
            <ChartControlsButton
              isChart={isChart}
              onToggle={() => setIsChart(true)}
              settings={settings}
              onSettings={handleSettings}
            />
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
      ) : !isChart ? (
        <PerformanceTable assetPerfs={assetPerfs} />
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
