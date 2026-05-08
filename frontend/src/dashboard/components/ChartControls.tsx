import { useEffect, useRef, useState } from "react";
import { type ChartSettings, type IntradayWindow, type MomentumWindow } from "../lib/chartSettings";

const RANGES = [
  { label: "1W", days:   7 },
  { label: "1M", days:  30 },
  { label: "3M", days:  90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
];

const MOMENTUM_WINDOWS: MomentumWindow[] = [1, 3, 5, 7];

const INTRADAY_WINDOWS: { label: string; value: IntradayWindow }[] = [
  { label: "2H", value: "2h" },
  { label: "4H", value: "4h" },
  { label: "1D", value: "1d" },
  { label: "3D", value: "3d" },
  { label: "7D", value: "7d" },
];

const pill = (active: boolean) =>
  `px-2 py-0.5 rounded text-xs font-medium transition-colors cursor-pointer ${
    active ? "bg-[#404868] text-slate-100" : "text-slate-500 hover:text-slate-300"
  }`;

/**
 * Split-button: left half toggles chart mode, right half (☰) opens a flyout
 * for chart type and range settings. Settings are managed by the parent and
 * persisted to sessionStorage by the caller.
 */
export function ChartControlsButton({
  isChart,
  onToggle,
  settings,
  onSettings,
}: {
  isChart: boolean;
  onToggle: () => void;
  settings: ChartSettings;
  onSettings: (s: ChartSettings) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function clearCloseTimer() {
    if (closeTimer.current !== null) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }

  function scheduleClose() {
    clearCloseTimer();
    closeTimer.current = setTimeout(() => setOpen(false), 2500);
  }

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const sharedBg = isChart ? "bg-[#404868]" : "";
  const isIntraday = settings.chartType === "intraday";

  return (
    <div ref={ref} className="relative flex">
      <button
        onClick={onToggle}
        className={`pl-2 pr-1 py-0.5 rounded-l text-xs font-medium transition-colors cursor-pointer ${
          isChart ? "bg-[#404868] text-slate-100" : "text-slate-500 hover:text-slate-300"
        }`}
      >
        Charts
      </button>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Chart settings"
        className={`pl-1 pr-1.5 py-0.5 rounded-r text-xs transition-colors cursor-pointer border-l border-[#2a2d3a] ${sharedBg} ${
          open ? "text-slate-100" : isChart ? "text-slate-400 hover:text-slate-100" : "text-slate-500 hover:text-slate-300"
        }`}
      >
        ☰
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-1 bg-[#1e2130] border border-[#404868] rounded-md shadow-lg z-20 p-3 w-64"
          onMouseEnter={clearCloseTimer}
          onMouseLeave={scheduleClose}
        >
          <p className="text-[0.6rem] uppercase tracking-wide text-slate-500 mb-1.5">Type</p>
          <div className="flex flex-wrap gap-1 mb-1.5">
            <button className={pill(settings.chartType === "return")}
              onClick={() => onSettings({ ...settings, chartType: "return" })}>
              Return
            </button>
            <button className={pill(settings.chartType === "momentum")}
              onClick={() => onSettings({ ...settings, chartType: "momentum" })}>
              Momentum
            </button>
            <button className={pill(settings.chartType === "volume")}
              onClick={() => onSettings({ ...settings, chartType: "volume" })}>
              Volume
            </button>
            <button className={pill(settings.chartType === "intraday")}
              onClick={() => onSettings({ ...settings, chartType: "intraday" })}>
              Intraday
            </button>
          </div>

          {settings.chartType === "momentum" && (
            <div className="flex gap-1 mb-3 pl-1">
              {MOMENTUM_WINDOWS.map((w) => (
                <button key={w} className={pill(settings.momentumWindow === w)}
                  onClick={() => onSettings({ ...settings, momentumWindow: w })}>
                  {w}D
                </button>
              ))}
            </div>
          )}
          {settings.chartType !== "momentum" && <div className="mb-3" />}

          <p className="text-[0.6rem] uppercase tracking-wide text-slate-500 mb-1.5">
            {isIntraday ? "Window" : "Range"}
          </p>
          {isIntraday ? (
            <div className="flex gap-1">
              {INTRADAY_WINDOWS.map((w) => (
                <button key={w.value} className={pill(settings.intradayWindow === w.value)}
                  onClick={() => onSettings({ ...settings, intradayWindow: w.value })}>
                  {w.label}
                </button>
              ))}
            </div>
          ) : (
            <div className="flex gap-1">
              {RANGES.map((r) => (
                <button key={r.days} className={pill(settings.chartRange === r.days)}
                  onClick={() => onSettings({ ...settings, chartRange: r.days })}>
                  {r.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
