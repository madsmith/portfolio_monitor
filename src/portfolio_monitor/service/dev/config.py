import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from portfolio_monitor.config.config import PortfolioMonitorConfig


@dataclass
class DevConfig:
    """Configuration for dev mode — loads shared settings from AppConfig,
    then applies dev-specific overrides."""

    portfolio_path: Path
    monitors: dict[str, dict[str, Any]]
    tick_interval: float = 5.0
    prime_history_minutes: int = 120
    host: str = "127.0.0.1"
    port: int = 8401
    api_port: int = 8400
    debug: bool = False
    auth_key: str = "44fde1940cf3ddf9af4fcadbdd0852e575079543208e1e10e73daba9ac698f35"
    dashboard_username: str = "admin"
    dashboard_password: str = "admin"
    openclaw_host: str = "127.0.0.1"
    openclaw_port: int = 18789
    openclaw_agent_id: str = ""
    openclaw_auth_key: str = (
        "345b2454f2ff62f76fefab3925ada29f5fe04c4ba838f08383f577955647be2e"
    )
    openclaw_session_key: str = ""
    openclaw_gateway_token: str = ""
    openclaw_gateway_password: str = ""
    openclaw_gateway_device_identity_file: Path = Path("config/device_identity.json")
    openclaw_alert_enable_http: bool = False
    openclaw_alert_enable_ws: bool = True

    @classmethod
    def from_config_file(
        cls, config_path: Path, args: argparse.Namespace
    ) -> "DevConfig":
        cfg = PortfolioMonitorConfig(config_path, args)
        return cls(
            portfolio_path=cfg.portfolio_path or Path("config/portfolios"),
            monitors=cfg.monitors,
            tick_interval=getattr(args, "tick_interval", 5.0),
            debug=cfg.debug,
            host=getattr(args, "host", None) or "127.0.0.1",
            port=getattr(args, "port", None) or 8401,
            dashboard_username=cfg.dashboard_username or "admin",
            dashboard_password=cfg.dashboard_password or "admin",
            openclaw_host=cfg.openclaw_host,
            openclaw_port=cfg.openclaw_port,
            openclaw_agent_id=cfg.openclaw_agent_id or "finance",
            openclaw_auth_key=cfg.openclaw_auth_key or "",
            openclaw_session_key=cfg.openclaw_session_key,
            openclaw_gateway_token=cfg.openclaw_gateway_token or "",
            openclaw_gateway_password=cfg.openclaw_gateway_password or "",
            openclaw_gateway_device_identity_file=cfg.openclaw_gateway_device_identity_file,
        )


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
