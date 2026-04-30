import { Fragment, useEffect, useState } from "react";
import { api, type WatchlistDetail, type WatchlistEntry, type WatchlistSummary } from "../../api/client";
import { fmtChg, fmtMoney, fmtPct, plColor, prevCloseKey } from "../../lib/formatters";
import { Chart } from "../Chart";

// ---------------------------------------------------------------------------
// Entry table
// ---------------------------------------------------------------------------

type EnrichedEntry = WatchlistEntry & {
  dayChgPrice: number | null;
  dayChgPct: number | null;
  sinceAdded: number | null;
};

function WatchlistTable({
  entries,
  prevClose,
}: {
  entries: WatchlistEntry[];
  prevClose: Record<string, number>;
}) {
  const [priceChgMode, setPriceChgMode] = useState<"dollar" | "percent">("percent");
  const [chartTickers, setChartTickers] = useState<Set<string>>(new Set());

  function toggleChart(ticker: string) {
    setChartTickers((prev) => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }

  const enriched: EnrichedEntry[] = entries.map((e) => {
    const pcKey = prevCloseKey(e);
    const pc = prevClose[pcKey] ?? null;
    // Fall back to previous close when no live price is available (market closed / not yet primed)
    const price = e.current_price ?? pc;
    const dayChgPrice = e.current_price !== null && pc !== null ? e.current_price - pc : null;
    const dayChgPct = dayChgPrice !== null && pc !== null && pc !== 0 ? (dayChgPrice / pc) * 100 : null;
    const sinceAdded =
      price !== null && e.initial_price !== null && e.initial_price !== 0
        ? ((price - e.initial_price) / e.initial_price) * 100
        : null;
    return { ...e, current_price: price, dayChgPrice, dayChgPct, sinceAdded };
  });

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr>
          {(
            [
              ["Ticker",      "text-left",  ""],
              ["Type",        "text-left",  "hidden sm:table-cell"],
              ["Price",       "text-right", ""],
              ["Day Chg",     "text-right", ""],
              ["Since Added", "text-right", "hidden md:table-cell"],
              ["Buy",         "text-right", "hidden lg:table-cell"],
              ["Sell",        "text-right", "hidden lg:table-cell"],
              ["Notes",       "text-left",  "hidden xl:table-cell"],
            ] as [string, string, string][]
          ).map(([label, align, vis]) => (
            <th
              key={label}
              className={`${align} ${vis} text-[0.7rem] uppercase tracking-wide text-slate-500 font-semibold px-2 sm:px-3 py-2 border-b border-[#404868]`}
            >
              {label === "Day Chg" ? (
                <span className="inline-flex items-center justify-end">
                  Day Chg
                  <span
                    onClick={() => setPriceChgMode((m) => (m === "dollar" ? "percent" : "dollar"))}
                    className="ml-1 px-1 rounded bg-[#2a2d3a] text-slate-400 hover:text-slate-100 hover:bg-[#404868] cursor-pointer transition-colors normal-case tracking-normal font-normal"
                  >
                    {priceChgMode === "dollar" ? "$" : "%"}
                  </span>
                </span>
              ) : label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {enriched.map((e) => (
          <Fragment key={e.ticker}>
            <tr className="border-b border-[#2a2d3a] last:border-b-0 transition-colors">
              <td className="px-2 sm:px-3 py-2 font-semibold">
                <button
                  onClick={() => toggleChart(e.ticker)}
                  className="hover:text-sky-400 transition-colors cursor-pointer text-slate-100"
                >
                  {e.ticker}
                </button>
              </td>
              <td className="hidden sm:table-cell px-2 sm:px-3 py-2 text-slate-500 text-xs">{e.asset_type}</td>
              <td className="px-2 sm:px-3 py-2 text-right tabular-nums text-slate-300">{fmtMoney(e.current_price)}</td>
              <td className={`px-2 sm:px-3 py-2 text-right tabular-nums ${plColor(e.dayChgPrice)}`}>
                {priceChgMode === "dollar" ? fmtChg(e.dayChgPrice) : fmtPct(e.dayChgPct)}
              </td>
              <td className={`hidden md:table-cell px-2 sm:px-3 py-2 text-right tabular-nums ${plColor(e.sinceAdded)}`}>
                {fmtPct(e.sinceAdded)}
              </td>
              <td className="hidden lg:table-cell px-2 sm:px-3 py-2 text-right tabular-nums text-slate-400">
                {fmtMoney(e.target_buy)}
              </td>
              <td className="hidden lg:table-cell px-2 sm:px-3 py-2 text-right tabular-nums text-slate-400">
                {fmtMoney(e.target_sell)}
              </td>
              <td className="hidden xl:table-cell px-2 sm:px-3 py-2 text-slate-500 text-xs truncate max-w-[200px]">
                {e.notes || "—"}
              </td>
            </tr>
            {chartTickers.has(e.ticker) && (
              <tr className="border-b border-[#2a2d3a] last:border-b-0">
                <td colSpan={8} className="px-4 py-3 bg-[#0c0f18]">
                  <Chart ticker={e.ticker} assetType={e.asset_type} />
                </td>
              </tr>
            )}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Watchlist selector (shown when > 1 watchlist)
// ---------------------------------------------------------------------------

function WatchlistSelector({
  watchlists,
  selectedId,
  onSelect,
}: {
  watchlists: WatchlistSummary[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="flex gap-2 flex-wrap mb-4">
      {watchlists.map((wl) => (
        <button
          key={wl.id}
          onClick={() => onSelect(wl.id)}
          className={[
            "px-3 py-1 text-xs font-medium rounded-full border transition-colors cursor-pointer",
            wl.id === selectedId
              ? "bg-[#252a40] border-[#5060a0] text-slate-100"
              : "bg-transparent border-[#2a2d3a] text-slate-400 hover:border-[#404868] hover:text-slate-300",
          ].join(" ")}
        >
          {wl.name}
          <span className="ml-1.5 text-slate-500">{wl.entry_count}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main WatchlistView
// ---------------------------------------------------------------------------

export function WatchlistsPane({ watchlists }: { watchlists: WatchlistSummary[] }) {
  const [selectedId, setSelectedId] = useState<string>(watchlists[0]?.id ?? "");

  // When watchlists load after a hard refresh, selectedId may be "" — sync it.
  useEffect(() => {
    if (!selectedId && watchlists.length > 0) {
      setSelectedId(watchlists[0].id);
    }
  }, [watchlists]); // eslint-disable-line react-hooks/exhaustive-deps
  const [detail, setDetail] = useState<WatchlistDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prevClose, setPrevClose] = useState<Record<string, number>>({});

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    setLoading(true);
    setError(null);
    api.getWatchlist(selectedId)
      .then((d) => { if (active) setDetail(d); })
      .catch(() => { if (active) setError("Failed to load watchlist"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedId]);

  // Fetch previous-close prices incrementally — update state as each resolves
  // so prices populate one-by-one rather than all at once after a batch wait.
  useEffect(() => {
    if (!detail) { setPrevClose({}); return; }
    let active = true;
    setPrevClose({});
    for (const e of detail.entries) {
      api.getPreviousClose(e.asset_type, e.ticker)
        .then((data) => {
          if (!active) return;
          setPrevClose((prev) => ({ ...prev, [prevCloseKey(e)]: data.close }));
        })
        .catch(() => {});
    }
    return () => { active = false; };
  }, [detail?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      {watchlists.length > 1 && (
        <WatchlistSelector
          watchlists={watchlists}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      )}
      {loading ? (
        <p className="text-slate-500 py-2 text-sm">Loading…</p>
      ) : error ? (
        <p className="text-red-400 py-2 text-sm">{error}</p>
      ) : detail && detail.entries.length === 0 ? (
        <p className="text-slate-500 text-sm py-2">No entries in this watchlist.</p>
      ) : detail ? (
        <div className="border border-[#404868] rounded-md overflow-hidden">
          <WatchlistTable entries={detail.entries} prevClose={prevClose} />
        </div>
      ) : null}
    </div>
  );
}
