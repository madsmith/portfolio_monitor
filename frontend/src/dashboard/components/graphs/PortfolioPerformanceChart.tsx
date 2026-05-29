import { useEffect, useRef, useState } from "react";
import { api, type PerformanceSnapshot, type PortfolioSummary } from "../../api/client";
import { fmtMoney } from "../../lib/formatters";

const MARGIN = { top: 16, right: 60, bottom: 24, left: 12 };
const HEIGHT = 200;

// Wheel-sequence classification: continuous wheel events (gaps < SEQUENCE_GAP_MS)
// belong to the same gesture. The first event in a sequence decides whether the
// gesture is a page-scroll (started outside any chart) or a chart-zoom (started
// inside a chart). The classification sticks until the gesture ends — so a
// page scroll that drifts over the chart keeps scrolling instead of being
// hijacked, and a deliberate chart-zoom started inside the chart isn't blocked
// just because the user was scrolling the page a moment earlier.
const SEQUENCE_GAP_MS = 150;
const PAGE_MOVEMENT_GRACE_MS = 1500;
let lastWheelAt = 0;
let lastPageScrollAt = 0;
let currentSequenceIsPageScroll = false;
let wheelListenerInstalled = false;

function ensureWheelClassifier() {
  if (wheelListenerInstalled || typeof window === "undefined") return;
  wheelListenerInstalled = true;
  window.addEventListener("wheel", (e: WheelEvent) => {
    const now = performance.now();
    const target = e.target;
    const insideChart = target instanceof Element && !!target.closest("[data-perf-chart]");
    if (now - lastWheelAt > SEQUENCE_GAP_MS) {
      // New gesture. Page-scroll if it started outside any chart, OR if the
      // page is still in motion from a recent scroll (covers the case where
      // a chart drifts under the cursor mid-scroll, including trackpad
      // momentum scrolling where wheel events may pause briefly).
      const pageInMotion = now - lastPageScrollAt < PAGE_MOVEMENT_GRACE_MS;
      currentSequenceIsPageScroll = !insideChart || pageInMotion;
    }
    lastWheelAt = now;
  }, { capture: true, passive: true });
  window.addEventListener("scroll", () => {
    lastPageScrollAt = performance.now();
  }, { capture: true, passive: true });
}

