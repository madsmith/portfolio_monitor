import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CancelButton, ConfirmButton } from "./buttons";
import { DropdownSelector, Input } from "./inputs";

// ---------------------------------------------------------------------------
// Detector kinds — hardcoded for mockup; will be fetched from API when wired
// ---------------------------------------------------------------------------

type ArgSpec = { name: string; placeholder: string };

const DETECTOR_KINDS: { name: string; label: string; args: ArgSpec[] }[] = [
  {
    name: "percent_change",
    label: "% Change",
    args: [
      { name: "threshold", placeholder: "0.05  (e.g. 5%)" },
      { name: "period",    placeholder: "1h" },
    ],
  },
  {
    name: "SMA_deviation",
    label: "SMA Deviation",
    args: [
      { name: "threshold", placeholder: "0.05" },
      { name: "period",    placeholder: "1h" },
    ],
  },
  {
    name: "volume_spike",
    label: "Volume Spike",
    args: [
      { name: "threshold", placeholder: "2.0  (2× average)" },
      { name: "period",    placeholder: "1h" },
    ],
  },
  {
    name: "zscore_return",
    label: "Z-Score Return",
    args: [
      { name: "threshold", placeholder: "2.0" },
      { name: "period",    placeholder: "1h" },
    ],
  },
  {
    name: "zscore_volume",
    label: "Z-Score Volume",
    args: [
      { name: "threshold", placeholder: "2.0" },
      { name: "period",    placeholder: "1h" },
    ],
  },
  {
    name: "average_true_range_move",
    label: "ATR Move",
    args: [
      { name: "threshold", placeholder: "2.0  (2× ATR)" },
      { name: "samples",   placeholder: "14" },
    ],
  },
];

// ---------------------------------------------------------------------------
// Add-alert modal
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
  const [kindName, setKindName] = useState(DETECTOR_KINDS[0].name);
  const [args, setArgs] = useState<Record<string, string>>({});

  const kindDef = DETECTOR_KINDS.find((k) => k.name === kindName) ?? DETECTOR_KINDS[0];

  function handleKindChange(name: string) {
    setKindName(name);
    setArgs({});
  }

  function handleSave() {
    console.log("Add alert (mockup)", { ticker, assetType, kind: kindName, args });
    onClose();
  }

  return createPortal(
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-[#1e2130] border border-[#404868] rounded-lg p-5 w-full max-w-sm mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-100">Add alert</h3>
          <p className="text-xs text-slate-500">
            {ticker} &middot; {assetType}
          </p>
        </div>

        <div className="mb-4">
          <label className="text-xs text-slate-500 uppercase tracking-wide mb-1 block">
            Kind
          </label>
          <DropdownSelector
            value={kindName}
            onChange={handleKindChange}
            options={DETECTOR_KINDS.map((k) => ({ value: k.name, label: k.label }))}
          />
        </div>

        {kindDef.args.length > 0 && (
          <div className="flex gap-3 mb-3">
            {kindDef.args.slice(0, 2).map((arg) => (
              <div key={arg.name} className="flex-1 min-w-0">
                <label className="text-xs text-slate-500 uppercase tracking-wide mb-1 block">
                  {arg.name}
                </label>
                <Input
                  value={args[arg.name] ?? ""}
                  placeholder={arg.placeholder}
                  onChange={(v) => setArgs((prev) => ({ ...prev, [arg.name]: v }))}
                  className="w-full"
                />
              </div>
            ))}
          </div>
        )}
        {kindDef.args.slice(2).map((arg) => (
          <div key={arg.name} className="mb-3">
            <label className="text-xs text-slate-500 uppercase tracking-wide mb-1 block">
              {arg.name}
            </label>
            <Input
              value={args[arg.name] ?? ""}
              placeholder={arg.placeholder}
              onChange={(v) => setArgs((prev) => ({ ...prev, [arg.name]: v }))}
              className="w-full"
            />
          </div>
        ))}

        <div className="flex gap-2 justify-end mt-5">
          <CancelButton onClick={onClose} />
          <ConfirmButton onClick={handleSave} />
        </div>
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
  onClose,
}: {
  top: number;
  right: number;
  onAddAlert: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    function handleClick() { onClose(); }
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [onClose]);

  return createPortal(
    <div
      style={{ position: "fixed", top, right, zIndex: 999 }}
      className="bg-[#1e2130] border border-[#404868] rounded-md shadow-lg py-1 min-w-[140px]"
      onClick={(e) => e.stopPropagation()}
    >
      <button
        className="w-full text-left px-3 py-1.5 text-sm text-slate-300 hover:bg-[#2a2f45] transition-colors cursor-pointer"
        onClick={() => { onClose(); onAddAlert(); }}
      >
        Add alert…
      </button>
    </div>,
    document.body
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function AssetMenu({ ticker, assetType }: { ticker: string; assetType: string }) {
  const btnRef = useRef<HTMLButtonElement>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null);
  const [showModal, setShowModal] = useState(false);

  function handleToggle(e: React.MouseEvent) {
    e.stopPropagation();
    if (menuPos) {
      setMenuPos(null);
      return;
    }
    const rect = btnRef.current?.getBoundingClientRect();
    if (rect) {
      setMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
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
          onAddAlert={() => setShowModal(true)}
          onClose={() => setMenuPos(null)}
        />
      )}

      {showModal && (
        <AddAlertModal
          ticker={ticker}
          assetType={assetType}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  );
}
