/**
 * Display configuration for crypto assets, mirroring the Python CURRENCY_CONFIGS.
 *
 * `precision` is the native smallest-unit precision (e.g. 8 for satoshis).
 * `displayDecimals` is the practical number of decimal places to show when
 * rendering a USD price for that coin in the UI.
 */
export type CryptoConfig = {
  symbol: string;
  name: string;
  precision: number;
  displayDecimals: number;
};

export const CRYPTO_CONFIGS: Record<string, CryptoConfig> = {
  BTC:  { symbol: "₿",    name: "Bitcoin",   precision: 8,  displayDecimals: 2 },
  ETH:  { symbol: "Ξ",    name: "Ethereum",  precision: 18, displayDecimals: 2 },
  USDT: { symbol: "USDT", name: "Tether",    precision: 6,  displayDecimals: 4 },
  USDC: { symbol: "USDC", name: "USD Coin",  precision: 6,  displayDecimals: 4 },
  XRP:  { symbol: "XRP",  name: "Ripple",    precision: 6,  displayDecimals: 4 },
  ADA:  { symbol: "ADA",  name: "Cardano",   precision: 6,  displayDecimals: 4 },
  SOL:  { symbol: "SOL",  name: "Solana",    precision: 9,  displayDecimals: 2 },
  DOGE: { symbol: "DOGE", name: "Dogecoin",  precision: 8,  displayDecimals: 4 },
  LTC:  { symbol: "LTC",  name: "Litecoin",  precision: 8,  displayDecimals: 2 },
  ATOM: { symbol: "ATOM", name: "Cosmos",    precision: 6,  displayDecimals: 6 },
};

/**
 * Returns the number of decimal places to use when displaying the USD price
 * of a crypto asset. Falls back to a magnitude-based heuristic for tickers
 * not in CRYPTO_CONFIGS (so newly-added coins display sensibly without a
 * config update).
 */
export function cryptoPriceDecimals(ticker: string, price?: number | null): number {
  const config = CRYPTO_CONFIGS[ticker.toUpperCase()];
  if (config) return config.displayDecimals;
  // Magnitude fallback for unknown tickers
  if (price != null) {
    if (price >= 100) return 2;
    if (price >= 1)   return 4;
    return 6;
  }
  return 4;
}
