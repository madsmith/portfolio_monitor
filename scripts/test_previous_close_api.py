"""
Diagnostic script: test get_daily_open_close_agg directly against the Massive API.

Bypasses the aggregate cache entirely so failures are not masked by cached data.
Tests several recent trading dates to isolate whether the issue is date-specific
or symbol-specific.

Usage:
    .venv/bin/python scripts/test_previous_close_api.py [TICKER ...]

    # Default: uses INTC and FLEX (the reported failing symbols) plus a
    #          known-stable symbol (AAPL) as a control.
    .venv/bin/python scripts/test_previous_close_api.py
    .venv/bin/python scripts/test_previous_close_api.py INTC FLEX MSFT AAPL
"""
import sys
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from massive import RESTClient as MassiveRESTClient, BadResponse
from massive.rest.aggs import DailyOpenCloseAgg
from urllib3.exceptions import RequestError

from portfolio_monitor.config import PortfolioMonitorConfig

CONFIG_PATH = Path("config/config.yaml")

# Trading days to probe, most recent first.  Adjust if today is a holiday.
# 2026-05-25 is Memorial Day (US market closed), so last close would be 2026-05-22.
_PROBE_DATES: list[datetime.date] = [
    datetime.date(2026, 5, 23),
    datetime.date(2026, 5, 22),
    datetime.date(2026, 5, 21),
    datetime.date(2026, 5, 20),
    datetime.date(2026, 5, 19),
]

_DEFAULT_TICKERS = ["INTC", "FLEX", "AAPL"]


def fetch_one(
    client: MassiveRESTClient,
    ticker: str,
    date: datetime.date,
) -> tuple[str, str]:
    """Return (outcome_label, detail_string) for one (ticker, date) call."""
    try:
        result = client.get_daily_open_close_agg(ticker=ticker, date=date)
    except BadResponse as e:
        return "BAD_RESPONSE", str(e)
    except RequestError as e:
        return "REQUEST_ERROR", str(e)
    except Exception as e:
        return "EXCEPTION", f"{type(e).__name__}: {e}"

    if not isinstance(result, DailyOpenCloseAgg):
        return "UNEXPECTED_TYPE", repr(type(result))

    status = result.status or "?"
    if status != "OK":
        return f"STATUS:{status}", repr(result)

    if None in (result.open, result.high, result.low, result.close):
        return "INCOMPLETE", repr(result)

    return "OK", f"O={result.open} H={result.high} L={result.low} C={result.close} V={result.volume}"


def main() -> None:
    tickers = sys.argv[1:] or _DEFAULT_TICKERS

    config = PortfolioMonitorConfig(CONFIG_PATH)
    client = MassiveRESTClient(
        config.massive_api_key,
        connect_timeout=config.massive_request_timeout,
        read_timeout=config.massive_request_timeout,
    )

    col_ticker = max(len(t) for t in tickers)
    col_date   = 10

    header = f"{'Ticker':<{col_ticker}}  {'Date':<{col_date}}  {'Outcome':<16}  Detail"
    print(header)
    print("-" * (len(header) + 20))

    for ticker in tickers:
        for date in _PROBE_DATES:
            outcome, detail = fetch_one(client, ticker, date)
            print(f"{ticker:<{col_ticker}}  {date}  {outcome:<16}  {detail}")
        print()


if __name__ == "__main__":
    main()
