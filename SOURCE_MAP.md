# Source Map — NexusPortfolioMonitor

Quick orientation for navigating the codebase. Start here before exploring files.

---

## Top-level layout

```
NexusPortfolioMonitor/
├── src/portfolio_monitor/   Python package (backend + service)
├── frontend/                React/TypeScript dashboard
├── tests/                   Pytest test suite
├── config/                  YAML configs, SQLite DBs, portfolios, watchlists
├── scripts/                 One-off utility scripts (DB migrations, plotting)
├── docs/                    Documentation
├── pyproject.toml           Package metadata, entry points, dependencies
├── Makefile                 Build/dev targets
└── pytest.ini               Pytest configuration
```

**Python:** 3.12–3.13 · **Framework:** Starlette/Uvicorn · **Frontend:** React + Vite + TypeScript  
**Package version:** see `src/portfolio_monitor/__init__.py`

---

## Entry points

| Command | Module | Purpose |
|---------|--------|---------|
| `portfolio-monitor` | `service/main.py:main` | Run the full service (API + WS + monitor) |
| `portfolio-manager` | `cli/main.py:main` | CLI tool (login, portfolio, prices, alerts, watchlist) |

---

## Backend — `src/portfolio_monitor/`

### `cli/` — Command-line tool (`portfolio-manager`)
- `main.py` — entry point, argparse dispatcher
- `commands/` — one file per subcommand: `login`, `portfolio`, `prices`, `alerts`, `watchlist`
- `display.py`, `request.py`, `utils.py` — formatting and HTTP helpers

### `config/`
- `config.py` — loads `config/config.yaml` + `config_private.yaml` via OmegaConf into `PortfolioMonitorConfig`

### `core/`
- `datetime.py` — datetime helpers (`eastern_midnight`, etc.)
- `currency.py` — currency conversion
- `permissions.py` — role-based permission checks
- `events/bus.py` — async event bus used throughout the service

### `data/` — Market data access
- `provider.py` — `DataProvider` protocol (interface)
- `polygon.py` — `PolygonDataProvider`: Polygon.io REST client, cache-first fetching, rate-limit + connectivity backoff, `_api_unavailable_until` circuit
- `aggregate_cache.py` — `AggregateCache` (SQLite + in-memory SortedDict); `MemoryOnlyAggregateCache`; `Aggregate` / `DailyOpenCloseAggregate` dataclasses
- `market_info.py` — `MarketInfo`: session windows, close times, market-closed checks; crypto = 24h UTC; stocks = 6h30m closing 21:00 UTC
- `timespan.py` — `AggregateTimespan` enum (minute, hour, day…)
- `database/` — SQLite persistence per domain: `accounts.py`, `alerts.py`, `portfolios.py`, `sessions.py`, `watchlists.py`

### `detectors/` — Alert detection algorithms
- `engine.py` — `DeviationEngine`: runs all detectors against incoming price ticks
- `service.py` — orchestrates the engine lifecycle
- `base.py` — abstract `Detector` base class
- `registry.py` — detector registration
- Individual detectors: `percent_change`, `price_value`, `volume_spike`, `moving_average_deviation`, `average_true_range_move`, `zscore_return`, `zscore_volume`

### `portfolio/` — Portfolio model
- `models/portfolio.py`, `asset.py`, `lot.py` — Portfolio → Asset → Lot hierarchy; all values via `@property`
- `service.py` — CRUD operations
- `events.py` — portfolio change events

### `watchlist/` — Watchlist model (mirrors portfolio structure)
- `models/watchlist.py`, `watchlist_entry.py`
- `service.py`, `events.py`

### `session/` — User sessions
- `store.py` — `SessionStore`: in-memory token → `SessionInfo`; tokens reset on restart
- `models/session.py`

### `account/` — User accounts
- `store.py` — `AccountStore`: loads/saves `config/settings.yaml`; CRUD for named accounts + default-admin alert config
- `models/account.py`
- `password.py` — PBKDF2 hashing (`pbkdf2:sha256:600000$salt$dk_hex`)

### `service/` — Application service layer
- `main.py` — service entry point; builds `DeviationEngine` (`_build_union_engine`), wires event hooks, starts Uvicorn
- `monitor.py` — `MarketMonitor`: periodic price-fetch loop, feeds detectors
- `context.py` — `AppContext` dependency container
- `types.py` — shared types: `AssetSymbol` (frozen dataclass, coerces `asset_type` to `AssetTypes`)
- `vite.py` — Vite dev server proxy integration

### `service/api/` — REST + WebSocket
- `app.py` — Starlette app factory; mounts v1 router, dashboard, auth middleware
- `auth.py` — `SessionBackend`: sets `AuthCredentials(["authenticated", "role:<role>"])` + `SimpleUser(username)`
- `v1/routes/` — one file per resource group:
  - `login.py` — POST login → `{token, username, role}`
  - `me.py` — GET/PUT `/me` and `/me/alerts`
  - `portfolios.py` — GET portfolio detail (includes lots sorted date-desc, nulls last)
  - `accounts.py` — admin CRUD for accounts
  - `watchlists.py`, `prices.py`, `market_info.py`, `detectors.py`, `health.py`
  - `admin_channels.py` — alert delivery channel config
- `v1/ws/manager.py` — `WebSocketManager`: takes `session_store`; broadcasts price/alert events
- `v1/ws/messages.py` — WebSocket message schemas

