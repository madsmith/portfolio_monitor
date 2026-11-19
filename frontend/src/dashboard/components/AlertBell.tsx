import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AlertEntry, AlertWsMessage } from "../api/ws";
import { ChevronLeftIcon } from "./icons/ChevronLeftIcon";
import { CheckIcon } from "./icons/CheckIcon";
import { XIcon } from "./icons/XIcon";

const DISPLAY_LIMIT = 50;

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
    timerRef.current = setTimeout(() => onRead(alert.id), 3500);
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
        "group px-1.5 py-1 border-b border-[#2a2f45] last:border-0 cursor-pointer transition-colors hover:bg-[#323759]",
        alert.read ? "opacity-60" : "bg-[#1e2130]",
      ].join(" ")}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      <div className="flex items-center gap-1.5 min-w-0">
        <span className={["shrink-0 w-1 h-1 rounded-full", alert.read ? "bg-[#604040]" : "bg-[#9c4040]"].join(" ")} />
        <span
          className={["text-xs truncate flex-1 group-hover:text-slate-100", alert.read ? "text-slate-400" : "text-slate-200"].join(" ")}
          title={formatAlert(alert)}
        >
          {formatAlert(alert)}
        </span>
        <span className="text-[10px] text-slate-500 shrink-0">{formatAt(alert)}</span>
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
  markAllAlertsRead,
  onViewAll,
}: {
  alertWsEvent: AlertWsMessage | null;
  markAlertRead: (id: string) => void;
  markAllAlertsRead: () => void;
  onViewAll: () => void;
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
      case "alert_deleted":
        setAlerts((prev) => prev.filter((a) => a.id !== alertWsEvent.alert_id));
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
        className="relative p-1.5 rounded text-slate-400 hover:text-slate-200 hover:bg-[#2a2f45] transition-colors cursor-pointer"
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
            <button
              onClick={() => { onViewAll(); setOpen(false); }}
              className="flex items-center gap-1.5 text-sm font-medium text-slate-200 hover:text-slate-100 transition-colors cursor-pointer"
            >
              <ChevronLeftIcon />
              Recent Alerts
            </button>
            {alerts.length > 0 && (
              <div className="flex items-center gap-1">
                <button
                  onClick={markAllAlertsRead}
                  title="Mark all read"
                  className="p-1 rounded text-slate-400 hover:text-[#e2e8f0] hover:bg-[#404868] transition-colors cursor-pointer"
                >
                  <CheckIcon />
                </button>
                <button
                  onClick={handleClear}
                  title="Clear all"
                  className="p-1 rounded text-slate-400 hover:text-[#e2e8f0] hover:bg-[#404868] transition-colors cursor-pointer"
                >
                  <XIcon />
                </button>
              </div>
            )}
          </div>
          <div className="scrollbar-dark min-h-[80px] max-h-[360px] overflow-y-auto">
            {alerts.length === 0 ? (
              <p className="px-3 py-4 text-sm text-slate-500 text-center">No recent alerts</p>
            ) : (
              <ul>
                {alerts.slice(0, DISPLAY_LIMIT).map((a) => (
                  <AlertRow key={a.id} alert={a} onRead={markAlertRead} />
                ))}
              </ul>
            )}
          </div>
          {alerts.length >= DISPLAY_LIMIT && (
            <div className="px-3 py-2 border-t border-[#404868] text-center">
              <span className="text-xs text-slate-500">
                Showing {DISPLAY_LIMIT} most recent —{" "}
                <span className="text-slate-400 cursor-not-allowed" title="Coming soon">view all</span>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
