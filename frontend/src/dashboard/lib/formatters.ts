import type { Asset, PortfolioDetail } from "../api/client";
import { cryptoPriceDecimals } from "./assetFormat";

// ---------------------------------------------------------------------------
// Display formatters
// ---------------------------------------------------------------------------

/** Strip trailing decimal zeros from a quantity string, e.g. "4.000000" → "4", "0.6229" → "0.6229". */
export function fmtQty(qty: string | null): string {
  if (qty === null) return "—";
  const n = parseFloat(qty);
  return isNaN(n) ? qty : n.toString();
}

export function fmtMoney(v: number | null): string {
  if (v === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v);
}

/** Format a per-unit price with precision appropriate for the asset type and ticker. */
export function fmtPrice(v: number | null, assetType: string, ticker: string): string {
  if (v === null) return "—";
  const decimals = assetType === "crypto" ? cryptoPriceDecimals(ticker, v) : 2;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(v);
}

export function fmtPct(v: number | null): string {
  if (v === null) return "—";
  const formatted = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Math.abs(v));
  return `${v >= 0 ? "+" : "-"}${formatted}%`;
}

export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

export function fmtVol(v: number | null): string {
  if (v === null) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return `${Math.round(v)}`;
}

export function fmtChg(v: number | null): string {
  if (v === null) return "—";
  const s = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v);
  return v > 0 ? `+${s}` : s;
}

export function plColor(v: number | null): string {
  if (v === null || v === 0) return "text-slate-400";
  return v > 0 ? "text-[#3fb950]" : "text-[#f85149]";
}

export function lotPlColor(v: number | null): string {
  if (v === null || v === 0) return "text-slate-500";
  return v > 0 ? "text-[#3a7040]" : "text-[#8c3838]";
}

export function prevCloseKey(a: { ticker: string; asset_type: string }): string {
  return `${a.ticker}:${a.asset_type}`;
}

// ---------------------------------------------------------------------------
// Domain helpers
// ---------------------------------------------------------------------------

export type TodayChange = { value: number; pct: number };

export function computeTodayChange(
  detail: PortfolioDetail,
  prevClose: Record<string, number>,
): TodayChange | null {
  const allAssets = [...detail.stocks, ...detail.currencies, ...detail.crypto];
  let totalChgValue = 0;
  let prevTotalValue = 0;
  let hasAny = false;
  for (const a of allAssets) {
    const pc = prevClose[prevCloseKey(a)] ?? null;
    if (pc !== null && a.current_price !== null) {
      const qty = parseFloat(a.total_quantity);
      totalChgValue += (a.current_price - pc) * qty;
      prevTotalValue += pc * qty;
      hasAny = true;
    }
  }
  return hasAny && prevTotalValue !== 0
    ? { value: totalChgValue, pct: (totalChgValue / prevTotalValue) * 100 }
    : null;
}

export function applyPriceUpdate(detail: PortfolioDetail, ticker: string, price: number): PortfolioDetail {
  function updateAsset(asset: Asset): Asset {
    if (asset.ticker !== ticker) return asset;
    const qty = parseFloat(asset.total_quantity);
    const currentValue = price * qty;
    const profitLoss = asset.cost_basis !== null ? currentValue - asset.cost_basis : null;
    const profitLossPct =
      asset.cost_basis !== null && asset.cost_basis !== 0
        ? (profitLoss! / asset.cost_basis) * 100
        : null;
    return { ...asset, current_price: price, current_value: currentValue, profit_loss: profitLoss, profit_loss_percentage: profitLossPct };
  }

  const stocks = detail.stocks.map(updateAsset);
  const currencies = detail.currencies.map(updateAsset);
  const crypto = detail.crypto.map(updateAsset);
  const allAssets = [...stocks, ...currencies, ...crypto];
  const totalValue = allAssets.reduce((sum, a) => sum + (a.current_value ?? 0), 0);
  const totalPL = detail.total_cost_basis !== null ? totalValue - detail.total_cost_basis : null;
  const plPct =
    detail.total_cost_basis !== null && detail.total_cost_basis !== 0
      ? (totalPL! / detail.total_cost_basis) * 100
      : null;
  return { ...detail, stocks, currencies, crypto, total_value: totalValue, total_profit_loss: totalPL, profit_loss_percentage: plPct };
}
