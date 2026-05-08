export type MomentumWindow = 1 | 3 | 5 | 7;
export type IntradayWindow = "2h" | "4h" | "1d" | "3d" | "7d";

export type ChartSettings = {
  chartType: "return" | "momentum" | "volume" | "intraday";
  momentumWindow: MomentumWindow;
  chartRange: number;
  intradayWindow: IntradayWindow;
};

const DEFAULTS: ChartSettings = {
  chartType: "return",
  momentumWindow: 5,
  chartRange: 365,
  intradayWindow: "1d",
};

const KEY = "portfolio:chartSettings";

export function loadChartSettings(): ChartSettings {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {}
  return { ...DEFAULTS };
}

export function saveChartSettings(s: ChartSettings): void {
  try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch {}
}

const RANGE_LABELS: Record<number, string> = {
  7: "1 Week",
  30: "1 Month",
  90: "3 Month",
  180: "6 Month",
  365: "1 Year",
};

export function chartLabel(settings: ChartSettings): string {
  if (settings.chartType === "intraday") return `${settings.intradayWindow.toUpperCase()} Intraday`;
  const range = RANGE_LABELS[settings.chartRange] ?? `${settings.chartRange}D`;
  if (settings.chartType === "return") return `${range} Return`;
  if (settings.chartType === "volume") return `${range} Volume`;
  return `${range} Momentum (${settings.momentumWindow}D)`;
}
