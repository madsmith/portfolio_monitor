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
              className={`${align} ${vis} text-[0.65rem] uppercase tracking-wide text-slate-600 font-semibold px-3 py-1.5 border-b border-[#2a2d3a]`}
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
              <td className="hidden sm:table-cell px-3 py-1.5 text-right tabular-nums text-slate-500">{lot.quantity}</td>
              <td className={`px-3 py-1.5 text-right tabular-nums ${lotPlColor(priceGain)}`}>{fmtMoney(lot.price)}</td>
              <td className="hidden sm:table-cell px-3 py-1.5 text-right tabular-nums text-slate-500">{fmtMoney(lot.cost_basis)}</td>
              <td className={`hidden md:table-cell px-3 py-1.5 text-right tabular-nums ${lotPlColor(lotPL)}`}>{fmtMoney(lotPL)}</td>
              <td className="hidden md:table-cell px-3 py-1.5 text-right tabular-nums text-slate-500">{fmtMoney(lot.fees)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

type SortKey = "ticker" | "qty" | "price" | "priceChg" | "value" | "valueChg" | "pl" | "plPct";

function AssetTable({ assets, prevClose }: { assets: Asset[]; prevClose: Record<string, number> }) {
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set());
  const [priceChgMode, setPriceChgMode] = useState<"dollar" | "percent">("percent");
  const [valueChgMode, setValueChgMode] = useState<"dollar" | "percent">("dollar");
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function toggleTicker(ticker: string) {
    setExpandedTickers((prev) => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "ticker" ? "asc" : "desc");
    }
  }

  // Enrich assets with computed day-change values so sorting can access them
  const enriched = assets.map((a) => {
    const pc = prevClose[prevCloseKey(a)] ?? null;
    const dayChgPrice = a.current_price !== null && pc !== null ? a.current_price - pc : null;
    const dayChgValue = dayChgPrice !== null ? dayChgPrice * parseFloat(a.total_quantity) : null;
    const dayChgPct = dayChgPrice !== null && pc !== null && pc !== 0 ? (dayChgPrice / pc) * 100 : null;
    return { ...a, dayChgPrice, dayChgValue, dayChgPct };
  });

  const sorted = sortKey === null ? enriched : [...enriched].sort((a, b) => {
    const nullLast = (v: number | null) => v ?? (sortDir === "asc" ? Infinity : -Infinity);
    let cmp = 0;
    switch (sortKey) {
      case "ticker":    cmp = a.ticker.localeCompare(b.ticker); break;
      case "qty":       cmp = parseFloat(a.total_quantity) - parseFloat(b.total_quantity); break;
      case "price":     cmp = nullLast(a.current_price) - nullLast(b.current_price); break;
      case "priceChg":  cmp = nullLast(a.dayChgPrice) - nullLast(b.dayChgPrice); break;
      case "value":     cmp = nullLast(a.current_value) - nullLast(b.current_value); break;
      case "valueChg":  cmp = nullLast(a.dayChgValue) - nullLast(b.dayChgValue); break;
      case "pl":        cmp = nullLast(a.profit_loss) - nullLast(b.profit_loss); break;
      case "plPct":     cmp = nullLast(a.profit_loss_percentage) - nullLast(b.profit_loss_percentage); break;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <span className="text-slate-700 ml-0.5">⇅</span>;
    return <span className="text-slate-300 ml-0.5">{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  function ModeToggle({ mode, onToggle }: { mode: string; onToggle: () => void }) {
    return (
      <span
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        className="ml-1 px-1 rounded bg-[#2a2d3a] text-slate-400 hover:text-slate-100 hover:bg-[#404868] cursor-pointer transition-colors normal-case tracking-normal font-normal"
      >
        {mode}
      </span>
    );
  }

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr>
          {(
            [
              { label: "Ticker",    align: "text-left",  vis: "",                      sk: "ticker"   as SortKey },
              { label: "Qty",       align: "text-right", vis: "hidden sm:table-cell",  sk: "qty"      as SortKey },
              { label: "Price",     align: "text-right", vis: "",                      sk: "price"    as SortKey },
              { label: "Price Chg", align: "text-right", vis: "",                      sk: "priceChg" as SortKey, badge: priceChgMode === "dollar" ? "$" : "%", onBadge: () => setPriceChgMode((m) => (m === "dollar" ? "percent" : "dollar")) },
              { label: "Value",     align: "text-right", vis: "",                      sk: "value"    as SortKey },
              { label: "Value Chg", align: "text-right", vis: "hidden md:table-cell",  sk: "valueChg" as SortKey, badge: valueChgMode === "dollar" ? "$" : "%", onBadge: () => setValueChgMode((m) => (m === "dollar" ? "percent" : "dollar")) },
              { label: "P&L",       align: "text-right", vis: "hidden lg:table-cell",  sk: "pl"       as SortKey },
              { label: "P&L %",     align: "text-right", vis: "hidden lg:table-cell",  sk: "plPct"    as SortKey },
            ] as { label: string; align: string; vis: string; sk: SortKey; badge?: string; onBadge?: () => void }[]
          ).map(({ label, align, vis, sk, badge, onBadge }) => (
            <th
              key={sk}
              onClick={() => handleSort(sk)}
              className={[
                align, vis,
                "text-[0.7rem] uppercase tracking-wide text-slate-500 font-semibold px-3 py-2 border-b border-[#404868]",
                "cursor-pointer hover:text-slate-300 select-none",
              ].join(" ")}
            >
              <span className={`inline-flex items-center ${align === "text-right" ? "justify-end" : ""}`}>
                {label}
                {badge && <ModeToggle mode={badge} onToggle={onBadge!} />}
                <SortIcon k={sk} />
              </span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((a) => {
          const isExpanded = expandedTickers.has(a.ticker);
          const hasLots = a.lots.length > 0;
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
                      <span className="hidden sm:inline text-slate-500 text-[0.65rem]">
                        {isExpanded ? "▾" : "▸"}
                      </span>
                    )}
                    {a.ticker}
                  </span>
                </td>
                <td className="hidden sm:table-cell px-3 py-2 text-right tabular-nums text-slate-300">{a.total_quantity}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-300">{fmtMoney(a.current_price)}</td>
                <td className={`px-3 py-2 text-right tabular-nums ${plColor(a.dayChgPrice)}`}>
                  {priceChgMode === "dollar" ? fmtChg(a.dayChgPrice) : fmtPct(a.dayChgPct)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-300">{fmtMoney(a.current_value)}</td>
                <td className={`hidden md:table-cell px-3 py-2 text-right tabular-nums ${plColor(a.dayChgValue)}`}>
                  {valueChgMode === "dollar" ? fmtChg(a.dayChgValue) : fmtPct(a.dayChgPct)}
                </td>
                <td className={`hidden lg:table-cell px-3 py-2 text-right tabular-nums font-medium ${plColor(a.profit_loss)}`}>
                  {fmtMoney(a.profit_loss)}
                </td>
                <td className={`hidden lg:table-cell px-3 py-2 text-right tabular-nums ${plColor(a.profit_loss_percentage)}`}>
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
