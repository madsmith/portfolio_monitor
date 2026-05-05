import { getToken } from "./client";

export type AssetSymbol = {
  ticker: string;
  type: string;
};

export type PriceUpdateMessage = {
  type: "price_update";
  symbol: AssetSymbol;
  price: number;
};

export type PriceMessage = {
  type: "price";
  symbol: AssetSymbol;
  price: number;
  timestamp: string;
};

export type PreviousCloseMessage = {
  type: "previous_close";
  symbol: AssetSymbol;
  price: number;
  timestamp: string;
};

export type AuthenticatedMessage = {
  type: "authenticated";
};

export type AlertEntry = Record<string, unknown> & { id: string; read: boolean };

export type AlertEventMessage = {
  type: "alert_event";
  event: "fired" | "updated";
  alert: AlertEntry;
  unread_count: number;
};

export type AlertReadMessage = {
  type: "alert_read";
  alert_id: string;
  unread_count: number;
};

export type AllAlertsReadMessage = {
  type: "all_alerts_read";
  unread_count: number;
};

export type AlertsClearedMessage = {
  type: "alerts_cleared";
  unread_count: number;
};

export type UnreadCountMessage = {
  type: "unread_count";
  unread_count: number;
};

export type AlertWsMessage =
  | AlertEventMessage
  | AlertReadMessage
  | AllAlertsReadMessage
  | AlertsClearedMessage
  | UnreadCountMessage;

type IncomingMessage =
  | AuthenticatedMessage
  | PriceUpdateMessage
  | PriceMessage
  | PreviousCloseMessage
  | AlertEventMessage
  | AlertReadMessage
  | AllAlertsReadMessage
  | AlertsClearedMessage
  | UnreadCountMessage;

/** Called once per animation frame with all price updates received since the last flush. */
type PriceUpdateHandler = (msgs: PriceUpdateMessage[]) => void;
type PriceHandler = (msg: PriceMessage) => void;
type PreviousCloseHandler = (msg: PreviousCloseMessage) => void;
type AlertHandler = (msg: AlertWsMessage) => void;

/**
 * Manages a WebSocket connection to /api/v1/ws.
 *
 * Authentication: sends {"type":"authenticate","token":"..."} as the first
 * message after the socket opens; subscriptions are flushed only after the
 * server responds with {"type":"authenticated"}.
 * Reconnects automatically after 5 s on unexpected close.
 *
 * Price updates are buffered and delivered in batches via requestAnimationFrame
 * so rapid bursts (e.g. a full polling cycle) produce a single UI pass.
 */
export class PortfolioWebSocket {
  private ws: WebSocket | null = null;
  private handlers: PriceUpdateHandler[] = [];
  private priceHandlers: PriceHandler[] = [];
  private previousCloseHandlers: PreviousCloseHandler[] = [];
  private alertHandlers: AlertHandler[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;
  // Keyed by "ticker:type" to provide O(1) dedup
  private subscriptions: Map<string, AssetSymbol> = new Map();
  // Batching
  private pendingUpdates: PriceUpdateMessage[] = [];
  private rafHandle: number | null = null;

  private _key(s: AssetSymbol): string {
    return `${s.ticker}:${s.type}`;
  }

  connect(): void {
    this.closed = false;
    this._open();
  }

  private _open(): void {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/api/v1/ws`;
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "authenticate", token: getToken() ?? "" }));
    };

    ws.onmessage = ({ data }: MessageEvent) => {
      try {
        const msg = JSON.parse(data as string) as IncomingMessage;
        if (msg.type === "authenticated") {
          if (this.subscriptions.size > 0) {
            ws.send(JSON.stringify({ type: "subscribe", symbols: [...this.subscriptions.values()] }));
          }
        } else if (msg.type === "price") {
          for (const handler of this.priceHandlers) handler(msg);
        } else if (msg.type === "previous_close") {
          for (const handler of this.previousCloseHandlers) handler(msg);
        } else if (
          msg.type === "alert_event" ||
          msg.type === "alert_read" ||
          msg.type === "all_alerts_read" ||
          msg.type === "alerts_cleared" ||
          msg.type === "unread_count"
        ) {
          for (const handler of this.alertHandlers) handler(msg);
        } else if (msg.type === "price_update") {
          this.pendingUpdates.push(msg);
          if (this.rafHandle === null) {
            this.rafHandle = requestAnimationFrame(() => {
              this.rafHandle = null;
              const batch = this.pendingUpdates.splice(0);
              if (batch.length > 0) {
                for (const handler of this.handlers) handler(batch);
              }
            });
          }
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      this.ws = null;
      if (!this.closed) {
        this.reconnectTimer = setTimeout(() => this._open(), 5000);
      }
    };
  }

  subscribe(symbols: AssetSymbol[]): void {
    for (const s of symbols) this.subscriptions.set(this._key(s), s);
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "subscribe", symbols }));
    }
  }

  unsubscribe(symbols: AssetSymbol[]): void {
    for (const s of symbols) this.subscriptions.delete(this._key(s));
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "unsubscribe", symbols }));
    }
  }

  requestPrice(symbol: AssetSymbol): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "get_price", symbol }));
    }
  }

  requestPreviousClose(symbol: AssetSymbol): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "get_previous_close", symbol }));
    }
  }

  markAlertRead(alertId: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "mark_alert_read", alert_id: alertId }));
    }
  }

  markAllAlertsRead(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "mark_all_alerts_read" }));
    }
  }

  onPrice(handler: PriceHandler): () => void {
    this.priceHandlers.push(handler);
    return () => {
      this.priceHandlers = this.priceHandlers.filter((h) => h !== handler);
    };
  }

  onPreviousClose(handler: PreviousCloseHandler): () => void {
    this.previousCloseHandlers.push(handler);
    return () => {
      this.previousCloseHandlers = this.previousCloseHandlers.filter((h) => h !== handler);
    };
  }

  onAlert(handler: AlertHandler): () => void {
    this.alertHandlers.push(handler);
    return () => {
      this.alertHandlers = this.alertHandlers.filter((h) => h !== handler);
    };
  }

  onPriceUpdate(handler: PriceUpdateHandler): () => void {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  close(): void {
    this.closed = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.rafHandle !== null) {
      cancelAnimationFrame(this.rafHandle);
      this.rafHandle = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}
