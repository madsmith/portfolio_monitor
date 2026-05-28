import { useState } from "react";
import { type Asset } from "../../api/client";
import { fmtMoney } from "../../lib/formatters";

const PIE_COLORS = [
  "#4e8cbf", "#5db88e", "#c9784a", "#9b6bc9", "#bf9c4e",
  "#c94a6b", "#4ec9bf", "#9dbf4e", "#bf4e9b", "#6b9bc9",
  "#c9c24e", "#bf6b6b",
];

const VB = 200;
const CX = VB / 2;
const CY = VB / 2;
const OUTER_R = 88;
const INNER_R = 54;
const LEGEND_THRESHOLD = 20;

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number): { x: number; y: number } {
  const rad = (angleDeg - 90) * (Math.PI / 180);
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, outerR: number, innerR: number, startDeg: number, endDeg: number): string {
  const sweep = Math.min(endDeg - startDeg, 359.999);
  const end = startDeg + sweep;
  const large = sweep > 180 ? 1 : 0;
  const o1 = polarToCartesian(cx, cy, outerR, startDeg);
  const o2 = polarToCartesian(cx, cy, outerR, end);
  const i1 = polarToCartesian(cx, cy, innerR, end);
  const i2 = polarToCartesian(cx, cy, innerR, startDeg);
  return [
    `M ${o1.x.toFixed(2)} ${o1.y.toFixed(2)}`,
    `A ${outerR} ${outerR} 0 ${large} 1 ${o2.x.toFixed(2)} ${o2.y.toFixed(2)}`,
    `L ${i1.x.toFixed(2)} ${i1.y.toFixed(2)}`,
    `A ${innerR} ${innerR} 0 ${large} 0 ${i2.x.toFixed(2)} ${i2.y.toFixed(2)}`,
    "Z",
  ].join(" ");
}

type PieSlice = { ticker: string; value: number; color: string; pct: number };
type PathSlice = PieSlice & { start: number; span: number };

function DonutSvg({ paths, hovSlice, total, hovered, onHover }: {
  paths: PathSlice[];
  hovSlice: PieSlice | null | undefined;
  total: number;
  hovered: string | null;
  onHover: (ticker: string | null) => void;
}) {
  return (
    <svg width="100%" viewBox={`0 0 ${VB} ${VB}`} style={{ maxWidth: 360 }}>
      {paths.map((p) => (
        <path
          key={p.ticker}
          d={arcPath(CX, CY, OUTER_R, INNER_R, p.start, p.start + p.span)}
          fill={p.color}
          fillOpacity={hovered === null || hovered === p.ticker ? 1 : 0.3}
          stroke="#0f1117"
          strokeWidth={1}
          onMouseEnter={() => onHover(p.ticker)}
          onMouseLeave={() => onHover(null)}
          className="cursor-default transition-opacity duration-100"
        />
      ))}
      <text x={CX} y={CY - 8} textAnchor="middle" fontSize="11" fill={hovSlice ? hovSlice.color : "#94a3b8"} fontWeight="600">
        {hovSlice ? hovSlice.ticker : "Total"}
      </text>
      <text x={CX} y={CY + 7} textAnchor="middle" fontSize="10" fill={hovSlice ? hovSlice.color : "#94a3b8"}>
        {hovSlice ? fmtMoney(hovSlice.value) : fmtMoney(total)}
      </text>
      {hovSlice && (
        <text x={CX} y={CY + 21} textAnchor="middle" fontSize="9" fill="#64748b">
          {hovSlice.pct.toFixed(1)}%
        </text>
      )}
    </svg>
  );
}

export function CompositionPieChart({ assets }: { assets: Asset[] }) {
  const [hovered, setHovered] = useState<string | null>(null);

  const slices: PieSlice[] = assets
    .filter((a) => a.current_value !== null && a.current_value > 0)
    .sort((a, b) => (b.current_value ?? 0) - (a.current_value ?? 0))
    .map((a, i) => ({
      ticker: a.ticker,
      value: a.current_value as number,
      color: PIE_COLORS[i % PIE_COLORS.length],
      pct: 0,
    }));

  const total = slices.reduce((s, a) => s + a.value, 0);
  if (total === 0 || slices.length === 0) return null;
  slices.forEach((s) => { s.pct = (s.value / total) * 100; });

  let cursor = 0;
  const paths: PathSlice[] = slices.map((s) => {
    const start = cursor;
    const span = (s.value / total) * 360;
    cursor += span;
    return { ...s, start, span };
  });

  const hovSlice = hovered ? slices.find((s) => s.ticker === hovered) : null;
  const showLegend = slices.length > LEGEND_THRESHOLD;

  if (!showLegend) {
    return (
      <div className="flex justify-center py-3">
        <DonutSvg paths={paths} hovSlice={hovSlice} total={total} hovered={hovered} onHover={setHovered} />
      </div>
    );
  }

  // Legend in flow sets the container height.
  // Donut is absolutely centred over the full width on sm+.
  // On mobile the legend is hidden and the donut falls back to normal flow.
  return (
    <div className="relative">
      {/* Legend — sm+ only, in normal flow to establish container height */}
      <div className="hidden min-[840px]:flex flex-col gap-y-0.5 ml-auto w-fit py-3">
        {slices.map((s) => (
          <div
            key={s.ticker}
            className={`flex items-center gap-2 cursor-default transition-opacity duration-100 ${hovered !== null && hovered !== s.ticker ? "opacity-30" : ""}`}
            onMouseEnter={() => setHovered(s.ticker)}
            onMouseLeave={() => setHovered(null)}
          >
            <span className="w-2 h-2 rounded-sm flex-shrink-0" style={{ background: s.color }} />
            <span className="text-xs text-slate-300 font-medium w-12 truncate">{s.ticker}</span>
            <span className="text-xs text-slate-500 tabular-nums w-10 text-right">{s.pct.toFixed(1)}%</span>
            <span className="text-xs text-slate-600 tabular-nums w-24 text-right">{fmtMoney(s.value)}</span>
          </div>
        ))}
      </div>

      {/* Donut — sm+: absolute, centred over the full container */}
      <div className="absolute inset-0 hidden min-[840px]:flex items-center justify-center pointer-events-none">
        <div className="w-full max-w-sm pointer-events-auto">
          <DonutSvg paths={paths} hovSlice={hovSlice} total={total} hovered={hovered} onHover={setHovered} />
        </div>
      </div>

      {/* Donut — mobile: normal flow (legend hidden) */}
      <div className="flex min-[840px]:hidden justify-center py-3">
        <DonutSvg paths={paths} hovSlice={hovSlice} total={total} hovered={hovered} onHover={setHovered} />
      </div>
    </div>
  );
}
