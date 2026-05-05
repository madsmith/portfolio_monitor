import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AlertEntry, AlertWsMessage } from "../api/ws";

const alertSound = new Audio("/sounds/alert.mp3");
alertSound.volume = 0.5;

function playAlertSound() {
  alertSound.currentTime = 0;
  alertSound.play().catch(() => {});
}

function formatAlert(a: AlertEntry): string {
  const msg = a["message"] as string | undefined;
  const ticker = (a["ticker"] as Record<string, unknown> | undefined)?.["ticker"] as string | undefined;
  const kind = a["kind"] as string | undefined;
  if (msg) return msg;
  return [ticker, kind].filter(Boolean).join(" — ") || "Alert";
}

function formatAt(a: AlertEntry): string {
  const at = (a["updated_at"] ?? a["at"]) as string | undefined;
  if (!at) return "";
  try {
    return new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function AlertRow({
  alert,
  onRead,
}: {
  alert: AlertEntry;
  onRead: (id: string) => void;
}) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = () => {
    if (alert.read) return;
    timerRef.current = setTimeout(() => onRead(alert.id), 750);
  };

  const handleMouseLeave = () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const handleClick = () => {
    if (!alert.read) onRead(alert.id);
  };

  return (
    <li
      className={[
        "px-3 py-2 border-b border-[#2a2f45] last:border-0 cursor-default transition-colors",
        alert.read ? "opacity-60" : "bg-[#1e2130]",
      ].join(" ")}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-1.5 min-w-0">
          {!alert.read && (
            <span className="mt-1.5 shrink-0 w-1.5 h-1.5 rounded-full bg-[#9c4040]" />
          )}
          <span className={["text-sm leading-snug", alert.read ? "text-slate-400 ml-3" : "text-slate-200"].join(" ")}>
            {formatAlert(alert)}
          </span>
        </div>
        <span className="text-xs text-slate-500 shrink-0 mt-0.5">{formatAt(alert)}</span>
      </div>
    </li>
  );
}

/**
 * Notification bell with a per-user alert buffer.
 *
 * Receives WS alert events from the parent and handles all event types:
 *   alert_event (fired/updated) — upsert by id
 *   alert_read / all_alerts_read — sync read state
 *   alerts_cleared — empty the list
 *   unread_count — sync badge count on connect
 */
export function AlertBell({
  alertWsEvent,
  markAlertRead,
}: {
  alertWsEvent: AlertWsMessage | null;
  markAlertRead: (id: string) => void;
}) {
  const [alerts, setAlerts] = useState<AlertEntry[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const prevEvent = useRef<AlertWsMessage | null>(null);

  // Load buffered alerts on mount
  useEffect(() => {
    api.getRecentAlerts(50).then((res) => {
      setAlerts(res.alerts as AlertEntry[]);
      setUnread((res.alerts as AlertEntry[]).filter((a) => !a.read).length);
    }).catch(() => {});
  }, []);

  // Handle incoming WS events
  useEffect(() => {
    if (!alertWsEvent || alertWsEvent === prevEvent.current) return;
    prevEvent.current = alertWsEvent;

    switch (alertWsEvent.type) {
      case "alert_event": {
        const incoming = alertWsEvent.alert;
        if (alertWsEvent.event === "fired") playAlertSound();
        setAlerts((prev) => {
          const idx = prev.findIndex((a) => a.id === incoming.id);
          if (idx === -1) return [incoming, ...prev].slice(0, 100);
          const updated = [...prev];
          updated[idx] = incoming;
          return updated;
        });
        setUnread(alertWsEvent.unread_count);
        break;
      }
      case "alert_read":
        setAlerts((prev) =>
          prev.map((a) => (a.id === alertWsEvent.alert_id ? { ...a, read: true } : a))
        );
        setUnread(alertWsEvent.unread_count);
        break;
      case "all_alerts_read":
        setAlerts((prev) => prev.map((a) => ({ ...a, read: true })));
        setUnread(0);
        break;
      case "alerts_cleared":
        setAlerts([]);
        setUnread(0);
        break;
      case "unread_count":
        setUnread(alertWsEvent.unread_count);
        break;
    }
  }, [alertWsEvent]);

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

  const handleOpen = () => setOpen((o) => !o);

  const handleClear = () => {
    api.clearRecentAlerts().catch(() => {});
    // Optimistic — the WS "alerts_cleared" event will confirm
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
                {alerts.map((a) => (
                  <AlertRow key={a.id} alert={a} onRead={markAlertRead} />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
