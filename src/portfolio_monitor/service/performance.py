import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.database.performance import PortfolioPerformanceModule
from portfolio_monitor.portfolio.service import PortfolioService

logger = logging.getLogger(__name__)


class PortfolioSnapshotService:
    """Writes hourly snapshots of each portfolio's total value and cost basis."""

    def __init__(
        self,
        portfolio_service: PortfolioService,
        performance_module: PortfolioPerformanceModule,
    ) -> None:
        self._portfolio_service: PortfolioService = portfolio_service
        self._performance_module: PortfolioPerformanceModule = performance_module
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        try:
            # Take an immediate snapshot; INSERT OR IGNORE prevents duplicates on restart.
            await self._take_snapshots(datetime.now(ZoneInfo("UTC")))

            while True:
                now = datetime.now(ZoneInfo("UTC"))
                next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                sleep_seconds = (next_hour - now).total_seconds()
                logger.debug("Portfolio snapshot sleeping %.0f seconds until next hour", sleep_seconds)
                await asyncio.sleep(sleep_seconds)
                await self._take_snapshots(datetime.now(ZoneInfo("UTC")))

        except asyncio.CancelledError:
            logger.debug("Portfolio snapshot loop cancelled")
            raise
        except Exception:
            logger.exception("Error in portfolio snapshot loop")

    async def _take_snapshots(self, now: datetime) -> None:
        recorded_at = now.replace(minute=0, second=0, microsecond=0)
        portfolios = self._portfolio_service.get_all_portfolios()
        count = 0
        for portfolio in portfolios:
            try:
                cost_basis_currency = portfolio.total_cost_basis
                if cost_basis_currency is None:
                    logger.warning("Skipping snapshot for portfolio %s (%s): total_cost_basis is None", portfolio.id, portfolio.name)
                    continue
                total_value_currency = portfolio.total_value
                total_value = float(total_value_currency._value) if total_value_currency is not None else None
                cost_basis = float(cost_basis_currency._value)
                self._performance_module.insert_snapshot(
                    portfolio_id=portfolio.id,
                    recorded_at=recorded_at,
                    total_value=total_value,
                    cost_basis=cost_basis,
                )
                logger.debug(
                    "Snapshot for portfolio %s (%s): value=%s basis=%s",
                    portfolio.id, portfolio.name, total_value, cost_basis,
                )
                count += 1
            except Exception:
                logger.exception("Error snapshotting portfolio %s (%s) — skipping", portfolio.id, portfolio.name)
        if count:
            logger.info("Wrote %d portfolio performance snapshot(s) at %s", count, recorded_at.isoformat())
