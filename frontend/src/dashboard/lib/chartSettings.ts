export type MomentumWindow = 1 | 3 | 5 | 7;

export type ChartSettings = {
  chartType: "return" | "momentum" | "volume";
  momentumWindow: MomentumWindow;
  chartRange: number;
};

const DEFAULTS: ChartSettings = {
  chartType: "return",
  momentumWindow: 5,
  chartRange: 365,
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
  30: "1 Month",
  90: "3 Month",
  180: "6 Month",
  365: "1 Year",
};

export function chartLabel(settings: ChartSettings): string {
  const range = RANGE_LABELS[settings.chartRange] ?? `${settings.chartRange}D`;
  if (settings.chartType === "return") return `${range} Return`;
  if (settings.chartType === "volume") return `${range} Volume`;
  return `${range} Momentum (${settings.momentumWindow}D)`;
}
