import { useEffect, useMemo, useState } from "react";
import { api, type PriceAggregate } from "../../api/client";
import type { IntradayWindow } from "../../lib/chartSettings";
import { Sparkline } from "../Sparkline";
import { PctBadge } from "./PctBadge";
import type { PerfRow } from "./PerfChartViews";

// Coarser span per window keeps point counts manageable for the renderer.
const WINDOW_SPAN: Record<IntradayWindow, string> = {
  "2h": "5m",
  "4h": "5m",
  "1d": "15m",
  "3d": "30m",
  "7d": "1h",
};

type IntradayEntry = {
  aggregates: PriceAggregate[] | null;
  error: boolean;
};


export function IntradayView({
  rows,
  window,
}: {
  rows: Pick<PerfRow, "id" | "ticker" | "asset_type" | "sublabel" | "current_price">[];
  window: IntradayWindow;
}) {
  const [data, setData] = useState<Record<string, IntradayEntry>>({});
  const [hoverFraction, setHoverFraction] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const rowKey = useMemo(() => rows.map((r) => r.id).join(","), [rows]);

  useEffect(() => {
    setData({});
    for (const row of rows) {
      api.getPriceHistory(row.asset_type, row.ticker, window, WINDOW_SPAN[window])
        .then((h) => {
          setData((prev) => ({ ...prev, [row.id]: { aggregates: h.aggregates, error: false } }));
        })
        .catch(() => {
          setData((prev) => ({ ...prev, [row.id]: { aggregates: null, error: true } }));
        });
    }
  }, [rowKey, window]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleHover(id: string, fraction: number | null) {
    setHoverFraction(fraction);
    setHoveredId(fraction !== null ? id : null);
  }

  return (
    <div className="border border-[#404868] rounded-md overflow-visible">
      {rows.map((row) => {
        const entry = data[row.id];
        const aggs = entry?.aggregates ?? null;

        const hoverPct = (hoverFraction !== null && aggs !== null && aggs.length >= 2)
          ? (() => {
              const idx = Math.round(hoverFraction * (aggs.length - 1));
              return ((aggs[idx].close - aggs[0].close) / aggs[0].close) * 100;
            })()
          : null;
        const rangeReturn = aggs && aggs.length > 0
          ? ((aggs[aggs.length - 1].close - aggs[0].close) / aggs[0].close) * 100
          : null;
        const displayPct = hoverPct !== null ? hoverPct : rangeReturn;

        return (
          <div
            key={row.id}
            className="flex items-center gap-3 px-3 py-2.5 border-b border-[#2a2d3a] last:border-b-0"
          >
            <div className="w-28 shrink-0">
              <div>
                <span className="font-semibold text-sm text-slate-100">{row.ticker}</span>
                <span className="hidden sm:inline ml-1.5 text-[0.65rem] text-slate-600 uppercase">{row.asset_type}</span>
              </div>
              <div className="text-xs text-slate-500 tabular-nums">{row.sublabel}</div>
            </div>
            <div className="flex-1 min-w-0 pt-3">
              {!entry?.error && aggs !== null && aggs.length >= 2 && (
                <Sparkline
                  id={`${row.id}-intraday`}
                  values={aggs.map((a) => a.close)}
                  labels={aggs.map((a) => a.timestamp)}
                  height={40}
                  hoverFraction={hoverFraction}
                  onHoverFraction={(f) => handleHover(row.id, f)}
                  showTooltip={hoveredId === row.id}
                  tooltipStyle="html"
                />
              )}
            </div>
            <div className="w-16 shrink-0 text-right">
              {entry?.error ? (
                <span className="text-slate-600 text-xs">unavailable</span>
              ) : entry === undefined ? (
                <span className="text-slate-600 text-xs">loading…</span>
              ) : (
                <PctBadge pct={displayPct} />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
