from dataclasses import dataclass

from starlette.requests import Request

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import DataProvider
from portfolio_monitor.portfolio import PortfolioService
from portfolio_monitor.service.settings import AccountStore, SessionStore
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
        role = next(
            (s.split(":", 1)[1] for s in request.auth.scopes if s.startswith("role:")),
            "normal",
        )
        return cls(username=request.user.display_name, role=role)


@dataclass
class PortfolioMonitorContext:
    """Runtime context passed to API handlers — holds config and live services."""

    config: PortfolioMonitorConfig
    portfolio_service: PortfolioService
    watchlist_service: WatchlistService
    bus: EventBus
    data_provider: DataProvider
    account_store: AccountStore
    session_store: SessionStore
