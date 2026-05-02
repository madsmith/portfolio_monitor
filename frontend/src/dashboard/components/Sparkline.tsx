export const SPARK_GREEN = "#4d9060";
export const SPARK_RED   = "#9c4040";

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

/**
 * Normalized percent-change sparkline.
 *
 * Renders `values` as a line chart normalized to % change from the first value.
 * The zero baseline (starting price) divides the chart into green (above) and
 * red (below) segments. Segments crossing zero are split at the exact intercept.
 *
 * Props:
 *   id      — unique string used to scope SVG gradient IDs; must be stable across renders
 *   values  — raw price (or any numeric) series, left-to-right chronological order
 *   height  — rendered height in px; width expands to fill the container
 *   positiveColor / negativeColor — override the default green/red colors
 */
export function Sparkline({
  id,
  values,
  height,
  positiveColor = SPARK_GREEN,
  negativeColor = SPARK_RED,
}: {
  id: string;
  values: number[];
  height: number;
  positiveColor?: string;
  negativeColor?: string;
}) {
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
  const first = values[0];
  const pcts = values.map((v) => ((v - first) / first) * 100);

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

  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} preserveAspectRatio="none"
      className="overflow-visible">
      <defs>
        {/* Positive gradient: opaque at the top (where the line is), fades down to the baseline */}
        <linearGradient id={posId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positiveColor} stopOpacity="0.25" />
          <stop offset="100%" stopColor={positiveColor} stopOpacity="0.02" />
        </linearGradient>
        {/* Negative gradient: fades from the baseline down to the line (inverted direction) */}
        <linearGradient id={negId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={negativeColor} stopOpacity="0.02" />
          <stop offset="100%" stopColor={negativeColor} stopOpacity="0.25" />
        </linearGradient>
      </defs>

      {/* Dashed horizontal rule at y=0 (the starting price) */}
      <line x1={PAD.left} y1={zeroY} x2={PAD.left + plotW} y2={zeroY}
        stroke="#404868" strokeWidth={1} strokeDasharray="3 2" opacity={0.6} />

      {/* Filled area between the line and the zero baseline, one path per segment */}
      {segments.map((seg, i) => (
        <path key={i} d={mkArea(seg.points)}
          fill={`url(#${seg.positive ? posId : negId})`} />
      ))}

      {/* The price line itself, drawn on top of the fill */}
      {segments.map((seg, i) => (
        <path key={i} d={mkLine(seg.points)} fill="none"
          stroke={seg.positive ? positiveColor : negativeColor} strokeWidth={1.5}
          strokeLinejoin="round" strokeLinecap="round" />
      ))}
    </svg>
  );
}
