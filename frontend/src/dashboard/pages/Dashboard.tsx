import { useEffect, useRef, useState } from "react";
import { useMatch, useNavigate } from "react-router-dom";
import { api, clearToken, type PortfolioDetail, type PortfolioSummary } from "../api/client";
import { type AssetSymbol as WsAssetSymbol, PortfolioWebSocket } from "../api/ws";
import { applyPriceUpdate, computeTodayChange, prevCloseKey, type TodayChange } from "../lib/formatters";
import { Overview } from "../components/Overview";
import { PortfolioDetailContent } from "../components/PortfolioDetail";

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
  const activeId = match?.params.id ?? null;

  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [portfoliosLoading, setPortfoliosLoading] = useState(true);
  const [portfoliosError, setPortfoliosError] = useState<string | null>(null);

  const [detail, setDetail] = useState<PortfolioDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [prevClose, setPrevClose] = useState<Record<string, number>>({});
  const [portfolioTodayChange, setPortfolioTodayChange] = useState<Record<string, TodayChange>>({});

  const wsRef = useRef<PortfolioWebSocket | null>(null);

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
          ? { ...p, total_value: detail.total_value, total_profit_loss: detail.total_profit_loss, profit_loss_percentage: detail.profit_loss_percentage }
          : p
      )
    );
  }, [detail]);

  // Fetch portfolio list once. Also kicks off background detail+prevClose fetches for all
  // portfolios so the overview "Today's Chg" column is populated immediately.
  useEffect(() => {
    api
      .getPortfolios()
      .then((list) => {
        setPortfolios(list);
        for (const p of list) {
          api.getPortfolio(p.id).then((d) => {
            const allAssets = [...d.stocks, ...d.currencies, ...d.crypto];
            Promise.allSettled(
              allAssets.map((a) =>
                api.getPreviousClose(a.asset_type, a.ticker).then((data) => ({ key: prevCloseKey(a), price: data.price }))
              )
            ).then((results) => {
              const closes: Record<string, number> = {};
              for (const r of results) {
                if (r.status === "fulfilled") closes[r.value.key] = r.value.price;
              }
              const chg = computeTodayChange(d, closes);
              if (chg !== null) setPortfolioTodayChange((prev) => ({ ...prev, [d.id]: chg }));
            });
          }).catch(() => {});
        }
      })
      .catch((e: Error) => {
        if (e.message === "401") { clearToken(); navigate("/login"); return; }
        setPortfoliosError("Failed to load portfolios");
      })
      .finally(() => setPortfoliosLoading(false));
  }, [navigate]);

  // Fetch previous-close prices for the active portfolio
  useEffect(() => {
    if (!detail) { setPrevClose({}); return; }
    const allAssets = [...detail.stocks, ...detail.currencies, ...detail.crypto];
    Promise.allSettled(
      allAssets.map((a) =>
        api.getPreviousClose(a.asset_type, a.ticker).then((data) => ({ key: prevCloseKey(a), price: data.price }))
      )
    ).then((results) => {
      const closes: Record<string, number> = {};
      for (const r of results) {
        if (r.status === "fulfilled") closes[r.value.key] = r.value.price;
      }
      setPrevClose(closes);
      const chg = computeTodayChange(detail, closes);
      if (chg !== null) setPortfolioTodayChange((prev) => ({ ...prev, [detail.id]: chg }));
    });
  }, [detail?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch detail whenever the active portfolio changes
  useEffect(() => {
    if (!activeId) { setDetail(null); return; }
    setDetailLoading(true);
    setDetailError(null);
    api
      .getPortfolio(activeId)
      .then(setDetail)
      .catch((e: Error) => {
        if (e.message === "401") { clearToken(); navigate("/login"); return; }
        setDetailError(e.message === "404" ? "Portfolio not found" : "Failed to load portfolio");
      })
      .finally(() => setDetailLoading(false));
  }, [activeId, navigate]);

  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-300 pt-8 px-4">
      <div className="max-w-6xl mx-auto">

        <div className="flex items-baseline justify-between mb-4 px-1">
          <span className="text-xl font-semibold text-slate-100 tracking-wide">Portfolio Monitor</span>
          <button
            onClick={() => { clearToken(); navigate("/login"); }}
            className="text-xs text-slate-600 hover:text-slate-400 transition-colors"
          >
            Sign out
          </button>
        </div>

        <div className="flex items-end gap-1">
          <Tab label="Overview" active={activeId === null} onClick={() => navigate("/")} />
          {portfolios.map((p) => (
            <Tab key={p.id} label={p.name} active={p.id === activeId} onClick={() => navigate(`/portfolio/${p.id}`)} />
          ))}
          <div className="flex-1 border-b-2 border-[#404868]" />
        </div>

        <div className="bg-[#1e2130] border-2 border-[#404868] rounded-b-lg p-6">
          {activeId === null ? (
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
