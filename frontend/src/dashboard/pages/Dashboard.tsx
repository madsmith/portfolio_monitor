import { useEffect, useRef, useState } from "react";
import { useMatch, useNavigate } from "react-router-dom";
import { api, clearToken, getUsername, type PortfolioDetail, type PortfolioSummary, type WatchlistSummary } from "../api/client";
import { type AlertWsMessage, type AssetSymbol as WsAssetSymbol, PortfolioWebSocket } from "../api/ws";
import { AlertsPane } from "../components/panes/AlertsPane";
import { AlertBell } from "../components/AlertBell";
import { applyPriceUpdate, computeTodayChange, prevCloseKey, type TodayChange } from "../lib/formatters";
import { OverviewPane } from "../components/panes/OverviewPane";
import { PortfolioDetailPane } from "../components/panes/PortfolioDetailPane";
import { PortfolioPerformancePane } from "../components/panes/PortfolioPerformancePane";
import { WatchlistsPane } from "../components/panes/WatchlistsPane";
import { WatchlistPerformancePane } from "../components/panes/WatchlistPerformancePane";
import SettingsPane from "../components/panes/SettingsPane";

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
  const perfMatch = useMatch("/portfolio/:id/performance");
  const settingsMatch = useMatch("/settings");
  const watchlistMatch = useMatch("/watchlist");
  const watchlistPerfMatch = useMatch("/watchlist/:id/performance");
  const alertsMatch = useMatch("/alerts");
  const activeId = (settingsMatch || watchlistMatch || watchlistPerfMatch || alertsMatch) ? null : (match?.params.id ?? perfMatch?.params.id ?? null);
  const isPerfActive = perfMatch !== null;
  const isSettingsActive = settingsMatch !== null;
  const isWatchlistActive = watchlistMatch !== null || watchlistPerfMatch !== null;
  const isAlertsActive = alertsMatch !== null;
  const currentUsername = getUsername();

  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [watchlists, setWatchlists] = useState<WatchlistSummary[]>([]);
  const [portfoliosLoading, setPortfoliosLoading] = useState(true);
  const [portfoliosError, setPortfoliosError] = useState<string | null>(null);
  const [addingPortfolio, setAddingPortfolio] = useState(false);
  const [newPortfolioName, setNewPortfolioName] = useState("");
  const [addPortfolioSaving, setAddPortfolioSaving] = useState(false);
  const [newlyCreatedId, setNewlyCreatedId] = useState<string | null>(null);

  const [detail, setDetail] = useState<PortfolioDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [prevClose, setPrevClose] = useState<Record<string, number>>({});
  const [portfolioTodayChange, setPortfolioTodayChange] = useState<Record<string, TodayChange>>({});

  const wsRef = useRef<PortfolioWebSocket | null>(null);
  const [alertWsEvent, setAlertWsEvent] = useState<AlertWsMessage | null>(null);

  // Promise caches — deduplicate requests within the current UTC hour. Keyed by
  // "<id>:<YYYY-MM-DDTHH>" so stale data is discarded at the top of each hour.
  const detailCacheRef = useRef<Record<string, Promise<PortfolioDetail>>>({});
  const prevCloseCacheRef = useRef<Record<string, Promise<Record<string, number>>>>({});

  function hourKey(id: string): string {
    return `${id}:${new Date().toISOString().slice(0, 13)}`;
  }

  function cachedDetail(id: string): Promise<PortfolioDetail> {
    const key = hourKey(id);
    detailCacheRef.current[key] ??= api.getPortfolio(id);
    return detailCacheRef.current[key];
  }

  function cachedPrevClose(d: PortfolioDetail): Promise<Record<string, number>> {
    const key = hourKey(d.id);
    prevCloseCacheRef.current[key] ??= Promise.allSettled(
      [...d.stocks, ...d.currencies, ...d.crypto].map((a) =>
        api.getPreviousClose(a.asset_type, a.ticker).then((data) => ({ key: prevCloseKey(a), price: data.close }))
      )
    ).then((results) => {
      const closes: Record<string, number> = {};
      for (const r of results) {
        if (r.status === "fulfilled") closes[r.value.key] = r.value.price;
      }
      return closes;
    });
    return prevCloseCacheRef.current[key];
  }

  // Connect WebSocket on mount, close on unmount
  useEffect(() => {
    const ws = new PortfolioWebSocket();
    wsRef.current = ws;
    ws.connect();
    const unsub = ws.onPriceUpdate((msgs) => {
      setDetail((prev) => prev ? msgs.reduce((d, { symbol, price }) => applyPriceUpdate(d, symbol.ticker, price), prev) : null);
    });
    const unsubAlert = ws.onAlert((msg) => setAlertWsEvent(msg));
    return () => { unsub(); unsubAlert(); ws.close(); wsRef.current = null; };
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
  const [watchlistRefreshKey, setWatchlistRefreshKey] = useState(0);
  useEffect(() => {
    let active = true;
    api.getWatchlists()
      .then((list) => { if (active) setWatchlists(list); })
      .catch(() => {});
    return () => { active = false; };
  }, [watchlistRefreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

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

  async function handleAddPortfolio() {
    if (!newPortfolioName.trim() || addPortfolioSaving) return;
    setAddPortfolioSaving(true);
    try {
      const created = await api.createPortfolio(newPortfolioName.trim());
      setPortfolios((prev) => [...prev, created]);
      setAddingPortfolio(false);
      setNewPortfolioName("");
      setNewlyCreatedId(created.id);
      navigate(`/portfolio/${created.id}`);
    } catch { /* silent */ }
    finally { setAddPortfolioSaving(false); }
  }

  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-300 pt-8 px-4">
      <div className="max-w-6xl mx-auto">

        <div className="flex items-baseline justify-between mb-4 px-1">
          <span className="text-xl font-semibold text-slate-100 tracking-wide">Portfolio Monitor</span>
          <div className="flex items-center gap-3">
            <AlertBell alertWsEvent={alertWsEvent} markAlertRead={(id) => wsRef.current?.markAlertRead(id)} markAllAlertsRead={() => wsRef.current?.markAllAlertsRead()} deleteAlert={(id) => wsRef.current?.deleteAlert(id)} onViewAll={() => navigate("/alerts")} />
            {currentUsername && (
              <span className="text-xs text-slate-500">{currentUsername}</span>
            )}
            <button
              onClick={() => { clearToken(); navigate("/login"); }}
              className="text-xs text-slate-600 hover:text-slate-400 transition-colors cursor-pointer"
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
              { value: "__add__", label: "+ Add portfolio…", go: () => setAddingPortfolio(true) },
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
                    if (v === "__add__") { setAddingPortfolio(true); return; }
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
        <div className="group/tabbar relative hidden sm:flex items-end gap-1">
          <Tab label="Overview" active={!isSettingsActive && !isWatchlistActive && !isAlertsActive && activeId === null} onClick={() => navigate("/")} />
          {portfolios.map((p) => (
            <Tab key={p.id} label={p.name} active={p.id === activeId} onClick={() => navigate(`/portfolio/${p.id}`)} />
          ))}
          <Tab label="Watchlists" active={isWatchlistActive} onClick={() => navigate("/watchlist")} />
          {/* Add portfolio button — visible on hover of tab bar, opens modal */}
          <button
            onClick={() => setAddingPortfolio(true)}
            className="opacity-0 group-hover/tabbar:opacity-100 transition-opacity px-3 py-2 text-sm font-medium rounded-t-md border-2 border-transparent hover:border-[#404868] hover:bg-[#13171f] text-slate-500 hover:text-slate-300 cursor-pointer min-w-[4em] text-center"
            title="Add portfolio"
          >
            +
          </button>
          <div className="flex-1" />
          <Tab label="Settings" active={isSettingsActive} onClick={() => navigate("/settings")} />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[2px] bg-[#404868]" />
        </div>

        {/* Add portfolio modal */}
        {addingPortfolio && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
            onMouseDown={(e) => { if (e.target === e.currentTarget) { setAddingPortfolio(false); setNewPortfolioName(""); } }}
          >
            <div className="bg-[#1a1e2e] border border-[#404868] rounded-lg shadow-2xl px-6 py-5 w-80">
              <h2 className="text-sm font-semibold text-slate-200 mb-3">New Portfolio</h2>
              <input
                autoFocus
                value={newPortfolioName}
                onChange={(e) => setNewPortfolioName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleAddPortfolio(); if (e.key === "Escape") { setAddingPortfolio(false); setNewPortfolioName(""); } }}
                placeholder="Portfolio name"
                className="w-full bg-[#0f1117] border border-[#404868] rounded px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-slate-500 mb-3"
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => { setAddingPortfolio(false); setNewPortfolioName(""); }}
                  className="px-3 py-1.5 text-sm rounded bg-[#2a2f45] text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddPortfolio}
                  disabled={addPortfolioSaving || !newPortfolioName.trim()}
                  className="px-3 py-1.5 text-sm rounded bg-[#2d4a3e] text-[#6bc98a] hover:bg-[#3a5e50] disabled:opacity-40 transition-colors cursor-pointer"
                >
                  {addPortfolioSaving ? "Creating…" : "Create"}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="bg-[#1e2130] border-2 border-[#404868] rounded-lg sm:rounded-t-none p-6 min-h-[120px]">
          {isAlertsActive ? (
            <AlertsPane alertWsEvent={alertWsEvent} markAlertRead={(id) => wsRef.current?.markAlertRead(id)} markAllAlertsRead={() => wsRef.current?.markAllAlertsRead()} deleteAlert={(id) => wsRef.current?.deleteAlert(id)} />
          ) : isSettingsActive ? (
            <SettingsPane />
          ) : watchlistPerfMatch ? (
            <WatchlistPerformancePane id={watchlistPerfMatch.params.id!} />
          ) : isWatchlistActive ? (
            <WatchlistsPane watchlists={watchlists} ws={wsRef} onMutated={() => setWatchlistRefreshKey((k) => k + 1)} />
          ) : activeId === null ? (
            <OverviewPane
              portfolios={portfolios}
              loading={portfoliosLoading}
              error={portfoliosError}
              onSelect={(id) => navigate(`/portfolio/${id}`)}
              todayChange={portfolioTodayChange}
            />
          ) : isPerfActive ? (
            <PortfolioPerformancePane
              detail={detail}
              loading={detailLoading}
              error={detailError}
            />
          ) : (
            <PortfolioDetailPane
              detail={detail}
              loading={detailLoading}
              error={detailError}
              prevClose={prevClose}
              initialEditing={detail?.id === newlyCreatedId}
              onMutated={(updated) => {
                const key = hourKey(updated.id);
                detailCacheRef.current[key] = Promise.resolve(updated);
                delete prevCloseCacheRef.current[key];
                setDetail(updated);
                cachedPrevClose(updated).then(setPrevClose).catch(() => {});
                const symbols = [...updated.stocks, ...updated.currencies, ...updated.crypto]
                  .map(toWsSymbol);
                wsRef.current?.subscribe(symbols);
              }}
              onDelete={async () => {
                if (!detail) return;
                await api.deletePortfolio(detail.id);
                setPortfolios((prev) => prev.filter((p) => p.id !== detail.id));
                setDetail(null);
                navigate("/");
              }}
            />
          )}
        </div>

      </div>
    </div>
  );
}
