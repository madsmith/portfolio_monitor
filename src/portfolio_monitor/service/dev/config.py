import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omegaconf import OmegaConf


@dataclass
class DevConfig:
    """Configuration for dev mode — bypasses PortfolioMonitorConfig entirely."""

    portfolio_path: Path
    monitors: dict[str, dict[str, Any]]
    tick_interval: float = 5.0
    prime_history_minutes: int = 120
    host: str = "127.0.0.1"
    port: int = 8401
    debug: bool = False

    @classmethod
    def from_config_file(cls, config_path: Path, args: argparse.Namespace) -> "DevConfig":
        raw = OmegaConf.load(config_path)
        portfolio_path = Path(OmegaConf.select(raw, "portfolio_monitor.portfolio_path"))
        monitors_raw = OmegaConf.select(raw, "portfolio_monitor.monitors") or {}
        monitors = OmegaConf.to_container(monitors_raw, resolve=False) or {"default": {}}
        return cls(
            portfolio_path=portfolio_path,
            monitors=monitors,
            tick_interval=getattr(args, "tick_interval", 5.0),
            debug=getattr(args, "debug", False),
            host=getattr(args, "host", None) or "127.0.0.1",
            port=getattr(args, "port", None) or 8401,
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
