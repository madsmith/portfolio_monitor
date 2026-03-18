import { useEffect, useRef, useState } from "react";
import { api, type DailyOpenClose, type PriceAggregate } from "../api/client";
import { fmtMoney } from "../lib/formatters";

const PERIODS = [
  { label: "1H", last: "1h", span: "1m",  refreshMs:      60_000, trendMaxMs: null,         compactGapMs: 4 * 60 * 60_000 },
  { label: "4H", last: "4h", span: "1m",  refreshMs:  1 * 60_000, trendMaxMs:  20 * 60_000, compactGapMs: 4 * 60 * 60_000 },
  { label: "1D", last: "1d", span: "1m",  refreshMs:  1 * 60_000, trendMaxMs:  60 * 60_000, compactGapMs: 4 * 60 * 60_000 },
  { label: "3D", last: "3d", span: "5m",  refreshMs:  5 * 60_000, trendMaxMs: 180 * 60_000, compactGapMs: 4 * 60 * 60_000 },
  { label: "7D", last: "7d", span: "10m", refreshMs: 10 * 60_000, trendMaxMs: 420 * 60_000, compactGapMs: 4 * 60 * 60_000 },
] as const;

type Period = typeof PERIODS[number];

// SVG layout constants
const W = 800;
const H = 180;
const PAD = { top: 10, right: 50, bottom: 28, left: 0 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;
const Y_LABELS = 4;
const X_LABELS = 6;
const Y_LABEL_X = PAD.left + PLOT_W + 6;  // x origin of right-hand Y axis labels/boxes
const Y_BOX_W = 48;                        // width of price label boxes on right axis

// Pixels of visual gap between sessions in compact mode
const COMPACT_GAP_PX = 6;

const PERIOD_MS: Record<string, number> = {
  "1h": 60 * 60_000,
  "4h": 4 * 60 * 60_000,
  "1d": 24 * 60 * 60_000,
  "3d": 3 * 24 * 60 * 60_000,
  "7d": 7 * 24 * 60 * 60_000,
};

function parsePeriodMs(last: string): number {
  return PERIOD_MS[last] ?? 60 * 60_000;
}

function fmtAxisTime(d: Date, period: Period): string {
  if (period.last === "3d" || period.last === "7d") {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
  }
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

function fmtTooltipTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

/** A filled price label box on the right-hand axis. */
function PriceBox({
  y, price, fill, stroke, textFill, fillOpacity = 1, strokeOpacity = 1
}: {
  y: number; price: number; fill: string; stroke?: string; textFill: string;
  fillOpacity?: number; strokeOpacity?: number;
}) {
  return (
    <g>
      <rect x={Y_LABEL_X} y={y - 8} width={Y_BOX_W} height={16} rx={2}
        fill={fill} stroke={stroke} strokeWidth={stroke ? 1 : 0}
        fillOpacity={fillOpacity} strokeOpacity={strokeOpacity}/>
      <text x={Y_LABEL_X + Y_BOX_W / 2} y={y} textAnchor="middle"
        dominantBaseline="middle" fontSize="0.9em" fontWeight="600" fill={textFill}>
        {fmtMoney(price)}
      </text>
    </g>
  );
}

type CompactLayout = {
  xScale: (ts: string) => number;
  xInverse: (x: number) => Date;
  dividers: number[];
  xLabels: { x: number; time: Date }[];
};

/** Build a compressed x-axis layout from raw data.
 *  Splits data into market sessions by collapsing only gaps ≥ compactGapMs
 *  (market-closed periods like overnight/weekends), leaving intraday data gaps intact.
 *  Each session gets x-space proportional to its duration.
 *  A COMPACT_GAP_PX visual gap separates adjacent sessions.
 */
function buildCompactLayout(data: PriceAggregate[], compactGapMs: number): CompactLayout | null {
  if (data.length === 0) return null;

  // Split data into sessions at market-closed gaps only
  const sessions: PriceAggregate[][] = [];
  let session: PriceAggregate[] = [data[0]];
  for (let i = 1; i < data.length; i++) {
    const gap = new Date(data[i].timestamp).getTime() - new Date(data[i - 1].timestamp).getTime();
    if (gap >= compactGapMs) {
      sessions.push(session);
      session = [];
    }
    session.push(data[i]);
  }
  sessions.push(session);

  const segments = sessions;
  if (segments.length === 0) return null;

  const segInfo = segments.map((seg) => {
    const tFirst = new Date(seg[0].timestamp).getTime();
    const tLast  = new Date(seg[seg.length - 1].timestamp).getTime();
    return { tFirst, tLast, dur: Math.max(tLast - tFirst, 1) };
  });

  const totalDur    = segInfo.reduce((s, si) => s + si.dur, 0);
  const totalGapPx  = COMPACT_GAP_PX * (segments.length - 1);
  const availW      = PLOT_W - totalGapPx;

  let xCursor = PAD.left;
  const segLayout = segInfo.map((si) => {
    const w = totalDur > 0
      ? Math.max(1, (si.dur / totalDur) * availW)
      : availW / segInfo.length;
    const result = { ...si, xStart: xCursor, w };
    xCursor += w + COMPACT_GAP_PX;
    return result;
  });

  function xScale(ts: string): number {
    const t = new Date(ts).getTime();
    for (const sl of segLayout) {
      // +120s buffer to include the last bar's timestamp
      if (t >= sl.tFirst && t <= sl.tLast + 120_000) {
        const frac = Math.min(1, (t - sl.tFirst) / sl.dur);
        return sl.xStart + frac * sl.w;
      }
    }
    const last = segLayout[segLayout.length - 1];
    return last.xStart + last.w;
  }

  function xInverse(x: number): Date {
    for (const sl of segLayout) {
      if (x >= sl.xStart && x <= sl.xStart + sl.w) {
        const frac = sl.w > 0 ? (x - sl.xStart) / sl.w : 0;
        return new Date(sl.tFirst + frac * sl.dur);
      }
    }
    const last = segLayout[segLayout.length - 1];
    return new Date(last.tLast);
  }

  const dividers = segLayout.slice(0, -1).map((sl) => sl.xStart + sl.w + COMPACT_GAP_PX / 2);

  // Distribute X_LABELS evenly across total active (trading) time, skipping gaps
  const xLabels: { x: number; time: Date }[] = [];
  for (let i = 0; i < X_LABELS; i++) {
    const targetMs = (i / (X_LABELS - 1)) * totalDur;
    let elapsed = 0;
    for (const sl of segLayout) {
      if (targetMs <= elapsed + sl.dur) {
        const t = new Date(sl.tFirst + (targetMs - elapsed));
        xLabels.push({ x: sl.xStart + ((targetMs - elapsed) / sl.dur) * sl.w, time: t });
        break;
      }
      elapsed += sl.dur;
    }
  }

  return { xScale, xInverse, dividers, xLabels };
}

export function Chart({
  ticker,
  assetType,
  showTooltip = true,
  showCurrent = true,
  showOpen = null,
  showXIntercept = true,
  showYIntercept = true,
  compact = true,
}: {
  ticker: string;
  assetType: string;
  /** Show a floating price/time tooltip while hovering. Default: true. */
  showTooltip?: boolean;
  /** Show a dashed line + label at the most recent price. Default: true. */
  showCurrent?: boolean;
  /**
   * Show a dashed line + label at the period's open price.
   * Pass `null` to auto-enable for periods ≤ 1D. Default: false.
   */
  showOpen?: boolean | null;
  /** Show a vertical crosshair + time label on hover. Default: true. */
  showXIntercept?: boolean;
  /** Show a horizontal crosshair + price label on hover. Default: true. */
  showYIntercept?: boolean;
  /**
   * Compress the x-axis to only show active trading time.
   * Sessions (segments split by trendMaxMs gaps) are laid out proportionally
   * to their duration; non-trading gaps between sessions are collapsed to a
   * thin visual divider. Default: false.
   */
  compact?: boolean;
}) {
  const [period, setPeriod] = useState<Period>(PERIODS[1]);
  const [data, setData] = useState<PriceAggregate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
  const [openClose, setOpenClose] = useState<DailyOpenClose | null>(null);
  const [openCloseLoading, setOpenCloseLoading] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    let active = true;

    function fetchData(initialLoad: boolean) {
      if (initialLoad) { setLoading(true); setError(null); }
      api.getPriceHistory(assetType, ticker, period.last, period.span)
        .then((r)  => { if (active) { setData(r.aggregates); if (initialLoad) setLoading(false); } })
        .catch(()  => { if (active && initialLoad) { setError("Failed to load price data"); setLoading(false); } });
    }

    fetchData(true);
    const interval = setInterval(() => fetchData(false), period.refreshMs);
    return () => { active = false; clearInterval(interval); };
  }, [ticker, assetType, period]);

  const effectiveShowOpen =
    showOpen === null
      ? (period.last === "1h" || period.last === "4h" || period.last === "1d")
      : (showOpen ?? false);

  useEffect(() => {
    if (!effectiveShowOpen) { setOpenClose(null); return; }
    let active = true;
    setOpenCloseLoading(true);
    api.getOpenClose(assetType, ticker)
      .then((r) => { if (active) { setOpenClose(r); setOpenCloseLoading(false); } })
      .catch(() => { if (active) { setOpenClose(null); setOpenCloseLoading(false); } });
    return () => { active = false; };
  }, [ticker, assetType, effectiveShowOpen]);

  const displayAgg = data.length > 0
    ? (hoverIdx !== null ? data[hoverIdx] : data[data.length - 1])
    : null;

  const openPrice = openClose?.open ?? null;

  const isPositive = data.length >= 2
    ? data[data.length - 1].close >= (openPrice ?? data[0].close)
    : null;
  const lineColor = isPositive === null ? "#64748b" : isPositive ? "#4d9060" : "#9c4040";
  const areaColor = lineColor;

  // Scales
  const prices = data.map((d) => d.close);
  const rawMin = prices.length ? Math.min(...prices) : 0;
  const rawMax = prices.length ? Math.max(...prices) : 1;
  const pad = (rawMax - rawMin) * 0.06 || rawMax * 0.02 || 0.01;
  const yMin = rawMin - pad;
  const yMax = rawMax + pad;

  // Time domain: full requested window, not just the span of returned data
  const tMin = Date.now() - parsePeriodMs(period.last);
  const tMax = Date.now();
  const tRange = tMax - tMin;

  const yScale = (p: number) => PAD.top + PLOT_H - ((p - yMin) / (yMax - yMin)) * PLOT_H;

  // Split data into contiguous segments, breaking on gaps > trendMaxMs
  const trendMaxMs = period.trendMaxMs;
  const segments: PriceAggregate[][] = [];
  if (data.length >= 2) {
    let seg: PriceAggregate[] = [data[0]];
    for (let i = 1; i < data.length; i++) {
      const gap = new Date(data[i].timestamp).getTime() - new Date(data[i - 1].timestamp).getTime();
      if (trendMaxMs !== null && gap > trendMaxMs) {
        segments.push(seg);
        seg = [];
      }
      seg.push(data[i]);
    }
    segments.push(seg);
  }

  // Compact layout: compress x-axis so only active trading time takes up space
  const compactLayout: CompactLayout | null = compact ? buildCompactLayout(data, period.compactGapMs) : null;

  // Unified x scale — compact or linear
  const xScaleTs = compactLayout
    ? compactLayout.xScale
    : (ts: string) => PAD.left + ((new Date(ts).getTime() - tMin) / tRange) * PLOT_W;

  // Paths — one M…L run per segment, joined into a single <path> each
  const linePath = segments
    .map((seg) => seg.map((d, i) => `${i === 0 ? "M" : "L"} ${xScaleTs(d.timestamp).toFixed(1)} ${yScale(d.close).toFixed(1)}`).join(" "))
    .join(" ");
  const areaPath = segments
    .filter((seg) => seg.length >= 2)
    .map((seg) => {
      const lp = seg.map((d, i) => `${i === 0 ? "M" : "L"} ${xScaleTs(d.timestamp).toFixed(1)} ${yScale(d.close).toFixed(1)}`).join(" ");
      return `${lp} L ${xScaleTs(seg[seg.length - 1].timestamp).toFixed(1)} ${(PAD.top + PLOT_H).toFixed(1)} L ${xScaleTs(seg[0].timestamp).toFixed(1)} ${(PAD.top + PLOT_H).toFixed(1)} Z`;
    })
    .join(" ");

  // Y axis labels
  const yLabels = Array.from({ length: Y_LABELS }, (_, i) => {
    const price = yMin + (yMax - yMin) * (i / (Y_LABELS - 1));
    const y = yScale(price);
    return { price, y };
  }).reverse();

  // X axis labels — evenly spaced across the full time window (non-compact)
  const xLabelTimes = Array.from({ length: X_LABELS }, (_, i) =>
    new Date(tMin + (i / (X_LABELS - 1)) * tRange)
  );

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const svgX = ((e.clientX - rect.left) / rect.width) * W;
    const svgY = ((e.clientY - rect.top) / rect.height) * H;
    const plotX = svgX - PAD.left;
    const plotY = svgY - PAD.top;
    if (plotX < 0 || plotX > PLOT_W || plotY < 0 || plotY > PLOT_H) {
      setHoverIdx(null);
      setHoverPos(null);
      return;
    }
    setHoverPos({ x: svgX, y: svgY });
    if (data.length >= 2) {
      const hoverTs = compactLayout
        ? compactLayout.xInverse(svgX).getTime()
        : tMin + (plotX / PLOT_W) * tRange;
      let nearest = 0;
      let nearestDist = Infinity;
      for (let i = 0; i < data.length; i++) {
        const dist = Math.abs(new Date(data[i].timestamp).getTime() - hoverTs);
        if (dist < nearestDist) { nearestDist = dist; nearest = i; }
      }
      setHoverIdx(nearest);
    }
  }

  const currentPrice  = data.length > 0 ? data[data.length - 1].close : null;

  return (
    <div className="text-sm">
      {/* Header: period controls + price display */}
      <div className="flex items-center justify-between mb-2 gap-4">
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.label}
              onClick={() => setPeriod(p)}
              className={[
                "px-2 py-0.5 rounded text-xs font-medium transition-colors cursor-pointer",
                period.label === p.label
                  ? "bg-[#404868] text-slate-100"
                  : "text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="text-right tabular-nums shrink-0">
          {displayAgg ? (
            <>
              <span className="font-semibold" style={{ color: lineColor }}>
                {fmtMoney(displayAgg.close)}
              </span>
              <span className="text-slate-500 text-xs ml-2">
                {fmtTooltipTime(displayAgg.timestamp)}
              </span>
            </>
          ) : null}
        </div>
      </div>

      {/* Chart area */}
      {(loading || openCloseLoading) && <p className="text-slate-500 text-xs py-6 text-center">Loading…</p>}
      {error && <p className="text-red-400 text-xs py-6 text-center">{error}</p>}
      {!(loading || openCloseLoading) && !error && data.length === 0 && (
        <p className="text-slate-600 text-xs py-6 text-center">No data available</p>
      )}
      {!(loading || openCloseLoading) && !error && data.length >= 2 && (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          fontSize="10"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => { setHoverIdx(null); setHoverPos(null); }}
          className="overflow-visible"
        >
          <defs>
            <linearGradient id={`chartArea-${ticker}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={areaColor} stopOpacity="0.2" />
              <stop offset="100%" stopColor={areaColor} stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Horizontal grid lines */}
          {yLabels.map(({ y }, i) => (
            <line key={i} x1={PAD.left} y1={y} x2={PAD.left + PLOT_W} y2={y}
              stroke="#1e2130" strokeWidth={1} />
          ))}

          {/* Compact mode: session dividers */}
          {compactLayout && compactLayout.dividers.map((x, i) => (
            <line key={i} x1={x} y1={PAD.top} x2={x} y2={PAD.top + PLOT_H}
              stroke="#2a3050" strokeWidth={1} strokeDasharray="2 2" />
          ))}

          {/* Area fill */}
          <path d={areaPath} fill={`url(#chartArea-${ticker})`} />

          {/* Open price line + label — renders before current so current sits on top */}
          {effectiveShowOpen && openPrice !== null && (() => {
            const raw = yScale(openPrice);
            const oy = Math.max(PAD.top, Math.min(PAD.top + PLOT_H, raw));
            const boxOy = raw < PAD.top ? oy - 8 : raw > PAD.top + PLOT_H ? oy + 8 : oy;
            return (
              <>
                <line x1={PAD.left} y1={oy} x2={PAD.left + PLOT_W} y2={oy}
                  stroke="#64748b" strokeWidth={1} strokeDasharray="4 3" opacity={0.6} />
                <PriceBox y={boxOy} price={openPrice}
                  fill="#1e2130" stroke="#404868" textFill="#94a3b8" />
              </>
            );
          })()}

          {/* Current price line */}
          {showCurrent && currentPrice !== null && (() => {
            const cy = yScale(currentPrice);
            return (
              <line x1={PAD.left} y1={cy} x2={PAD.left + PLOT_W} y2={cy}
                stroke={lineColor} strokeWidth={1} strokeDasharray="4 3" opacity={0.7} />
            );
          })()}

          {/* Price line */}
          <path d={linePath} fill="none" stroke={lineColor} strokeWidth={1.5}
            strokeLinejoin="round" strokeLinecap="round" />

          {/* Y axis labels (right-hand side) */}
          {yLabels.map(({ price, y }, i) => (
            <text key={i} x={Y_LABEL_X} y={y} textAnchor="start"
              dominantBaseline="middle" fontSize="1em" fill="#64748b">
              {fmtMoney(price)}
            </text>
          ))}

          {/* Current price label box */}
          {showCurrent && currentPrice !== null && (
            <PriceBox y={yScale(currentPrice)} price={currentPrice}
              fill={lineColor} textFill="#fff" stroke={lineColor}
              fillOpacity={0.35} strokeOpacity={1}/>
          )}

          {/* X axis tick marks + labels */}
          {(compactLayout
            ? compactLayout.xLabels.map((lbl) => ({ x: lbl.x, time: lbl.time, anchor: "middle" as const }))
            : xLabelTimes.map((d, i) => ({
                x: PAD.left + (i / (X_LABELS - 1)) * PLOT_W,
                time: d,
                anchor: (i === 0 ? "start" : i === xLabelTimes.length - 1 ? "end" : "middle") as "start" | "middle" | "end",
              }))
          ).map(({ x, time, anchor }, i) => (
            <g key={i}>
              <line x1={x} y1={PAD.top + PLOT_H} x2={x} y2={PAD.top + PLOT_H + 4}
                stroke="#404868" strokeWidth={1} />
              <text x={x} y={PAD.top + PLOT_H + 14} textAnchor={anchor}
                fontSize="1em" fill="#64748b">
                {fmtAxisTime(time, period)}
              </text>
            </g>
          ))}

          {/* Intercepts — driven by raw mouse position */}
          {hoverPos !== null && (() => {
            const mx = hoverPos.x;
            const my = hoverPos.y;
            const hoverTime = compactLayout
              ? compactLayout.xInverse(mx)
              : new Date(tMin + ((mx - PAD.left) / PLOT_W) * tRange);
            const hoverPrice = yMin + (1 - (my - PAD.top) / PLOT_H) * (yMax - yMin);
            const xLabelW = 72;
            return (
              <g>
                {showXIntercept && (
                  <>
                    <line x1={mx} y1={PAD.top} x2={mx} y2={PAD.top + PLOT_H}
                      stroke="#404868" strokeWidth={1} strokeDasharray="3 2" />
                    <rect x={mx - xLabelW / 2} y={PAD.top + PLOT_H + 6} width={xLabelW} height={15}
                      rx={2} fill="#252a40" stroke="#404868" strokeWidth={1} fillOpacity={0.5}/>
                    <text x={mx} y={PAD.top + PLOT_H + 13} textAnchor="middle"
                      dominantBaseline="middle" fontSize="0.9em" fill="#94a3b8">
                      {fmtAxisTime(hoverTime, period)}
                    </text>
                  </>
                )}
                {showYIntercept && (
                  <>
                    <line x1={PAD.left} y1={my} x2={PAD.left + PLOT_W} y2={my}
                      stroke="#404868" strokeWidth={1} strokeDasharray="3 2" />
                    <PriceBox y={my} price={hoverPrice}
                      fill="#252a40" stroke="#404868" textFill="#e2e8f0"
                      fillOpacity={0.5} strokeOpacity={1}/>
                  </>
                )}
              </g>
            );
          })()}

          {/* Snapped dot + tooltip — driven by nearest data point */}
          {hoverIdx !== null && (() => {
            const hovered = data[hoverIdx];
            const cx = xScaleTs(hovered.timestamp);
            const cy = yScale(hovered.close);
            const tipW = 132;
            const tipH = 32;
            const tipX = cx > PAD.left + PLOT_W / 2 ? cx - tipW - 10 : cx + 10;
            const tipY = PAD.top + 2;
            return (
              <g>
                <circle cx={cx} cy={cy} r={3} fill={lineColor} stroke="#0f1117" strokeWidth={1.5} />
                {showTooltip && (
                  <g>
                    <rect x={tipX} y={tipY} width={tipW} height={tipH} rx={3}
                      fill="#1e2130" stroke="#404868" strokeWidth={1}
                      fillOpacity={0.5} strokeOpacity={1} />
                    <text x={tipX + 8} y={tipY + 12} fontSize="1em" fill="#e2e8f0" fontWeight="600">
                      {fmtMoney(hovered.close)}
                    </text>
                    <text x={tipX + 8} y={tipY + 25} fontSize="0.9em" fill="#64748b">
                      {fmtTooltipTime(hovered.timestamp)}
                    </text>
                  </g>
                )}
              </g>
            );
          })()}
        </svg>
      )}
    </div>
  );
}
