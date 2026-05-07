import logging

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.database.alerts import AlertsModule
from portfolio_monitor.detectors.engine import DeviationEngine
from portfolio_monitor.detectors.registry import DetectorRegistry
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.service.alerts.models import AlertRule as ServiceAlertRule
from portfolio_monitor.service.alerts.events import AlertRuleAdded, AlertRuleRemoved, AlertRuleUpdated
from portfolio_monitor.service.alerts.user_alert_manager import UserAlertManager
from portfolio_monitor.service.types import AssetSymbol, AssetTypes
from portfolio_monitor.watchlist.service import WatchlistService

logger = logging.getLogger(__name__)


class AlertConfigAdapter:
    """Syncs DB alert rules → DeviationEngine detectors + UserAlertManager mapping.

    Call wire(bus) then load_all() at startup after portfolio/watchlist services
    are ready. Rule change events keep the engine in sync at runtime.
    """

    def __init__(
        self,
        engine: DeviationEngine,
        alert_manager: UserAlertManager,
        detection_service: DetectionService,
        portfolio_service: PortfolioService,
        watchlist_service: WatchlistService,
        alerts_module: AlertsModule,
    ) -> None:
        self._engine: DeviationEngine = engine
        self._alert_manager: UserAlertManager = alert_manager
        self._detection_service: DetectionService = detection_service
        self._portfolio_service: PortfolioService = portfolio_service
        self._watchlist_service: WatchlistService = watchlist_service
        self._alerts_module: AlertsModule = alerts_module
        # rule id → [(symbol, detector_id)] for cleanup on remove/update
        self._rule_detectors: dict[str, list[tuple[AssetSymbol, str]]] = {}

    def wire(self, bus: EventBus) -> None:
        bus.subscribe(AlertRuleAdded, self._on_rule_added)
        bus.subscribe(AlertRuleRemoved, self._on_rule_removed)
        bus.subscribe(AlertRuleUpdated, self._on_rule_updated)

    def load_all(self) -> None:
        """Load all DB rules and register detectors. Call once at startup."""
        rules = self._alerts_module.get_all_rules()
        logger.info("AlertConfigAdapter: loading %d rules from DB", len(rules))
        for db_rule in rules:
            service_rule = ServiceAlertRule(
                id=db_rule.id,
                ticker=db_rule.ticker or "",
                kind=db_rule.kind,
                args=db_rule.args,
            )
            self._register_rule(db_rule.owner, service_rule)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_rule_added(self, event: AlertRuleAdded) -> None:
        self._register_rule(event.username, event.rule)

    async def _on_rule_removed(self, event: AlertRuleRemoved) -> None:
        self._unregister_rule(event.rule.id)

    async def _on_rule_updated(self, event: AlertRuleUpdated) -> None:
        self._unregister_rule(event.old_rule.id)
        self._register_rule(event.username, event.new_rule)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_rule(self, username: str, rule: ServiceAlertRule) -> None:
        symbols = self._symbols_for_rule(rule.ticker, rule.args.get("asset_type"))
        if not symbols:
            logger.warning(
                "Rule %s (ticker=%r) matched no known symbols — skipping",
                rule.id, rule.ticker,
            )
        registered: list[tuple[AssetSymbol, str]] = []
        for symbol in symbols:
            detector = DetectorRegistry.create_detector(rule.kind, rule.args)
            if detector is None:
                logger.error(
                    "Unknown detector kind %r for rule %s — skipping symbol %s",
                    rule.kind, rule.id, symbol,
                )
                continue
            self._engine.add_detector(symbol, detector)
            self._alert_manager.register_detector_account(detector.detector_id, username)
            registered.append((symbol, detector.detector_id))
            logger.debug(
                "Registered detector %r for symbol %s (rule=%s, user=%s)",
                rule.kind, symbol, rule.id, username,
            )
        self._rule_detectors[rule.id] = registered

    def apply_rules_to_symbol(self, symbol: AssetSymbol, owner: str) -> None:
        """Register detectors for a newly-tracked symbol against the owner's existing rules.

        Called by WatchlistAdapter when a new entry is added post-startup.
        """
        for db_rule in self._alerts_module.get_rules(owner):
            if db_rule.ticker and db_rule.ticker != symbol.ticker:
                continue
            asset_type_hint = db_rule.args.get("asset_type")
            if asset_type_hint and asset_type_hint != symbol.asset_type.value:
                continue
            detector = DetectorRegistry.create_detector(db_rule.kind, db_rule.args)
            if detector is None:
                continue
            self._engine.add_detector(symbol, detector)
            self._alert_manager.register_detector_account(detector.detector_id, owner)
            self._rule_detectors.setdefault(db_rule.id, []).append((symbol, detector.detector_id))
            logger.debug("Applied rule %s to new symbol %s (user=%s)", db_rule.id, symbol, owner)

    def remove_rules_from_symbol(self, symbol: AssetSymbol, owner: str) -> None:
        """Remove detectors for a symbol being removed from a watchlist.

        Called by WatchlistAdapter when an entry is deleted.
        """
        for rule_id, registrations in self._rule_detectors.items():
            to_remove = [(s, did) for s, did in registrations if s == symbol]
            for s, detector_id in to_remove:
                self._engine.remove_detector(s, detector_id)
                self._alert_manager.unregister_detector_account(detector_id)
                registrations.remove((s, detector_id))
            logger.debug("Removed detectors for symbol %s (user=%s)", symbol, owner)

    def _unregister_rule(self, rule_id: str) -> None:
        registrations = self._rule_detectors.pop(rule_id, [])
        for symbol, detector_id in registrations:
            self._engine.remove_detector(symbol, detector_id)
            self._alert_manager.unregister_detector_account(detector_id)

    def _symbols_for_rule(
        self, ticker: str, asset_type_hint: str | None
    ) -> list[AssetSymbol]:
        """Resolve a rule's ticker to concrete AssetSymbol instances.

        ticker="" means the rule applies to all tracked symbols.
        ticker set means match that specific ticker across portfolios/watchlists.
        If a specific ticker isn't tracked yet and asset_type_hint is given,
        constructs the symbol so detectors are pre-registered for it.
        """
        all_symbols: set[AssetSymbol] = set()
        for portfolio in self._portfolio_service.get_all_portfolios():
            for asset in portfolio.assets():
                all_symbols.add(asset.symbol)
        for wl in self._watchlist_service.get_all_watchlists():
            for entry in wl.entries:
                all_symbols.add(entry.symbol)

        if not ticker:
            if asset_type_hint:
                return [s for s in all_symbols if s.asset_type.value == asset_type_hint]
            return list(all_symbols)

        matches = [s for s in all_symbols if s.ticker == ticker]
        if not matches and asset_type_hint:
            try:
                matches = [AssetSymbol(ticker, AssetTypes(asset_type_hint))]
            except ValueError:
                logger.warning(
                    "Invalid asset_type %r for rule ticker %r", asset_type_hint, ticker
                )
        return matches
