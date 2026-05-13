import { useState } from "react";
import type { DailyClose } from "../../api/client";
import { fmtVol } from "../../lib/formatters";
import type { MomentumWindow } from "../../lib/chartSettings";
import type { PeriodPrices } from "../../lib/perfUtils";
import { sliceDays, momentumSeries, pctChange } from "../../lib/perfUtils";
import { Sparkline } from "../Sparkline";
import { VolumeBars } from "../VolumeBars";
import { PctBadge } from "./PctBadge";

export type PerfRow = {
  id: string;
  ticker: string;
  asset_type: string;
  sublabel: string;
  current_price: number | null;
  prices: PeriodPrices | null;
  days: DailyClose[] | null;
  error: boolean;
};

function RowShell({ row, right }: { row: PerfRow; right: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 border-b border-[#2a2d3a] last:border-b-0">
      <div className="w-28 shrink-0">
        <div>
          <span className="font-semibold text-sm text-slate-100">{row.ticker}</span>
          <span className="hidden sm:inline ml-1.5 text-[0.65rem] text-slate-600 uppercase">{row.asset_type}</span>
        </div>
        <div className="text-xs text-slate-500 tabular-nums">{row.sublabel}</div>
      </div>
      {right}
    </div>
  );
}

export function SparklineView({ rows, chartDays }: { rows: PerfRow[]; chartDays: number }) {
  const [hoverFraction, setHoverFraction] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  function handleHover(id: string, fraction: number | null) {
    setHoverFraction(fraction);
    setHoveredId(fraction !== null ? id : null);
  }

  return (
    <div className="border border-[#404868] rounded-md overflow-visible">
      {rows.map((row) => {
        const visible = row.days !== null ? sliceDays(row.days, chartDays) : null;
        const rangeReturn = visible && visible.length > 0
          ? pctChange(row.current_price, visible[0].close)
          : null;
        const hoverPct = (hoverFraction !== null && visible !== null && visible.length >= 2)
          ? (() => {
              const idx = Math.round(hoverFraction * (visible.length - 1));
              return ((visible[idx].close - visible[0].close) / visible[0].close) * 100;
            })()
          : null;
        const displayPct = hoverPct !== null ? hoverPct : rangeReturn;

        return (
          <RowShell key={row.id} row={row} right={
            <>
              <div className="flex-1 min-w-0 pt-3">
                {!row.error && visible !== null && (
                  <Sparkline
                    id={row.id}
                    values={visible.map((d) => d.close)}
                    labels={visible.map((d) => d.date)}
                    height={40}
                    hoverFraction={hoverFraction}
                    onHoverFraction={(f) => handleHover(row.id, f)}
                    showTooltip={hoveredId === row.id}
                    tooltipStyle="html"
                  />
                )}
              </div>
              <div className="w-16 shrink-0 text-right">
                {row.error ? (
                  <span className="text-slate-600 text-xs">unavailable</span>
                ) : row.days === null ? (
                  <span className="text-slate-600 text-xs">loading…</span>
                ) : (
                  <PctBadge pct={displayPct} />
                )}
              </div>
            </>
          } />
        );
      })}
    </div>
  );
}

export function MomentumView({ rows, windowSize, chartDays }: {
  rows: PerfRow[];
  windowSize: MomentumWindow;
  chartDays: number;
}) {
  const [hoverFraction, setHoverFraction] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  function handleHover(id: string, fraction: number | null) {
    setHoverFraction(fraction);
    setHoveredId(fraction !== null ? id : null);
  }

  return (
    <div className="border border-[#404868] rounded-md overflow-visible">
      {rows.map((row) => {
        const series = row.days !== null
          ? momentumSeries(sliceDays(row.days, chartDays), windowSize)
          : null;
        const currentMom = series && series.values.length > 0
          ? series.values[series.values.length - 1]
          : null;
        const hoverMom = (hoverFraction !== null && series !== null && series.values.length >= 2)
          ? series.values[Math.round(hoverFraction * (series.values.length - 1))]
          : null;
        const displayPct = hoverMom !== null ? hoverMom : currentMom;

        return (
          <RowShell key={row.id} row={row} right={
            <>
              <div className="flex-1 min-w-0 pt-3">
                {!row.error && series !== null && series.values.length > 1 && (
                  <Sparkline
                    id={`${row.id}-mom`}
                    values={series.values}
                    labels={series.labels}
                    height={40}
                    normalize={false}
                    hoverFraction={hoverFraction}
                    onHoverFraction={(f) => handleHover(row.id, f)}
                    showTooltip={hoveredId === row.id}
                    tooltipStyle="html"
                  />
                )}
              </div>
              <div className="w-16 shrink-0 text-right">
                {row.error ? (
                  <span className="text-slate-600 text-xs">unavailable</span>
                ) : row.days === null ? (
                  <span className="text-slate-600 text-xs">loading…</span>
                ) : (
                  <PctBadge pct={displayPct} />
                )}
              </div>
            </>
          } />
        );
      })}
    </div>
  );
}

export function VolumeView({ rows, chartDays }: { rows: PerfRow[]; chartDays: number }) {
  const [hoverFraction, setHoverFraction] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  function handleHover(id: string, fraction: number | null) {
    setHoverFraction(fraction);
    setHoveredId(fraction !== null ? id : null);
  }

  return (
    <div className="border border-[#404868] rounded-md overflow-visible">
      {rows.map((row) => {
        const visible = row.days !== null ? sliceDays(row.days, chartDays) : null;
        const nearestIdx = (hoverFraction !== null && visible !== null && visible.length >= 2)
          ? Math.round(hoverFraction * (visible.length - 1))
          : null;
        const displayDay = nearestIdx !== null
          ? visible![nearestIdx]
          : visible && visible.length > 0 ? visible[visible.length - 1] : null;
        const up = displayDay ? displayDay.close >= displayDay.open : null;
        const volTxt = up === null ? "text-slate-400"  : up ? "text-[#3fb950]" : "text-[#f85149]";

        return (
          <RowShell key={row.id} row={row} right={
            <>
              <div className="flex-1 min-w-0 pt-3">
                {!row.error && visible !== null && visible.length >= 2 && (
                  <VolumeBars
                    id={`${row.id}-vol`}
                    days={visible}
                    height={40}
                    hoverFraction={hoverFraction}
                    onHoverFraction={(f) => handleHover(row.id, f)}
                    showTooltip={hoveredId === row.id}
                    tooltipStyle="html"
                  />
                )}
              </div>
              <div className="w-16 shrink-0 text-right">
                {row.error ? (
                  <span className="text-slate-600 text-xs">unavailable</span>
                ) : row.days === null ? (
                  <span className="text-slate-600 text-xs">loading…</span>
                ) : (
                  <span className={`inline-block ${volTxt} rounded px-1.5 py-0.5 text-xs tabular-nums font-medium`}>
                    {fmtVol(displayDay?.volume ?? null)}
                  </span>
                )}
              </div>
            </>
          } />
        );
      })}
    </div>
  );
}
