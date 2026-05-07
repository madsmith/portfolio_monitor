# Portfolio Monitor

A self-hosted investment portfolio monitoring service with a real-time web dashboard, alert engine, watchlists, and CLI management tools.

## Features

- **Portfolio tracking** — multi-asset portfolios (stocks, crypto, currencies) with lot-level cost basis and P&L
- **Real-time dashboard** — live price updates via WebSocket; per-asset lot tables, day change, and portfolio totals
- **Alert engine** — pluggable detector system with per-user rules and alert delivery via configurable channels (Matrix)
- **Watchlists** — track symbols with notes, target buy/sell prices, and per-entry alert rules
- **Multi-user** — role-based accounts (admin/normal), per-portfolio access control, per-user alert configuration
- **CLI** — `portfolio-manager` client for querying portfolios, prices, alerts, and watchlists from the terminal

### Alert Detectors

| Detector | Description |
|---|---|
| Percent Change | Triggers when price moves by a set % over a rolling window |
| Price Value | Triggers when price crosses above or below a fixed level |
| SMA Deviation | Triggers when price deviates from its rolling SMA by a set % |
| Volume Spike | Triggers when volume exceeds a multiple of the rolling average |
| Average True Range | Triggers when the bar's range exceeds a multiple of ATR |
| Z-Score Return | Triggers on statistically significant return outliers |
| Z-Score Volume | Triggers on statistically significant volume outliers |

Rules can be scoped to a specific asset or applied globally across all tracked symbols.

## Requirements

- Python 3.12–3.13
- [Polygon.io](https://polygon.io) API key (market data)
- Node.js (frontend build)

## Installation

```bash
git clone https://github.com/madsmith/portfolio_monitor.git
cd portfolio_monitor

# Install with dev dependencies
uv pip install -e '.[dev]'

# Build the frontend
cd frontend && npm install && npm run build && cd ..
```

## Configuration

The application uses two YAML config files:

- `config/config.yaml` — main configuration (paths, dashboard credentials, integrations)
- `config/config_private.yaml` — secrets (API keys, passwords)

Minimal `config/config.yaml`:

```yaml
portfolio_monitor:
  datastore_path: "config/app_data.db"
  aggregate_cache_path: "config/aggregate_cache.db"
  auth_key: "${private.portfolio_monitor.auth_key}"

  dashboard:
    username: "${private.portfolio_monitor.dashboard.username}"
    password: "${private.portfolio_monitor.dashboard.password}"

polygon:
  api_key: "${private.polygon.api_key}"
```

Minimal `config/config_private.yaml`:

```yaml
portfolio_monitor:
  auth_key: "your-secret-auth-key"
  dashboard:
    username: "admin"
    password: "your-password"

polygon:
  api_key: "your-polygon-api-key"
```

Portfolios and watchlists are managed through the web dashboard or CLI and stored in the SQLite datastore.

## Running

```bash
# Start the service (default: http://localhost:8400)
portfolio-monitor

# With a custom config path
portfolio-monitor --config path/to/config.yaml
```

## CLI

```bash
portfolio-manager [--url URL] [--token TOKEN] COMMAND ...
```

### `login`
```bash
portfolio-manager login
```

### `portfolio`
```bash
portfolio-manager portfolio list
portfolio-manager portfolio show <id>
```

### `price`
```bash
portfolio-manager price TICKER [-t stock|crypto|currency]
  --previous-close             Previous session OHLCV
  --open-close [--time DATE]   Session OHLCV with pre/after-hours
  --daily-range [--from DATE]  Daily OHLCV over a date range
  --last PERIOD [--span SPAN]  Candle history (e.g. --last 7d --span 1h)
```

### `alert`
```bash
portfolio-manager alert list
portfolio-manager alert list-detectors
portfolio-manager alert add --ticker AAPL --kind percent_change threshold=0.03 period=1d
portfolio-manager alert remove <id>
```

### `watchlist`
```bash
portfolio-manager watchlist list
portfolio-manager watchlist show <id>
portfolio-manager watchlist create <name>
portfolio-manager watchlist delete <id>
portfolio-manager watchlist add <id> <ticker> [-t stock|crypto|currency]
portfolio-manager watchlist remove <id> <ticker>
portfolio-manager watchlist note <id> <ticker> <text>
portfolio-manager watchlist target <id> <ticker> [--buy PRICE] [--sell PRICE]
portfolio-manager watchlist meta <id> <ticker> KEY=VALUE ...
```

## Development

```bash
# Run tests
.venv/bin/python -m pytest

# Frontend dev server (proxies API to localhost:8400)
cd frontend && npm run dev
```

## License

MIT
