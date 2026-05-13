import { useRef, useEffect, useState } from "react";

export const SPARK_GREEN = "#4d9060";
export const SPARK_RED   = "#9c4040";
export const SPARK_TEXT_GREEN = "#2cb152";
export const SPARK_TEXT_RED = "#d92a2a";

type SparkSegment = { points: { x: number; y: number }[]; positive: boolean };

// Walks the normalized-% series and splits it into contiguous above-zero and
// below-zero runs. Where a consecutive pair of values straddles zero, we
// interpolate the exact crossing point (linear) and use it as the shared
// endpoint of the outgoing segment and start of the incoming one — so the
// colored paths meet cleanly at the baseline rather than jumping across it.
function splitAtZero(
  pcts: number[],
  xScale: (i: number) => number,
  yScale: (p: number) => number,
): SparkSegment[] {
  if (pcts.length === 0) return [];
  const segments: SparkSegment[] = [];
  let pts: { x: number; y: number }[] = [{ x: xScale(0), y: yScale(pcts[0]) }];
  let isPos = pcts[0] >= 0;

  for (let i = 1; i < pcts.length; i++) {
    const prev = pcts[i - 1];
    const curr = pcts[i];
    if ((prev >= 0) !== (curr >= 0)) {
      // t is the fraction along this step where the value crosses zero
      const t = prev / (prev - curr);
      const cx = xScale(i - 1) + t * (xScale(i) - xScale(i - 1));
      pts.push({ x: cx, y: yScale(0) });       // close current segment at the crossing
      segments.push({ points: pts, positive: isPos });
      pts = [{ x: cx, y: yScale(0) }];         // start next segment from the same point
      isPos = curr >= 0;
    }
    pts.push({ x: xScale(i), y: yScale(pcts[i]) });
  }
  segments.push({ points: pts, positive: isPos });
  return segments;
}

// Format an ISO date ("YYYY-MM-DD") or datetime ("YYYY-MM-DDThh:mm:ssZ") label for hover display.
function fmtShortDate(iso: string): string {
  if (iso.includes("T")) {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit",
      timeZone: "America/New_York",
    });
  }
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

/**
 * Normalized percent-change sparkline.
 *
 * Renders `values` as a line chart normalized to % change from the first value.
 * The zero baseline (starting price) divides the chart into green (above) and
 * red (below) segments. Segments crossing zero are split at the exact intercept.
 *
 * Basic usage (no hover):
 *   <Sparkline id="AAPL" values={closes} height={40} />
 *
 * Group hover usage (synchronized across multiple sparklines):
 *   <Sparkline
 *     id="AAPL"
 *     values={closes}
 *     labels={dates}                  // ISO date strings per point, for tooltip
 *     height={40}
 *     hoverFraction={sharedFraction}  // 0–1 x position driven by the group
 *     onHoverFraction={setFraction}   // reports this sparkline's cursor position
 *     showTooltip={isActiveSparkline} // only the sparkline under cursor shows text
 *   />
 *
 * Props:
 *   id               — unique string used to scope SVG gradient IDs; must be stable across renders
 *   values           — raw price (or any numeric) series, left-to-right chronological order
 *   labels           — optional parallel array of strings (e.g. ISO dates) shown in hover tooltip
 *   height           — rendered height in px; width expands to fill the container
 *   positiveColor    — override the default green line/fill color
 *   negativeColor    — override the default red line/fill color
 *   hoverFraction    — incoming shared x position (0–1); renders intercept line + dot on all group members
 *   onHoverFraction  — reports this sparkline's cursor x fraction to the parent group coordinator
 *   showTooltip      — when true, renders the % value + date label at the intercept (only the active sparkline)
 */
