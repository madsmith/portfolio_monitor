import { Fragment, useEffect, useRef, useState } from "react";
import {
  api,
  type WatchlistDetail,
  type WatchlistEntry,
  type WatchlistSummary,
} from "../../api/client";
import { fmtChg, fmtMoney, fmtPct, plColor, prevCloseKey } from "../../lib/formatters";
import { Chart } from "../Chart";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type EnrichedEntry = WatchlistEntry & {
  dayChgPrice: number | null;
  dayChgPct: number | null;
  sinceAdded: number | null;
};

type AddEntryDraft = {
  ticker: string;
  asset_type: string;
  notes: string;
  target_buy: string;
  target_sell: string;
};

const BLANK_ADD: AddEntryDraft = { ticker: "", asset_type: "stock", notes: "", target_buy: "", target_sell: "" };
const ASSET_TYPES = ["stock", "crypto", "currency"];

function parseOptFloat(s: string): number | null {
  const v = parseFloat(s.trim());
  return Number.isFinite(v) ? v : null;
}

// ---------------------------------------------------------------------------
// WatchlistTable — view + edit mode
// ---------------------------------------------------------------------------

function WatchlistTable({
  entries,
  prevClose,
  editing,
  savingTicker,
  deletingTicker,
  onDeleteRow,
  onSaveRow,
  addDraft,
  onAddDraftChange,
  onAddEntry,
  addSaving,
}: {
  entries: WatchlistEntry[];
  prevClose: Record<string, number>;
  editing: boolean;
  savingTicker: string | null;
  deletingTicker: string | null;
  onDeleteRow: (ticker: string) => void;
  onSaveRow: (ticker: string, fields: { notes: string; target_buy: number | null; target_sell: number | null }) => Promise<void>;
  addDraft: AddEntryDraft;
  onAddDraftChange: (d: AddEntryDraft) => void;
  onAddEntry: () => void;
  addSaving: boolean;
}) {
  const [priceChgMode, setPriceChgMode] = useState<"dollar" | "percent">("percent");
  const [chartTickers, setChartTickers] = useState<Set<string>>(new Set());
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [editNotes, setEditNotes] = useState("");
  const [editBuy, setEditBuy] = useState("");
  const [editSell, setEditSell] = useState("");

  useEffect(() => {
    if (!editing) setExpandedTicker(null);
  }, [editing]);

  useEffect(() => {
    if (!expandedTicker) return;
    const entry = entries.find((e) => e.ticker === expandedTicker);
    if (entry) {
      setEditNotes(entry.notes ?? "");
      setEditBuy(entry.target_buy != null ? String(entry.target_buy) : "");
      setEditSell(entry.target_sell != null ? String(entry.target_sell) : "");
    }
  }, [expandedTicker]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleExpand(ticker: string) {
    setExpandedTicker((prev) => (prev === ticker ? null : ticker));
  }

  function toggleChart(ticker: string) {
    setChartTickers((prev) => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }

  async function handleSave(ticker: string) {
    await onSaveRow(ticker, {
      notes: editNotes,
      target_buy: parseOptFloat(editBuy),
      target_sell: parseOptFloat(editSell),
    });
    setExpandedTicker(null);
  }

  const enriched: EnrichedEntry[] = entries.map((e) => {
    const pcKey = prevCloseKey(e);
    const pc = prevClose[pcKey] ?? null;
    const price = e.current_price ?? pc;
    const dayChgPrice = e.current_price !== null && pc !== null ? e.current_price - pc : null;
    const dayChgPct = dayChgPrice !== null && pc !== null && pc !== 0 ? (dayChgPrice / pc) * 100 : null;
    const sinceAdded =
      price !== null && e.initial_price !== null && e.initial_price !== 0
        ? ((price - e.initial_price) / e.initial_price) * 100
        : null;
    return { ...e, current_price: price, dayChgPrice, dayChgPct, sinceAdded };
  });

  const COLS = editing ? 9 : 8;

  const inputCls = "bg-[#0f1117] border border-[#404868] rounded px-2 py-1 text-sm text-slate-200 focus:outline-none focus:border-slate-400";

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
              ...(editing ? [["", "text-right", ""]] : []),
            ] as [string, string, string][]
          ).map(([label, align, vis], i) => (
            <th
              key={i}
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
        {enriched.map((e) => {
          const isExpanded = expandedTicker === e.ticker;
          const isSaving = savingTicker === e.ticker;
          const isDeleting = deletingTicker === e.ticker;
          return (
            <Fragment key={e.ticker}>
              <tr className={`border-b border-[#2a2d3a] last:border-b-0 transition-colors ${isDeleting ? "opacity-40" : ""}`}>
                <td className="px-2 sm:px-3 py-2 font-semibold">
                  <button
                    onClick={() => !editing && toggleChart(e.ticker)}
                    disabled={editing}
                    className={`transition-colors ${editing ? "text-slate-100 cursor-default" : "hover:text-sky-400 cursor-pointer text-slate-100"}`}
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
                <td className="hidden lg:table-cell px-2 sm:px-3 py-2 text-right tabular-nums text-slate-400">{fmtMoney(e.target_buy)}</td>
                <td className="hidden lg:table-cell px-2 sm:px-3 py-2 text-right tabular-nums text-slate-400">{fmtMoney(e.target_sell)}</td>
                <td className="hidden xl:table-cell px-2 sm:px-3 py-2 text-slate-500 text-xs truncate max-w-[200px]">{e.notes || "—"}</td>
                {editing && (
                  <td className="px-2 py-2 text-right whitespace-nowrap">
                    <button
                      onClick={() => toggleExpand(e.ticker)}
                      disabled={isDeleting}
                      title={isExpanded ? "Close" : "Edit"}
                      className="text-slate-500 hover:text-slate-200 transition-colors cursor-pointer disabled:opacity-40 mr-3"
                    >
                      {isExpanded ? "✕" : "✏"}
                    </button>
                    <button
                      onClick={() => onDeleteRow(e.ticker)}
                      disabled={isDeleting || isSaving}
                      title="Remove"
                      className="text-slate-500 hover:text-red-400 transition-colors cursor-pointer disabled:opacity-40"
                    >
                      ✕
                    </button>
                  </td>
                )}
              </tr>

              {isExpanded && (
                <tr className="border-b border-[#2a2d3a] bg-[#151825]">
                  <td colSpan={COLS} className="px-3 py-3">
                    <div className="flex flex-wrap gap-3 items-start">
                      <label className="flex flex-col gap-1">
                        <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Notes</span>
                        <input value={editNotes} onChange={(ev) => setEditNotes(ev.target.value)}
                          className={`${inputCls} w-48`} placeholder="Optional" />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Buy target</span>
                        <input value={editBuy} onChange={(ev) => setEditBuy(ev.target.value)}
                          className={`${inputCls} w-28 tabular-nums`} placeholder="—" />
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Sell target</span>
                        <input value={editSell} onChange={(ev) => setEditSell(ev.target.value)}
                          className={`${inputCls} w-28 tabular-nums`} placeholder="—"
                          onKeyDown={(ev) => { if (ev.key === "Enter") handleSave(e.ticker); }} />
                      </label>
                      <div className="flex flex-col gap-1">
                        <span className="text-[0.65rem] invisible select-none">_</span>
                        <button onClick={() => handleSave(e.ticker)} disabled={isSaving}
                          className="px-3 py-1 bg-[#252a40] border border-[#5060a0] text-slate-100 rounded text-xs hover:bg-[#2e345a] transition-colors cursor-pointer disabled:opacity-50">
                          {isSaving ? "Saving…" : "Save"}
                        </button>
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="text-[0.65rem] invisible select-none">_</span>
                        <button onClick={() => setExpandedTicker(null)}
                          className="px-3 py-1 text-slate-400 hover:text-slate-200 text-xs transition-colors cursor-pointer">
                          Cancel
                        </button>
                      </div>
                    </div>
                  </td>
                </tr>
              )}

              {!editing && chartTickers.has(e.ticker) && (
                <tr className="border-b border-[#2a2d3a] last:border-b-0">
                  <td colSpan={8} className="px-4 py-3 bg-[#0c0f18]">
                    <Chart ticker={e.ticker} assetType={e.asset_type} />
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}

        {editing && (
          <tr className="bg-[#0f1117]">
            <td colSpan={COLS} className="px-3 py-3">
              <div className="flex flex-wrap gap-3 items-start">
                <label className="flex flex-col gap-1">
                  <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Ticker</span>
                  <input value={addDraft.ticker}
                    onChange={(ev) => onAddDraftChange({ ...addDraft, ticker: ev.target.value.toUpperCase() })}
                    onKeyDown={(ev) => { if (ev.key === "Enter" && addDraft.ticker.trim()) onAddEntry(); }}
                    className={`${inputCls} w-24 uppercase`} placeholder="AAPL" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Type</span>
                  <div className="relative">
                    <select value={addDraft.asset_type}
                      onChange={(ev) => onAddDraftChange({ ...addDraft, asset_type: ev.target.value })}
                      className={`${inputCls} appearance-none cursor-pointer pr-6 w-full`}>
                      {ASSET_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 text-[0.6rem]">▾</span>
                  </div>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Notes</span>
                  <input value={addDraft.notes}
                    onChange={(ev) => onAddDraftChange({ ...addDraft, notes: ev.target.value })}
                    className={`${inputCls} w-40`} placeholder="Optional" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Buy target</span>
                  <input value={addDraft.target_buy}
                    onChange={(ev) => onAddDraftChange({ ...addDraft, target_buy: ev.target.value })}
                    className={`${inputCls} w-24 tabular-nums`} placeholder="—" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Sell target</span>
                  <input value={addDraft.target_sell}
                    onChange={(ev) => onAddDraftChange({ ...addDraft, target_sell: ev.target.value })}
                    className={`${inputCls} w-24 tabular-nums`} placeholder="—" />
                </label>
                <div className="flex flex-col gap-1">
                  <span className="text-[0.65rem] invisible select-none">_</span>
                  <button onClick={onAddEntry} disabled={!addDraft.ticker.trim() || addSaving}
                    className="px-3 py-1.5 bg-[#252a40] border border-[#5060a0] text-slate-100 rounded text-xs hover:bg-[#2e345a] transition-colors cursor-pointer disabled:opacity-50">
                    {addSaving ? "Adding…" : "+ Add entry"}
                  </button>
                </div>
              </div>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Main WatchlistsPane
// ---------------------------------------------------------------------------

export function WatchlistsPane({ watchlists: initialWatchlists }: { watchlists: WatchlistSummary[] }) {
  const [summaries, setSummaries] = useState<WatchlistSummary[]>(initialWatchlists);
  const [selectedId, setSelectedId] = useState<string>(initialWatchlists[0]?.id ?? "");
  const [detail, setDetail] = useState<WatchlistDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prevClose, setPrevClose] = useState<Record<string, number>>({});

  // Edit mode
  const [editing, setEditing] = useState(false);
  const [savingTicker, setSavingTicker] = useState<string | null>(null);
  const [deletingTicker, setDeletingTicker] = useState<string | null>(null);
  const [addDraft, setAddDraft] = useState<AddEntryDraft>(BLANK_ADD);
  const [addSaving, setAddSaving] = useState(false);

  // New watchlist form
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [createSaving, setCreateSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const newNameRef = useRef<HTMLInputElement>(null);

  // Delete watchlist confirm
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deletingWl, setDeletingWl] = useState(false);

  // Sync summaries when Dashboard's initial prop arrives (async load)
  useEffect(() => {
    if (initialWatchlists.length > 0) {
      setSummaries((prev) => (prev.length === 0 ? initialWatchlists : prev));
      setSelectedId((prev) => prev || initialWatchlists[0].id);
    }
  }, [initialWatchlists]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset edit state when switching watchlists
  useEffect(() => {
    setEditing(false);
    setDeleteConfirm(false);
    setAddDraft(BLANK_ADD);
  }, [selectedId]);

  // Auto-focus name input when creating
  useEffect(() => {
    if (creating) newNameRef.current?.focus();
  }, [creating]);

  // Load watchlist detail
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

  // Fetch previous-close prices; re-runs when the set of entry tickers changes
  const entryKey = detail?.entries.map((e) => `${e.asset_type}:${e.ticker}`).sort().join(",") ?? "";
  useEffect(() => {
    if (!detail) { setPrevClose({}); return; }
    let active = true;
    for (const e of detail.entries) {
      api.getPreviousClose(e.asset_type, e.ticker)
        .then((data) => { if (!active) return; setPrevClose((prev) => ({ ...prev, [prevCloseKey(e)]: data.close })); })
        .catch(() => {});
    }
    return () => { active = false; };
  }, [entryKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- handlers ----

  async function handleCreateWatchlist() {
    const name = newName.trim();
    if (!name) return;
    setCreateSaving(true);
    setCreateError(null);
    try {
      const wl = await api.createWatchlist(name);
      const summary: WatchlistSummary = { id: wl.id, name: wl.name, owner: wl.owner, entry_count: 0 };
      setSummaries((prev) => [...prev, summary]);
      setSelectedId(wl.id);
      setDetail(wl);
      setCreating(false);
      setNewName("");
    } catch {
      setCreateError("Failed to create watchlist");
    } finally {
      setCreateSaving(false);
    }
  }

  async function handleDeleteWatchlist() {
    if (!selectedId) return;
    setDeletingWl(true);
    try {
      await api.deleteWatchlist(selectedId);
      const remaining = summaries.filter((s) => s.id !== selectedId);
      setSummaries(remaining);
      setSelectedId(remaining[0]?.id ?? "");
      setDetail(null);
      setEditing(false);
      setDeleteConfirm(false);
    } finally {
      setDeletingWl(false);
    }
  }

  async function handleDeleteRow(ticker: string) {
    if (!selectedId) return;
    setDeletingTicker(ticker);
    try {
      const updated = await api.removeWatchlistEntry(selectedId, ticker);
      setDetail(updated);
      setSummaries((prev) => prev.map((s) => s.id === selectedId ? { ...s, entry_count: updated.entries.length } : s));
    } finally {
      setDeletingTicker(null);
    }
  }

  async function handleSaveRow(
    ticker: string,
    fields: { notes: string; target_buy: number | null; target_sell: number | null }
  ): Promise<void> {
    if (!selectedId) return;
    setSavingTicker(ticker);
    try {
      const updated = await api.updateWatchlistEntry(selectedId, ticker, fields);
      setDetail(updated);
    } finally {
      setSavingTicker(null);
    }
  }

  async function handleAddEntry() {
    if (!selectedId || !addDraft.ticker.trim()) return;
    setAddSaving(true);
    try {
      const updated = await api.addWatchlistEntry(selectedId, {
        ticker: addDraft.ticker.trim(),
        asset_type: addDraft.asset_type,
        notes: addDraft.notes,
        target_buy: parseOptFloat(addDraft.target_buy),
        target_sell: parseOptFloat(addDraft.target_sell),
      });
      setDetail(updated);
      setSummaries((prev) => prev.map((s) => s.id === selectedId ? { ...s, entry_count: updated.entries.length } : s));
      setAddDraft(BLANK_ADD);
    } finally {
      setAddSaving(false);
    }
  }

  const btnBase = "px-3 py-1 text-xs rounded border transition-colors cursor-pointer";

  return (
    <div>
      {/* Controls bar */}
      <div className="flex items-center gap-2 flex-wrap mb-4">
        {summaries.map((wl) => (
          <button
            key={wl.id}
            onClick={() => { setSelectedId(wl.id); setCreating(false); }}
            className={[
              "px-3 py-1 text-xs font-medium rounded-full border transition-colors cursor-pointer",
              wl.id === selectedId && !creating
                ? "bg-[#252a40] border-[#5060a0] text-slate-100"
                : "bg-transparent border-[#2a2d3a] text-slate-400 hover:border-[#404868] hover:text-slate-300",
            ].join(" ")}
          >
            {wl.name}
            <span className="ml-1.5 text-slate-500">{wl.entry_count}</span>
          </button>
        ))}

        <div className="flex-1" />

        {selectedId && !creating && (
          <>
            {editing && (
              deleteConfirm ? (
                <>
                  <button onClick={handleDeleteWatchlist} disabled={deletingWl}
                    className={`${btnBase} border-red-700 text-red-400 hover:bg-red-900/30 disabled:opacity-50`}>
                    {deletingWl ? "Deleting…" : "Confirm delete"}
                  </button>
                  <button onClick={() => setDeleteConfirm(false)}
                    className="px-2 py-1 text-xs text-slate-500 hover:text-slate-300 transition-colors cursor-pointer">
                    Cancel
                  </button>
                </>
              ) : (
                <button onClick={() => setDeleteConfirm(true)}
                  className={`${btnBase} border-[#2a2d3a] text-slate-500 hover:border-red-700 hover:text-red-400`}>
                  Delete list
                </button>
              )
            )}
            <button
              onClick={() => { setEditing((e) => !e); setDeleteConfirm(false); }}
              className={[
                btnBase,
                editing
                  ? "bg-[#252a40] border-[#5060a0] text-slate-100 hover:bg-[#2e345a]"
                  : "border-[#2a2d3a] text-slate-400 hover:border-[#404868] hover:text-slate-300",
              ].join(" ")}
            >
              {editing ? "Done" : "Edit"}
            </button>
          </>
        )}

        <button
          onClick={() => { setCreating(true); setEditing(false); setSelectedId(""); }}
          className={`${btnBase} border-[#2a2d3a] text-slate-400 hover:border-[#404868] hover:text-slate-300`}
        >
          + New
        </button>
      </div>

      {/* New watchlist inline form */}
      {creating && (
        <div className="mb-4 flex items-center gap-2 flex-wrap">
          <input
            ref={newNameRef}
            value={newName}
            onChange={(ev) => setNewName(ev.target.value)}
            onKeyDown={(ev) => {
              if (ev.key === "Enter") handleCreateWatchlist();
              if (ev.key === "Escape") { setCreating(false); setNewName(""); setSelectedId(summaries[0]?.id ?? ""); }
            }}
            className="bg-[#0f1117] border border-[#404868] rounded px-3 py-1.5 text-sm text-slate-200 w-52 focus:outline-none focus:border-slate-400"
            placeholder="Watchlist name"
          />
          <button onClick={handleCreateWatchlist} disabled={!newName.trim() || createSaving}
            className="px-3 py-1.5 bg-[#252a40] border border-[#5060a0] text-slate-100 rounded text-xs hover:bg-[#2e345a] transition-colors cursor-pointer disabled:opacity-50">
            {createSaving ? "Creating…" : "Create"}
          </button>
          <button onClick={() => { setCreating(false); setNewName(""); setCreateError(null); setSelectedId(summaries[0]?.id ?? ""); }}
            className="px-3 py-1.5 text-slate-400 hover:text-slate-200 text-xs transition-colors cursor-pointer">
            Cancel
          </button>
          {createError && <span className="text-red-400 text-xs">{createError}</span>}
        </div>
      )}

      {/* Content */}
      {creating && summaries.length === 0 ? null
        : !selectedId ? (
          <p className="text-slate-500 text-sm py-2">No watchlists yet. Create one above.</p>
        ) : loading ? (
          <p className="text-slate-500 py-2 text-sm">Loading…</p>
        ) : error ? (
          <p className="text-red-400 py-2 text-sm">{error}</p>
        ) : detail && detail.entries.length === 0 && !editing ? (
          <p className="text-slate-500 text-sm py-2">No entries yet. Click Edit to add some.</p>
        ) : detail ? (
          <div className="border border-[#404868] rounded-md overflow-hidden overflow-x-auto">
            <WatchlistTable
              entries={detail.entries}
              prevClose={prevClose}
              editing={editing}
              savingTicker={savingTicker}
              deletingTicker={deletingTicker}
              onDeleteRow={handleDeleteRow}
              onSaveRow={handleSaveRow}
              addDraft={addDraft}
              onAddDraftChange={setAddDraft}
              onAddEntry={handleAddEntry}
              addSaving={addSaving}
            />
          </div>
        ) : null}
    </div>
  );
}
