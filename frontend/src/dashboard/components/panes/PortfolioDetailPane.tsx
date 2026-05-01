import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Asset, Lot, PortfolioDetail } from "../../api/client";
import { fmtMoney, fmtPct, fmtDate, fmtChg, plColor, lotPlColor, prevCloseKey, computeTodayChange } from "../../lib/formatters";
import { DataTable, type ColDef } from "../DataTable";
import { Chart } from "../Chart";

type EnrichedAsset = Asset & {
  dayChgPrice: number | null;
  dayChgValue: number | null;
  dayChgPct: number | null;
};

function LotTable({ lots, currentPrice }: { lots: Lot[]; currentPrice: number | null }) {
  return (
    <table className="w-full text-xs border-collapse">
      <thead>
        <tr>
          {(
            [
              ["Date",       "text-left",  ""],
              ["Qty",        "text-right", "hidden sm:table-cell"],
              ["Price",      "text-right", ""],
              ["Cost Basis", "text-right", "hidden sm:table-cell"],
              ["P&L",        "text-right", "hidden md:table-cell"],
              ["Fees",       "text-right", "hidden md:table-cell"],
            ] as [string, string, string][]
          ).map(([label, align, vis]) => (
            <th
              key={label}
              className={`${align} ${vis} text-[0.65rem] uppercase tracking-wide text-slate-600 font-semibold px-2 sm:px-3 py-1.5 border-b border-[#2a2d3a]`}
            >
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {lots.map((lot, i) => {
          const lotPL =
            currentPrice !== null && lot.cost_basis !== null
              ? currentPrice * parseFloat(lot.quantity) - lot.cost_basis
              : null;
          const priceGain =
            currentPrice !== null && lot.price !== null ? currentPrice - lot.price : null;
          return (
            <tr key={i} className="border-b border-[#222536] last:border-b-0">
              <td className="pl-4 sm:pl-8 pr-2 sm:pr-3 py-1.5 text-slate-500">{fmtDate(lot.date)}</td>
              <td className="hidden sm:table-cell px-2 sm:px-3 py-1.5 text-right tabular-nums text-slate-500">{lot.quantity}</td>
              <td className={`px-2 sm:px-3 py-1.5 text-right tabular-nums ${lotPlColor(priceGain)}`}>{fmtMoney(lot.price)}</td>
              <td className="hidden sm:table-cell px-2 sm:px-3 py-1.5 text-right tabular-nums text-slate-500">{fmtMoney(lot.cost_basis)}</td>
              <td className={`hidden md:table-cell px-2 sm:px-3 py-1.5 text-right tabular-nums ${lotPlColor(lotPL)}`}>{fmtMoney(lotPL)}</td>
              <td className="hidden md:table-cell px-2 sm:px-3 py-1.5 text-right tabular-nums text-slate-500">{fmtMoney(lot.fees)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function AssetTable({ assets, prevClose, defaultPeriodLabel, onPeriodChange }: {
  assets: Asset[];
  prevClose: Record<string, number>;
  defaultPeriodLabel: string;
  onPeriodChange: (label: string) => void;
}) {
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set());
  const [chartTickers, setChartTickers] = useState<Set<string>>(new Set());
  const [priceChgMode, setPriceChgMode] = useState<"dollar" | "percent">("percent");
  const [valueChgMode, setValueChgMode] = useState<"dollar" | "percent">("dollar");

  function toggleTicker(ticker: string) {
    setExpandedTickers((prev) => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }

  function toggleChartTicker(ticker: string) {
    setChartTickers((prev) => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }

  const enriched: EnrichedAsset[] = assets.map((a) => {
    const pc = prevClose[prevCloseKey(a)] ?? null;
    const dayChgPrice = a.current_price !== null && pc !== null ? a.current_price - pc : null;
    const dayChgValue = dayChgPrice !== null ? dayChgPrice * parseFloat(a.total_quantity) : null;
    const dayChgPct = dayChgPrice !== null && pc !== null && pc !== 0 ? (dayChgPrice / pc) * 100 : null;
    return { ...a, dayChgPrice, dayChgValue, dayChgPct };
  });

  const columns: ColDef<EnrichedAsset>[] = [
    { key: "ticker",    label: "Ticker",    align: "left",  sortValue: (a) => a.ticker,                    defaultDir: "asc" },
    { key: "qty",       label: "Qty",       align: "right", sortValue: (a) => parseFloat(a.total_quantity), vis: "hidden sm:table-cell" },
    { key: "price",     label: "Price",     align: "right", sortValue: (a) => a.current_price },
    { key: "priceChg",  label: "Price Chg", align: "right", sortValue: (a) => priceChgMode === "dollar" ? a.dayChgPrice : a.dayChgPct,
      badge: priceChgMode === "dollar" ? "$" : "%", onBadge: () => setPriceChgMode((m) => (m === "dollar" ? "percent" : "dollar")) },
    { key: "value",     label: "Value",     align: "right", sortValue: (a) => a.current_value },
    { key: "valueChg",  label: "Value Chg", align: "right", sortValue: (a) => valueChgMode === "dollar" ? a.dayChgValue : a.dayChgPct, vis: "hidden md:table-cell",
      badge: valueChgMode === "dollar" ? "$" : "%", onBadge: () => setValueChgMode((m) => (m === "dollar" ? "percent" : "dollar")) },
    { key: "pl",        label: "P&L",       align: "right", sortValue: (a) => a.profit_loss,               vis: "hidden lg:table-cell" },
    { key: "plPct",     label: "P&L %",     align: "right", sortValue: (a) => a.profit_loss_percentage,    vis: "hidden lg:table-cell" },
  ];

  return (
    <DataTable
      columns={columns}
      rows={enriched}
      getKey={(a) => a.ticker}
      renderRow={(a) => {
        const isExpanded = expandedTickers.has(a.ticker);
        const hasChart = chartTickers.has(a.ticker)
        const hasLots = a.lots.length > 0;
        return (
          <>
            <tr
              className={[
                "border-b border-[#2a2d3a] transition-colors",
                !isExpanded ? "last:border-b-0" : "",
                isExpanded ? "bg-[#252a40]" : "",
              ].join(" ")}
            >
              <td className="px-2 sm:px-3 py-2 font-semibold text-slate-100">
                <button
                  onClick={() => toggleChartTicker(a.ticker)}
                  className="hover:text-sky-400 transition-colors cursor-pointer"
                >
                  {a.ticker}
                </button>
              </td>
              <td className="hidden sm:table-cell px-2 sm:px-3 py-2 text-right tabular-nums text-slate-300">
                <span className="inline-flex items-center justify-end gap-1.5">
                  {a.total_quantity}
                  {hasLots && (
                    <button
                      onClick={() => toggleTicker(a.ticker)}
                      title="View lots"
                      className="text-[#404868] hover:text-slate-400 transition-colors cursor-pointer leading-none"
                    >
                      ⓘ
                    </button>
                  )}
                </span>
              </td>
              <td className="px-2 sm:px-3 py-2 text-right tabular-nums text-slate-300">{fmtMoney(a.current_price)}</td>
              <td className={`px-2 sm:px-3 py-2 text-right tabular-nums ${plColor(a.dayChgPrice)}`}>
                {priceChgMode === "dollar" ? fmtChg(a.dayChgPrice) : fmtPct(a.dayChgPct)}
              </td>
              <td className="px-2 sm:px-3 py-2 text-right tabular-nums text-slate-300">{fmtMoney(a.current_value)}</td>
              <td className={`hidden md:table-cell px-2 sm:px-3 py-2 text-right tabular-nums ${plColor(a.dayChgValue)}`}>
                {valueChgMode === "dollar" ? fmtChg(a.dayChgValue) : fmtPct(a.dayChgPct)}
              </td>
              <td className={`hidden lg:table-cell px-2 sm:px-3 py-2 text-right tabular-nums font-medium ${plColor(a.profit_loss)}`}>
                {fmtMoney(a.profit_loss)}
              </td>
              <td className={`hidden lg:table-cell px-2 sm:px-3 py-2 text-right tabular-nums ${plColor(a.profit_loss_percentage)}`}>
                {fmtPct(a.profit_loss_percentage)}
              </td>
            </tr>
            {isExpanded && (
              <tr className="border-b border-[#2a2d3a] last:border-b-0">
                <td colSpan={columns.length} className="px-0 py-0 bg-[#181c28]">
                  <LotTable lots={a.lots} currentPrice={a.current_price} />
                </td>
              </tr>
            )}
            {hasChart && (
              <tr className="border-b border-[#2a2d3a] last:border-b-0">
                <td colSpan={columns.length} className="px-4 py-3 bg-[#0c0f18]">
                  <Chart ticker={a.ticker} assetType={a.asset_type} defaultPeriodLabel={defaultPeriodLabel} onPeriodChange={onPeriodChange} />
                </td>
              </tr>
            )}
          </>
        );
      }}
    />
  );
}

function AssetSection({ title, assets, prevClose, defaultPeriodLabel, onPeriodChange }: {
  title: string;
  assets: Asset[];
  prevClose: Record<string, number>;
  defaultPeriodLabel: string;
  onPeriodChange: (label: string) => void;
}) {
  if (assets.length === 0) return null;
  return (
    <div className="mb-5 last:mb-0">
      <h3 className="text-[0.7rem] font-semibold uppercase tracking-wide text-slate-500 mb-2 px-1">
        {title}
      </h3>
      <div className="border border-[#404868] rounded-md overflow-hidden">
        <AssetTable assets={assets} prevClose={prevClose} defaultPeriodLabel={defaultPeriodLabel} onPeriodChange={onPeriodChange} />
      </div>
    </div>
  );
}

export function PortfolioDetailPane({
  detail,
  loading,
  error,
  prevClose,
}: {
  detail: PortfolioDetail | null;
  loading: boolean;
  error: string | null;
  prevClose: Record<string, number>;
}) {
  const navigate = useNavigate();
  const [defaultPeriodLabel, setDefaultPeriodLabel] = useState("4H");

  if (loading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 py-2 text-sm">{error}</p>;
  if (!detail) return null;

  const todayChg = computeTodayChange(detail, prevClose);

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
        {(
          [
            ["Value",     fmtMoney(detail.total_value),              null,                          ""],
            ["Cost Basis",fmtMoney(detail.total_cost_basis),         null,                          ""],
            ["P&L",       fmtMoney(detail.total_profit_loss),        detail.total_profit_loss,      ""],
            ["P&L %",     fmtPct(detail.profit_loss_percentage),     detail.profit_loss_percentage, "hidden sm:block"],
          ] as [string, string, number | null, string][]
        ).reduce<React.ReactNode[]>((acc, [label, value, colorVal, vis], i) => {
          if (i === 1) {
            acc.push(
              <div key="today-chg" className="bg-[#131928] border border-[#404868] rounded-md px-2 py-2">
                <div className="text-[0.65rem] uppercase tracking-wide text-slate-500 mb-1">Today&apos;s Chg</div>
                <div className={`text-sm sm:text-base font-semibold tabular-nums ml-2 ${plColor(todayChg?.value ?? null)}`}>
                  {todayChg ? <>{fmtChg(todayChg.value)}<span className="hidden sm:inline"> ({fmtPct(todayChg.pct)})</span></> : "—"}
                </div>
              </div>
            );
          }
          acc.push(
            <div key={label} className={`${vis} bg-[#131928] border border-[#404868] rounded-md px-2 py-2`}>
              <div className="text-[0.65rem] uppercase tracking-wide text-slate-500 mb-1">{label}</div>
              <div className={`text-sm sm:text-base font-semibold tabular-nums ml-2 ${colorVal !== null ? plColor(colorVal) : "text-slate-100"}`}>
                {value}
              </div>
            </div>
          );
          return acc;
        }, [])}
      </div>
      <div className="flex justify-end mb-3">
        <button
          onClick={() => navigate(`/portfolio/${detail.id}/performance`)}
          className="text-xs text-slate-500 hover:text-sky-400 transition-colors cursor-pointer"
        >
          Performance →
        </button>
      </div>
      <AssetSection title="Stocks" assets={detail.stocks} prevClose={prevClose} defaultPeriodLabel={defaultPeriodLabel} onPeriodChange={setDefaultPeriodLabel} />
      <AssetSection title="Currencies" assets={detail.currencies} prevClose={prevClose} defaultPeriodLabel={defaultPeriodLabel} onPeriodChange={setDefaultPeriodLabel} />
      <AssetSection title="Crypto" assets={detail.crypto} prevClose={prevClose} defaultPeriodLabel={defaultPeriodLabel} onPeriodChange={setDefaultPeriodLabel} />
    </div>
  );
}
