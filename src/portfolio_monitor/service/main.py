import argparse
import asyncio
import logging
import secrets
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

import logfire
import uvicorn
from appconf.omegaconf import OmegaConfig, OmegaConfigLoader
from appconf.omegaconf.errors import PrivateConfigError
from omegaconf import OmegaConf
from starlette.applications import Starlette
from uvicorn.server import Server

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.aggregate_cache import AggregateCache
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.data.provider import PolygonDataProvider
from portfolio_monitor.detectors import DeviationEngine, DetectorRegistry
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.portfolio.loader import load_portfolios
from portfolio_monitor.portfolio.service import PortfolioService
from portfolio_monitor.service.alerts import (
    AlertRouter,
    LoggingAlertDelivery,
    OpenClawAgentHttpDelivery,
    OpenClawGatewayWsDelivery,
)
from portfolio_monitor.service.api import create_api_app
from portfolio_monitor.service.context import PortfolioMonitorContext
from portfolio_monitor.service.monitor import MonitorService
from portfolio_monitor.service.settings import AccountStore, SessionStore
from portfolio_monitor.service.types import AssetSymbol

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def _start_vite() -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec("pnpm", "dev", cwd=str(_FRONTEND_DIR))


async def run_service(config: PortfolioMonitorConfig, *, is_dev: bool = False) -> None:
    """Run the monitor service until interrupted"""

    if config.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)

    # Load portfolios
    if not config.portfolio_path:
        raise ValueError("Portfolio path not configured")

    portfolios = load_portfolios(config.portfolio_path)

    if config.debug:
        print("=== Portfolios     ===")
        for portfolio in portfolios:
            print(portfolio)
        print("=== End Portfolios ===")

    # Load aggregate cache
    aggregate_cache = AggregateCache(config.aggregate_cache_path)
    aggregate_cache.initialize()
    await aggregate_cache.load()

    # Create event bus
    bus = EventBus()

    # Wire aggregate cache to persist on AggregateUpdated
    async def _persist_aggregate(event: AggregateUpdated) -> None:
        await aggregate_cache.add(event.aggregate)

    bus.subscribe(AggregateUpdated, _persist_aggregate)

    # Create data provider
    data_provider = PolygonDataProvider(config, aggregate_cache)

    # Initialize account and session stores
    account_store = AccountStore(config.settings_path)
    account_store.load()

    # Seed default admin alerts from alerts.yaml on first run
    if not account_store.get_default_admin_alerts():
        try:
            raw = OmegaConfigLoader.load(Path("config/alerts.yaml"))
            resolved = OmegaConf.to_container(raw.get("alerts", {}), resolve=True)
            if isinstance(resolved, dict):
                account_store.set_default_admin_alerts(resolved)  # type: ignore[arg-type]
                account_store.save()
                logger.info("Seeded default admin alerts from config/alerts.yaml")
        except Exception as e:
            logger.warning("Could not seed alerts from alerts.yaml: %s", e)

    session_store = SessionStore(config.session_store_path)
    session_store.load()

    # Build per-account detection engine
    detection_engine, detector_accounts = _build_per_account_engine(
        account_store, portfolios, default_admin_username=config.dashboard_username or "default"
    )

    # Create services — subscriptions happen in constructors
    detection_service = DetectionService(
        bus=bus,
        detection_engine=detection_engine,
        data_provider=data_provider,
    )
    portfolio_service = PortfolioService(bus=bus, portfolios=portfolios)
    alert_router = AlertRouter(bus=bus)
    for detector_id, usernames in detector_accounts.items():
        for username in usernames:
            alert_router.register_detector_account(detector_id, username)
    if is_dev:
        # Suppress all alert delivery by default in dev mode;
        # detectors still process data and build history.
        alert_router.suppressed_detectors = {
            d.name
            for detectors in detection_engine.asset_detectors.values()
            for d in detectors
        }
    alert_router.add_target(LoggingAlertDelivery())
    # TODO: make configurable or state driven.
    if config.openclaw_alert_enable_http and config.openclaw_auth_key and config.openclaw_agent_id:
        alert_router.add_target(
            OpenClawAgentHttpDelivery(
                config.openclaw_host,
                config.openclaw_port,
                config.openclaw_auth_key,
                config.openclaw_agent_id,
                name="Portfolio Alert",
                session_key=config.openclaw_session_key,
            )
        )
    if config.openclaw_alert_enable_ws and (config.openclaw_gateway_token or config.openclaw_gateway_password) and config.openclaw_agent_id:
        alert_router.add_target(
            OpenClawGatewayWsDelivery(
                config.openclaw_host,
                config.openclaw_port,
                config.openclaw_agent_id,
                gateway_token=config.openclaw_gateway_token or None,
                gateway_password=config.openclaw_gateway_password or None,
                device_identity_file=config.openclaw_gateway_device_identity_file,
                name="Portfolio Alert",
                session_key=config.openclaw_session_key,
                extra_prompt=config.openclaw_alert_extra_prompt,
            )
        )

    monitor = MonitorService(
        bus=bus,
        data_provider=data_provider,
        portfolios=portfolios,
    )

    # Prime detection engine with historical data
    all_symbols: list[AssetSymbol] = list(
        {asset.symbol for portfolio in portfolios for asset in portfolio.assets()}
    )
    await detection_service.prime(all_symbols, datetime.now(ZoneInfo("UTC")))

    # Seed portfolio prices with the most recent available price (current bar preferred,
    # falling back to previous close when the market is closed and no live bar is available)
    logger.info("Seeding portfolio prices...")
    for symbol in all_symbols:
        agg = await data_provider.get_aggregate(symbol)
        if agg:
            await bus.publish(AggregateUpdated(symbol=symbol, aggregate=agg))

    # Start API server
    ctx = PortfolioMonitorContext(
        config=config,
        portfolio_service=portfolio_service,
        bus=bus,
        data_provider=data_provider,
        account_store=account_store,
        session_store=session_store,
    )
    api_app: Starlette = create_api_app(ctx)
    uvicorn_config = uvicorn.Config(
        api_app,
        host=config.host,
        port=config.port,
        log_level="debug" if config.debug else "info",
    )
    api_server: Server = uvicorn.Server(uvicorn_config)

    # Build control panel for dev-live mode (synthetic_source=None disables sim controls)
    cp_server: Server | None = None
    if is_dev:
        from portfolio_monitor.service.dev.control_panel.app import ControlPanelApp

        control_panel = ControlPanelApp(
            bus=bus,
            synthetic_source=None,
            detection_engine=detection_engine,
            detection_service=detection_service,
            alert_router=alert_router,
            aggregate_cache=aggregate_cache,
            portfolios=portfolios,
        )
        cp_uvicorn_config = uvicorn.Config(
            control_panel.app,
            host=config.host,
            port=config.control_panel_port,
            log_level="debug" if config.debug else "info",
        )
        cp_server = uvicorn.Server(cp_uvicorn_config)

        def _initiate_shutdown() -> None:
            control_panel.shutdown()
            cp_server.should_exit = True  # type: ignore[union-attr]
            api_server.should_exit = True

        control_panel._stop_callback = _initiate_shutdown

    vite_proc: asyncio.subprocess.Process | None = None
    try:
        await alert_router.connect_all()
        await monitor.start()
        if is_dev:
            vite_proc = await _start_vite()
            print(f"\nControl:   http://{config.host}:{config.control_panel_port}/")
            print(f"Dashboard: http://{config.host}:{config.port}/")
            print(f"Frontend:  http://127.0.0.1:5173/")
            print(f"API:       http://{config.host}:{config.port}/api/v1/health\n")
        if cp_server is not None:
            await asyncio.gather(api_server.serve(), cp_server.serve())
        else:
            await api_server.serve()
    except asyncio.CancelledError:
        logger.info("Main task cancelled, initiating graceful shutdown...")
    except Exception as e:
        logger.error("Error in service: %s", e)
        raise
    finally:
        if vite_proc is not None and vite_proc.returncode is None:
            vite_proc.terminate()
            await vite_proc.wait()

        try:
            if monitor.running:
                await monitor.stop()
        except Exception as e:
            logger.error("Error stopping monitor: %s", e)

        try:
            await alert_router.disconnect_all()
        except Exception as e:
            logger.error("Error disconnecting alert router: %s", e)

        try:
            await aggregate_cache.close()
        except Exception as e:
            logger.error("Error closing aggregate cache: %s", e)