### `service/alerts/` — Alert routing and delivery
- `models.py` — `Alert` dataclass; `_KIND_VALUE_KEY` maps detector kind → `alert.extra` key
- `user_alert_manager.py` — per-user alert config management
- `channel_pool.py` — fan-out to multiple delivery channels
- `delivery/` — channels: `logging`, `dashboard_buffer`, `matrix` (Matrix.org), `openclaw_agent_http`, `openclaw_gateway_ws`

Alert routing: `AlertRouter` accepts `account_store` + `default_admin_username`; `_matched_accounts(alert)` finds accounts where measured value ≥ threshold (symbol-specific first, then default).

### `service/dev/` — Development mode
- `config.py` — `DevConfig` extends `PortfolioMonitorConfig`
- `seed_price_provider.py` — `SeedPriceProvider`: fetches previous-close from Polygon per asset; `get_prices() -> dict[str, float]`
- `synthetic_source.py` — `SyntheticDataSource`: generates fake ticks from seed prices
- `price_generator.py` — random-walk price generator
- `service.py` — dev service wiring
- `control_panel/` — Jinja2 HTML admin UI for dev mode

### `service/event_hooks/`
- `alert_adapter.py` — listens for detection events → routes alerts
- `watchlist_adapter.py` — listens for watchlist changes → updates monitor

### `utils/`
- `logfire.py` — Logfire span helpers (`get_trace_logger`, `logfire_set_attribute`)
- `trace.py` — tracing utilities

---

## Frontend — `frontend/src/`

**Build:** Vite · **Language:** TypeScript · **Package manager:** pnpm

### `dashboard/` — Main user-facing app

**Entry:** `main.tsx` → `App.tsx` → router → `Login.tsx` or `Dashboard.tsx`

#### `pages/`
- `Dashboard.tsx` — consolidated single-page view: file-folder tabs (Overview + one per portfolio + Settings for admin)
- `Login.tsx` — login form; stores `token`, `username`, `role` in `localStorage`

#### `components/`
- `Chart.tsx` — price OHLCV chart (lightweight-charts)
- `ChartControls.tsx` — range/timespan selector
- `Sparkline.tsx` — mini sparkline for price history
- `VolumeBars.tsx` — volume bar visualization
- `AlertBell.tsx` — notification bell with unread badge
- `AssetMenu.tsx` — asset picker dropdown
- `panes/` — tab content panels:
  - `OverviewPane.tsx` — portfolio summary cards
  - `PortfolioDetailPane.tsx` — asset + lot table; `AssetTable` tracks expanded rows as `Set<string>`
  - `PortfolioPerformancePane.tsx` — portfolio-level chart
  - `WatchlistsPane.tsx`, `WatchlistPerformancePane.tsx`
  - `AlertsPane.tsx` — live alert feed
  - `SettingsPane.tsx` — admin: `AccountsSection` (CRUD table + create form) + `AlertConfigsSection` (per-account alert editor)
- `perf/`
  - `PerfChartViews.tsx` — chart mode switcher
  - `IntradayView.tsx` — intraday chart using sampled aggregates
  - `PctBadge.tsx` — coloured percentage badge
- `buttons/`, `inputs/`, `icons/` — small reusable UI primitives

#### `api/client.ts`
HTTP + WS client. `getRole()` / `getUsername()` read `localStorage`. Types: `Lot`, `Asset` (with `lots: Lot[]`), `PortfolioDetail`, `PortfolioSummary`, `AccountSummary`, `AlertConfig`.

#### `lib/`
- `formatters.ts` — currency/number formatting
- `assetFormat.ts` — symbol display formatting
- `chartSettings.ts` — shared chart config
- `perfUtils.ts` — P&L and return calculations

### `control-panel/` — Dev admin UI
- `pages/ControlPanel.tsx` — controls for synthetic data, scenario triggers

### `public/`
- `icons/` — `favicon.svg`, `favicon.png`, app icons
- `sounds/` — alert audio files

---

## Tests — `tests/`

Run with: `.venv/bin/python -m pytest`

- `conftest.py` — shared fixtures
- `test_portfolio.py` — portfolio/asset/lot model
- `test_market_info.py` — session windows, close times
- `test_alert_models.py` — alert model and routing
- `test_currency.py` — currency conversion
- `test_permissions.py` — role permission checks
- `test_events.py` — event bus
- `test_integration_event_chain.py` — end-to-end event flow
- `detectors/` — one file per detector algorithm (`test_percent_change.py`, `test_volume_spike.py`, `test_zscore_return.py`, etc.)

---

## Config — `config/`

| File/Dir | Purpose |
|----------|---------|
| `config.yaml` | Main app config (ports, API keys references, feature flags) |
| `config_private.yaml` | Secrets: `dashboard.username`, `dashboard.password` (default admin) |
| `alerts.yaml` | Alert rule definitions; seeded into `default_admin_alerts` on first run |
| `settings.yaml` | Account store: named accounts + per-account alert configs |
| `datastore.db` | Primary SQLite DB (accounts, portfolios, watchlists) |
| `aggregate_cache.db` | Market data cache |
| `portfolios/<user>/<name>.yaml` | Portfolio definitions (lots, assets) |
| `watchlists/<user>/<name>.yaml` | Watchlist definitions |

---

## Scripts — `scripts/`

Diagnostic utilities (not part of the installed package):
- `plot_symbol.py` — plot price history for a symbol using matplotlib
- `test_matrix.py` — smoke-test Matrix.org alert delivery
