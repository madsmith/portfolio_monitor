import { useState } from "react";
import type { AlertEntry, AlertWsMessage } from "../api/ws";

export type AlertListState = { alerts: AlertEntry[]; unread: number };

/** Keep at most this many alerts in memory. */
const MAX_ALERTS = 100;

/** Pure reducer: apply one alert WebSocket message to the alert list. */
export function applyAlertWsEvent(state: AlertListState, ev: AlertWsMessage): AlertListState {
  switch (ev.type) {
    case "alert_event": {
      const incoming = ev.alert;
      const idx = state.alerts.findIndex((a) => a.id === incoming.id);
      const alerts = idx === -1
        ? [incoming, ...state.alerts].slice(0, MAX_ALERTS)
        : state.alerts.map((a, i) => (i === idx ? incoming : a));
      return { alerts, unread: ev.unread_count };
    }
    case "alert_read":
      return {
        alerts: state.alerts.map((a) => (a.id === ev.alert_id ? { ...a, read: true } : a)),
        unread: ev.unread_count,
      };
    case "alert_deleted":
      return { alerts: state.alerts.filter((a) => a.id !== ev.alert_id), unread: ev.unread_count };
    case "all_alerts_read":
      return { alerts: state.alerts.map((a) => ({ ...a, read: true })), unread: 0 };
    case "alerts_cleared":
      return { alerts: [], unread: 0 };
    case "unread_count":
      return { ...state, unread: ev.unread_count };
    default:
      return state;
  }
}

/**
 * Alert list state that follows a stream of WebSocket messages delivered as a
 * prop. Each new message object is applied exactly once, during render — the
 * React-recommended way to derive state from a changing prop (no effect, no
 * extra render pass).
 */
export function useAlertList(alertWsEvent: AlertWsMessage | null) {
  const [state, setState] = useState<AlertListState>({ alerts: [], unread: 0 });
  const [seenEvent, setSeenEvent] = useState<AlertWsMessage | null>(null);

  if (alertWsEvent && alertWsEvent !== seenEvent) {
    setSeenEvent(alertWsEvent);
    setState((s) => applyAlertWsEvent(s, alertWsEvent));
  }

  return [state, setState] as const;
}
