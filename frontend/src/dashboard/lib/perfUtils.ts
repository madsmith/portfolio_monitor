import type { DailyClose } from "../api/client";

export type PeriodKey = "1d" | "1w" | "1m" | "3m" | "6m" | "1y";

export const PERIODS: { key: PeriodKey; label: string; days: number; window: number }[] = [
  { key: "1d", label: "1D",  days:   1, window:  1 },
  { key: "1w", label: "1W",  days:   7, window:  3 },
  { key: "1m", label: "1M",  days:  30, window:  7 },
  { key: "3m", label: "3M",  days:  90, window:  7 },
  { key: "6m", label: "6M",  days: 180, window: 14 },
  { key: "1y", label: "1Y",  days: 365, window: 30 },
];

export type PeriodPrices = Record<PeriodKey, number | null>;

export function daysAgoDate(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

export function smoothedClose(days: DailyClose[], anchorDate: string, windowDays: number): number | null {
  const anchor = new Date(anchorDate);
  const windowStart = new Date(anchor);
  windowStart.setUTCDate(windowStart.getUTCDate() - (windowDays - 1));
  const windowStartStr = windowStart.toISOString().slice(0, 10);

  const windowCloses: number[] = [];
  let fallback: number | null = null;
  for (const day of days) {
    if (day.date > anchorDate) break;
    if (day.date <= anchorDate) fallback = day.close;
    if (day.date >= windowStartStr) windowCloses.push(day.close);
  }

  if (windowCloses.length === 0) return fallback;
  return windowCloses.reduce((sum, c) => sum + c, 0) / windowCloses.length;
}

export function pctChange(current: number | null, historic: number | null): number | null {
  if (current === null || historic === null || historic === 0) return null;
  return ((current - historic) / historic) * 100;
}

export function sliceDays(days: DailyClose[], limitDays: number): DailyClose[] {
  const cutoff = daysAgoDate(limitDays);
  return days.filter((d) => d.date >= cutoff);
}

export function momentumSeries(days: DailyClose[], windowSize: number): { values: number[]; labels: string[] } {
  const values: number[] = [];
  const labels: string[] = [];
  for (let i = windowSize; i < days.length; i++) {
    let sum = 0;
    for (let j = i - windowSize + 1; j <= i; j++) {
      sum += (days[j].close / days[j - 1].close) - 1;
    }
    values.push((sum / windowSize) * 100);
    labels.push(days[i].date);
  }
  return { values, labels };
}