export function Sparkline({
  id,
  values,
  labels,
  height,
  positiveColor = SPARK_GREEN,
  negativeColor = SPARK_RED,
  normalize = true,
  hoverFraction = null,
  onHoverFraction,
  showTooltip = false,
  tooltipStyle = "svg",
  textPositiveColor = SPARK_TEXT_GREEN,
  textNegativeColor = SPARK_TEXT_RED
}: {
  id: string;
  values: number[];
  labels?: string[];
  height: number;
  positiveColor?: string;
  negativeColor?: string;
  textPositiveColor?: string;
  textNegativeColor?: string;
  /**
   * When true (default), values are raw prices — normalized to % change from the
   * first value before rendering. When false, values are already in % units
   * (e.g. a momentum series) and are plotted as-is against a zero baseline.
   */
  normalize?: boolean;
  /** Incoming shared x position (0–1); renders an intercept line on this sparkline. */
  hoverFraction?: number | null;
  /** Called with the cursor's x fraction (0–1) as the mouse moves, or null on leave. */
  onHoverFraction?: (fraction: number | null) => void;
  /** When true, renders the % value + date label next to the intercept. */
  showTooltip?: boolean;
  /** "svg" (default) renders tooltip text inside the SVG; "html" renders it as an
   *  absolutely-positioned div above the chart so it isn't subject to viewBox scaling. */
  tooltipStyle?: "svg" | "html";
}) {
  const svgRef     = useRef<SVGSVGElement>(null);
  const touchCbRef = useRef<{ handle: (e: TouchEvent) => void; clear: () => void } | null>(null);
  // Local fraction updated synchronously on touch — avoids the parent round-trip
  // (onHoverFraction → parent setState → re-render → hoverFraction prop back) that
  // makes the crosshair feel laggy during a drag.
  const [localFraction, setLocalFraction] = useState<number | null>(null);

  // Non-passive touch listeners so preventDefault() actually suppresses page scroll
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const handle = (e: TouchEvent) => touchCbRef.current?.handle(e);
    const clear  = ()              => touchCbRef.current?.clear();
    el.addEventListener("touchstart",  handle, { passive: false });
    el.addEventListener("touchmove",   handle, { passive: false });
    el.addEventListener("touchend",    clear);
    el.addEventListener("touchcancel", clear);
    return () => {
      el.removeEventListener("touchstart",  handle);
      el.removeEventListener("touchmove",   handle);
      el.removeEventListener("touchend",    clear);
      el.removeEventListener("touchcancel", clear);
    };
  }, []);

  // Always-current callbacks — closed over latest props/state
  touchCbRef.current = onHoverFraction ? {
    handle(e: TouchEvent) {
      if (e.touches.length === 0) return;
      e.preventDefault();
      const el = svgRef.current;
      if (!el) return;
      const f = fractionFromClientX(el, e.touches[0].clientX);
      setLocalFraction(f);    // immediate local update — no parent round-trip
      onHoverFraction(f);     // sync group (other sparklines) async
    },
    clear() {
      setLocalFraction(null);
      onHoverFraction(null);
    },
  } : null;

  const W = 400; // internal viewBox width; CSS scales to container

  // Not enough data to draw a line — render a muted dashed placeholder
  if (values.length < 2) {
    return (
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} preserveAspectRatio="none">
        <line x1={0} y1={height / 2} x2={W} y2={height / 2}
          stroke="#404868" strokeWidth={1} strokeDasharray="4 3" />
      </svg>
    );
  }

  // Normalize every value to % change from the first, so the y-axis is
  // "how far above/below the starting price" rather than a raw price scale.
  // When normalize=false the caller has already done this (e.g. momentum series).
  const first = values[0];
  const pcts = normalize ? values.map((v) => ((v - first) / first) * 100) : values;

  // Leave a few px of breathing room on each edge so the line isn't clipped
  const PAD = { top: 4, right: 2, bottom: 4, left: 2 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  // Always include 0 in the y domain so the baseline is always visible,
  // then add 8% headroom above and below the extremes
  const pMin = Math.min(...pcts, 0);
  const pMax = Math.max(...pcts, 0);
  const range = pMax - pMin || 0.01;
  const yMin = pMin - range * 0.08;
  const yMax = pMax + range * 0.08;

  // Map data-space → SVG pixel space (y is inverted: larger % = higher on screen)
  const xScale = (i: number) => PAD.left + (i / (pcts.length - 1)) * plotW;
  const yScale = (p: number) => PAD.top + plotH - ((p - yMin) / (yMax - yMin)) * plotH;
  const zeroY = yScale(0); // pixel y of the zero baseline

  // Split the series into green/red runs so each can be colored independently
  const segments = splitAtZero(pcts, xScale, yScale);

  // Build an SVG "M x y L x y …" path string from a list of points
  const mkLine = (pts: { x: number; y: number }[]) =>
    pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");

  // Extend the line path down to the zero baseline and back to form a closed
  // filled region between the line and the zero axis
  const mkArea = (pts: { x: number; y: number }[]) => {
    const last = pts[pts.length - 1];
    const first = pts[0];
    return `${mkLine(pts)} L ${last.x.toFixed(1)} ${zeroY.toFixed(1)} L ${first.x.toFixed(1)} ${zeroY.toFixed(1)} Z`;
  };

  const posId = `spark-pos-${id}`;
  const negId = `spark-neg-${id}`;

  // localFraction (touch-driven) takes priority over the parent-propagated hoverFraction
  // so the crosshair reacts instantly on touch without waiting for the parent re-render cycle.
  const activeFraction = localFraction ?? hoverFraction;

  // Compute the hovered intercept point from the incoming fraction.
  // ix is the SVG x coordinate; nearestIdx snaps to the closest data point.
  const intercept = activeFraction !== null ? (() => {
    const ix = PAD.left + activeFraction * plotW;
    const nearestIdx = Math.round(activeFraction * (pcts.length - 1));
    const pct = pcts[nearestIdx];
    const iy = yScale(pct);
    const color = pct >= 0 ? positiveColor : negativeColor;
    const textColor = pct >= 0 ? textPositiveColor : textNegativeColor;
    const label = labels?.[nearestIdx];
    // Keep the tooltip text anchor within the horizontal chart bounds
    const tipX = Math.max(PAD.left + 22, Math.min(ix, PAD.left + plotW - 22));
    const tipSign = pct >= 0 ? "+" : "";
    const tipText = label
      ? `${tipSign}${pct.toFixed(1)}% · ${fmtShortDate(label)}`
      : `${tipSign}${pct.toFixed(1)}%`;
    return { ix, iy, color, tipX, tipText, textColor };
  })() : null;

  // Report the cursor's x fraction whenever the mouse moves over this SVG.
  // Fraction is computed in CSS space (clientX / rendered width) so it's
  // independent of the SVG viewBox scale and always in [0, 1].
  function fractionFromClientX(el: SVGSVGElement, clientX: number): number {
    const rect = el.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  }

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!onHoverFraction) return;
    onHoverFraction(fractionFromClientX(e.currentTarget, e.clientX));
  }


  const tipPct = activeFraction !== null
    ? Math.max(4, Math.min(96, activeFraction * 100))
    : 50;

  const svg = (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${height}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      className="overflow-visible select-none"
      onMouseMove={onHoverFraction ? handleMouseMove : undefined}
      onMouseLeave={onHoverFraction ? () => onHoverFraction(null) : undefined}
    >
      <defs>
        <linearGradient id={posId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positiveColor} stopOpacity="0.25" />
          <stop offset="100%" stopColor={positiveColor} stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id={negId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={negativeColor} stopOpacity="0.02" />
          <stop offset="100%" stopColor={negativeColor} stopOpacity="0.25" />
        </linearGradient>
      </defs>

      <line x1={PAD.left} y1={zeroY} x2={PAD.left + plotW} y2={zeroY}
        stroke="#404868" strokeWidth={1} strokeDasharray="3 2" opacity={0.6} />

      {segments.map((seg, i) => (
        <path key={i} d={mkArea(seg.points)}
          fill={`url(#${seg.positive ? posId : negId})`} />
      ))}

      {segments.map((seg, i) => (
        <path key={i} d={mkLine(seg.points)} fill="none"
          stroke={seg.positive ? positiveColor : negativeColor} strokeWidth={1.5}
          strokeLinejoin="round" strokeLinecap="round" />
      ))}

      {intercept !== null && (
        <g>
          <line
            x1={intercept.ix} y1={PAD.top}
            x2={intercept.ix} y2={PAD.top + plotH}
            stroke="#94a3b8" strokeWidth={0.75} strokeDasharray="2 2" opacity={0.7}
          />
          <circle
            cx={intercept.ix} cy={intercept.iy} r={2.5}
            fill={intercept.color} stroke="#0f1117" strokeWidth={1}
          />
          {showTooltip && tooltipStyle === "svg" && (
            <text
              x={intercept.tipX} y={-3}
              textAnchor="middle"
              fontSize="7.5"
              fontWeight="400"
              fill={intercept.color}
            >
              {intercept.tipText}
            </text>
          )}
        </g>
      )}
    </svg>
  );

  if (tooltipStyle === "html") {
    return (
      <div className="relative select-none">
        {svg}
        {showTooltip && intercept !== null && (
          <div
            className="absolute pointer-events-none text-sm whitespace-nowrap -translate-x-1/2"
            style={{ left: `${tipPct}%`, bottom: "calc(100% + 1em)", color: intercept.textColor }}
          >
            {intercept.tipText}
          </div>
        )}
      </div>
    );
  }

  return svg;
}