def _build_per_account_engine(
    account_store: AccountStore,
    portfolios: list,
    default_admin_username: str = "default",
) -> tuple[DeviationEngine, dict[str, list[str]]]:
    """Build a DeviationEngine with one detector per (account × symbol × kind).

    Default configs are expanded into per-symbol detectors for all known symbols,
    skipping symbols where that account has a symbol-specific override of the same kind.

    Returns:
        engine: DeviationEngine with all account detectors registered as asset detectors.
        detector_accounts: mapping of detector_id → list of account usernames.
    """
    all_symbols: list[AssetSymbol] = list(
        {asset.symbol for portfolio in portfolios for asset in portfolio.assets()}
    )
    ticker_to_symbol: dict[str, AssetSymbol] = {s.ticker: s for s in all_symbols}

    account_configs: list[tuple[str, dict]] = [
        (default_admin_username, account_store.get_default_admin_alerts()),
    ] + [(a.username, a.alerts) for a in account_store.get_all()]

    # symbol → list of (detector, username) to register
    sym_detectors: dict[AssetSymbol, list[tuple[object, str]]] = {}
    detector_accounts: dict[str, list[str]] = {}

    for username, alert_config in account_configs:
        if not isinstance(alert_config, dict) or not alert_config:
            continue

        default_cfg = alert_config.get("default") or {}
        # ticker → set of kinds with symbol-specific override for this account
        sym_overrides: defaultdict[str, set[str]] = defaultdict(set)

        # Symbol-specific detectors
        for ticker, sym_cfg in alert_config.items():
            if ticker in ("default", "templates") or not isinstance(sym_cfg, dict):
                continue
            symbol = ticker_to_symbol.get(ticker)
            if symbol is None:
                logger.warning(
                    "Alert config for '%s' references unknown ticker '%s', skipping",
                    username,
                    ticker,
                )
                continue
            for kind, args in sym_cfg.items():
                if not isinstance(args, dict):
                    continue
                d = DetectorRegistry.create_detector(kind, args)
                if d is None:
                    continue
                sym_detectors.setdefault(symbol, []).append((d, username))
                detector_accounts.setdefault(d.detector_id, []).append(username)
                sym_overrides[ticker].add(kind)

        # Default detectors — expand to per-symbol, excluding overridden kinds
        if not isinstance(default_cfg, dict):
            continue
        for kind, args in default_cfg.items():
            if not isinstance(args, dict):
                continue
            for symbol in all_symbols:
                if kind in sym_overrides[symbol.ticker]:
                    continue
                d = DetectorRegistry.create_detector(kind, args)
                if d is None:
                    continue
                sym_detectors.setdefault(symbol, []).append((d, username))
                detector_accounts.setdefault(d.detector_id, []).append(username)

    engine = DeviationEngine()
    for symbol, pairs in sym_detectors.items():
        for detector, _ in pairs:
            engine.add_detector(symbol, detector)  # type: ignore[arg-type]

    return engine, detector_accounts


