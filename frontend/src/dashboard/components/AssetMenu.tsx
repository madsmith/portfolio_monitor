import { Fragment, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type AlertRule, type DetectorInfo } from "../api/client";
import { CancelButton, ConfirmButton } from "./buttons";
import { DropdownSelector, Input } from "./inputs";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------


// Threshold first, then period/samples, then anything else in original order.
const ARG_PRIORITY = ["threshold", "period", "samples"];
function sortedArgs(args: DetectorInfo["args"]) {
  return [...args].sort((a, b) => {
    const ai = ARG_PRIORITY.indexOf(a.name);
    const bi = ARG_PRIORITY.indexOf(b.name);
    if (ai === -1 && bi === -1) return 0;
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
}

function parseArg(value: string, type: string): number | string {
  if (type === "float") { const n = parseFloat(value); return isNaN(n) ? value : n; }
  if (type === "int")   { const n = parseInt(value, 10); return isNaN(n) ? value : n; }
  return value;
}

function defaultsFor(det: DetectorInfo): Record<string, string> {
  const out: Record<string, string> = {};
  for (const arg of det.args) {
    if (arg.default !== undefined) out[arg.name] = String(arg.default);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Shared add-alert form (used standalone and embedded in ManageAlertsModal)
// ---------------------------------------------------------------------------

function AddAlertForm({
  ticker,
  detectors,
  onAdded,
  onCancel,
}: {
  ticker: string;
  detectors: DetectorInfo[];
  onAdded: (rule: AlertRule) => void;
  onCancel: () => void;
}) {
  const [kindName, setKindName] = useState(() => detectors[0]?.name ?? "");
  const [args, setArgs] = useState<Record<string, string>>(() =>
    detectors[0] ? defaultsFor(detectors[0]) : {}
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showInfo, setShowInfo] = useState(false);

  function handleKindChange(name: string) {
    const det = detectors.find((d) => d.name === name);
    setKindName(name);
    setArgs(det ? defaultsFor(det) : {});
  }

  async function handleConfirm() {
    setSaving(true);
    setError(null);
    try {
      const det = detectors.find((d) => d.name === kindName);
      const parsedArgs: Record<string, number | string> = {};
      for (const arg of det?.args ?? []) {
        const raw = args[arg.name] ?? "";
        if (raw !== "") parsedArgs[arg.name] = parseArg(raw, arg.type);
      }
      const rule = await api.addAlertRule({ ticker, kind: kindName, args: parsedArgs });
      onAdded(rule);
    } catch (e) {
      console.error("Add alert failed:", e);
      setError("Alert save failed");
    } finally {
      setSaving(false);
    }
  }

  const kindDef = detectors.find((d) => d.name === kindName);
  const ordered = kindDef ? sortedArgs(kindDef.args) : [];

  function argField(arg: DetectorInfo["args"][number]) {
    return (
      <div key={arg.name} className="flex-1 min-w-0">
        <label className="relative group inline-flex items-center gap-1 text-xs text-slate-500 uppercase tracking-wide mb-1 cursor-default select-none">
          {arg.name}
          {arg.description && (
            <span className="absolute bottom-full left-0 mb-1.5 w-64 bg-[#0e1018] border border-[#404868] rounded px-2.5 py-2 text-xs text-slate-300 normal-case tracking-normal z-20 shadow-lg hidden group-hover:block pointer-events-none">
              {arg.description}
            </span>
          )}
        </label>
        <Input
          value={args[arg.name] ?? ""}
          placeholder={arg.default !== undefined ? String(arg.default) : ""}
          onChange={(v) => setArgs((prev) => ({ ...prev, [arg.name]: v }))}
          className="w-full"
        />
      </div>
    );
  }

  return (
    <div className="bg-[#151720] border border-[#404868] rounded p-3 mb-2">
      <div className="flex items-center gap-3 mb-3">
        <label className="relative group text-xs text-slate-500 uppercase tracking-wide shrink-0 cursor-default select-none">
          Kind
          {kindDef?.description && (
            <span className="absolute bottom-full left-0 mb-1.5 w-72 bg-[#0e1018] border border-[#404868] rounded px-2.5 py-2 text-xs text-slate-300 normal-case tracking-normal z-20 shadow-lg hidden group-hover:block pointer-events-none">
              {kindDef.description}
            </span>
          )}
        </label>
        <DropdownSelector
          value={kindName}
          onChange={handleKindChange}
          options={detectors.map((d) => ({ value: d.name, label: d.display_name || d.name }))}
        />
        <button
          type="button"
          onClick={() => setShowInfo((v) => !v)}
          className={`ml-auto shrink-0 w-5 h-5 rounded-full border text-xs font-semibold transition-colors cursor-pointer ${
            showInfo
              ? "border-slate-400 text-slate-200 bg-slate-700"
              : "border-slate-600 text-slate-500 hover:border-slate-400 hover:text-slate-300"
          }`}
          title="Toggle description"
        >
          i
        </button>
      </div>

      {ordered.length > 0 && (
        <div className="flex gap-3 mb-3">
          {ordered.slice(0, 2).map(argField)}
        </div>
      )}
      {ordered.slice(2).map((arg) => (
        <div key={arg.name} className="mb-3">{argField(arg)}</div>
      ))}

      {showInfo && kindDef && (
        <div className="border-t border-[#2a2f45] mt-1 pt-3 mb-3 space-y-2.5">
          {kindDef.description && (
            <p className="text-xs text-slate-300 leading-relaxed">{kindDef.description}</p>
          )}
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            {sortedArgs(kindDef.args).filter((a) => a.description).map((arg) => (
              <Fragment key={arg.name}>
                <div className="text-xs text-slate-400 uppercase tracking-wide pt-px">{arg.name}</div>
                <div className="text-xs text-slate-300 leading-relaxed">{arg.description}</div>
              </Fragment>
            ))}
          </div>
        </div>
      )}

      {error && <p className="text-xs text-red-400 mb-2">{error}</p>}
      <div className="flex gap-2 justify-end mt-2">
        <CancelButton onClick={onCancel} disabled={saving} />
        <ConfirmButton onClick={handleConfirm} disabled={saving}>
          {saving ? "Saving…" : "Confirm"}
        </ConfirmButton>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edit-rule row (inline editor inside ManageAlertsModal)
// ---------------------------------------------------------------------------

function EditRuleRow({
  rule,
  detectors,
  onSaved,
  onCancel,
}: {
  rule: AlertRule;
  detectors: DetectorInfo[];
  onSaved: (updated: AlertRule) => void;
  onCancel: () => void;
}) {
  const kindDef = detectors.find((d) => d.name === rule.kind);
  const ordered = kindDef ? sortedArgs(kindDef.args) : [];
  const [args, setArgs] = useState<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(rule.args)) out[k] = String(v);
    return out;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const parsedArgs: Record<string, number | string> = {};
      for (const arg of kindDef?.args ?? []) {
        const raw = args[arg.name] ?? "";
        if (raw !== "") parsedArgs[arg.name] = parseArg(raw, arg.type);
      }
      await api.updateAlertRule(rule.id, { args: parsedArgs });
      onSaved({ ...rule, args: parsedArgs });
    } catch (e) {
      console.error("Update alert failed:", e);
      setError("Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg-[#151720] border border-[#404868] rounded p-3 mb-2">
      <div className="text-xs text-slate-400 mb-2 font-medium">
        {kindDef?.display_name || rule.kind}
      </div>
      <div className="flex flex-wrap gap-2 mb-2">
        {ordered.map((arg) => (
          <div key={arg.name} className="flex-1 min-w-0">
            <label className="relative group inline-flex items-center gap-1 text-xs text-slate-500 uppercase tracking-wide mb-1 cursor-default select-none">
              {arg.name}
              {arg.description && (
                <span className="absolute bottom-full left-0 mb-1.5 w-64 bg-[#0e1018] border border-[#404868] rounded px-2.5 py-2 text-xs text-slate-300 normal-case tracking-normal z-20 shadow-lg hidden group-hover:block pointer-events-none">
                  {arg.description}
                </span>
              )}
            </label>
            <Input
              value={args[arg.name] ?? ""}
              placeholder={arg.default !== undefined ? String(arg.default) : ""}
              onChange={(v) => setArgs((prev) => ({ ...prev, [arg.name]: v }))}
              className="w-full"
            />
          </div>
        ))}
      </div>
      {error && <p className="text-xs text-red-400 mb-2">{error}</p>}
      <div className="flex gap-2 justify-end">
        <CancelButton onClick={onCancel} disabled={saving} />
        <ConfirmButton onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </ConfirmButton>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Manage-alerts modal
// ---------------------------------------------------------------------------

function ManageAlertsModal({
  ticker,
  assetType,
  onClose,
}: {
  ticker: string;
  assetType: string;
  onClose: () => void;
}) {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [detectors, setDetectors] = useState<DetectorInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getMyAlerts(), api.getDetectors()])
      .then(([config, dets]) => {
        setRules(config.rules.filter((r) => r.ticker === ticker || r.ticker === ""));
        setDetectors(dets);
      })
      .catch((e: unknown) => {
        console.error("Failed to load alerts:", e);
        setError("Failed to load alerts");
      })
      .finally(() => setLoading(false));
  }, [ticker]);

  async function handleDelete(id: string) {
    setDeletingId(id);
    setError(null);
    try {
      await api.deleteAlertRule(id);
      setRules((prev) => prev.filter((r) => r.id !== id));
    } catch (e) {
      console.error("Delete alert failed:", e);
      setError("Delete failed");
    } finally {
      setDeletingId(null);
    }
  }

  function handleSaved(updated: AlertRule) {
    setRules((prev) => prev.map((r) => r.id === updated.id ? updated : r));
    setEditingId(null);
  }

  function handleAdded(rule: AlertRule) {
    setRules((prev) => [...prev, rule]);
    setShowAdd(false);
  }

  return createPortal(
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onMouseDown={onClose}
    >
      <div
        className="bg-[#1e2130] border border-[#404868] rounded-lg p-5 w-full max-w-md mx-4 shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-100">Manage alerts</h3>
          <p className="text-xs text-slate-500">{ticker} &middot; {assetType}</p>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500 mb-4">Loading…</p>
        ) : (
          <>
            {rules.length === 0 && !showAdd && (
              <p className="text-sm text-slate-500 mb-4">No alerts configured for this asset.</p>
            )}

            {rules.map((rule) =>
              editingId === rule.id ? (
                <EditRuleRow
                  key={rule.id}
                  rule={rule}
                  detectors={detectors}
                  onSaved={handleSaved}
                  onCancel={() => setEditingId(null)}
                />
              ) : (
                <div
                  key={rule.id}
                  className="flex items-center justify-between bg-[#151720] border border-[#2a2f45] rounded px-3 py-2 mb-2"
                >
                  <div>
                    <span className="text-sm text-slate-200 font-medium">
                      {detectors.find((d) => d.name === rule.kind)?.display_name || rule.kind}
                    </span>
                    {rule.ticker === "" && (
                      <span className="ml-2 text-xs text-slate-500">all symbols</span>
                    )}
                    <div className="text-xs text-slate-500 mt-0.5">
                      {Object.entries(rule.args).map(([k, v]) => `${k}=${v}`).join("  ")}
                    </div>
                  </div>
                  <div className="flex gap-2 ml-3 shrink-0">
                    <button
                      className="text-xs text-slate-400 hover:text-slate-200 cursor-pointer transition-colors"
                      onClick={() => { setEditingId(rule.id); setShowAdd(false); }}
                    >
                      Edit
                    </button>
                    <button
                      className="text-xs text-red-500 hover:text-red-400 cursor-pointer transition-colors disabled:opacity-50"
                      disabled={deletingId === rule.id}
                      onClick={() => handleDelete(rule.id)}
                    >
                      {deletingId === rule.id ? "…" : "Remove"}
                    </button>
                  </div>
                </div>
              )
            )}

            {showAdd && (
              <AddAlertForm
                ticker={ticker}
                detectors={detectors}
                onAdded={handleAdded}
                onCancel={() => setShowAdd(false)}
              />
            )}
          </>
        )}

        {error && <p className="text-xs text-red-400 mb-2">{error}</p>}

        <div className="flex justify-between items-center mt-4">
          {!showAdd && !loading ? (
            <button
              className="text-xs text-slate-400 hover:text-slate-200 cursor-pointer transition-colors"
              onClick={() => { setShowAdd(true); setEditingId(null); }}
            >
              + Add Alert
            </button>
          ) : <span />}
          <CancelButton onClick={onClose}>Close</CancelButton>
        </div>
      </div>
    </div>,
    document.body
  );
}

// ---------------------------------------------------------------------------
// Standalone add-alert modal (used from "Add alert…" menu item)
// ---------------------------------------------------------------------------

function AddAlertModal({
  ticker,
  assetType,
  onClose,
}: {
  ticker: string;
  assetType: string;
  onClose: () => void;
}) {
  const [detectors, setDetectors] = useState<DetectorInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getDetectors()
      .then(setDetectors)
      .catch((e: unknown) => {
        console.error("Failed to load detectors:", e);
        setError("Failed to load alert types");
      })
      .finally(() => setLoading(false));
  }, []);

  return createPortal(
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onMouseDown={onClose}
    >
      <div
        className="bg-[#1e2130] border border-[#404868] rounded-lg p-5 w-full max-w-lg mx-4 shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-100">Add alert</h3>
          <p className="text-xs text-slate-500">{ticker} &middot; {assetType}</p>
        </div>
        {loading ? (
          <p className="text-sm text-slate-500 mb-4">Loading…</p>
        ) : error ? (
          <>
            <p className="text-xs text-red-400 mb-4">{error}</p>
            <div className="flex justify-end">
              <CancelButton onClick={onClose}>Close</CancelButton>
            </div>
          </>
        ) : (
          <AddAlertForm
            ticker={ticker}
            detectors={detectors}
            onAdded={onClose}
            onCancel={onClose}
          />
        )}
      </div>
    </div>,
    document.body
  );
}

