import { useEffect, useRef, useState } from "react";
import { api, type PerformanceSnapshot, type PortfolioSummary } from "../api/client";
import { fmtMoney } from "../lib/formatters";

const MARGIN = { top: 16, right: 60, bottom: 24, left: 12 };
const HEIGHT = 200;

const GREEN_FILL  = "#4d9060";
const RED_FILL    = "#9c4040";
const GREEN_LINE  = "#3fb950";
const RED_LINE    = "#f85149";
const BASIS_COLOR = "#52566e";
const GRID_COLOR  = "#2a2d3a";
const AXIS_COLOR  = "#475569";

// ── Formatting helpers ────────────────────────────────────────────────────────

function fmtAxisMoney(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000)     return `$${(v / 1_000).toFixed(1)}k`;
  return `$${v.toFixed(0)}`;
}

function fmtTooltipTime(ms: number): string {
  return new Date(ms).toLocaleString("en-US", {
    month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
    hour12: true,
    timeZone: "America/New_York",
  });
}

function fmtAxisTime(ms: number, rangeMs: number): string {
  if (rangeMs > 3 * 24 * 3600 * 1000) {
    return new Date(ms).toLocaleDateString("en-US", {
      month: "short", day: "numeric",
      timeZone: "America/New_York",
    });
  }
  return new Date(ms).toLocaleTimeString("en-US", {
    hour: "numeric", minute: "2-digit",
    hour12: true,
    timeZone: "America/New_York",
  });
}

// ── Tick generation ───────────────────────────────────────────────────────────

function niceTicks(min: number, max: number, targetCount: number): number[] {
  const range = max - min || 1;
  const rawStep = range / targetCount;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  let step = mag;
  for (const mult of [1, 2, 2.5, 5, 10]) {
    if (mag * mult >= rawStep) { step = mag * mult; break; }
  }
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= max + step * 0.001; v = +(v + step).toPrecision(10)) {
    ticks.push(v);
  }
  return ticks;
}

function niceTimeTicks(fromMs: number, toMs: number, count: number): number[] {
  const range = toMs - fromMs;
  const rawInterval = range / count;
  const intervals = [
    5 * 60_000, 15 * 60_000, 30 * 60_000,
    3_600_000, 2 * 3_600_000, 3 * 3_600_000,
    6 * 3_600_000, 12 * 3_600_000, 24 * 3_600_000,
  ];
  let interval = intervals[intervals.length - 1];
  for (const iv of intervals) {
    if (iv >= rawInterval) { interval = iv; break; }
  }
  const start = Math.ceil(fromMs / interval) * interval;
  const ticks: number[] = [];
  for (let t = start; t <= toMs; t += interval) ticks.push(t);
  return ticks;
}

// ── Fill segment builder ──────────────────────────────────────────────────────

type Point = { x: number; y: number };
type FillSeg = { valuePts: Point[]; basisPts: Point[]; above: boolean };

// Splits the area between two series at the crossings where value and cost_basis
// exchange positions. At each crossing we interpolate the exact x/y so that the
// green and red regions meet cleanly without overlap.
function buildFillSegments(
  xs: number[],
  valueYs: number[],
  basisYs: number[],
  diffs: number[], // value - cost_basis in data coords (sign determines above/below)
): FillSeg[] {
  if (xs.length < 2) return [];
  const segs: FillSeg[] = [];
  let vPts: Point[] = [{ x: xs[0], y: valueYs[0] }];
  let bPts: Point[] = [{ x: xs[0], y: basisYs[0] }];
  let above = diffs[0] >= 0;

  for (let i = 1; i < xs.length; i++) {
    const d0 = diffs[i - 1];
    const d1 = diffs[i];
    if ((d0 >= 0) !== (d1 >= 0)) {
      const t  = d0 / (d0 - d1);
      const cx = xs[i - 1]      + t * (xs[i]      - xs[i - 1]);
      const cvy = valueYs[i - 1] + t * (valueYs[i] - valueYs[i - 1]);
      const cby = basisYs[i - 1] + t * (basisYs[i] - basisYs[i - 1]);
      const cy  = (cvy + cby) / 2; // both converge at the crossing
      vPts.push({ x: cx, y: cy });
      bPts.push({ x: cx, y: cy });
      segs.push({ valuePts: vPts, basisPts: bPts, above });
      vPts  = [{ x: cx, y: cy }];
      bPts  = [{ x: cx, y: cy }];
      above = d1 >= 0;
    }
    vPts.push({ x: xs[i], y: valueYs[i] });
    bPts.push({ x: xs[i], y: basisYs[i] });
  }
  segs.push({ valuePts: vPts, basisPts: bPts, above });
  return segs;
}

function mkLinePath(pts: Point[]): string {
  return pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
}

