import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

type AlertEntry = Record<string, unknown>;

function formatAlert(a: AlertEntry): string {
  const msg = a["message"] as string | undefined;
  const ticker = (a["ticker"] as Record<string, unknown> | undefined)?.["ticker"] as string | undefined;
  const kind = a["kind"] as string | undefined;
  if (msg) return msg;
  return [ticker, kind].filter(Boolean).join(" — ") || "Alert";
}

function formatAt(a: AlertEntry): string {
  const at = a["at"] as string | undefined;
  if (!at) return "";
  try {
    return new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

/**
 * Notification bell that shows recent alerts from the dashboard channel buffer.
 *
 * Pass `latestAlert` (from the WebSocket `alert_fired` frame) whenever a new
 * alert arrives — the component will prepend it to the list and bump the badge.
 */
export function AlertBell({ latestAlert }: { latestAlert: AlertEntry | null }) {
  const [alerts, setAlerts] = useState<AlertEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);
  const prevAlert = useRef<AlertEntry | null>(null);

  // Load buffered alerts on mount
  useEffect(() => {
    api.getRecentAlerts(50).then((res) => {
      setAlerts(res.alerts);
    }).catch(() => {});
  }, []);

  // Push incoming WS alerts
  useEffect(() => {
    if (latestAlert && latestAlert !== prevAlert.current) {
      prevAlert.current = latestAlert;
      setAlerts((prev) => [latestAlert, ...prev].slice(0, 100));
      if (!open) setUnread((n) => n + 1);
    }
  }, [latestAlert, open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleOpen = () => {
    setOpen((o) => !o);
    if (!open) setUnread(0);
  };

  const handleClear = () => {
    api.clearRecentAlerts().catch(() => {});
    setAlerts([]);
    setUnread(0);
    setOpen(false);
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={handleOpen}
        className="relative p-1.5 rounded text-slate-400 hover:text-slate-200 hover:bg-[#2a2f45] transition-colors"
        title="Alerts"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-0.5 flex items-center justify-center rounded-full bg-[#9c4040] text-white text-[10px] font-bold leading-none">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-80 bg-[#1a1e2e] border border-[#404868] rounded shadow-xl z-50">
          <div className="flex items-center justify-between px-3 py-2 border-b border-[#404868]">
            <span className="text-sm font-medium text-slate-200">Recent Alerts</span>
            {alerts.length > 0 && (
              <button
                onClick={handleClear}
                className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                Clear all
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {alerts.length === 0 ? (
              <p className="px-3 py-4 text-sm text-slate-500 text-center">No recent alerts</p>
            ) : (
              <ul>
                {alerts.map((a, i) => (
                  <li key={i} className="px-3 py-2 border-b border-[#2a2f45] last:border-0">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm text-slate-200 leading-snug">{formatAlert(a)}</span>
                      <span className="text-xs text-slate-500 shrink-0 mt-0.5">{formatAt(a)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
