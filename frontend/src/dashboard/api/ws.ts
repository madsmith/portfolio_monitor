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

/** Called once per animation frame with all price updates received since the last flush. */
type PriceUpdateHandler = (msgs: PriceUpdateMessage[]) => void;

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
        const msg = JSON.parse(data as string) as { type: string } & Partial<PriceUpdateMessage>;
        if (msg.type === "authenticated") {
          if (this.subscriptions.size > 0) {
            ws.send(JSON.stringify({ type: "subscribe", symbols: [...this.subscriptions.values()] }));
          }
        } else if (msg.type === "price_update") {
          this.pendingUpdates.push(msg as PriceUpdateMessage);
          if (this.rafHandle === null) {
            this.rafHandle = requestAnimationFrame(() => {
              this.rafHandle = null;
              const batch = this.pendingUpdates.splice(0);
              if (batch.length > 0) {
                for (const h of this.handlers) h(batch);
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
