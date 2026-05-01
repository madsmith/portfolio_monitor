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

const inputCls = "bg-[#0f1117] border border-[#404868] rounded px-2 py-1 text-sm text-slate-200 focus:outline-none focus:border-slate-400";

// ---------------------------------------------------------------------------
// EditableCell — table cell with click-to-edit input in edit mode
// ---------------------------------------------------------------------------

function EditableCell({
  tdClassName,
  inputClassName,
  displayClassName,
  isActive,
  editing,
  cellValue,
  onOpen,
  onChange,
  onCommit,
  onCancel,
  children,
}: {
  tdClassName: string;
  inputClassName: string;
  displayClassName: string;
  isActive: boolean;
  editing: boolean;
  cellValue: string;
  onOpen: () => void;
  onChange: (v: string) => void;
  onCommit: () => void;
  onCancel: () => void;
  children: React.ReactNode;
}) {
  return (
    <td className={tdClassName}>
      {isActive ? (
        <input
          autoFocus
          value={cellValue}
          onChange={(ev) => onChange(ev.target.value)}
          onKeyDown={(ev) => {
            if (ev.key === "Enter") onCommit();
            if (ev.key === "Escape") onCancel();
          }}
          onBlur={onCommit}
          className={`${inputCls} ${inputClassName}`}
        />
      ) : (
        <span
          onClick={editing ? onOpen : undefined}
          className={`block px-2 py-1 rounded ${editing ? "cursor-pointer hover:text-slate-100 hover:bg-[#1a1d2a] transition-colors" : ""} ${displayClassName}`}
        >
          {children}
        </span>
      )}
    </td>
  );
}

// ---------------------------------------------------------------------------
// EditRow — inline edit form shown below a row in edit mode
// ---------------------------------------------------------------------------

