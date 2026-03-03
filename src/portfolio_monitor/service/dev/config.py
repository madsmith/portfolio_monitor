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
