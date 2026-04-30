import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Asset, type PortfolioDetail } from "../api/client";
import { fmtMoney, fmtPct } from "../lib/formatters";

type PeriodKey = "1d" | "1w" | "1m" | "3m" | "6m" | "1y";

const PERIODS: { key: PeriodKey; label: string; days: number }[] = [
  { key: "1d", label: "1D",  days:   1 },
  { key: "1w", label: "1W",  days:   7 },
  { key: "1m", label: "1M",  days:  30 },
  { key: "3m", label: "3M",  days:  90 },
  { key: "6m", label: "6M",  days: 180 },
  { key: "1y", label: "1Y",  days: 365 },
];

function daysAgoDate(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function pctChange(current: number | null, historic: number | null): number | null {
  if (current === null || historic === null || historic === 0) return null;
  return ((current - historic) / historic) * 100;
}

type PeriodPrices = Record<PeriodKey, number | null>;

type AssetPerf = {
  asset: Asset;
  prices: PeriodPrices | null;  // null = still loading
  error: boolean;
};

function PerfCell({ pct }: { pct: number | null }) {
  if (pct === null) {
    return (
      <td className="px-1.5 py-2 text-right">
        <span className="text-slate-600 text-xs">—</span>
      </td>
    );
  }
  const positive = pct > 0;
  const zero = pct === 0;
  const bg = zero ? "bg-[#1e2130]" : positive ? "bg-[#152618]" : "bg-[#2c1414]";
  const text = zero ? "text-slate-400" : positive ? "text-[#3fb950]" : "text-[#f85149]";
  return (
    <td className="px-1.5 py-1.5 text-right">
      <span className={`inline-block ${bg} ${text} rounded px-1.5 py-0.5 text-xs tabular-nums font-medium`}>
        {fmtPct(pct)}
      </span>
    </td>
  );
}

function PerformanceTable({ assetPerfs }: { assetPerfs: AssetPerf[] }) {
  return (
    <div className="border border-[#404868] rounded-md overflow-hidden overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-[#404868]">
            <th className="text-left text-[0.65rem] uppercase tracking-wide text-slate-500 font-semibold px-3 py-2">
              Asset
            </th>
            <th className="text-right text-[0.65rem] uppercase tracking-wide text-slate-500 font-semibold px-3 py-2 hidden sm:table-cell">
              Value
            </th>
            {PERIODS.map((p) => (
              <th
                key={p.key}
                className="text-right text-[0.65rem] uppercase tracking-wide text-slate-500 font-semibold px-1.5 py-2"
              >
                {p.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {assetPerfs.map(({ asset, prices, error }) => (
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

export function PortfolioPerformance({
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

  useEffect(() => {
    if (!detail) return;
    const assets = [...detail.stocks, ...detail.currencies, ...detail.crypto];
    setAssetPerfs(assets.map((a) => ({ asset: a, prices: null, error: false })));

    for (const asset of assets) {
      Promise.allSettled(
        PERIODS.map((p) =>
          api
            .getOpenClose(asset.asset_type, asset.ticker, daysAgoDate(p.days), true)
            .then((r) => ({ key: p.key, close: r.close }))
        )
      ).then((results) => {
        const prices = Object.fromEntries(PERIODS.map((p) => [p.key, null])) as PeriodPrices;
        for (const r of results) {
          if (r.status === "fulfilled") prices[r.value.key] = r.value.close;
        }
        setAssetPerfs((prev) =>
          prev.map((p) =>
            p.asset.ticker === asset.ticker && p.asset.asset_type === asset.asset_type
              ? { ...p, prices }
              : p
          )
        );
      });
    }
  }, [detail?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 py-2 text-sm">{error}</p>;
  if (!detail) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-base font-semibold text-slate-100">{detail.name} — Performance</h2>
        <button
          onClick={() => navigate(`/portfolio/${detail.id}`)}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
        >
          ← Back to portfolio
        </button>
      </div>
      {assetPerfs.length === 0 ? (
        <p className="text-slate-500 text-sm">No assets.</p>
      ) : (
        <PerformanceTable assetPerfs={assetPerfs} />
      )}
    </div>
  );
}
