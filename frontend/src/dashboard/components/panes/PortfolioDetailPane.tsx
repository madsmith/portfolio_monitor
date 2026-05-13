import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, getRole, getUsername, type Asset, type Lot, type LotInput, type PortfolioDetail, type PortfolioUserPermission, type PortfolioUsers } from "../../api/client";
import { fmtMoney, fmtPrice, fmtPct, fmtQty, fmtDate, fmtChg, plColor, lotPlColor, prevCloseKey, computeTodayChange } from "../../lib/formatters";
import { DataTable, type ColDef } from "../DataTable";
import { Chart } from "../Chart";
import { AssetMenu } from "../AssetMenu";
import { Button } from "../buttons/Button";

// ---------------------------------------------------------------------------
// Portfolio users section (admin-only, shown in edit mode)
// ---------------------------------------------------------------------------

function PortfolioUsersSection({ portfolioId }: { portfolioId: string }) {
  const [data, setData] = useState<PortfolioUsers | null>(null);
  const [accounts, setAccounts] = useState<{ username: string }[]>([]);
  const [draft, setDraft] = useState<Record<string, PortfolioUserPermission>>({});
  const [addUsername, setAddUsername] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getPortfolioUsers(portfolioId).then(d => {
      setData(d);
      setDraft(d.permissions);
    });
    api.getUsers().then(setAccounts);
  }, [portfolioId]);

  const available = accounts.filter(a => a.username !== data?.owner && !(a.username in draft));

  const handleAdd = useCallback(() => {
    if (!addUsername) return;
    setDraft(prev => ({ ...prev, [addUsername]: { read: true, write: false } }));
    setAddUsername("");
    setSaved(false);
  }, [addUsername]);

  const handleRemove = useCallback((username: string) => {
    setDraft(prev => { const next = { ...prev }; delete next[username]; return next; });
    setSaved(false);
  }, []);

  const handleToggle = useCallback((username: string, flag: "read" | "write") => {
    setDraft(prev => ({ ...prev, [username]: { ...prev[username], [flag]: !prev[username][flag] } }));
    setSaved(false);
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await api.updatePortfolioUsers(portfolioId, draft);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }, [portfolioId, draft]);

  if (!data) return null;

  const users = Object.entries(draft);

  return (
    <div className="mt-5 border border-[#404868] rounded-md overflow-hidden">
      <div className="px-3 py-2 bg-[#131928] border-b border-[#404868] flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-slate-400 font-medium">Users</span>
        <button
          onClick={handleSave}
          disabled={saving}
          className="text-xs px-2 py-0.5 rounded border border-[#5060a0] bg-[#252a40] text-slate-100 hover:bg-[#2e345a] transition-colors disabled:opacity-50 cursor-pointer"
        >
          {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
        </button>
      </div>

      <div className="divide-y divide-[#2a2d3a]">
        <div className="px-3 py-2 flex items-center gap-3 text-xs text-slate-400">
          <span className="w-36 truncate font-medium text-slate-300">{data.owner}</span>
          <span className="text-slate-500 italic">owner</span>
        </div>

        {users.map(([username, perm]) => (
          <div key={username} className="px-3 py-2 flex items-center gap-3 text-xs">
            <span className="w-36 truncate text-slate-300">{username}</span>
            <label className="flex items-center gap-1 text-slate-400 cursor-pointer select-none">
              <input type="checkbox" checked={perm.read} onChange={() => handleToggle(username, "read")} className="accent-sky-500" />
              Read
            </label>
            <label className="flex items-center gap-1 text-slate-400 cursor-pointer select-none">
              <input type="checkbox" checked={perm.write} onChange={() => handleToggle(username, "write")} className="accent-sky-500" />
              Write
            </label>
            <button
              onClick={() => handleRemove(username)}
              className="ml-auto text-slate-600 hover:text-red-400 transition-colors cursor-pointer"
              title="Remove"
            >✕</button>
          </div>
        ))}

        {available.length > 0 && (
          <div className="px-3 py-2 flex items-center gap-2">
            <select
              value={addUsername}
              onChange={e => setAddUsername(e.target.value)}
              className="text-xs bg-[#1a1f2e] border border-[#404868] rounded px-2 py-1 text-slate-300 focus:outline-none focus:border-[#5060a0]"
            >
              <option value="">Add user…</option>
              {available.map(a => <option key={a.username} value={a.username}>{a.username}</option>)}
            </select>
            <button
              onClick={handleAdd}
              disabled={!addUsername}
              className="text-xs px-2 py-1 rounded border border-[#404868] bg-transparent text-slate-400 hover:border-[#5060a0] hover:text-slate-200 transition-colors disabled:opacity-40 cursor-pointer"
            >
              Add
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edit-mode helpers
// ---------------------------------------------------------------------------

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
}

type LotDraft = { quantity: string; price: string; date: string; fees: string };
const BLANK_LOT: LotDraft = { quantity: "", price: "", date: "", fees: "" };

function lotDraftToInput(d: LotDraft): LotInput {
  const input: LotInput = { quantity: d.quantity, price: parseFloat(d.price) };
  if (d.date.trim()) input.date = d.date.trim();
  const fees = parseFloat(d.fees);
  if (d.fees.trim() && !isNaN(fees) && fees > 0) input.fees = fees;
  return input;
}

function lotToEditDraft(lot: Lot): LotDraft {
  return {
    quantity: lot.quantity,
    price: lot.price != null ? String(lot.price) : "",
    date: lot.date ? lot.date.slice(0, 10).replace(/-/g, "/") : "",
    fees: lot.fees != null ? String(lot.fees) : "",
  };
}

// ---------------------------------------------------------------------------
// LotForm — inline form used for both add and edit
// ---------------------------------------------------------------------------

function LotForm({ draft, onChange, onSave, onCancel, saving, colSpan }: {
  draft: LotDraft;
  onChange: (d: LotDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  colSpan: number;
}) {
  const [dateTouched, setDateTouched] = useState(false);
  const today = todayStr();
  const ic = "bg-[#0f1117] border border-[#404868] rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-slate-400";
  const canSave = draft.quantity.trim() !== "" && draft.price.trim() !== "" && !isNaN(parseFloat(draft.price));
  const fields: { key: keyof LotDraft; label: string; ph: string; w: string; onFocus?: () => void }[] = [
    { key: "quantity", label: "Qty *",   ph: "10.5",   w: "w-24" },
    { key: "price",    label: "Price *", ph: "150.00", w: "w-28" },
    { key: "date",     label: "Date",    ph: today,    w: "w-28",
      onFocus: () => { if (!dateTouched) { setDateTouched(true); if (!draft.date) onChange({ ...draft, date: today }); } } },
    { key: "fees",     label: "Fees",    ph: "0.00",   w: "w-20" },
  ];
  return (
    <tr className="bg-[#0a0c14] border-b border-[#222536]">
      <td colSpan={colSpan} className="pl-4 sm:pl-8 pr-3 py-2">
        <div className="flex flex-wrap gap-2 items-end">
          {fields.map(({ key, label, ph, w, onFocus }) => (
            <div key={key} className="flex flex-col gap-1">
              <label className="text-[0.6rem] uppercase tracking-wide text-slate-500">{label}</label>
              <input
                value={draft[key]}
                onChange={(e) => onChange({ ...draft, [key]: e.target.value })}
                onFocus={onFocus}
                className={`${ic} ${w}`}
                placeholder={ph}
              />
            </div>
          ))}
          <div className="flex items-end gap-1.5 pb-0.5">
            <button
              onClick={onSave}
              disabled={saving || !canSave}
              className="px-2.5 py-1 text-xs rounded bg-[#2d4a3e] text-[#6bc98a] hover:bg-[#3a5e50] disabled:opacity-40 transition-colors cursor-pointer"
            >
              {saving ? "…" : "Save"}
            </button>
            <button
              onClick={onCancel}
              disabled={saving}
              className="px-2.5 py-1 text-xs rounded bg-[#2a2f45] text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
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
// LotTable
// ---------------------------------------------------------------------------

function LotTable({ lots, currentPrice, assetType, ticker, editing, portfolioId, onMutated }: {
  lots: Lot[];
  currentPrice: number | null;
  assetType: string;
  ticker: string;
  editing?: boolean;
  portfolioId?: string;
  onMutated?: (updated: PortfolioDetail) => void;
}) {
  const [editLotIdx, setEditLotIdx] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<LotDraft>(BLANK_LOT);
  const [deletingIdx, setDeletingIdx] = useState<number | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [addDraft, setAddDraft] = useState<LotDraft>(BLANK_LOT);
  const [addSaving, setAddSaving] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [opError, setOpError] = useState<string | null>(null);

  const colCount = editing ? 7 : 6;

  async function handleSaveAdd() {
    if (!portfolioId || !onMutated) return;
    setAddSaving(true); setOpError(null);
    try {
      onMutated(await api.addPortfolioLot(portfolioId, assetType, ticker, lotDraftToInput(addDraft)));
      setAddDraft(BLANK_LOT); setShowAdd(false);
    } catch { setOpError("Failed to add lot"); }
    finally { setAddSaving(false); }
  }

  async function handleSaveEdit(lotIdx: number) {
    if (!portfolioId || !onMutated) return;
    setEditSaving(true); setOpError(null);
    try {
      onMutated(await api.updatePortfolioLot(portfolioId, assetType, ticker, lotIdx, lotDraftToInput(editDraft)));
      setEditLotIdx(null);
    } catch { setOpError("Failed to update lot"); }
    finally { setEditSaving(false); }
  }

  async function handleDeleteLot(lotIdx: number) {
    if (!portfolioId || !onMutated) return;
    setDeletingIdx(lotIdx); setOpError(null);
    try {
      onMutated(await api.deletePortfolioLot(portfolioId, assetType, ticker, lotIdx));
    } catch { setOpError("Failed to delete lot"); }
    finally { setDeletingIdx(null); }
  }

  const iconBtn = "text-slate-500 hover:text-slate-200 transition-colors cursor-pointer px-1 leading-none";
  const headers: [string, string, string][] = [
    ["Date",       "text-left",  ""],
    ["Qty",        "text-right", "hidden sm:table-cell"],
    ["Price",      "text-right", ""],
    ["Cost Basis", "text-right", "hidden sm:table-cell"],
    ["P&L",        "text-right", "hidden md:table-cell"],
    ["Fees",       "text-right", "hidden md:table-cell"],
    ...(editing ? [["", "text-right", ""] as [string, string, string]] : []),
  ];

  return (
    <table className="w-full text-xs border-collapse">
      <thead>
        <tr>
          {headers.map(([label, align, vis], i) => (
            <th key={i} className={`${align} ${vis} text-[0.65rem] uppercase tracking-wide text-slate-600 font-semibold px-1 sm:px-1.5 py-1.5 border-b border-[#2a2d3a]`}>
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {lots.map((lot) => {
          const lotIdx = lot.lot_idx;
          const lotPL = currentPrice !== null && lot.cost_basis !== null ? currentPrice * parseFloat(lot.quantity) - lot.cost_basis : null;
          const priceGain = currentPrice !== null && lot.price !== null ? currentPrice - lot.price : null;

          if (editing && editLotIdx === lotIdx) {
            return (
              <LotForm
                key={lotIdx}
                draft={editDraft}
                onChange={setEditDraft}
                onSave={() => handleSaveEdit(lotIdx)}
                onCancel={() => setEditLotIdx(null)}
                saving={editSaving}
                colSpan={colCount}
              />
            );
          }

          return (
            <tr key={lotIdx} className="border-b border-[#222536] last:border-b-0">
              <td className="pl-4 sm:pl-8 pr-2 sm:pr-3 py-1.5 text-slate-500">{fmtDate(lot.date)}</td>
              <td className="hidden sm:table-cell px-1 sm:px-1.5 py-1.5 text-right tabular-nums text-slate-500">{fmtQty(lot.quantity)}</td>
              <td className={`px-1 sm:px-1.5 py-1.5 text-right tabular-nums ${lotPlColor(priceGain)}`}>{fmtPrice(lot.price, assetType, ticker)}</td>
              <td className="hidden sm:table-cell px-1 sm:px-1.5 py-1.5 text-right tabular-nums text-slate-500">{fmtMoney(lot.cost_basis)}</td>
              <td className={`hidden md:table-cell px-1 sm:px-1.5 py-1.5 text-right tabular-nums ${lotPlColor(lotPL)}`}>{fmtMoney(lotPL)}</td>
              <td className="hidden md:table-cell px-1 sm:px-1.5 py-1.5 text-right tabular-nums text-slate-500">{fmtMoney(lot.fees)}</td>
              {editing && (
                <td className="pr-1 sm:pr-1.5 py-1.5 text-right whitespace-nowrap">
                  <button
                    onClick={() => { setEditLotIdx(lotIdx); setEditDraft(lotToEditDraft(lot)); setShowAdd(false); }}
                    title="Edit lot"
                    className={iconBtn}
                  >
                    ✎
                  </button>
                  <button
                    onClick={() => handleDeleteLot(lotIdx)}
                    disabled={deletingIdx === lotIdx}
                    title="Delete lot"
                    className={`${iconBtn} hover:text-red-400 disabled:opacity-40`}
                  >
                    {deletingIdx === lotIdx ? "…" : "×"}
                  </button>
                </td>
              )}
            </tr>
          );
        })}
        {editing && showAdd && (
          <LotForm
            draft={addDraft}
            onChange={setAddDraft}
            onSave={handleSaveAdd}
            onCancel={() => { setShowAdd(false); setAddDraft(BLANK_LOT); }}
            saving={addSaving}
            colSpan={colCount}
          />
        )}
        {editing && !showAdd && (
          <tr>
            <td colSpan={colCount} className="pl-4 sm:pl-8 py-1.5">
              <button
                onClick={() => { setShowAdd(true); setEditLotIdx(null); }}
                className="text-xs text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
              >
                + Add lot
              </button>
            </td>
          </tr>
        )}
        {opError && (
          <tr>
            <td colSpan={colCount} className="px-4 py-1 text-xs text-red-400">{opError}</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// AddAssetForm — add a new ticker with its first lot
// ---------------------------------------------------------------------------

function AddAssetForm({ assetType, portfolioId, onMutated, onCancel }: {
  assetType: string;
  portfolioId: string;
  onMutated: (updated: PortfolioDetail) => void;
  onCancel: () => void;
}) {
  const isCurrency = assetType === "currency";
  const [ticker, setTicker] = useState(isCurrency ? "USD" : "");
  const [draft, setDraft] = useState<LotDraft>(isCurrency ? { ...BLANK_LOT, price: "1" } : BLANK_LOT);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dateTouched, setDateTouched] = useState(false);
  const [priceFetching, setPriceFetching] = useState(false);
  const today = todayStr();

  async function fetchCurrencyPrice(code: string) {
    if (!isCurrency || code === "USD") return;
    setPriceFetching(true);
    try {
      const result = await api.getCurrentPrice("currency", code);
      setDraft((d) => ({ ...d, price: result.price.toString() }));
    } catch { /* leave price as-is if fetch fails */ }
    finally { setPriceFetching(false); }
  }

  const ic = "bg-[#0a0c14] border border-[#404868] rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-slate-400";
  const canSave = ticker.trim() !== "" && draft.quantity.trim() !== "" && draft.price.trim() !== "" && !isNaN(parseFloat(draft.price));

  async function handleSave() {
    if (!canSave) return;
    setSaving(true); setError(null);
    try {
      onMutated(await api.addPortfolioLot(portfolioId, assetType, ticker.trim().toUpperCase(), lotDraftToInput(draft)));
    } catch { setError("Failed to add asset"); }
    finally { setSaving(false); }
  }

  const fields: { key: keyof LotDraft; label: string; ph: string; w: string; onFocus?: () => void; readOnly?: boolean }[] = [
    { key: "quantity", label: "Qty *",   ph: "10.5",   w: "w-24" },
    { key: "price",    label: "Price *", ph: "1.00",   w: "w-28", readOnly: priceFetching },
    { key: "date",     label: "Date",    ph: today,    w: "w-28",
      onFocus: () => { if (!dateTouched) { setDateTouched(true); if (!draft.date) setDraft((d) => ({ ...d, date: today })); } } },
    { key: "fees",     label: "Fees",    ph: "0.00",   w: "w-20" },
  ];

  return (
    <div className="border-t border-[#404868] px-3 py-2.5 bg-[#0f1117]">
      <div className="flex flex-wrap gap-2 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-[0.6rem] uppercase tracking-wide text-slate-500">
            {isCurrency ? "Currency *" : "Ticker *"}
          </label>
          <input
            value={ticker}
            onChange={(e) => {
              const val = e.target.value.toUpperCase();
              setTicker(val);
              if (isCurrency) setDraft((d) => ({ ...d, price: val === "USD" ? "1" : "" }));
            }}
            onBlur={() => { if (isCurrency && ticker && ticker !== "USD") fetchCurrencyPrice(ticker); }}
            onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") onCancel(); }}
            className={`${ic} w-20 uppercase`}
            placeholder={isCurrency ? "USD" : "AAPL"}
            autoFocus
          />
        </div>
        {fields.map(({ key, label, ph, w, onFocus, readOnly }) => (
          <div key={key} className="flex flex-col gap-1">
            <label className="text-[0.6rem] uppercase tracking-wide text-slate-500">{label}</label>
            <input
              value={draft[key]}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
              onFocus={onFocus}
              readOnly={readOnly}
              className={`${ic} ${w} ${readOnly ? "opacity-50" : ""}`}
              placeholder={ph}
            />
          </div>
        ))}
        <div className="flex items-end gap-1.5 pb-0.5">
          <button
            onClick={handleSave}
            disabled={saving || !canSave}
            className="px-2.5 py-1 text-xs rounded bg-[#2d4a3e] text-[#6bc98a] hover:bg-[#3a5e50] disabled:opacity-40 transition-colors cursor-pointer"
          >
            {saving ? "Adding…" : "Add"}
          </button>
          <button onClick={onCancel} disabled={saving} className="px-2.5 py-1 text-xs rounded bg-[#2a2f45] text-slate-400 hover:text-slate-200 transition-colors cursor-pointer">
            Cancel
          </button>
        </div>
      </div>
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AssetTable
// ---------------------------------------------------------------------------

type EnrichedAsset = Asset & {
  dayChgPrice: number | null;
  dayChgValue: number | null;
  dayChgPct: number | null;
};

function AssetTable({ assets, prevClose, defaultPeriodLabel, onPeriodChange, editing, portfolioId, onMutated }: {
  assets: Asset[];
  prevClose: Record<string, number>;
  defaultPeriodLabel: string;
  onPeriodChange: (label: string) => void;
  editing?: boolean;
  portfolioId?: string;
  onMutated?: (updated: PortfolioDetail) => void;
}) {
  const [expandedTickers, setExpandedTickers] = useState<Set<string>>(new Set());
  const [chartTickers, setChartTickers] = useState<Set<string>>(new Set());
  const [priceChgMode, setPriceChgMode] = useState<"dollar" | "percent">("percent");
  const [valueChgMode, setValueChgMode] = useState<"dollar" | "percent">("dollar");
  const [priceColMode, setPriceColMode] = useState<"price" | "qty">("price");
  const [valueGroupMode, setValueGroupMode] = useState<"value" | "pl">("value");
  const [deletingTicker, setDeletingTicker] = useState<string | null>(null);

  function toggleTicker(ticker: string) {
    setExpandedTickers((prev) => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }

  function toggleChartTicker(ticker: string) {
    setChartTickers((prev) => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }

  async function handleDeleteAsset(assetType: string, ticker: string) {
    if (!portfolioId || !onMutated) return;
    setDeletingTicker(ticker);
    try {
      onMutated(await api.deletePortfolioAsset(portfolioId, assetType, ticker));
    } catch { /* silent */ }
    finally { setDeletingTicker(null); }
  }

  const enriched: EnrichedAsset[] = assets.map((a) => {
    const pc = prevClose[prevCloseKey(a)] ?? null;
    const dayChgPrice = a.current_price !== null && pc !== null ? a.current_price - pc : null;
    const dayChgValue = dayChgPrice !== null ? dayChgPrice * parseFloat(a.total_quantity) : null;
    const dayChgPct = dayChgPrice !== null && pc !== null && pc !== 0 ? (dayChgPrice / pc) * 100 : null;
    return { ...a, dayChgPrice, dayChgValue, dayChgPct };
  });

  const valueHoldMenu = [
    { label: "Value / Value Chg", active: valueGroupMode === "value", onSelect: () => setValueGroupMode("value") },
    { label: "P&L / P&L %",       active: valueGroupMode === "pl",    onSelect: () => setValueGroupMode("pl") },
  ];

  const columns: ColDef<EnrichedAsset>[] = [
    { key: "ticker",   label: "Ticker",    align: "left",  sortValue: (a) => a.ticker,                    defaultDir: "asc" },
    {
      key: "qty", label: "Qty", align: "right", sortValue: (a) => parseFloat(a.total_quantity),
      vis: priceColMode === "qty" ? "hidden" : (editing ? undefined : "hidden sm:table-cell"),
    },
    {
      key: "price",
      label: priceColMode === "price" ? "Price" : "Qty",
      align: "right",
      sortValue: priceColMode === "price" ? (a) => a.current_price : (a) => parseFloat(a.total_quantity),
      vis: priceColMode === "price" ? (editing ? "hidden sm:table-cell" : undefined) : undefined,
      holdMenu: [
        { label: "Price", active: priceColMode === "price", onSelect: () => setPriceColMode("price") },
        { label: "Qty",   active: priceColMode === "qty",   onSelect: () => setPriceColMode("qty") },
      ],
    },
    { key: "priceChg", label: "Price Chg", align: "right", sortValue: (a) => priceChgMode === "dollar" ? a.dayChgPrice : a.dayChgPct,
      badge: priceChgMode === "dollar" ? "$" : "%", onBadge: () => setPriceChgMode((m) => (m === "dollar" ? "percent" : "dollar")) },
    {
      key: "value",
      label: valueGroupMode === "value" ? "Value" : "P&L",
      align: "right",
      sortValue: valueGroupMode === "value" ? (a) => a.current_value : (a) => a.profit_loss,
      holdMenu: valueHoldMenu,
    },
    {
      key: "valueChg",
      label: valueGroupMode === "value" ? "Value Chg" : "P&L %",
      align: "right",
      sortValue: valueGroupMode === "value"
        ? (a) => valueChgMode === "dollar" ? a.dayChgValue : a.dayChgPct
        : (a) => a.profit_loss_percentage,
      badge: valueGroupMode === "value" ? (valueChgMode === "dollar" ? "$" : "%") : undefined,
      onBadge: valueGroupMode === "value" ? () => setValueChgMode((m) => (m === "dollar" ? "percent" : "dollar")) : undefined,
      holdMenu: valueHoldMenu,
    },
    { key: "pl",    label: "P&L",   align: "right", sortValue: (a) => a.profit_loss,            vis: valueGroupMode === "value" ? "hidden lg:table-cell" : "hidden" },
    { key: "plPct", label: "P&L %", align: "right", sortValue: (a) => a.profit_loss_percentage, vis: valueGroupMode === "value" ? "hidden lg:table-cell" : "hidden" },
    { key: "menu",  label: "",      align: "right" },
  ];

  return (
    <DataTable
      columns={columns}
      rows={enriched}
      getKey={(a) => a.ticker}
      renderRow={(a) => {
        const isExpanded = expandedTickers.has(a.ticker);
        const hasChart = chartTickers.has(a.ticker);
        const isDeleting = deletingTicker === a.ticker;
        return (
          <>
            <tr
              className={[
                "border-b border-[#2a2d3a] transition-colors",
                !isExpanded ? "last:border-b-0" : "",
                isExpanded ? "bg-[#252a40]" : "",
                isDeleting ? "opacity-40" : "",
              ].join(" ")}
            >
              <td className="px-1 sm:px-1.5 py-2 font-semibold text-slate-100">
                <button onClick={() => toggleChartTicker(a.ticker)} className="hover:text-sky-400 transition-colors cursor-pointer">
                  {a.ticker}
                </button>
              </td>
              {/* qty column — hidden when priceColMode=qty (data shown in price slot instead) */}
              <td className={`${priceColMode === "qty" ? "hidden " : (editing ? "" : "hidden sm:table-cell ")}px-1 sm:px-1.5 py-2 text-right tabular-nums text-slate-300`}>
                <span className="inline-flex items-center justify-end gap-1.5">
                  {fmtQty(a.total_quantity)}
                  <button
                    onClick={() => toggleTicker(a.ticker)}
                    title="View lots"
                    disabled={!editing && a.lots.length === 0}
                    className={`leading-none transition-colors ${a.lots.length > 0 || editing ? "text-[#404868] hover:text-slate-400 cursor-pointer" : "invisible"}`}
                  >
                    ⓘ
                  </button>
                </span>
              </td>
              {/* price/qty slot — shows qty data when priceColMode=qty */}
              <td className={`${priceColMode === "price" && editing ? "hidden sm:table-cell " : ""}px-1 sm:px-1.5 py-2 text-right tabular-nums text-slate-300`}>
                {priceColMode === "price" ? fmtPrice(a.current_price, a.asset_type, a.ticker) : (
                  <span className="inline-flex items-center justify-end gap-1.5">
                    {fmtQty(a.total_quantity)}
                    <button
                      onClick={() => toggleTicker(a.ticker)}
                      title="View lots"
                      disabled={!editing && a.lots.length === 0}
                      className={`leading-none transition-colors ${a.lots.length > 0 || editing ? "text-[#404868] hover:text-slate-400 cursor-pointer" : "invisible"}`}
                    >
                      ⓘ
                    </button>
                  </span>
                )}
              </td>
              <td className={`px-1 sm:px-1.5 py-2 text-right tabular-nums ${plColor(a.dayChgPrice)}`}>
                {priceChgMode === "dollar" ? fmtChg(a.dayChgPrice) : fmtPct(a.dayChgPct)}
              </td>
              {/* value/P&L slot */}
              <td className={`px-1 sm:px-1.5 py-2 text-right tabular-nums ${valueGroupMode === "value" ? "text-slate-300" : plColor(a.profit_loss)}`}>
                {valueGroupMode === "value" ? fmtMoney(a.current_value) : fmtMoney(a.profit_loss)}
              </td>
              {/* valueChg/P&L% slot */}
              <td className={`px-1 sm:px-1.5 py-2 text-right tabular-nums ${plColor(valueGroupMode === "value" ? a.dayChgValue : a.profit_loss_percentage)}`}>
                {valueGroupMode === "value"
                  ? (valueChgMode === "dollar" ? fmtChg(a.dayChgValue) : fmtPct(a.dayChgPct))
                  : fmtPct(a.profit_loss_percentage)}
              </td>
              {/* P&L columns — hidden when valueGroupMode=pl to avoid duplication on large screens */}
              <td className={`${valueGroupMode === "value" ? "hidden lg:table-cell" : "hidden"} px-1 sm:px-1.5 py-2 text-right tabular-nums font-medium ${plColor(a.profit_loss)}`}>
                {fmtMoney(a.profit_loss)}
              </td>
              <td className={`${valueGroupMode === "value" ? "hidden lg:table-cell" : "hidden"} px-1 sm:px-1.5 py-2 text-right tabular-nums ${plColor(a.profit_loss_percentage)}`}>
                {fmtPct(a.profit_loss_percentage)}
              </td>
              <td className="pl-0 pr-1 sm:pr-1.5 py-2 text-right">
                <span className="inline-flex items-center justify-end gap-0.5">
                  {editing && (
                    <button
                      onClick={() => handleDeleteAsset(a.asset_type, a.ticker)}
                      disabled={isDeleting}
                      title="Remove asset"
                      className="text-slate-600 hover:text-red-400 transition-colors cursor-pointer px-0.5 text-base leading-none disabled:opacity-40"
                    >
                      ×
                    </button>
                  )}
                  <AssetMenu ticker={a.ticker} assetType={a.asset_type} />
                </span>
              </td>
            </tr>
            {isExpanded && (
              <tr className="border-b border-[#2a2d3a] last:border-b-0">
                <td colSpan={columns.length} className="px-0 py-0 bg-[#181c28]">
                  <LotTable
                    lots={a.lots}
                    currentPrice={a.current_price}
                    assetType={a.asset_type}
                    ticker={a.ticker}
                    editing={editing}
                    portfolioId={portfolioId}
                    onMutated={onMutated}
                  />
                </td>
              </tr>
            )}
            {hasChart && (
              <tr className="border-b border-[#2a2d3a] last:border-b-0">
                <td colSpan={columns.length} className="px-4 py-3 bg-[#0c0f18]">
                  <Chart ticker={a.ticker} assetType={a.asset_type} defaultPeriodLabel={defaultPeriodLabel} onPeriodChange={onPeriodChange} />
                </td>
              </tr>
            )}
          </>
        );
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// AssetSection
// ---------------------------------------------------------------------------

function AssetSection({ title, assetType, assets, prevClose, defaultPeriodLabel, onPeriodChange, editing, portfolioId, onMutated }: {
  title: string;
  assetType: string;
  assets: Asset[];
  prevClose: Record<string, number>;
  defaultPeriodLabel: string;
  onPeriodChange: (label: string) => void;
  editing?: boolean;
  portfolioId?: string;
  onMutated?: (updated: PortfolioDetail) => void;
}) {
  const [showAdd, setShowAdd] = useState(false);

  if (assets.length === 0 && !editing) return null;

  return (
    <div className="mb-5 last:mb-0">
      <h3 className="text-[0.7rem] font-semibold uppercase tracking-wide text-slate-500 mb-2 px-1">{title}</h3>
      <div className="border border-[#404868] rounded-md overflow-hidden">
        {assets.length > 0 && (
          <AssetTable
            assets={assets}
            prevClose={prevClose}
            defaultPeriodLabel={defaultPeriodLabel}
            onPeriodChange={onPeriodChange}
            editing={editing}
            portfolioId={portfolioId}
            onMutated={onMutated}
          />
        )}
        {editing && !showAdd && (
          <div className={`px-3 py-1.5 bg-[#0f1117]${assets.length > 0 ? " border-t border-[#404868]" : ""}`}>
            <button
              onClick={() => setShowAdd(true)}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
            >
              + Add {assetType}
            </button>
          </div>
        )}
        {editing && showAdd && portfolioId && onMutated && (
          <AddAssetForm
            assetType={assetType}
            portfolioId={portfolioId}
            onMutated={(u) => { onMutated(u); setShowAdd(false); }}
            onCancel={() => setShowAdd(false)}
          />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PortfolioDetailPane
// ---------------------------------------------------------------------------

export function PortfolioDetailPane({
  detail,
  loading,
  error,
  prevClose,
  onMutated,
  onDelete,
  initialEditing = false,
}: {
  detail: PortfolioDetail | null;
  loading: boolean;
  error: string | null;
  prevClose: Record<string, number>;
  onMutated?: (updated: PortfolioDetail) => void;
  onDelete?: () => Promise<void>;
  initialEditing?: boolean;
}) {
  const navigate = useNavigate();
  const [defaultPeriodLabel, setDefaultPeriodLabel] = useState("4H");
  const [editing, setEditing] = useState(initialEditing);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const canManageUsers = getRole() === "admin" || getUsername() === detail?.owner;
  const isAdmin = getRole() === "admin";

  useEffect(() => { setEditing(initialEditing); setConfirmDelete(false); }, [detail?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 py-2 text-sm">{error}</p>;
  if (!detail) return null;

  const todayChg = computeTodayChange(detail, prevClose);

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
        {(
          [
            ["Value",      fmtMoney(detail.total_value),          null,                          ""],
            ["Cost Basis", fmtMoney(detail.total_cost_basis),     null,                          ""],
            ["P&L",        fmtMoney(detail.total_profit_loss),    detail.total_profit_loss,      ""],
            ["P&L %",      fmtPct(detail.profit_loss_percentage), detail.profit_loss_percentage, "hidden sm:block"],
          ] as [string, string, number | null, string][]
        ).reduce<React.ReactNode[]>((acc, [label, value, colorVal, vis], i) => {
          if (i === 1) {
            acc.push(
              <div key="today-chg" className="bg-[#131928] border border-[#404868] rounded-md px-2 py-2">
                <div className="text-[0.65rem] uppercase tracking-wide text-slate-500 mb-1">Today&apos;s Chg</div>
                <div className={`text-sm sm:text-base font-semibold tabular-nums ml-2 ${plColor(todayChg?.value ?? null)}`}>
                  {todayChg ? <>{fmtChg(todayChg.value)}<span className="hidden sm:inline"> ({fmtPct(todayChg.pct)})</span></> : "—"}
                </div>
              </div>
            );
          }
          acc.push(
            <div key={label} className={`${vis} bg-[#131928] border border-[#404868] rounded-md px-2 py-2`}>
              <div className="text-[0.65rem] uppercase tracking-wide text-slate-500 mb-1">{label}</div>
              <div className={`text-sm sm:text-base font-semibold tabular-nums ml-2 ${colorVal !== null ? plColor(colorVal) : "text-slate-100"}`}>
                {value}
              </div>
            </div>
          );
          return acc;
        }, [])}
      </div>

      <div className="flex items-center justify-between mb-3">
        {onMutated ? (
          <button
            onClick={() => { setEditing((e) => !e); setConfirmDelete(false); }}
            className={`text-xs transition-colors cursor-pointer ${editing ? "text-sky-400 hover:text-sky-300" : "text-slate-500 hover:text-slate-300"}`}
          >
            {editing ? "Done" : "Edit"}
          </button>
        ) : <span />}
        <button
          onClick={() => navigate(`/portfolio/${detail.id}/performance`)}
          className="text-xs text-slate-500 hover:text-sky-400 transition-colors cursor-pointer"
        >
          Performance →
        </button>
      </div>

      <AssetSection
        title="Stocks" assetType="stock"
        assets={detail.stocks} prevClose={prevClose}
        defaultPeriodLabel={defaultPeriodLabel} onPeriodChange={setDefaultPeriodLabel}
        editing={editing} portfolioId={detail.id} onMutated={onMutated}
      />
      <AssetSection
        title="Currencies" assetType="currency"
        assets={detail.currencies} prevClose={prevClose}
        defaultPeriodLabel={defaultPeriodLabel} onPeriodChange={setDefaultPeriodLabel}
        editing={editing} portfolioId={detail.id} onMutated={onMutated}
      />
      <AssetSection
        title="Crypto" assetType="crypto"
        assets={detail.crypto} prevClose={prevClose}
        defaultPeriodLabel={defaultPeriodLabel} onPeriodChange={setDefaultPeriodLabel}
        editing={editing} portfolioId={detail.id} onMutated={onMutated}
      />
      {editing && canManageUsers && <PortfolioUsersSection portfolioId={detail.id} />}
      {editing && isAdmin && onDelete && (
        <div className="mt-6 pt-5 border-t border-[#2a2d3a] flex items-center gap-3">
          {confirmDelete ? (
            <>
              <span className="text-xs text-slate-400">Delete this portfolio?</span>
              <Button variant="danger" disabled={deleting} onClick={async () => { setDeleting(true); await onDelete(); }}>
                {deleting ? "Deleting…" : "Confirm delete"}
              </Button>
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            </>
          ) : (
            <Button variant="dangerGhost" onClick={() => setConfirmDelete(true)}>Delete portfolio</Button>
          )}
        </div>
      )}
    </div>
  );
}
