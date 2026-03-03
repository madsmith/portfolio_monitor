import React, { useEffect, useState } from "react";
import { useMatch, useNavigate } from "react-router-dom";
import { api, clearToken, type Asset, type Lot, type PortfolioDetail, type PortfolioSummary } from "../api/client";

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function fmtMoney(v: number | null): string {
  if (v === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v);
}

function fmtPct(v: number | null): string {
  if (v === null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

function plColor(v: number | null): string {
  if (v === null || v === 0) return "text-slate-400";
  return v > 0 ? "text-[#3fb950]" : "text-[#f85149]";
}

function lotPlColor(v: number | null): string {
  if (v === null || v === 0) return "text-slate-500";
  return v > 0 ? "text-[#3a7040]" : "text-[#8c3838]";
}

// ---------------------------------------------------------------------------
// File-folder tab
// ---------------------------------------------------------------------------

function Tab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={[
        "px-4 py-2 text-sm font-medium rounded-t-md border-2 border-[#404868] whitespace-nowrap transition-colors cursor-pointer",
        active
          ? "bg-[#1e2130] border-b-[#1e2130] text-slate-100 -mb-[2px] z-10 relative"
          : "bg-[#0b0e15] text-slate-400 hover:bg-[#13171f] hover:text-slate-300",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Overview tab content — vertical portfolio list
// ---------------------------------------------------------------------------

function Overview({
  portfolios,
  loading,
  error,
  onSelect,
}: {
  portfolios: PortfolioSummary[];
  loading: boolean;
  error: string | null;
  onSelect: (id: string) => void;
}) {
  if (loading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 py-2 text-sm">{error}</p>;
  if (portfolios.length === 0) return <p className="text-slate-500 py-2 text-sm">No portfolios found.</p>;

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr>
          {(
            [
              ["Portfolio", "text-left"],
              ["Value", "text-right"],
              ["Cost Basis", "text-right"],
              ["P&L", "text-right"],
              ["P&L %", "text-right"],
              ["", ""],
            ] as [string, string][]
          ).map(([label, align], i) => (
            <th
              key={i}
              className={`${align} text-[0.7rem] uppercase tracking-wide text-slate-500 font-semibold px-3 py-2 border-b border-[#404868]`}
            >
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {portfolios.map((p) => (
          <tr
            key={p.id}
            onClick={() => onSelect(p.id)}
            className="border-b border-[#2a2d3a] hover:bg-[#252a40] cursor-pointer transition-colors last:border-b-0"
          >
            <td className="px-3 py-3 font-semibold text-slate-100">{p.name}</td>
            <td className="px-3 py-3 text-right tabular-nums text-slate-300">{fmtMoney(p.total_value)}</td>
            <td className="px-3 py-3 text-right tabular-nums text-slate-300">{fmtMoney(p.total_cost_basis)}</td>
            <td className={`px-3 py-3 text-right tabular-nums font-medium ${plColor(p.total_profit_loss)}`}>
              {fmtMoney(p.total_profit_loss)}
            </td>
            <td className={`px-3 py-3 text-right tabular-nums ${plColor(p.profit_loss_percentage)}`}>
              {fmtPct(p.profit_loss_percentage)}
            </td>
            <td className="px-3 py-3 text-right text-slate-600 text-base">→</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Portfolio detail tab content
// ---------------------------------------------------------------------------

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

function AssetTable({ assets }: { assets: Asset[] }) {
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set());

  function toggleTicker(ticker: string) {
    setExpandedTickers((prev) => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr>
          {(
            [
              ["Ticker", "text-left"],
              ["Qty", "text-right"],
              ["Price", "text-right"],
              ["Value", "text-right"],
              ["P&L", "text-right"],
              ["P&L %", "text-right"],
            ] as [string, string][]
          ).map(([label, align]) => (
            <th
              key={label}
              className={`${align} text-[0.7rem] uppercase tracking-wide text-slate-500 font-semibold px-3 py-2 border-b border-[#404868]`}
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
                <td className="px-3 py-2 text-right tabular-nums text-slate-300">{fmtMoney(a.current_value)}</td>
                <td className={`px-3 py-2 text-right tabular-nums font-medium ${plColor(a.profit_loss)}`}>
                  {fmtMoney(a.profit_loss)}
                </td>
                <td className={`px-3 py-2 text-right tabular-nums ${plColor(a.profit_loss_percentage)}`}>
                  {fmtPct(a.profit_loss_percentage)}
                </td>
              </tr>
              {isExpanded && (
                <tr className="border-b border-[#2a2d3a] last:border-b-0">
                  <td colSpan={6} className="px-0 py-0 bg-[#181c28]">
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

function AssetSection({ title, assets }: { title: string; assets: Asset[] }) {
  if (assets.length === 0) return null;
  return (
    <div className="mb-5 last:mb-0">
      <h3 className="text-[0.7rem] font-semibold uppercase tracking-wide text-slate-500 mb-2 px-1">
        {title}
      </h3>
      <div className="border border-[#404868] rounded-md overflow-hidden">
        <AssetTable assets={assets} />
      </div>
    </div>
  );
}

function PortfolioDetailContent({
  detail,
  loading,
  error,
}: {
  detail: PortfolioDetail | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 py-2 text-sm">{error}</p>;
  if (!detail) return null;

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {(
          [
            ["Value", fmtMoney(detail.total_value), null],
            ["Cost Basis", fmtMoney(detail.total_cost_basis), null],
            ["P&L", fmtMoney(detail.total_profit_loss), detail.total_profit_loss],
            ["P&L %", fmtPct(detail.profit_loss_percentage), detail.profit_loss_percentage],
          ] as [string, string, number | null][]
        ).map(([label, value, colorVal]) => (
          <div key={label} className="bg-[#131928] border border-[#404868] rounded-md px-4 py-3">
            <div className="text-[0.65rem] uppercase tracking-wide text-slate-500 mb-1">{label}</div>
            <div
              className={`text-base font-semibold tabular-nums ${
                colorVal !== null ? plColor(colorVal) : "text-slate-100"
              }`}
            >
              {value}
            </div>
          </div>
        ))}
      </div>
      <AssetSection title="Stocks" assets={detail.stocks} />
      <AssetSection title="Currencies" assets={detail.currencies} />
      <AssetSection title="Crypto" assets={detail.crypto} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main consolidated component
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const navigate = useNavigate();
  const match = useMatch("/portfolio/:id");
  const activeId = match?.params.id ?? null;

  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [portfoliosLoading, setPortfoliosLoading] = useState(true);
  const [portfoliosError, setPortfoliosError] = useState<string | null>(null);

  const [detail, setDetail] = useState<PortfolioDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Fetch portfolio list once — preserved across tab switches since component stays mounted
  useEffect(() => {
    api
      .getPortfolios()
      .then(setPortfolios)
      .catch((e: Error) => {
        if (e.message === "401") { clearToken(); navigate("/login"); return; }
        setPortfoliosError("Failed to load portfolios");
      })
      .finally(() => setPortfoliosLoading(false));
  }, [navigate]);

  // Re-fetch detail whenever the active portfolio changes
  useEffect(() => {
    if (!activeId) { setDetail(null); return; }
    setDetailLoading(true);
    setDetailError(null);
    api
      .getPortfolio(activeId)
      .then(setDetail)
      .catch((e: Error) => {
        if (e.message === "401") { clearToken(); navigate("/login"); return; }
        setDetailError(e.message === "404" ? "Portfolio not found" : "Failed to load portfolio");
      })
      .finally(() => setDetailLoading(false));
  }, [activeId, navigate]);

  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-300 pt-8 px-4">
      <div className="max-w-4xl mx-auto">

        {/* Compact app header — scoped to the content container */}
        <div className="flex items-baseline justify-between mb-4 px-1">
          <span className="text-xl font-semibold text-slate-100 tracking-wide">Portfolio Monitor</span>
          <button
            onClick={() => { clearToken(); navigate("/login"); }}
            className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
          >
            Sign out
          </button>
        </div>

        {/* Tab strip */}
        <div className="flex items-end gap-1">
          <Tab label="Overview" active={activeId === null} onClick={() => navigate("/")} />
          {portfolios.map((p) => (
            <Tab
              key={p.id}
              label={p.name}
              active={p.id === activeId}
              onClick={() => navigate(`/portfolio/${p.id}`)}
            />
          ))}
          {/* Trailing shelf line */}
          <div className="flex-1 border-b-2 border-[#404868]" />
        </div>

        {/* Content panel — square top corners, rounded bottom */}
        <div className="bg-[#1e2130] border-2 border-[#404868] rounded-b-lg p-6">
          {activeId === null ? (
            <Overview
              portfolios={portfolios}
              loading={portfoliosLoading}
              error={portfoliosError}
              onSelect={(id) => navigate(`/portfolio/${id}`)}
            />
          ) : (
            <PortfolioDetailContent
              detail={detail}
              loading={detailLoading}
              error={detailError}
            />
          )}
        </div>

      </div>
    </div>
  );
}
