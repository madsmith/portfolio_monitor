import React, { useState } from "react";
import type { Asset, Lot, PortfolioDetail } from "../api/client";
import { fmtMoney, fmtPct, fmtDate, fmtChg, plColor, lotPlColor, prevCloseKey, computeTodayChange } from "../lib/formatters";

function LotTable({ lots, currentPrice }: { lots: Lot[]; currentPrice: number | null }) {
  return (
    <table className="w-full text-xs border-collapse">
      <thead>
        <tr>
          {(
            [
              ["Date", "text-left"],
              ["Qty", "text-right"],
              ["Price", "text-right"],
              ["Cost Basis", "text-right"],
              ["P&L", "text-right"],
              ["Fees", "text-right"],
            ] as [string, string][]
          ).map(([label, align]) => (
            <th
              key={label}
              className={`${align} text-[0.65rem] uppercase tracking-wide text-slate-600 font-semibold px-3 py-1.5 border-b border-[#2a2d3a]`}
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
              <td className="pl-8 pr-3 py-1.5 text-slate-500">{fmtDate(lot.date)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{lot.quantity}</td>
              <td className={`px-3 py-1.5 text-right tabular-nums ${lotPlColor(priceGain)}`}>{fmtMoney(lot.price)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{fmtMoney(lot.cost_basis)}</td>
              <td className={`px-3 py-1.5 text-right tabular-nums ${lotPlColor(lotPL)}`}>{fmtMoney(lotPL)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{fmtMoney(lot.fees)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function AssetTable({ assets, prevClose }: { assets: Asset[]; prevClose: Record<string, number> }) {
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set());
  const [priceChgMode, setPriceChgMode] = useState<"dollar" | "percent">("percent");
  const [valueChgMode, setValueChgMode] = useState<"dollar" | "percent">("dollar");

  function toggleTicker(ticker: string) {
    setExpandedTickers((prev) => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }

  const headers: [string, string, (() => void) | undefined][] = [
    ["Ticker", "text-left", undefined],
    ["Qty", "text-right", undefined],
    ["Price", "text-right", undefined],
    [`Price Chg ${priceChgMode === "dollar" ? "$" : "%"}`, "text-right", () => setPriceChgMode((m) => (m === "dollar" ? "percent" : "dollar"))],
    ["Value", "text-right", undefined],
    [`Value Chg ${valueChgMode === "dollar" ? "$" : "%"}`, "text-right", () => setValueChgMode((m) => (m === "dollar" ? "percent" : "dollar"))],
    ["P&L", "text-right", undefined],
    ["P&L %", "text-right", undefined],
  ];

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr>
          {headers.map(([label, align, onToggle], i) => (
            <th
              key={i}
              onClick={onToggle}
              className={[
                align,
                "text-[0.7rem] uppercase tracking-wide text-slate-500 font-semibold px-3 py-2 border-b border-[#404868]",
                onToggle ? "cursor-pointer hover:text-slate-300 select-none" : "",
              ].join(" ")}
            >
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {assets.map((a) => {
          const isExpanded = expandedTickers.has(a.ticker);
          const hasLots = a.lots.length > 0;
          const pc = prevClose[prevCloseKey(a)] ?? null;
          const dayChgPrice = a.current_price !== null && pc !== null ? a.current_price - pc : null;
          const dayChgValue = dayChgPrice !== null ? dayChgPrice * parseFloat(a.total_quantity) : null;
          const dayChgPct = dayChgPrice !== null && pc !== null && pc !== 0 ? (dayChgPrice / pc) * 100 : null;
          return (
            <React.Fragment key={a.ticker}>
              <tr
                onClick={() => hasLots && toggleTicker(a.ticker)}
                className={[
                  "border-b border-[#2a2d3a] transition-colors",
                  !isExpanded ? "last:border-b-0" : "",
                  hasLots ? "cursor-pointer hover:bg-[#252a40]" : "",
                  isExpanded ? "bg-[#252a40]" : "",
                ].join(" ")}
              >
                <td className="px-3 py-2 font-semibold text-slate-100">
                  <span className="inline-flex items-center gap-1.5">
                    {hasLots && (
                      <span className="text-slate-500 text-[0.65rem]">
                        {isExpanded ? "▾" : "▸"}
                      </span>
                    )}
                    {a.ticker}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-300">{a.total_quantity}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-300">{fmtMoney(a.current_price)}</td>
                <td className={`px-3 py-2 text-right tabular-nums ${plColor(dayChgPrice)}`}>
                  {priceChgMode === "dollar" ? fmtChg(dayChgPrice) : fmtPct(dayChgPct)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-300">{fmtMoney(a.current_value)}</td>
                <td className={`px-3 py-2 text-right tabular-nums ${plColor(dayChgValue)}`}>
                  {valueChgMode === "dollar" ? fmtChg(dayChgValue) : fmtPct(dayChgPct)}
                </td>
                <td className={`px-3 py-2 text-right tabular-nums font-medium ${plColor(a.profit_loss)}`}>
                  {fmtMoney(a.profit_loss)}
                </td>
                <td className={`px-3 py-2 text-right tabular-nums ${plColor(a.profit_loss_percentage)}`}>
                  {fmtPct(a.profit_loss_percentage)}
                </td>
              </tr>
              {isExpanded && (
                <tr className="border-b border-[#2a2d3a] last:border-b-0">
                  <td colSpan={8} className="px-0 py-0 bg-[#181c28]">
                    <LotTable lots={a.lots} currentPrice={a.current_price} />
                  </td>
                </tr>
              )}
            </React.Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

function AssetSection({ title, assets, prevClose }: { title: string; assets: Asset[]; prevClose: Record<string, number> }) {
  if (assets.length === 0) return null;
  return (
    <div className="mb-5 last:mb-0">
      <h3 className="text-[0.7rem] font-semibold uppercase tracking-wide text-slate-500 mb-2 px-1">
        {title}
      </h3>
      <div className="border border-[#404868] rounded-md overflow-hidden">
        <AssetTable assets={assets} prevClose={prevClose} />
      </div>
    </div>
  );
}

export function PortfolioDetailContent({
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
  if (loading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 py-2 text-sm">{error}</p>;
  if (!detail) return null;

  const todayChg = computeTodayChange(detail, prevClose);

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
        {(
          [
            ["Value", fmtMoney(detail.total_value), null],
            ["Cost Basis", fmtMoney(detail.total_cost_basis), null],
            ["P&L", fmtMoney(detail.total_profit_loss), detail.total_profit_loss],
            ["P&L %", fmtPct(detail.profit_loss_percentage), detail.profit_loss_percentage],
          ] as [string, string, number | null][]
        ).reduce<React.ReactNode[]>((acc, [label, value, colorVal], i) => {
          if (i === 1) {
            acc.push(
              <div key="today-chg" className="bg-[#131928] border border-[#404868] rounded-md px-4 py-3">
                <div className="text-[0.65rem] uppercase tracking-wide text-slate-500 mb-1">Today&apos;s Chg</div>
                <div className={`text-base font-semibold tabular-nums ${plColor(todayChg?.value ?? null)}`}>
                  {todayChg ? <>{fmtChg(todayChg.value)} ({fmtPct(todayChg.pct)})</> : "—"}
                </div>
              </div>
            );
          }
          acc.push(
            <div key={label} className="bg-[#131928] border border-[#404868] rounded-md px-4 py-3">
              <div className="text-[0.65rem] uppercase tracking-wide text-slate-500 mb-1">{label}</div>
              <div className={`text-base font-semibold tabular-nums ${colorVal !== null ? plColor(colorVal) : "text-slate-100"}`}>
                {value}
              </div>
            </div>
          );
          return acc;
        }, [])}
      </div>
      <AssetSection title="Stocks" assets={detail.stocks} prevClose={prevClose} />
      <AssetSection title="Currencies" assets={detail.currencies} prevClose={prevClose} />
      <AssetSection title="Crypto" assets={detail.crypto} prevClose={prevClose} />
    </div>
  );
}
