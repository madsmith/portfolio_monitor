import { useEffect, useRef, useState } from "react";
import { useMatch, useNavigate } from "react-router-dom";
import { api, clearToken, getUsername, type PortfolioDetail, type PortfolioSummary, type WatchlistSummary } from "../api/client";
import { type AssetSymbol as WsAssetSymbol, PortfolioWebSocket } from "../api/ws";
import { applyPriceUpdate, computeTodayChange, prevCloseKey, type TodayChange } from "../lib/formatters";
import { Overview } from "../components/Overview";
import { PortfolioDetailContent } from "../components/PortfolioDetail";
import { WatchlistView } from "../components/WatchlistView";
import Settings from "./Settings";

function toWsSymbol(a: { ticker: string; asset_type: string }): WsAssetSymbol {
  return { ticker: a.ticker, type: a.asset_type };
}

function Tab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={[
        "px-4 py-2 text-sm font-medium rounded-t-md border-2 border-[#404868] whitespace-nowrap transition-colors cursor-pointer",
        active
          ? "bg-[#1e2130] border-b-[#1e2130] text-slate-100 -mb-[2px] z-10 relative"
          : "bg-[#0b0e15] text-slate-400 hover:bg-[#13171f] hover:text-slate-300",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const match = useMatch("/portfolio/:id");
  const settingsMatch = useMatch("/settings");
  const watchlistMatch = useMatch("/watchlist");
  const activeId = (settingsMatch || watchlistMatch) ? null : (match?.params.id ?? null);
  const isSettingsActive = settingsMatch !== null;
  const isWatchlistActive = watchlistMatch !== null;
  const currentUsername = getUsername();

  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [watchlists, setWatchlists] = useState<WatchlistSummary[]>([]);
  const [portfoliosLoading, setPortfoliosLoading] = useState(true);
  const [portfoliosError, setPortfoliosError] = useState<string | null>(null);

  const [detail, setDetail] = useState<PortfolioDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [prevClose, setPrevClose] = useState<Record<string, number>>({});
  const [portfolioTodayChange, setPortfolioTodayChange] = useState<Record<string, TodayChange>>({});

  const wsRef = useRef<PortfolioWebSocket | null>(null);

  // Promise caches — deduplicate requests across background + foreground effects
  // and across React StrictMode's double-invocation.
  const detailCacheRef = useRef<Record<string, Promise<PortfolioDetail>>>({});
  const prevCloseCacheRef = useRef<Record<string, Promise<Record<string, number>>>>({});

  function cachedDetail(id: string): Promise<PortfolioDetail> {
    detailCacheRef.current[id] ??= api.getPortfolio(id);
    return detailCacheRef.current[id];
  }

  function cachedPrevClose(d: PortfolioDetail): Promise<Record<string, number>> {
    prevCloseCacheRef.current[d.id] ??= Promise.allSettled(
      [...d.stocks, ...d.currencies, ...d.crypto].map((a) =>
        api.getPreviousClose(a.asset_type, a.ticker).then((data) => ({ key: prevCloseKey(a), price: data.price }))
      )
    ).then((results) => {
      const closes: Record<string, number> = {};
      for (const r of results) {
        if (r.status === "fulfilled") closes[r.value.key] = r.value.price;
      }
      return closes;
    });
    return prevCloseCacheRef.current[d.id];
  }

  // Connect WebSocket on mount, close on unmount
  useEffect(() => {
    const ws = new PortfolioWebSocket();
    wsRef.current = ws;
    ws.connect();
    const unsub = ws.onPriceUpdate((msgs) => {
      setDetail((prev) => prev ? msgs.reduce((d, { symbol, price }) => applyPriceUpdate(d, symbol.ticker, price), prev) : null);
    });
    return () => { unsub(); ws.close(); wsRef.current = null; };
  }, []);

  // Subscribe to active portfolio's tickers whenever the loaded detail changes portfolio
  useEffect(() => {
    const ws = wsRef.current;
    if (!ws || !detail) return;
    const symbols = [
      ...detail.stocks.map(toWsSymbol),
      ...detail.currencies.map(toWsSymbol),
      ...detail.crypto.map(toWsSymbol),
    ];
    ws.subscribe(symbols);
    return () => ws.unsubscribe(symbols);
  }, [detail?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep portfolio summary totals in sync with live detail
  useEffect(() => {
    if (!detail) return;
    setPortfolios((prev) =>
      prev.map((p) =>
        p.id === detail.id
          ? {
              ...p,
              total_value: detail.total_value,
              total_profit_loss: detail.total_profit_loss,
              profit_loss_percentage: detail.profit_loss_percentage
            }
          : p
      )
    );
  }, [detail]);

  // Fetch watchlist summaries once
  useEffect(() => {
    let active = true;
    api.getWatchlists()
      .then((list) => { if (active) setWatchlists(list); })
      .catch(() => {});
    return () => { active = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch portfolio list once. Also kicks off background detail+prevClose fetches for all
  // portfolios so the overview "Today's Chg" column is populated immediately.
  useEffect(() => {
    let active = true;
    api.getPortfolios()
      .then((list) => {
        if (!active) return;
        setPortfolios(list);
        for (const p of list) {
          cachedDetail(p.id).then((d) => {
            if (!active) return;
            cachedPrevClose(d).then((closes) => {
              if (!active) return;
              const chg = computeTodayChange(d, closes);
              if (chg !== null) setPortfolioTodayChange((prev) => ({ ...prev, [d.id]: chg }));
            });
          }).catch(() => {});
        }
      })
      .catch((e: Error) => {
        if (!active) return;
        if (e.message === "401") { clearToken(); navigate("/login"); return; }
        setPortfoliosError("Failed to load portfolios");
      })
      .finally(() => { if (active) setPortfoliosLoading(false); });
    return () => { active = false; };
  }, [navigate]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch previous-close prices for the active portfolio
  useEffect(() => {
    if (!detail) { setPrevClose({}); return; }
    let active = true;
    cachedPrevClose(detail).then((closes) => {
      if (!active) return;
      setPrevClose(closes);
      const chg = computeTodayChange(detail, closes);
      if (chg !== null) setPortfolioTodayChange((prev) => ({ ...prev, [detail.id]: chg }));
    });
    return () => { active = false; };
  }, [detail?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load detail whenever the active portfolio changes
  useEffect(() => {
    if (!activeId) { setDetail(null); return; }
    let active = true;
    setDetailLoading(true);
    setDetailError(null);
    cachedDetail(activeId)
      .then((d) => { if (active) setDetail(d); })
      .catch((e: Error) => {
        if (!active) return;
        if (e.message === "401") { clearToken(); navigate("/login"); return; }
        setDetailError(e.message === "404" ? "Portfolio not found" : "Failed to load portfolio");
      })
      .finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; };
  }, [activeId, navigate]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-300 pt-8 px-4">
      <div className="max-w-6xl mx-auto">

        <div className="flex items-baseline justify-between mb-4 px-1">
          <span className="text-xl font-semibold text-slate-100 tracking-wide">Portfolio Monitor</span>
          <div className="flex items-center gap-3">
            {currentUsername && (
              <span className="text-xs text-slate-500">{currentUsername}</span>
            )}
            <button
              onClick={() => { clearToken(); navigate("/login"); }}
              className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>

        {/* Mobile: dropdown with prev/next arrows */}
        <div className="sm:hidden mb-3">
          {(() => {
            const pages = [
              { value: "overview", label: "Overview", go: () => navigate("/") },
              ...portfolios.map((p) => ({ value: p.id, label: p.name, go: () => navigate(`/portfolio/${p.id}`) })),
              ...(watchlists.length > 0 ? [{ value: "watchlist", label: "Watchlist", go: () => navigate("/watchlist") }] : []),
              { value: "settings", label: "Settings", go: () => navigate("/settings") },
            ];
            const currentValue = isSettingsActive ? "settings" : isWatchlistActive ? "watchlist" : (activeId ?? "overview");
            const currentIndex = pages.findIndex((p) => p.value === currentValue);
            const prev = currentIndex > 0 ? pages[currentIndex - 1] : null;
            const next = currentIndex < pages.length - 1 ? pages[currentIndex + 1] : null;
            const arrowCls = "flex items-center justify-center w-9 shrink-0 bg-[#1e2130] border border-[#404868] rounded-md text-slate-400 transition-colors";
            return (
              <div className="flex gap-2">
                <button
                  onClick={() => prev?.go()}
                  disabled={!prev}
                  className={`${arrowCls} ${prev ? "hover:text-slate-100 hover:border-slate-500 cursor-pointer" : "opacity-30 cursor-default"}`}
                  aria-label="Previous page"
                >
                  ‹
                </button>
                <select
                  value={currentValue}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v === "overview") navigate("/");
                    else if (v === "settings") navigate("/settings");
                    else if (v === "watchlist") navigate("/watchlist");
                    else navigate(`/portfolio/${v}`);
                  }}
                  className="flex-1 bg-[#1e2130] border border-[#404868] rounded-md px-3 py-2 text-sm text-slate-100 text-center focus:outline-none focus:border-slate-500 appearance-none cursor-pointer"
                >
                  {pages.map((p) => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
                <button
                  onClick={() => next?.go()}
                  disabled={!next}
                  className={`${arrowCls} ${next ? "hover:text-slate-100 hover:border-slate-500 cursor-pointer" : "opacity-30 cursor-default"}`}
                  aria-label="Next page"
                >
                  ›
                </button>
              </div>
            );
          })()}
        </div>

        {/* Desktop: tab bar */}
        <div className="relative hidden sm:flex items-end gap-1">
          <Tab label="Overview" active={!isSettingsActive && !isWatchlistActive && activeId === null} onClick={() => navigate("/")} />
          {portfolios.map((p) => (
            <Tab key={p.id} label={p.name} active={p.id === activeId} onClick={() => navigate(`/portfolio/${p.id}`)} />
          ))}
          {watchlists.length > 0 && (
            <Tab label="Watchlist" active={isWatchlistActive} onClick={() => navigate("/watchlist")} />
          )}
          <div className="flex-1" />
          <Tab label="Settings" active={isSettingsActive} onClick={() => navigate("/settings")} />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[2px] bg-[#404868]" />
        </div>

        <div className="bg-[#1e2130] border-2 border-[#404868] rounded-lg sm:rounded-t-none p-6">
          {isSettingsActive ? (
            <Settings />
          ) : isWatchlistActive ? (
            <WatchlistView watchlists={watchlists} />
          ) : activeId === null ? (
            <Overview
              portfolios={portfolios}
              loading={portfoliosLoading}
              error={portfoliosError}
              onSelect={(id) => navigate(`/portfolio/${id}`)}
              todayChange={portfolioTodayChange}
            />
          ) : (
            <PortfolioDetailContent
              detail={detail}
              loading={detailLoading}
              error={detailError}
              prevClose={prevClose}
            />
          )}
        </div>

      </div>
    </div>
  );
}