const GREEN_FILL  = "#4d9060";
const RED_FILL    = "#9c4040";
const GREEN_LINE  = "#3fb950";
const RED_LINE    = "#f85149";
const BASIS_COLOR         = "#52566e";
const GRID_COLOR          = "#2a2d3a";
const AXIS_COLOR          = "#475569";
const CURRENT_VALUE_COLOR = "#5a6490";

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
  const DAY = 24 * 3_600_000;
  if (rangeMs > 180 * DAY) {
    // Show "Jan 2025" style for very long ranges
    return new Date(ms).toLocaleDateString("en-US", {
      month: "short", year: "numeric",
      timeZone: "UTC",
    });
  }
  if (rangeMs > 3 * DAY) {
    return new Date(ms).toLocaleDateString("en-US", {
      month: "short", day: "numeric",
      timeZone: "UTC",
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
  const DAY = 24 * 3_600_000;
  const WEEK = 7 * DAY;

  // Sub-day intervals (fixed ms)
  const subDayIntervals = [
    5 * 60_000, 15 * 60_000, 30 * 60_000,
    3_600_000, 2 * 3_600_000, 3 * 3_600_000,
    6 * 3_600_000, 12 * 3_600_000,
  ];

  if (rawInterval < DAY) {
    let interval = subDayIntervals[subDayIntervals.length - 1];
    for (const iv of subDayIntervals) {
      if (iv >= rawInterval) { interval = iv; break; }
    }
    const start = Math.ceil(fromMs / interval) * interval;
    const ticks: number[] = [];
    for (let t = start; t <= toMs; t += interval) ticks.push(t);
    return ticks;
  }

  // Multi-day: snap to calendar boundaries in UTC
  if (rawInterval < WEEK) {
    // Daily ticks: midnight UTC
    const ticks: number[] = [];
    const d = new Date(fromMs);
    d.setUTCHours(0, 0, 0, 0);
    d.setUTCDate(d.getUTCDate() + 1);
    while (d.getTime() <= toMs) {
      ticks.push(d.getTime());
      d.setUTCDate(d.getUTCDate() + 1);
    }
    return ticks;
  }

  // Multi-week: weekly ticks (Monday midnight UTC)
  if (rawInterval < 4 * WEEK) {
    const ticks: number[] = [];
    const d = new Date(fromMs);
    d.setUTCHours(0, 0, 0, 0);
    // advance to next Monday
    d.setUTCDate(d.getUTCDate() + ((8 - d.getUTCDay()) % 7 || 7));
    while (d.getTime() <= toMs) {
      ticks.push(d.getTime());
      d.setUTCDate(d.getUTCDate() + 7);
    }
    return ticks;
  }

  // Multi-month: 1st of each month UTC
  const monthStep = rawInterval < 10 * WEEK ? 1 : rawInterval < 20 * WEEK ? 2 : rawInterval < 40 * WEEK ? 3 : 6;
  const ticks: number[] = [];
  const d = new Date(fromMs);
  d.setUTCDate(1);
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCMonth(d.getUTCMonth() + 1);
  while (d.getTime() <= toMs) {
    ticks.push(d.getTime());
    d.setUTCMonth(d.getUTCMonth() + monthStep);
  }
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
  const [viewWindow, setViewWindowRaw] = useState<[number, number] | null>(() => {
    try {
      const stored = sessionStorage.getItem(`perf-window-${chartId}`);
      if (stored) return JSON.parse(stored) as [number, number];
    } catch { /* ignore */ }
    return null;
  });
  const [yZoom, setYZoomRaw] = useState<number>(() => {
    try {
      const stored = sessionStorage.getItem(`perf-yzoom-${chartId}`);
      if (stored) return JSON.parse(stored) as number;
    } catch { /* ignore */ }
    return 0;
  });
  const [hoverMs,    setHoverMs]    = useState<number | null>(null);

  function setViewWindow(w: [number, number] | null) {
    if (w === null) {
      sessionStorage.removeItem(`perf-window-${chartId}`);
    } else {
      try { sessionStorage.setItem(`perf-window-${chartId}`, JSON.stringify(w)); } catch { /* ignore */ }
    }
    setViewWindowRaw(w);
  }

  function setYZoom(z: number) {
    const clamped = Math.max(0, Math.min(1, z));
    try { sessionStorage.setItem(`perf-yzoom-${chartId}`, JSON.stringify(clamped)); } catch { /* ignore */ }
    setYZoomRaw(clamped);
  }

  type DragState =
    | { kind: "pan"; startX: number; fromMs: number; toMs: number }
    | { kind: "hover" }
    | { kind: "yzoom"; startY: number; startZoom: number };
  const dragRef  = useRef<DragState | null>(null);
  const pinchRef = useRef<{ midFrac: number; dist: number; fromMs: number; toMs: number } | null>(null);
  const [hoverZone, setHoverZone] = useState<"none" | "pan" | "yzoom">("none");

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

  // Install the shared wheel-sequence classifier (no-op after first chart).
  useEffect(() => { ensureWheelClassifier(); }, []);

  // Register non-passive touch handlers so e.preventDefault() suppresses page scroll
  type TouchHandlers = { start: (e: TouchEvent) => void; move: (e: TouchEvent) => void; end: () => void };
  const touchRef = useRef<TouchHandlers | null>(null);
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onStart  = (e: TouchEvent) => touchRef.current?.start(e);
    const onMove   = (e: TouchEvent) => touchRef.current?.move(e);
    const onEnd    = ()              => touchRef.current?.end();
    el.addEventListener("touchstart",  onStart, { passive: false });
    el.addEventListener("touchmove",   onMove,  { passive: false });
    el.addEventListener("touchend",    onEnd);
    el.addEventListener("touchcancel", onEnd);
    return () => {
      el.removeEventListener("touchstart",  onStart);
      el.removeEventListener("touchmove",   onMove);
      el.removeEventListener("touchend",    onEnd);
      el.removeEventListener("touchcancel", onEnd);
    };
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
  const dataMin = Math.min(...visValues);
  const dataMax = Math.max(...allY);
  const yMaxBase = Math.max(dataMax, 0);
  // yZoom=0 → wide range: yLo at 0, yHi well above dataMax.
  // yZoom=1 → tight range hugging the data: yLo just below dataMin, yHi just above dataMax.
  const span     = Math.max(dataMax - dataMin, 1);
  const yHiOut   = yMaxBase + (yMaxBase || 1) * 0.08;
  const yHiIn    = dataMax + span * 0.01;
  const yLoOut   = Math.min(0, dataMin);
  const yLoIn    = dataMin - span * 0.04;
  const yHi      = yHiOut + yZoom * (yHiIn - yHiOut);
  const yLo      = yLoOut + yZoom * (yLoIn - yLoOut);

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
    // If this wheel gesture started as a page scroll, let it pass through.
    if (currentSequenceIsPageScroll) return;
    e.preventDefault();
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const relXAbs = e.clientX - rect.left;
    const relYAbs = e.clientY - rect.top;
    if (zoneAt(relXAbs, relYAbs) === "yzoom") {
      const step = e.deltaY > 0 ? -0.1 : 0.1;
      setYZoom(yZoom + step);
      return;
    }
    const relX    = relXAbs - MARGIN.left;
    const fraction = Math.max(0, Math.min(1, relX / plotW));
    const curFrom  = viewWindow?.[0] ?? dataFromMs;
    const curTo    = viewWindow?.[1] ?? dataToMs;
    const winSize  = curTo - curFrom;
    const factor   = e.deltaY > 0 ? 1.25 : 0.8;
    const newSize  = Math.max(30 * 60_000, winSize * factor);
    const pivot    = curFrom + fraction * winSize;
    const newFrom  = Math.max(dataFromMs, pivot - fraction * newSize);
    const newTo    = Math.min(dataToMs, newFrom + newSize);
    // If we've zoomed out to cover full range, reset to null (show all)
    if (newFrom <= dataFromMs && newTo >= dataToMs) {
      setViewWindow(null);
    } else {
      setViewWindow([newFrom, newTo]);
    }
  };

  // Y threshold separating hover zone (top 80%) from pan zone (bottom 20%)
  const panZoneY = MARGIN.top + plotH * 0.8;

  // Returns which interaction zone a pointer at (relX, relY) hits.
  // relX/relY are relative to the SVG element's top-left.
  function zoneAt(relX: number, relY: number): "yzoom" | "pan" | "hover" {
    if (relX > MARGIN.left + plotW && relY >= MARGIN.top && relY <= MARGIN.top + plotH) {
      return "yzoom";
    }
    if (relY > panZoneY) return "pan";
    return "hover";
  }

  // Touch interaction — always current via ref so handlers see latest state
  touchRef.current = {
    start(e: TouchEvent) {
      e.preventDefault();
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;

      if (e.touches.length === 2) {
        // Begin pinch — cancel any single-touch drag
        dragRef.current = null;
        setHoverMs(null);
        const t0 = e.touches[0];
        const t1 = e.touches[1];
        const midClientX = (t0.clientX + t1.clientX) / 2;
        const dist = Math.hypot(t1.clientX - t0.clientX, t1.clientY - t0.clientY);
        const relX = midClientX - rect.left - MARGIN.left;
        const midFrac = Math.max(0, Math.min(1, relX / plotW));
        pinchRef.current = { midFrac, dist, fromMs, toMs };
        return;
      }

      if (e.touches.length !== 1) return;
      const clientX = e.touches[0].clientX;
      const clientY = e.touches[0].clientY;
      const relX    = clientX - rect.left;
      const relY    = clientY - rect.top;
      const zone    = zoneAt(relX, relY);
      if (zone === "yzoom") {
        dragRef.current = { kind: "yzoom", startY: clientY, startZoom: yZoom };
      } else if (zone === "pan") {
        dragRef.current = { kind: "pan", startX: clientX, fromMs, toMs };
      } else {
        dragRef.current = { kind: "hover" };
        const fx = Math.max(0, Math.min(1, (relX - MARGIN.left) / plotW));
        setHoverMs(clampFrom + fx * (clampTo - clampFrom));
      }
    },
    move(e: TouchEvent) {
      e.preventDefault();
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;

      if (e.touches.length === 2 && pinchRef.current) {
        const t0 = e.touches[0];
        const t1 = e.touches[1];
        const newDist = Math.hypot(t1.clientX - t0.clientX, t1.clientY - t0.clientY);
        if (newDist < 1) return;
        const { midFrac, dist: initDist, fromMs: initFrom, toMs: initTo } = pinchRef.current;
        const initWinSize = initTo - initFrom;
        const newSize  = Math.max(30 * 60_000, initWinSize * (initDist / newDist));
        const pivot    = initFrom + midFrac * initWinSize;
        const newFrom  = Math.max(dataFromMs, pivot - midFrac * newSize);
        const newTo    = Math.min(dataToMs, newFrom + newSize);
        if (newFrom <= dataFromMs && newTo >= dataToMs) {
          setViewWindow(null);
        } else {
          setViewWindow([newFrom, newTo]);
        }
        return;
      }

      if (e.touches.length !== 1) return;
      const clientX = e.touches[0].clientX;
      const clientY = e.touches[0].clientY;
      const drag = dragRef.current;
      if (drag?.kind === "yzoom") {
        const dy = clientY - drag.startY;
        setYZoom(drag.startZoom + dy / plotH);
      } else if (drag?.kind === "pan") {
        const dx    = clientX - drag.startX;
        const msPx  = (drag.toMs - drag.fromMs) / plotW;
        const shift = -dx * msPx;
        const winSz = drag.toMs - drag.fromMs;
        const nFrom = Math.max(dataFromMs, Math.min(dataToMs - winSz, drag.fromMs + shift));
        setViewWindow([nFrom, nFrom + winSz]);
      } else {
        const relX = clientX - rect.left - MARGIN.left;
        const frac = Math.max(0, Math.min(1, relX / plotW));
        setHoverMs(clampFrom + frac * (clampTo - clampFrom));
      }
    },
    end() {
      dragRef.current = null;
      pinchRef.current = null;
      setHoverMs(null);
    },
  };

  // Interaction handlers
  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = e.clientX - rect.left;
    const relY = e.clientY - rect.top;
    const drag = dragRef.current;
    if (drag?.kind === "yzoom") {
      const dy = e.clientY - drag.startY;
      setYZoom(drag.startZoom + dy / plotH);
      setHoverZone("yzoom");
      return;
    }
    if (drag?.kind === "pan") {
      const dx    = e.clientX - drag.startX;
      const msPx  = (drag.toMs - drag.fromMs) / plotW;
      const shift = -dx * msPx;
      const winSz = drag.toMs - drag.fromMs;
      const nFrom = Math.max(dataFromMs, Math.min(dataToMs - winSz, drag.fromMs + shift));
      setViewWindow([nFrom, nFrom + winSz]);
      setHoverZone("pan");
      return;
    }
    const zone = zoneAt(relX, relY);
    setHoverZone(zone === "hover" ? "none" : zone);
    if (zone === "hover") {
      const frac = Math.max(0, Math.min(1, (relX - MARGIN.left) / plotW));
      setHoverMs(clampFrom + frac * (clampTo - clampFrom));
    } else {
      setHoverMs(null);
    }
  }

  function handleMouseDown(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = e.clientX - rect.left;
    const relY = e.clientY - rect.top;
    const zone = zoneAt(relX, relY);
    if (zone === "yzoom") {
      dragRef.current = { kind: "yzoom", startY: e.clientY, startZoom: yZoom };
    } else if (zone === "pan") {
      dragRef.current = { kind: "pan", startX: e.clientX, fromMs, toMs };
    } else {
      dragRef.current = { kind: "hover" };
    }
    e.preventDefault();
  }

  function handleMouseLeave() {
    dragRef.current = null;
    setHoverMs(null);
    setHoverZone("none");
  }

  function handleDoubleClick(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const zone = zoneAt(e.clientX - rect.left, e.clientY - rect.top);
    if (zone === "yzoom") {
      setYZoom(0);
    } else {
      setViewWindow(null);
    }
  }

  const clipId = `perf-clip-${chartId}`;

  const DAY = 24 * 3_600_000;
  const PRESETS: { label: string; ms: number | null }[] = [
    { label: "1D", ms: DAY },
    { label: "3D", ms: 3 * DAY },
    { label: "1W", ms: 7 * DAY },
    { label: "1M", ms: 30 * DAY },
    { label: "3M", ms: 91 * DAY },
    { label: "1Y", ms: 365 * DAY },
    { label: "All", ms: null },
  ];

  function activePreset(): string {
    if (viewWindow === null) return "All";
    const winMs = viewWindow[1] - viewWindow[0];
    for (const p of [...PRESETS].reverse()) {
      if (p.ms !== null && Math.abs(winMs - p.ms) < 0.1 * p.ms) return p.label;
    }
    return "";
  }

  function applyPreset(ms: number | null) {
    if (ms === null) { setViewWindow(null); return; }
    const from = Math.max(dataFromMs, dataToMs - ms);
    setViewWindow([from, dataToMs]);
  }

  const active = activePreset();

  return (
    <div className="relative select-none">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{name}</span>
        <div className="flex items-center gap-0.5">
          {PRESETS.filter((p) => p.ms === null || p.ms <= dataToMs - dataFromMs + DAY).map((p) => (
            <button
              key={p.label}
              onClick={() => applyPreset(p.ms)}
              className={[
                "px-1.5 py-0.5 text-[10px] rounded transition-colors cursor-pointer",
                active === p.label
                  ? "bg-[#2a2f45] text-slate-200"
                  : "text-slate-600 hover:text-slate-400",
              ].join(" ")}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div className="relative">
        <svg
          ref={svgRef}
          data-perf-chart
          width="100%"
          height={HEIGHT}
          onMouseMove={handleMouseMove}
          onMouseDown={handleMouseDown}
          onMouseUp={() => { dragRef.current = null; }}
          onMouseLeave={handleMouseLeave}
          onDoubleClick={handleDoubleClick}
          className={
            hoverZone === "yzoom" ? "cursor-ns-resize"
            : hoverZone === "pan" ? "cursor-ew-resize"
            : "cursor-crosshair"
          }
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

          {/* Current value reference line */}
          {(() => {
            const currentY = yScale(values[values.length - 1]);
            if (currentY < MARGIN.top || currentY > MARGIN.top + plotH) return null;
            return (
              <line
                x1={MARGIN.left} y1={currentY} x2={MARGIN.left + plotW} y2={currentY}
                stroke={CURRENT_VALUE_COLOR} strokeWidth={1} opacity={0.6}
              />
            );
          })()}

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

        {/* HTML tooltip — pinned above the chart, following cursor horizontally */}
        {hoverData && (
          <div
            className="absolute pointer-events-none -translate-x-1/2 z-10"
            style={{
              left: `calc(${MARGIN.left}px + ${hoverLeftPct / 100} * ${plotW}px)`,
              bottom: "calc(100% + 4px)",
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
        Scroll to zoom · Drag to pan · Drag Y axis to zoom Y · Double-click to reset
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
      api.getPortfolioPerformance(p.id, { all: true })
        .then((data) => {
          console.debug(`[perf] ${p.name} (${p.id}): ${data.snapshots.length} snapshots`, data.snapshots[0], "→", data.snapshots[data.snapshots.length - 1]);
          setPerfData((prev) => ({
            ...prev,
            [p.id]: { loading: false, error: false, snapshots: data.snapshots },
          }));
        })
        .catch((err: unknown) => {
          console.error(`[perf] ${p.name} (${p.id}): fetch failed`, err);
          setPerfData((prev) => ({
            ...prev,
            [p.id]: { loading: false, error: true, snapshots: [] },
          }));
        });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portfolioKey]);

  const allLoading = Object.values(perfData).length > 0 && Object.values(perfData).every((d) => d.loading);

  function suppressReason(id: string): string | null {
    const d = perfData[id];
    if (!d) return "no data loaded";
    if (d.loading) return "loading";
    if (d.error) return "fetch error";
    if (d.snapshots.length < 2) return `only ${d.snapshots.length} snapshot(s)`;
    return null;
  }

  const chartsToShow = portfolios.filter((p) => suppressReason(p.id) === null).sort((a, b) => (b.total_value || 0) - (a.total_value || 0));
  const suppressed   = portfolios.filter((p) => suppressReason(p.id) !== null && perfData[p.id] && !perfData[p.id].loading);

  if (allLoading) {
    return <div className="text-slate-600 text-sm py-2">Loading performance data…</div>;
  }

  if (chartsToShow.length === 0 && suppressed.length === 0) return null;

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
      {suppressed.map((p) => (
        <div key={p.id} className="text-xs text-slate-600 font-mono">
          [{p.name}] suppressed — {suppressReason(p.id)}
          {perfData[p.id]?.snapshots.length === 1 && (
            <span className="ml-2 text-slate-700">
              (1 snapshot: {perfData[p.id].snapshots[0].recorded_at})
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
