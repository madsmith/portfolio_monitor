import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { AlertEntry, AlertWsMessage } from "../../api/ws";

function formatAt(a: AlertEntry): string {
  const at = (a["updated_at"] ?? a["at"]) as string | undefined;
  if (!at) return "";
  try {
    return new Date(at).toLocaleString([], {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function formatMessage(a: AlertEntry): string {
  const msg = a["message"] as string | undefined;
  const ticker = (a["ticker"] as Record<string, unknown> | undefined)?.["ticker"] as string | undefined;
  const kind = a["kind"] as string | undefined;
  if (msg) return msg;
  return [ticker, kind].filter(Boolean).join(" — ") || "Alert";
}

export function AlertsPane({
  alertWsEvent,
  markAlertRead,
  markAllAlertsRead,
}: {
  alertWsEvent: AlertWsMessage | null;
  markAlertRead: (id: string) => void;
  markAllAlertsRead: () => void;
}) {
  const [alerts, setAlerts] = useState<AlertEntry[]>([]);
  const [unread, setUnread] = useState(0);
  const prevEvent = useRef<AlertWsMessage | null>(null);

  useEffect(() => {
    api.getRecentAlerts(100).then((res) => {
      setAlerts(res.alerts as AlertEntry[]);
      setUnread((res.alerts as AlertEntry[]).filter((a) => !a.read).length);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!alertWsEvent || alertWsEvent === prevEvent.current) return;
    prevEvent.current = alertWsEvent;

    switch (alertWsEvent.type) {
      case "alert_event": {
        const incoming = alertWsEvent.alert;
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

  const handleClear = () => {
    api.clearRecentAlerts().catch(() => {});
    setAlerts([]);
    setUnread(0);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-slate-100">Alerts</h2>
          {unread > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-[#9c4040] text-white text-[10px] font-bold leading-none">
              {unread}
            </span>
          )}
        </div>
        {alerts.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              onClick={markAllAlertsRead}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Mark all read
            </button>
            <span className="text-slate-600">·</span>
            <button
              onClick={handleClear}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Clear all
            </button>
          </div>
        )}
      </div>

      {alerts.length === 0 ? (
        <p className="text-sm text-slate-500 py-8 text-center">No recent alerts</p>
      ) : (
        <ul className="divide-y divide-[#2a2f45]">
          {alerts.map((a) => (
            <li
              key={a.id}
              onClick={() => { if (!a.read) markAlertRead(a.id); }}
              className={[
                "group flex items-center gap-3 py-2.5 px-2 rounded transition-colors cursor-default hover:bg-[#2a2f45]",
                a.read ? "opacity-60" : "",
              ].join(" ")}
            >
              <span className={["shrink-0 w-2 h-2 rounded-full", a.read ? "invisible" : "bg-[#9c4040]"].join(" ")} />
              <span className={["flex-1 text-sm group-hover:text-slate-100", a.read ? "text-slate-400" : "text-slate-200"].join(" ")}>
                {formatMessage(a)}
              </span>
              <span className="text-xs text-slate-500 shrink-0">{formatAt(a)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
