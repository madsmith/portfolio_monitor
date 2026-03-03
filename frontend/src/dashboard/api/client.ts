const TOKEN_KEY = "auth_token";

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string): void => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = (): void => localStorage.removeItem(TOKEN_KEY);

function authHeaders(): HeadersInit {
  return { Authorization: `Bearer ${getToken() ?? ""}` };
}

async function authGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: authHeaders() });
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

export const api = {
  login: async (
    username: string,
    password: string
  ): Promise<{ token?: string; error?: string }> => {
    const res = await fetch("/api/v1/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    return res.json();
  },

  getPortfolios: (): Promise<PortfolioSummary[]> =>
    authGet("/api/v1/portfolios"),

  getPortfolio: (id: string): Promise<PortfolioDetail> =>
    authGet(`/api/v1/portfolio/${id}`),

  getPreviousClose: (assetType: string, ticker: string): Promise<{ price: number; timestamp: string }> =>
    authGet(`/api/v1/price/${assetType}/${ticker}/previous-close`),
};