def generate_auth_key(config_path: Path) -> None:
    """Generate a random 256-bit auth key and save to the private config file."""
    private_path = config_path.with_name(config_path.stem + "_private.yaml")

    if private_path.exists():
        config = OmegaConf.load(private_path)
    else:
        config = OmegaConf.create()

    key = secrets.token_hex(32)
    OmegaConf.update(config, "private.portfolio_monitor.auth_key", key)
    OmegaConf.save(config, private_path)

    print(f"Auth key written to {private_path}")


def arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portfolio Monitor Service")
    subparsers = parser.add_subparsers(dest="command")

    # generate-auth-key subcommand
    subparsers.add_parser(
        "generate-auth-key",
        help="Generate a random auth key and save to private config",
    )

    # run subcommand (default)
    run_parser = subparsers.add_parser("run", help="Run the monitor service")
    run_parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )
    run_parser.add_argument("--host", type=str, help="Control interface host")
    run_parser.add_argument("--port", type=int, help="Control interface port")
    run_parser.add_argument("--auth-key", type=str, help="Authorization key")
    run_parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in dev mode with synthetic data (no API keys needed)",
    )
    run_parser.add_argument(
        "--dev-live",
        action="store_true",
        help="Run with live Polygon data but start Vite dev server for frontend development",
    )
    run_parser.add_argument(
        "--tick-interval",
        type=float,
        default=5.0,
        help="Dev mode: seconds between synthetic price ticks (default: 5.0)",
    )

    return parser


def _auth_key_exit() -> None:
    program_name = Path(sys.argv[0]).name
    print(f"Authorization key is not configured: ./{program_name} generate-auth-key")
    SystemExit(-1)


def main() -> None:
    parser = arg_parser()
    args = parser.parse_args()

    config_path = Path("config/config.yaml")

    if args.command == "generate-auth-key":
        generate_auth_key(config_path)
        return

    # Default to "run" when no subcommand given
    if args.command is None:
        args = parser.parse_args(["run"])


    # Dev mode — synthetic data, no Polygon API
    if args.dev:
        from portfolio_monitor.service.dev import run_dev_service
        from portfolio_monitor.service.dev.config import DevConfig

        dev_config = DevConfig.from_config_file(config_path, args)
        try:
            asyncio.run(run_dev_service(dev_config))
        except KeyboardInterrupt:
            logger.info("Shutting down dev mode [Ctrl+C]")
        return

    try:
        config = PortfolioMonitorConfig(config_path, args)
    except PrivateConfigError as e:
        if e.key == "private.portfolio_monitor.auth_key":
            return _auth_key_exit()
        else:
            raise e

    if args.dev_live:
        config.dev_console = True

    if not config.auth_key:
        return _auth_key_exit()

    # Set log level based on debug flag
    log_level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(level=log_level, format=logging.BASIC_FORMAT)

    logfire.configure(service_name="Portfolio Monitor")

    try:
        asyncio.run(run_service(config, is_dev=config.dev_console))
    except KeyboardInterrupt:
        logger.info("Shutting down [Ctrl+C]")


if __name__ == "__main__":
    main()
