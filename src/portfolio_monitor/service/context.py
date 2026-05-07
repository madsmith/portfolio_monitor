from dataclasses import dataclass

from starlette.requests import Request

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import DataProvider
from portfolio_monitor.data.database import AppDatabase
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.account import AccountStore
from portfolio_monitor.session import SessionStore
from portfolio_monitor.watchlist.service import WatchlistService


@dataclass(frozen=True)
class AuthContext:
    """Lightweight auth value object extracted from an authenticated request."""

    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @classmethod
    def from_request(cls, request: Request) -> "AuthContext":
        from portfolio_monitor.service.api.auth import PortfolioUser
        role = request.user.role if isinstance(request.user, PortfolioUser) else "normal"
        return cls(username=request.user.username, role=role)


@dataclass
class PortfolioMonitorContext:
    """Runtime context passed to API handlers — holds config and live services."""

    config: PortfolioMonitorConfig
    db: AppDatabase
    portfolio_service: PortfolioService
    watchlist_service: WatchlistService
    bus: EventBus
    data_provider: DataProvider
    account_store: AccountStore
    session_store: SessionStore