// ---------------------------------------------------------------------------
// Dropdown menu (portal, fixed-positioned relative to trigger button)
// ---------------------------------------------------------------------------

function AssetDropdown({
  top,
  right,
  onAddAlert,
  onManageAlerts,
  onClose,
}: {
  top: number;
  right: number;
  onAddAlert: () => void;
  onManageAlerts: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    function handleClick() { onClose(); }
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [onClose]);

  const itemCls = "w-full text-left px-3 py-1.5 text-sm text-slate-300 hover:bg-[#2a2f45] transition-colors cursor-pointer";

  return createPortal(
    <div
      style={{ position: "fixed", top, right, zIndex: 999 }}
      className="bg-[#1e2130] border border-[#404868] rounded-md shadow-lg py-1 min-w-[150px]"
      onClick={(e) => e.stopPropagation()}
    >
      <button className={itemCls} onClick={() => { onClose(); onAddAlert(); }}>
        Add alert…
      </button>
      <button className={itemCls} onClick={() => { onClose(); onManageAlerts(); }}>
        Manage alerts…
      </button>
    </div>,
    document.body
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

type ModalKind = "add" | "manage" | null;

let _closeOpenMenu: (() => void) | null = null;

export function AssetMenu({ ticker, assetType }: { ticker: string; assetType: string }) {
  const btnRef = useRef<HTMLButtonElement>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null);
  const [modal, setModal] = useState<ModalKind>(null);

  function handleToggle(e: React.MouseEvent) {
    e.stopPropagation();
    if (menuPos) {
      setMenuPos(null);
      _closeOpenMenu = null;
      return;
    }
    _closeOpenMenu?.();
    const rect = btnRef.current?.getBoundingClientRect();
    if (rect) {
      setMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
      _closeOpenMenu = () => setMenuPos(null);
    }
  }

  return (
    <>
      <button
        ref={btnRef}
        onClick={handleToggle}
        title="Actions"
        className="text-slate-600 hover:text-slate-300 transition-colors px-1 cursor-pointer leading-none select-none"
      >
        ⋮
      </button>

      {menuPos && (
        <AssetDropdown
          top={menuPos.top}
          right={menuPos.right}
          onAddAlert={() => setModal("add")}
          onManageAlerts={() => setModal("manage")}
          onClose={() => setMenuPos(null)}
        />
      )}

      {modal === "add" && (
        <AddAlertModal
          ticker={ticker}
          assetType={assetType}
          onClose={() => setModal(null)}
        />
      )}

      {modal === "manage" && (
        <ManageAlertsModal
          ticker={ticker}
          assetType={assetType}
          onClose={() => setModal(null)}
        />
      )}
    </>
  );
}