function EditRow({
  colSpan,
  initialNotes,
  initialBuy,
  initialSell,
  isSaving,
  onSave,
  onCancel,
}: {
  colSpan: number;
  initialNotes: string;
  initialBuy: string;
  initialSell: string;
  isSaving: boolean;
  onSave: (notes: string, buy: string, sell: string) => void;
  onCancel: () => void;
}) {
  const [notes, setNotes] = useState(initialNotes);
  const [buy, setBuy] = useState(initialBuy);
  const [sell, setSell] = useState(initialSell);

  return (
    <tr className="border-b border-[#2a2d3a] bg-[#151825]">
      <td colSpan={colSpan} className="px-3 py-3">
        <div className="flex flex-wrap gap-3 items-start">
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Notes</span>
            <input
              value={notes}
              onChange={(ev) => setNotes(ev.target.value)}
              className={`${inputCls} w-48`}
              placeholder="Optional"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Buy target</span>
            <input
              value={buy}
              onChange={(ev) => setBuy(ev.target.value)}
              className={`${inputCls} w-28 tabular-nums`}
              placeholder="—"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Sell target</span>
            <input
              value={sell}
              onChange={(ev) => setSell(ev.target.value)}
              className={`${inputCls} w-28 tabular-nums`}
              placeholder="—"
              onKeyDown={(ev) => {
                if (ev.key === "Enter") onSave(notes, buy, sell);
              }}
            />
          </label>
          <div className="flex flex-col gap-1">
            <span className="text-[0.65rem] invisible select-none">_</span>
            <button
              onClick={() => onSave(notes, buy, sell)}
              disabled={isSaving}
              className="px-3 py-1 bg-[#252a40] border border-[#5060a0] text-slate-100 rounded text-xs hover:bg-[#2e345a] transition-colors cursor-pointer disabled:opacity-50"
            >
              {isSaving ? "Saving…" : "Save"}
            </button>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[0.65rem] invisible select-none">_</span>
            <button
              onClick={onCancel}
              className="px-3 py-1 text-slate-400 hover:text-slate-200 text-xs transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// AddEntryRow — inline form at the bottom of the table for adding a new entry
// ---------------------------------------------------------------------------

function AddEntryRow({
  colSpan,
  draft,
  onDraftChange,
  onAdd,
  saving,
}: {
  colSpan: number;
  draft: AddEntryDraft;
  onDraftChange: (d: AddEntryDraft) => void;
  onAdd: () => void;
  saving: boolean;
}) {
  return (
    <tr className="bg-[#0f1117]">
      <td colSpan={colSpan} className="px-3 py-3">
        <div className="flex flex-wrap gap-3 items-start">
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Ticker</span>
            <input
              value={draft.ticker}
              onChange={(ev) => onDraftChange({ ...draft, ticker: ev.target.value.toUpperCase() })}
              onKeyDown={(ev) => {
                if (ev.key === "Enter" && draft.ticker.trim()) onAdd();
              }}
              className={`${inputCls} w-24 uppercase`}
              placeholder="AAPL"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Type</span>
            <div className="relative">
              <select
                value={draft.asset_type}
                onChange={(ev) => onDraftChange({ ...draft, asset_type: ev.target.value })}
                className={`${inputCls} appearance-none cursor-pointer pr-6 w-full`}
              >
                {ASSET_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 text-[0.6rem]">▾</span>
            </div>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Notes</span>
            <input
              value={draft.notes}
              onChange={(ev) => onDraftChange({ ...draft, notes: ev.target.value })}
              className={`${inputCls} w-40`}
              placeholder="Optional"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Buy target</span>
            <input
              value={draft.target_buy}
              onChange={(ev) => onDraftChange({ ...draft, target_buy: ev.target.value })}
              className={`${inputCls} w-24 tabular-nums`}
              placeholder="—"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">Sell target</span>
            <input
              value={draft.target_sell}
              onChange={(ev) => onDraftChange({ ...draft, target_sell: ev.target.value })}
              className={`${inputCls} w-24 tabular-nums`}
              placeholder="—"
            />
          </label>
          <div className="flex flex-col gap-1">
            <span className="text-[0.65rem] invisible select-none">_</span>
            <button
              onClick={onAdd}
              disabled={!draft.ticker.trim() || saving}
              className="px-3 py-1.5 bg-[#252a40] border border-[#5060a0] text-slate-100 rounded text-xs hover:bg-[#2e345a] transition-colors cursor-pointer disabled:opacity-50"
            >
              {saving ? "Adding…" : "+ Add entry"}
            </button>
          </div>
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// WatchlistRow — a single data row (view + inline-edit cells + action buttons)
// ---------------------------------------------------------------------------

type CellField = "notes" | "target_buy" | "target_sell";

function WatchlistRow({
  entry,
  editing,
  priceChgMode,
  isDeleting,
  isSaving,
  isExpanded,
  editingCell,
  cellValue,
  onCellChange,
  onOpenCell,
  onCommitCell,
  onCancelCell,
  onToggleExpand,
  onToggleChart,
  onDelete,
}: {
  entry: EnrichedEntry;
  editing: boolean;
  priceChgMode: "dollar" | "percent";
  isDeleting: boolean;
  isSaving: boolean;
  isExpanded: boolean;
  editingCell: { ticker: string; field: CellField } | null;
  cellValue: string;
  onCellChange: (v: string) => void;
  onOpenCell: (field: CellField, raw: string) => void;
  onCommitCell: (field: CellField, value: string) => void;
  onCancelCell: () => void;
  onToggleExpand: () => void;
  onToggleChart: () => void;
  onDelete: () => void;
}) {
  const e = entry;
  const activeField = editingCell?.ticker === e.ticker ? editingCell.field : null;

  return (
    <tr className={`border-b border-[#2a2d3a] last:border-b-0 transition-colors ${isDeleting ? "opacity-40" : ""}`}>
      <td className="px-2 sm:px-3 py-2 font-semibold">
        <button
          onClick={() => !editing && onToggleChart()}
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
      <EditableCell
        tdClassName="hidden lg:table-cell px-1 py-1"
        inputClassName="w-20 tabular-nums text-right"
        displayClassName="text-right tabular-nums text-slate-400"
        isActive={activeField === "target_buy"}
        editing={editing}
        cellValue={cellValue}
        onChange={onCellChange}
        onOpen={() => onOpenCell("target_buy", e.target_buy != null ? String(e.target_buy) : "")}
        onCommit={() => onCommitCell("target_buy", cellValue)}
        onCancel={onCancelCell}
      >
        {fmtMoney(e.target_buy)}
      </EditableCell>
      <EditableCell
        tdClassName="hidden lg:table-cell px-1 py-1"
        inputClassName="w-20 tabular-nums text-right"
        displayClassName="text-right tabular-nums text-slate-400"
        isActive={activeField === "target_sell"}
        editing={editing}
        cellValue={cellValue}
        onChange={onCellChange}
        onOpen={() => onOpenCell("target_sell", e.target_sell != null ? String(e.target_sell) : "")}
        onCommit={() => onCommitCell("target_sell", cellValue)}
        onCancel={onCancelCell}
      >
        {fmtMoney(e.target_sell)}
      </EditableCell>
      <EditableCell
        tdClassName="hidden xl:table-cell px-1 py-1 max-w-[200px]"
        inputClassName="w-40"
        displayClassName="text-xs truncate text-slate-500"
        isActive={activeField === "notes"}
        editing={editing}
        cellValue={cellValue}
        onChange={onCellChange}
        onOpen={() => onOpenCell("notes", e.notes ?? "")}
        onCommit={() => onCommitCell("notes", cellValue)}
        onCancel={onCancelCell}
      >
        {e.notes || "—"}
      </EditableCell>
      {editing && (
        <td className="px-2 py-2 text-right whitespace-nowrap">
          <button
            onClick={onToggleExpand}
            disabled={isDeleting}
            title={isExpanded ? "Close" : "Edit"}
            className="text-slate-500 hover:text-slate-200 transition-colors cursor-pointer disabled:opacity-40 mr-3"
          >
            {isExpanded ? "✕" : "✏"}
          </button>
          <button
            onClick={onDelete}
            disabled={isDeleting || isSaving}
            title="Remove"
            className="text-slate-500 hover:text-red-400 transition-colors cursor-pointer disabled:opacity-40"
          >
            ✕
          </button>
        </td>
      )}
    </tr>
  );
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
  onSaveRow: (ticker: string, fields: { notes?: string; target_buy?: number | null; target_sell?: number | null }) => Promise<void>;
  addDraft: AddEntryDraft;
  onAddDraftChange: (d: AddEntryDraft) => void;
  onAddEntry: () => void;
  addSaving: boolean;
}) {
  const [priceChgMode, setPriceChgMode] = useState<"dollar" | "percent">("percent");
  const [chartTickers, setChartTickers] = useState<Set<string>>(new Set());
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);

  // Inline cell editing
  const [editingCell, setEditingCell] = useState<{ ticker: string; field: "notes" | "target_buy" | "target_sell" } | null>(null);
  const [cellValue, setCellValue] = useState("");
  const cellSavedRef = useRef(false);
  const origCellValueRef = useRef("");

  useEffect(() => {
    if (!editing) {
      setExpandedTicker(null);
      setEditingCell(null);
    }
  }, [editing]);

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

  async function handleSave(ticker: string, notes: string, buy: string, sell: string) {
    await onSaveRow(ticker, {
      notes,
      target_buy: parseOptFloat(buy),
      target_sell: parseOptFloat(sell),
    });
    setExpandedTicker(null);
  }

  function openCell(ticker: string, field: "notes" | "target_buy" | "target_sell", raw: string) {
    cellSavedRef.current = false;
    origCellValueRef.current = raw;
    
    setCellValue(raw);
    setEditingCell({ ticker, field });
  }

  async function commitCell(ticker: string, field: "notes" | "target_buy" | "target_sell", value: string) {
    if (cellSavedRef.current) return;
    cellSavedRef.current = true;
    setEditingCell(null);

    if (value !== origCellValueRef.current) {
      const fields: { notes?: string; target_buy?: number | null; target_sell?: number | null } = {};
      if (field === "notes") fields.notes = value;
      else if (field === "target_buy") fields.target_buy = parseOptFloat(value);
      else if (field === "target_sell") fields.target_sell = parseOptFloat(value);
      await onSaveRow(ticker, fields);
    }
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
              <WatchlistRow
                entry={e}
                editing={editing}
                priceChgMode={priceChgMode}
                isDeleting={isDeleting}
                isSaving={isSaving}
                isExpanded={isExpanded}
                editingCell={editingCell}
                cellValue={cellValue}
                onCellChange={setCellValue}
                onOpenCell={(field, raw) => openCell(e.ticker, field, raw)}
                onCommitCell={(field, value) => commitCell(e.ticker, field, value)}
                onCancelCell={() => { cellSavedRef.current = true; setEditingCell(null); }}
                onToggleExpand={() => toggleExpand(e.ticker)}
                onToggleChart={() => toggleChart(e.ticker)}
                onDelete={() => onDeleteRow(e.ticker)}
              />

              {isExpanded && (
                <EditRow
                  colSpan={COLS}
                  initialNotes={e.notes ?? ""}
                  initialBuy={e.target_buy != null ? String(e.target_buy) : ""}
                  initialSell={e.target_sell != null ? String(e.target_sell) : ""}
                  isSaving={isSaving}
                  onSave={(notes, buy, sell) => handleSave(e.ticker, notes, buy, sell)}
                  onCancel={() => setExpandedTicker(null)}
                />
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
          <AddEntryRow
            colSpan={COLS}
            draft={addDraft}
            onDraftChange={onAddDraftChange}
            onAdd={onAddEntry}
            saving={addSaving}
          />
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
    fields: { notes?: string; target_buy?: number | null; target_sell?: number | null }
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
            onClick={() => {
            setSelectedId(wl.id);
            setCreating(false);
          }}
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
              onClick={() => {
                setEditing((e) => !e);
                setDeleteConfirm(false);
              }}
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
          onClick={() => {
            setCreating(true);
            setEditing(false);
            setSelectedId("");
          }}
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
              if (ev.key === "Escape") {
                setCreating(false);
                setNewName("");
                setSelectedId(summaries[0]?.id ?? "");
              }
            }}
            className="bg-[#0f1117] border border-[#404868] rounded px-3 py-1.5 text-sm text-slate-200 w-52 focus:outline-none focus:border-slate-400"
            placeholder="Watchlist name"
          />
          <button onClick={handleCreateWatchlist} disabled={!newName.trim() || createSaving}
            className="px-3 py-1.5 bg-[#252a40] border border-[#5060a0] text-slate-100 rounded text-xs hover:bg-[#2e345a] transition-colors cursor-pointer disabled:opacity-50">
            {createSaving ? "Creating…" : "Create"}
          </button>
          <button onClick={() => {
            setCreating(false);
            setNewName("");
            setCreateError(null);
            setSelectedId(summaries[0]?.id ?? "");
          }}
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
