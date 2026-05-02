import { SPARK_GREEN, SPARK_RED } from "./Sparkline";
import { fmtVol } from "../lib/formatters";

function fmtShortDate(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

/**
 * Daily volume bar chart.
 *
 * Each bar represents one day's volume. Bars are green when close >= open,
 * red otherwise. Shares the same hover-coordination interface as Sparkline
 * so both can be grouped under a single hoverFraction state.
 *
 * Props mirror Sparkline's hover props for drop-in interchangeability:
 *   id               — scopes SVG element IDs; must be stable across renders
 *   days             — array of daily OHLCV records, chronological order
 *   height           — rendered height in px
 *   hoverFraction    — incoming shared x position (0–1)
 *   onHoverFraction  — reports this chart's cursor x fraction to the group coordinator
 *   showTooltip      — when true, renders volume + date label above the chart
 */
export function VolumeBars({
  id,
  days,
  height,
  hoverFraction = null,
  onHoverFraction,
  showTooltip = false,
}: {
  id: string;
  days: { date: string; open: number; close: number; volume: number }[];
  height: number;
  hoverFraction?: number | null;
  onHoverFraction?: (fraction: number | null) => void;
  showTooltip?: boolean;
}) {
  void id; // reserved for future gradient/clip-path IDs

  const W = 400;

  if (days.length < 2) {
    return (
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} preserveAspectRatio="none">
        <line x1={0} y1={height / 2} x2={W} y2={height / 2}
          stroke="#404868" strokeWidth={1} strokeDasharray="4 3" />
      </svg>
    );
  }

  const PAD = { top: 4, right: 2, bottom: 4, left: 2 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  const N = days.length;
  const maxVol = Math.max(...days.map((d) => d.volume));

  // Same x-scale as Sparkline so hover fractions are interchangeable
  const xScale = (i: number) => PAD.left + (i / (N - 1)) * plotW;
  const barW = Math.max(1, (plotW / (N - 1)) * 0.8);
  const yBar = (v: number) => PAD.top + plotH - (v / maxVol) * plotH;

  const nearestIdx = hoverFraction !== null
    ? Math.round(hoverFraction * (N - 1))
    : null;
  const ix = hoverFraction !== null ? PAD.left + hoverFraction * plotW : null;
  const hoveredDay = nearestIdx !== null ? days[nearestIdx] : null;
  const tipX = ix !== null
    ? Math.max(PAD.left + 30, Math.min(ix, PAD.left + plotW - 30))
    : null;

  function fractionFromClientX(el: SVGSVGElement, clientX: number): number {
    const rect = el.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  }

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!onHoverFraction) return;
    onHoverFraction(fractionFromClientX(e.currentTarget, e.clientX));
  }

  function handleTouchMove(e: React.TouchEvent<SVGSVGElement>) {
    if (!onHoverFraction) return;
    e.preventDefault();
    onHoverFraction(fractionFromClientX(e.currentTarget, e.touches[0].clientX));
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      className="overflow-visible"
      onMouseMove={onHoverFraction ? handleMouseMove : undefined}
      onMouseLeave={onHoverFraction ? () => onHoverFraction(null) : undefined}
      onTouchMove={onHoverFraction ? handleTouchMove : undefined}
      onTouchEnd={onHoverFraction ? () => onHoverFraction(null) : undefined}
    >
      {days.map((d, i) => {
        const cx = xScale(i);
        const y = yBar(d.volume);
        const barHeight = plotH - (y - PAD.top);
        const color = d.close >= d.open ? SPARK_GREEN : SPARK_RED;
        const isHovered = nearestIdx === i;
        return (
          <rect
            key={i}
            x={cx - barW / 2}
            y={y}
            width={barW}
            height={barHeight}
            fill={color}
            opacity={isHovered ? 1 : 0.45}
          />
        );
      })}

      {ix !== null && (
        <g>
          <line
            x1={ix} y1={PAD.top}
            x2={ix} y2={PAD.top + plotH}
            stroke="#94a3b8" strokeWidth={0.75} strokeDasharray="2 2" opacity={0.7}
          />
          {showTooltip && hoveredDay && tipX !== null && (
            <text
              x={tipX} y={-3}
              textAnchor="middle"
              fontSize="7.5"
              fontWeight="400"
              fill="#94a3b8"
            >
              {`${fmtVol(hoveredDay.volume)} · ${fmtShortDate(hoveredDay.date)}`}
            </text>
          )}
        </g>
      )}
    </svg>
  );
}