function mkFillPath(seg: FillSeg): string {
  const fwd = mkLinePath(seg.valuePts);
  const bwd = [...seg.basisPts].reverse().map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  return `${fwd} ${bwd} Z`;
}

// ── Single chart ──────────────────────────────────────────────────────────────

function PortfolioPerformanceChart({
  chartId,
  name,
  snapshots,
}: {
  chartId: string;
  name: string;
  snapshots: PerformanceSnapshot[];
}) {
  const svgRef  = useRef<SVGSVGElement>(null);
  const [svgWidth, setSvgWidth] = useState(800);
  const [viewWindow, setViewWindow] = useState<[number, number] | null>(null);
  const [hoverMs,    setHoverMs]    = useState<number | null>(null);

  const dragRef = useRef<{ startX: number; fromMs: number; toMs: number } | null>(null);

  // Measure rendered SVG width so pixel coordinates are accurate
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => setSvgWidth(entries[0].contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Register non-passive wheel handler so e.preventDefault() works
  const zoomRef = useRef<((e: WheelEvent) => void) | null>(null);
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => zoomRef.current?.(e);
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, []);

  const validSnaps = snapshots.filter((s) => s.total_value !== null);

  if (validSnaps.length < 2) {
    return (
      <div>
        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">{name}</div>
        <div className="text-slate-600 text-sm py-2">No performance data yet.</div>
      </div>
    );
  }

  const times  = validSnaps.map((s) => new Date(s.recorded_at).getTime());
  const values = validSnaps.map((s) => s.total_value as number);
  const bases  = validSnaps.map((s) => s.cost_basis);

  const dataFromMs = times[0];
  const dataToMs   = times[times.length - 1];

  const [fromMs, toMs] = viewWindow ?? [dataFromMs, dataToMs];
  const clampFrom = Math.max(dataFromMs, fromMs);
  const clampTo   = Math.min(dataToMs,   toMs);

  // Extend window one point on each side for clean clip-area edges
  const startIdx = Math.max(0, times.findIndex((t) => t >= clampFrom) - 1);
  const endIdx   = Math.min(times.length - 1, (() => {
    for (let i = times.length - 1; i >= 0; i--) { if (times[i] <= clampTo) return i + 1; }
    return times.length - 1;
  })());

  const visTimes  = times.slice(startIdx, endIdx + 1);
  const visValues = values.slice(startIdx, endIdx + 1);
  const visBases  = bases.slice(startIdx, endIdx + 1);

  if (visTimes.length < 2) return null;

  // Layout
  const plotW = svgWidth - MARGIN.left - MARGIN.right;
  const plotH  = HEIGHT   - MARGIN.top  - MARGIN.bottom;

  // Scales
  const xScale = (ms: number) =>
    MARGIN.left + ((ms - clampFrom) / (clampTo - clampFrom)) * plotW;

  const allY = [...visValues, ...visBases];
  const yMin = Math.min(...allY, 0);
  const yMax = Math.max(...allY, 0);
  const yPad = (yMax - yMin || 1) * 0.08;
  const yLo  = yMin - yPad;
  const yHi  = yMax + yPad;

  const yScale = (v: number) =>
    MARGIN.top + plotH - ((v - yLo) / (yHi - yLo)) * plotH;

  const xs      = visTimes.map(xScale);
  const valueYs = visValues.map(yScale);
  const basisYs = visBases.map(yScale);
  const diffs   = visValues.map((v, i) => v - visBases[i]);

  const fillSegs = buildFillSegments(xs, valueYs, basisYs, diffs);

  // Ticks
  const yTicks = niceTicks(yLo, yHi, 4);
  const xTicks = niceTimeTicks(clampFrom, clampTo, 5);
  const xRange = clampTo - clampFrom;

  // Hover
  const hoverIdx = hoverMs !== null
    ? visTimes.reduce((best, t, i) =>
        Math.abs(t - hoverMs) < Math.abs(visTimes[best] - hoverMs) ? i : best, 0)
    : null;

  const hoverData = hoverIdx !== null ? {
    x:      xs[hoverIdx],
    valueY: valueYs[hoverIdx],
    value:  visValues[hoverIdx],
    basis:  visBases[hoverIdx],
    time:   visTimes[hoverIdx],
    above:  diffs[hoverIdx] >= 0,
  } : null;

  const hoverLeftPct = hoverData
    ? Math.max(5, Math.min(95, ((hoverData.x - MARGIN.left) / plotW) * 100))
    : 50;

  // Update zoom handler ref (always current values)
  zoomRef.current = (e: WheelEvent) => {
    e.preventDefault();
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const relX    = e.clientX - rect.left - MARGIN.left;
    const fraction = Math.max(0, Math.min(1, relX / plotW));
    const curFrom  = viewWindow?.[0] ?? dataFromMs;
    const curTo    = viewWindow?.[1] ?? dataToMs;
    const winSize  = curTo - curFrom;
    const factor   = e.deltaY > 0 ? 1.25 : 0.8;
    const newSize  = Math.max(30 * 60_000, Math.min(dataToMs - dataFromMs, winSize * factor));
    const pivot    = curFrom + fraction * winSize;
    const newFrom  = Math.max(dataFromMs, pivot - fraction * newSize);
    const newTo    = Math.min(dataToMs,   newFrom + newSize);
    setViewWindow([newFrom, newTo]);
  };

  // Interaction handlers
  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    if (dragRef.current) {
      const dx     = e.clientX - dragRef.current.startX;
      const msPx   = (dragRef.current.toMs - dragRef.current.fromMs) / plotW;
      const shift  = -dx * msPx;
      const winSz  = dragRef.current.toMs - dragRef.current.fromMs;
      const nFrom  = Math.max(dataFromMs, Math.min(dataToMs - winSz, dragRef.current.fromMs + shift));
      setViewWindow([nFrom, nFrom + winSz]);
      return;
    }
    const relX  = e.clientX - rect.left - MARGIN.left;
    const frac  = Math.max(0, Math.min(1, relX / plotW));
    setHoverMs(clampFrom + frac * (clampTo - clampFrom));
  }

  function handleMouseDown(e: React.MouseEvent<SVGSVGElement>) {
    dragRef.current = { startX: e.clientX, fromMs: fromMs, toMs: toMs };
    e.preventDefault();
  }

  function handleMouseLeave() {
    dragRef.current = null;
    setHoverMs(null);
  }

  function handleDoubleClick() {
    setViewWindow(null);
  }

  const clipId = `perf-clip-${chartId}`;
  const isZoomed = viewWindow !== null;

  return (
    <div className="relative select-none">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{name}</span>
        {isZoomed && (
          <button
            onClick={handleDoubleClick}
            className="text-[10px] text-slate-600 hover:text-slate-400 cursor-pointer transition-colors"
          >
            Reset zoom
          </button>
        )}
      </div>
      <div className="relative">
        <svg
          ref={svgRef}
          width="100%"
          height={HEIGHT}
          onMouseMove={handleMouseMove}
          onMouseDown={handleMouseDown}
          onMouseUp={() => { dragRef.current = null; }}
          onMouseLeave={handleMouseLeave}
          onDoubleClick={handleDoubleClick}
          className="cursor-crosshair"
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={MARGIN.left} y={MARGIN.top} width={plotW} height={plotH} />
            </clipPath>
          </defs>

          {/* Y axis grid + labels */}
          {yTicks.map((tick) => {
            const y = yScale(tick);
            if (y < MARGIN.top || y > MARGIN.top + plotH) return null;
            return (
              <g key={tick}>
                <line
                  x1={MARGIN.left} y1={y} x2={MARGIN.left + plotW} y2={y}
                  stroke={GRID_COLOR} strokeWidth={1}
                />
                <text
                  x={MARGIN.left + plotW + 6} y={y}
                  textAnchor="start" dominantBaseline="middle"
                  fontSize="10" fill={AXIS_COLOR}
                >
                  {fmtAxisMoney(tick)}
                </text>
              </g>
            );
          })}

          {/* X axis labels */}
          {xTicks.map((tick) => {
            const x = xScale(tick);
            if (x < MARGIN.left || x > MARGIN.left + plotW) return null;
            return (
              <text
                key={tick}
                x={x} y={MARGIN.top + plotH + 16}
                textAnchor="middle" fontSize="9" fill={AXIS_COLOR}
              >
                {fmtAxisTime(tick, xRange)}
              </text>
            );
          })}

          {/* Axis border lines */}
          <line
            x1={MARGIN.left + plotW} y1={MARGIN.top}
            x2={MARGIN.left + plotW} y2={MARGIN.top + plotH}
            stroke="#404868" strokeWidth={1}
          />
          <line
            x1={MARGIN.left} y1={MARGIN.top + plotH}
            x2={MARGIN.left + plotW} y2={MARGIN.top + plotH}
            stroke="#404868" strokeWidth={1}
          />

          {/* Clipped chart content */}
          <g clipPath={`url(#${clipId})`}>
            {/* Filled area between value and cost_basis */}
            {fillSegs.map((seg, i) => (
              <path
                key={i} d={mkFillPath(seg)}
                fill={seg.above ? GREEN_FILL : RED_FILL}
                fillOpacity={0.18}
              />
            ))}

            {/* Cost basis shaded area down to zero */}
            {(() => {
              const basisPts = visTimes.map((_, i) => ({ x: xs[i], y: basisYs[i] }));
              const zeroY = yScale(0);
              const last  = basisPts[basisPts.length - 1];
              const first = basisPts[0];
              const areaPath = `${mkLinePath(basisPts)} L ${last.x.toFixed(1)} ${zeroY.toFixed(1)} L ${first.x.toFixed(1)} ${zeroY.toFixed(1)} Z`;
              return (
                <path d={areaPath} fill={BASIS_COLOR} fillOpacity={0.22} />
              );
            })()}

            {/* Cost basis dashed reference line */}
            <path
              d={mkLinePath(visTimes.map((_, i) => ({ x: xs[i], y: basisYs[i] })))}
              fill="none"
              stroke={BASIS_COLOR} strokeWidth={1.5} strokeDasharray="5 3"
            />

            {/* Value line, colored green/red per segment */}
            {fillSegs.map((seg, i) => (
              <path
                key={i} d={mkLinePath(seg.valuePts)}
                fill="none"
                stroke={seg.above ? GREEN_LINE : RED_LINE}
                strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round"
              />
            ))}

            {/* Hover crosshair */}
            {hoverData && (
              <>
                <line
                  x1={hoverData.x} y1={MARGIN.top}
                  x2={hoverData.x} y2={MARGIN.top + plotH}
                  stroke="#94a3b8" strokeWidth={0.75} strokeDasharray="2 2" opacity={0.7}
                />
                <circle
                  cx={hoverData.x} cy={hoverData.valueY} r={3}
                  fill={hoverData.above ? GREEN_LINE : RED_LINE}
                  stroke="#0f1117" strokeWidth={1.5}
                />
              </>
            )}
          </g>
        </svg>

        {/* HTML tooltip — rendered above the chart area */}
        {hoverData && (
          <div
            className="absolute pointer-events-none -translate-x-1/2 z-10"
            style={{
              left: `calc(${MARGIN.left}px + ${hoverLeftPct / 100} * ${plotW}px)`,
              top: `${MARGIN.top + 4}px`,
            }}
          >
            <div className="bg-[#12151f] border border-[#404868] rounded px-2.5 py-1.5 shadow-lg text-xs whitespace-nowrap">
              <div className="text-slate-500 mb-1">{fmtTooltipTime(hoverData.time)}</div>
              <div className={hoverData.above ? "text-[#3fb950]" : "text-[#f85149]"}>
                {fmtMoney(hoverData.value)}
              </div>
              <div className="text-[#52566e]">Basis {fmtMoney(hoverData.basis)}</div>
              <div className={`mt-0.5 font-medium ${hoverData.above ? "text-[#3fb950]" : "text-[#f85149]"}`}>
                {hoverData.value - hoverData.basis >= 0 ? "+" : ""}
                {fmtMoney(hoverData.value - hoverData.basis)}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Scroll/zoom hint */}
      <div className="text-[10px] text-slate-700 mt-0.5">
        Scroll to zoom · Drag to pan · Double-click to reset
      </div>
    </div>
  );
}

