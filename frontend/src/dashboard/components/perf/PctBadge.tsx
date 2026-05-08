import { fmtPct } from "../../lib/formatters";

export function PctBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-slate-600 text-xs">—</span>;
  const positive = pct > 0;
  const zero = pct === 0;
  const text = zero ? "text-slate-400" : positive ? "text-[#3fb950]" : "text-[#f85149]";
  return (
    <span className={`inline-block ${text} rounded px-1.5 py-0.5 text-xs tabular-nums font-medium`}>
      {fmtPct(pct)}
    </span>
  );
}

export function PerfCell({ pct }: { pct: number | null }) {
  return (
    <td className={pct === null ? "px-1.5 py-2 text-right" : "px-1.5 py-1.5 text-right"}>
      <PctBadge pct={pct} />
    </td>
  );
}
