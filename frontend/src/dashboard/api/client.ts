const TOKEN_KEY = "auth_token";
const USERNAME_KEY = "auth_username";
const ROLE_KEY = "auth_role";

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string): void => localStorage.setItem(TOKEN_KEY, token);
export const getUsername = (): string | null => localStorage.getItem(USERNAME_KEY);
export const getRole = (): string | null => localStorage.getItem(ROLE_KEY);

export const clearToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
  localStorage.removeItem(ROLE_KEY);
};

function authHeaders(): HeadersInit {
  return { Authorization: `Bearer ${getToken() ?? ""}` };
}

async function authGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: authHeaders() });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

async function authPut<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "PUT",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

async function authPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

async function authDelete<T>(path: string): Promise<T> {
  const res = await fetch(path, { method: "DELETE", headers: authHeaders() });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

export type PortfolioSummary = {
  id: string;
  name: string;
  total_value: number | null;
  total_cost_basis: number | null;
  total_profit_loss: number | null;
  profit_loss_percentage: number | null;
};

export type Lot = {
  date: string | null;
  quantity: string;
  price: number | null;
  cost_basis: number | null;
  fees: number | null;
  rebates: number | null;
};

export type Asset = {
  ticker: string;
  asset_type: string;
  total_quantity: string;
  cost_basis: number | null;
  current_price: number | null;
  current_value: number | null;
  profit_loss: number | null;
  profit_loss_percentage: number | null;
  lots: Lot[];
};

export type PortfolioDetail = PortfolioSummary & {
  stocks: Asset[];
  currencies: Asset[];
  crypto: Asset[];
};

export type AccountSummary = {
  username: string;
  role: string;
  is_default?: boolean;
};

export type AlertConfig = Record<string, unknown>;

export type PriceAggregate = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type DailyOpenClose = {
  symbol: { ticker: string; asset_type: string };
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  pre_market: number | null;
  after_hours: number | null;
};

export type PriceHistory = {
  symbol: { ticker: string; asset_type: string };
  from: string;
  to: string;
  aggregates: PriceAggregate[];
};

export type WatchlistSummary = {
  id: string;
  name: string;
  owner: string;
  entry_count: number;
};

export type WatchlistEntry = {
  ticker: string;
  asset_type: string;
  current_price: number | null;
  notes: string;
  target_buy: number | null;
  target_sell: number | null;
  time_added: string | null;
  initial_price: number | null;
  meta: Record<string, unknown>;
  alerts: Record<string, unknown>;
};

export type WatchlistDetail = {
  id: string;
  name: string;
  owner: string;
  entries: WatchlistEntry[];
};

export type DetectorArgSpec = {
  name: string;
  type: string;        // "float", "str", "int", etc.
  default?: number | string;  // absent means the arg is required
};

export type DetectorInfo = {
  name: string;
  args: DetectorArgSpec[];
};

export const api = {
  login: async (
    username: string,
    password: string
  ): Promise<{ token?: string; username?: string; role?: string; error?: string }> => {
    const res = await fetch("/api/v1/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    return res.json();
  },

  getMe: (): Promise<{ username: string; role: string }> =>
    authGet("/api/v1/me"),

  getPortfolios: (): Promise<PortfolioSummary[]> =>
    authGet("/api/v1/portfolios"),

  getPortfolio: (id: string): Promise<PortfolioDetail> =>
    authGet(`/api/v1/portfolio/${id}`),

  getPreviousClose: (assetType: string, ticker: string): Promise<{ open: number; high: number; low: number; close: number; volume: number; timestamp: string }> =>
    authGet(`/api/v1/price/${assetType}/${ticker}/previous-close`),

  getOpenClose: (assetType: string, ticker: string, date?: string, returnPrevious?: boolean): Promise<DailyOpenClose> => {
    const params = new URLSearchParams();
    if (date) params.set("date", date);
    if (returnPrevious) params.set("return_previous", "true");
    const qs = params.size ? `?${params}` : "";
    return authGet(`/api/v1/price/${assetType}/${ticker}/open-close${qs}`);
  },

  getPriceHistory: (assetType: string, ticker: string, last: string, span?: string): Promise<PriceHistory> => {
    const params = new URLSearchParams({ last });
    if (span) params.set("span", span);
    return authGet(`/api/v1/price/${assetType}/${ticker}/history?${params}`);
  },

  // Account management (admin only)
  getAccounts: (): Promise<AccountSummary[]> =>
    authGet("/api/v1/accounts"),

  createAccount: (username: string, password: string, role: string): Promise<AccountSummary> =>
    authPost("/api/v1/accounts", { username, password, role }),

  deleteAccount: (username: string): Promise<{ ok: boolean }> =>
    authDelete(`/api/v1/accounts/${encodeURIComponent(username)}`),

  updateAccountRole: (username: string, role: string): Promise<{ ok: boolean }> =>
    authPut(`/api/v1/accounts/${encodeURIComponent(username)}`, { role }),

  resetAccountPassword: (username: string, password: string): Promise<{ ok: boolean }> =>
    authPut(`/api/v1/accounts/${encodeURIComponent(username)}/password`, { password }),

  // Alert configs
  getMyAlerts: (): Promise<AlertConfig> =>
    authGet("/api/v1/me/alerts"),

  updateMyAlerts: (config: AlertConfig): Promise<{ ok: boolean }> =>
    authPut("/api/v1/me/alerts", config),

  getAccountAlerts: (username: string): Promise<AlertConfig> =>
    authGet(`/api/v1/accounts/${encodeURIComponent(username)}/alerts`),

  updateAccountAlerts: (username: string, config: AlertConfig): Promise<{ ok: boolean }> =>
    authPut(`/api/v1/accounts/${encodeURIComponent(username)}/alerts`, config),

  getDetectors: (): Promise<DetectorInfo[]> =>
    authGet("/api/v1/detectors"),

  // Watchlists
  getWatchlists: (): Promise<WatchlistSummary[]> =>
    authGet("/api/v1/watchlists"),

  getWatchlist: (id: string): Promise<WatchlistDetail> =>
    authGet(`/api/v1/watchlist/${id}`),
};
