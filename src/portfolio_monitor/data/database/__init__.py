from pathlib import Path

from .core import Database, DatabaseModule, MigrationStep
from .accounts import AccountRecord, AccountRole, AccountsModule
from .alerts import AlertChannelConfig, AlertChannelSub, AlertRule, AlertsModule
from .performance import PortfolioPerformanceModule
from .portfolios import PortfoliosModule
from .sessions import SessionRecord, SessionsModule
from .watchlists import WatchlistsModule


class AppDatabase(Database):
    """Concrete database with typed accessors for each module."""

    accounts: AccountsModule
    alerts: AlertsModule
    performance: PortfolioPerformanceModule
    portfolios: PortfoliosModule
    sessions: SessionsModule
    watchlists: WatchlistsModule

    def __init__(self, path: Path) -> None:
        self.accounts = AccountsModule()
        self.alerts = AlertsModule()
        self.performance = PortfolioPerformanceModule()
        self.portfolios = PortfoliosModule()
        self.sessions = SessionsModule()
        self.watchlists = WatchlistsModule()
        super().__init__(path, [
            self.accounts,
            self.alerts,
            self.performance,
            self.portfolios,
            self.sessions,
            self.watchlists,
        ])


__all__ = [
    "AppDatabase",
    "Database",
    "DatabaseModule",
    "MigrationStep",
    "AccountRecord",
    "AccountRole",
    "AccountsModule",
    "AlertChannelConfig",
    "AlertChannelSub",
    "AlertRule",
    "AlertsModule",
    "PortfolioPerformanceModule",
    "PortfoliosModule",
    "SessionRecord",
    "SessionsModule",
    "WatchlistsModule",
]