// ── Multi-chart section with data fetching ────────────────────────────────────

type PerfEntry = { loading: boolean; error: boolean; snapshots: PerformanceSnapshot[] };

export function PortfolioPerformanceCharts({ portfolios }: { portfolios: PortfolioSummary[] }) {
  const [perfData, setPerfData] = useState<Record<string, PerfEntry>>({});

  const portfolioKey = portfolios.map((p) => p.id).join(",");

  useEffect(() => {
    if (portfolios.length === 0) return;
    setPerfData({});
    for (const p of portfolios) {
      setPerfData((prev) => ({ ...prev, [p.id]: { loading: true, error: false, snapshots: [] } }));
      api.getPortfolioPerformance(p.id, 1)
        .then((data) => {
          setPerfData((prev) => ({
            ...prev,
            [p.id]: { loading: false, error: false, snapshots: data.snapshots },
          }));
        })
        .catch(() => {
          setPerfData((prev) => ({
            ...prev,
            [p.id]: { loading: false, error: true, snapshots: [] },
          }));
        });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portfolioKey]);

  const allLoading = Object.values(perfData).length > 0 && Object.values(perfData).every((d) => d.loading);
  const chartsToShow = portfolios.filter(
    (p) => perfData[p.id] && !perfData[p.id].loading && !perfData[p.id].error && perfData[p.id].snapshots.length >= 2
  );

  if (allLoading) {
    return <div className="text-slate-600 text-sm py-2">Loading performance data…</div>;
  }

  if (chartsToShow.length === 0) return null;

  return (
    <div className="space-y-6">
      {chartsToShow.map((p) => (
        <PortfolioPerformanceChart
          key={p.id}
          chartId={p.id}
          name={p.name}
          snapshots={perfData[p.id].snapshots}
        />
      ))}
    </div>
  );
}
