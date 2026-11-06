# Portfolio Manager CLI Reference

`portfolio-manager` provides command-specific usage via `portfolio-manager <command> -h` or
`portfolio-manager <command> <subcommand> -h`.

The environment variable `PORTFOLIO_MANAGER_TOKEN` is used to authenticate with the API.
The `PORTFOLIO_MANAGER_URL` environment variable sets the base URL (default: `http://127.0.0.1:8400`).

Both can also be passed as global flags: `--token TOKEN` and `--url URL`.

Most commands accept `--json` to output raw JSON instead of formatted tables.

---

## Login

```bash
portfolio-manager login --username USERNAME --password PASSWORD
```

*Does not require `PORTFOLIO_MANAGER_TOKEN`. Prints a bearer token — use the returned value as `PORTFOLIO_MANAGER_TOKEN` for subsequent calls.*

---

## Portfolio

`portfolio-manager portfolio <subcommand> [--json]`

```bash
portfolio-manager portfolio list                        # list all portfolios with summary (value, P&L, day change)
portfolio-manager portfolio show PORTFOLIO_ID           # show holdings detail for a specific portfolio
```

Portfolio `show` breaks down holdings by Stocks, Currencies, and Crypto sections with per-asset
price, quantity, value, day change, and P&L.

---

## Watchlist

`portfolio-manager watchlist <subcommand> [--json]`

### Listing and viewing

```bash
portfolio-manager watchlist list                        # list all watchlists (id, name, owner, entry count)
portfolio-manager watchlist show WATCHLIST_ID           # show entries for a watchlist with price, targets, and notes
```

*`list` and `show` support json output with the `--json` flag.*

### Common path: create a watchlist and populate it

```bash
# 1. Create
portfolio-manager watchlist create --name "My Watchlist"

# 2. Add entries (default type is stock; use --type for currency or crypto)
portfolio-manager watchlist add WATCHLIST_ID --ticker AAPL
portfolio-manager watchlist add WATCHLIST_ID --ticker BTC --type crypto
portfolio-manager watchlist add WATCHLIST_ID --ticker AAPL --buy 170.00 --sell 210.00 --notes "Watching for breakout"

# 3. Update an existing entry
portfolio-manager watchlist note   WATCHLIST_ID --ticker AAPL "Updated thesis"
portfolio-manager watchlist target WATCHLIST_ID --ticker AAPL --buy 165.00 --sell 220.00

# 4. Remove an entry
portfolio-manager watchlist remove WATCHLIST_ID --ticker AAPL

# 5. Delete the watchlist
portfolio-manager watchlist delete WATCHLIST_ID
```

### Metadata

Arbitrary key/value metadata can be attached to a watchlist entry:

```bash
portfolio-manager watchlist meta WATCHLIST_ID --ticker AAPL sector=technology conviction=high
```

### Entry alerts

Per-entry alert detectors can be configured on a watchlist entry. See `watchlist alert -h` for full options.

```bash
portfolio-manager watchlist alert show   WATCHLIST_ID --ticker AAPL
portfolio-manager watchlist alert set    WATCHLIST_ID --ticker AAPL --kind percent_change threshold=0.05
portfolio-manager watchlist alert remove WATCHLIST_ID --ticker AAPL --kind percent_change
```

---

## Price

All `price` output is OHLCV. See `portfolio-manager price -h` for full options.

```bash
portfolio-manager price TICKER                        # most recent 1m candle (stock by default)
portfolio-manager price TICKER --type crypto          # asset types: stock, currency, crypto
portfolio-manager price TICKER --previous-close       # previous session OHLCV
portfolio-manager price TICKER --open-close           # today's session OHLCV including pre-market and after-hours
portfolio-manager price TICKER --open-close --time 2026-01-15  # specific date session OHLCV with pre/after-hours
portfolio-manager price TICKER --time 2026-01-15      # single candle at a historical date (default span: 1m)
portfolio-manager price TICKER --time 2026-01-15 --span 1d     # single daily candle at a historical date
portfolio-manager price TICKER --last 1mo --span 1d   # range of daily candles for the last month
portfolio-manager price TICKER --last 7d --span 1h    # range of hourly candles for the last 7 days
```

*Also supports `--json` output.*

```bash
% portfolio-manager price AAPL --json          
{
  "symbol": {
    "ticker": "AAPL",
    "type": "stock"
  },
  "timestamp": "2026-04-24T18:00:00+00:00",
  "open": 269.803,
  "high": 269.875,
  "low": 269.71,
  "close": 269.72,
  "price": 269.72,
  "volume": 58367.395367
}

% portfolio-manager price AAPL --json --last 3m
[
  {
    "symbol": {
      "ticker": "AAPL",
      "type": "stock"
    },
    "timestamp": "2026-04-24T17:59:00+00:00",
    "open": 269.89,
    "high": 269.89,
    "low": 269.76,
    "close": 269.8055,
    "price": 269.8055,
    "volume": 51765.350678
  },
  {
    "symbol": {
      "ticker": "AAPL",
      "type": "stock"
    },
    "timestamp": "2026-04-24T18:00:00+00:00",
    "open": 269.803,
    "high": 269.875,
    "low": 269.71,
    "close": 269.72,
    "price": 269.72,
    "volume": 58367.395367
  }
]
```

---

## Alert

User-level alert configuration (applies across all monitored symbols). See `portfolio-manager alert -h` for full options.

```bash
portfolio-manager alert list                                            # show current alert config
portfolio-manager alert list-detectors                                  # show available detector kinds and args
portfolio-manager alert add    --kind percent_change threshold=0.05     # set default detector
portfolio-manager alert add    --kind SMA_deviation --symbol NVDA threshold=0.08 period=2h
portfolio-manager alert remove --kind percent_change                    # remove from default config
portfolio-manager alert remove --kind SMA_deviation --symbol NVDA
```

*`list` and `list-detectors` support json output with the `--json` flag.*

*Omitting `--symbol` applies the detector to the default config (all symbols not otherwise configured).*
