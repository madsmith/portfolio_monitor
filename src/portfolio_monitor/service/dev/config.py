import argparse
from pathlib import Path

from appconf import BindDefault

from portfolio_monitor.config.config import PortfolioMonitorConfig


class DevConfig(PortfolioMonitorConfig):
    """Dev mode config — inherits from PortfolioMonitorConfig.

    Only defines fields that differ from the base class or are dev-specific.
    All other settings (portfolio_path, credentials, etc.) are read from the
    config file exactly as in production.
    """

    # auth_key has a hardcoded dev default so the service works out of the box
    auth_key = BindDefault[str](
        "portfolio_monitor.auth_key",
        default="44fde1940cf3ddf9af4fcadbdd0852e575079543208e1e10e73daba9ac698f35",
    )

    # Dev runs two servers; control_panel_port is the extra one (API uses base port)
    control_panel_port = BindDefault[int](
        "portfolio_monitor.dev.control_panel_port", default=8401
    )

    # Dev-specific tuning knobs
    tick_interval = BindDefault[float]("portfolio_monitor.dev.tick_interval", default=5.0)
    prime_history_minutes = BindDefault[int](
        "portfolio_monitor.dev.prime_history_minutes", default=120
    )

    # OpenClaw alert delivery is opt-in in dev (suppressed by default)
    openclaw_alert_enable_http = BindDefault[bool](
        "portfolio_monitor.openclaw.alert_enable_http", default=False
    )
    openclaw_alert_enable_ws = BindDefault[bool](
        "portfolio_monitor.openclaw.alert_enable_ws", default=True
    )

    @classmethod
    def from_config_file(
        cls, config_path: Path, args: argparse.Namespace
    ) -> "DevConfig":
        return cls(config_path, args)


# Approximate prices for all portfolio symbols (Feb 2026)
SEED_PRICES: dict[str, float] = {
    # Stocks
    "AMD": 120.0,
    "AMZN": 225.0,
    "AAPL": 240.0,
    "APLD": 10.0,
    "DELL": 120.0,
    "META": 620.0,
    "MU": 95.0,
    "MSFT": 430.0,
    "NVDA": 140.0,
    "PLTR": 100.0,
    "RIVN": 15.0,
    "SBUX": 100.0,
    "STNE": 15.0,
    "TSM": 200.0,
    "WOLF": 8.0,
    # Crypto
    "XRP": 2.50,
    "BTC": 95000.0,
    "ETH": 3200.0,
    "ATOM": 8.0,
    "USDT": 1.00,
    "SOL": 200.0,
}
