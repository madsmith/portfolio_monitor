"""Integration test: AggregateUpdated → DetectionService → AlertFired → AlertRouter → delivery target."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.detectors import (
    DeviationEngine,
    Detector,
    PercentChangeDetector,
    PercentChangeFromPreviousCloseDetector,
    AverageTrueRangeMoveDetector,
    SMADeviationDetector,
    VolumeSpikeDetector,
    ZScoreReturnDetector,
    ZScoreVolumeDetector,
)
from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.service.alerts import AlertRouter
from portfolio_monitor.service.alerts.delivery import AlertDelivery
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
BTC = AssetSymbol("BTC", AssetTypes.Crypto)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_aggregate(
    symbol: AssetSymbol,
    close: float,
    minutes_offset: int = 0,
    *,
    open: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: float = 1000.0,
) -> Aggregate:
    return Aggregate(
        symbol=symbol,
        date_open=NOW + timedelta(minutes=minutes_offset),
        open=open if open is not None else close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
        timespan=timedelta(minutes=1),
    )


@dataclass
class EventChain:
    """Fully wired event chain for integration tests."""

    bus: EventBus
    engine: DeviationEngine
    detection_service: DetectionService
    alert_router: AlertRouter
    mock_target: AsyncMock

    async def publish(self, symbol: AssetSymbol, aggregate: Aggregate) -> None:
        await self.bus.publish(AggregateUpdated(symbol=symbol, aggregate=aggregate))

    @property
    def delivered_alerts(self) -> list[Alert]:
        return [call.args[0] for call in self.mock_target.send_alert.call_args_list]


def build_chain(
    detectors: list[Detector],
    *,
    cooldown: timedelta = timedelta(seconds=0),
) -> EventChain:
    """Wire up EventBus → DetectionService → AlertRouter → mock target."""
    bus = EventBus()
    engine = DeviationEngine(default_detectors=detectors, cooldown=cooldown)
    data_provider = AsyncMock()
    detection_service = DetectionService(
        bus=bus, detection_engine=engine, data_provider=data_provider
    )
    alert_router = AlertRouter(bus=bus)
    mock_target = AsyncMock(spec=AlertDelivery)
    alert_router.add_target(mock_target)
    return EventChain(
        bus=bus,
        engine=engine,
        detection_service=detection_service,
        alert_router=alert_router,
        mock_target=mock_target,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def symbol() -> AssetSymbol:
    return BTC


# ---------------------------------------------------------------------------
# Basic event chain tests
# ---------------------------------------------------------------------------


class TestEventChainIntegration:
    """Publish AggregateUpdated, verify alert arrives at delivery target."""

    @pytest.mark.asyncio
    async def test_aggregate_triggers_alert_delivery(self, symbol: AssetSymbol) -> None:
        chain = build_chain([PercentChangeFromPreviousCloseDetector(threshold=0.05)])

        # First aggregate establishes baseline price
        await chain.publish(symbol, make_aggregate(symbol, close=100.0, minutes_offset=0))
        chain.mock_target.send_alert.assert_not_called()

        # Second aggregate: 10% jump should trigger alert
        await chain.publish(symbol, make_aggregate(symbol, close=110.0, minutes_offset=1))

        chain.mock_target.send_alert.assert_called_once()
        alert = chain.delivered_alerts[0]
        assert alert.ticker == symbol
        assert alert.kind == "percent_change_previous_close"
        assert alert.aggregate.close == 110.0

    @pytest.mark.asyncio
    async def test_small_change_no_alert(self, symbol: AssetSymbol) -> None:
        chain = build_chain([PercentChangeFromPreviousCloseDetector(threshold=0.05)])

        await chain.publish(symbol, make_aggregate(symbol, close=100.0, minutes_offset=0))
        # 1% move — below 5% threshold
        await chain.publish(symbol, make_aggregate(symbol, close=101.0, minutes_offset=1))

        chain.mock_target.send_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_detection_service_logs_alert(self, symbol: AssetSymbol) -> None:
        """DetectionService.get_recent_alerts returns fired alerts."""
        chain = build_chain([PercentChangeFromPreviousCloseDetector(threshold=0.05)])

        await chain.publish(symbol, make_aggregate(symbol, close=100.0, minutes_offset=0))
        await chain.publish(symbol, make_aggregate(symbol, close=110.0, minutes_offset=1))

        recent = chain.detection_service.get_recent_alerts()
        assert len(recent) == 1
        assert recent[0].ticker == symbol


# ---------------------------------------------------------------------------
# All-detectors integration (mirrors config.yaml all_detectors with defaults)
# ---------------------------------------------------------------------------


class TestAllDetectors:
    """Each detector fires through the full event chain when given extreme data."""

    @pytest.mark.asyncio
    async def test_percent_change_previous_close(self) -> None:
        chain = build_chain([PercentChangeFromPreviousCloseDetector()])  # threshold=0.03

        # Baseline
        await chain.publish(BTC, make_aggregate(BTC, close=100.0, minutes_offset=0))
        assert len(chain.delivered_alerts) == 0

        # 2% move — below 3% threshold
        await chain.publish(BTC, make_aggregate(BTC, close=102.0, minutes_offset=1))
        assert len(chain.delivered_alerts) == 0

        # 5% move from previous (102 → 107.1) — above threshold
        await chain.publish(BTC, make_aggregate(BTC, close=107.1, minutes_offset=2))
        assert len(chain.delivered_alerts) == 1
        assert chain.delivered_alerts[0].kind == "percent_change_previous_close"
        assert chain.delivered_alerts[0].aggregate.close == 107.1

    @pytest.mark.asyncio
    async def test_percent_change(self) -> None:
        # period="1m" so a 2-minute span gives enough history
        chain = build_chain([PercentChangeDetector(threshold=0.03, period="1m")])

        await chain.publish(BTC, make_aggregate(BTC, close=100.0, minutes_offset=0))
        assert len(chain.delivered_alerts) == 0

        # Small move within threshold
        await chain.publish(BTC, make_aggregate(BTC, close=101.0, minutes_offset=1))
        assert len(chain.delivered_alerts) == 0

        # 5% from reference — above threshold
        await chain.publish(BTC, make_aggregate(BTC, close=105.0, minutes_offset=2))
        assert len(chain.delivered_alerts) == 1
        assert chain.delivered_alerts[0].kind == "percent_change"
        assert chain.delivered_alerts[0].aggregate.close == 105.0

    @pytest.mark.asyncio
    async def test_average_true_range_move(self) -> None:
        # period=5 so we only need 6 samples before it can fire
        chain = build_chain([AverageTrueRangeMoveDetector(period=5, threshold=2.0)])

        # Build up 6 steady bars with narrow range (ATR ≈ 1.0)
        for i in range(6):
            await chain.publish(
                BTC, make_aggregate(BTC, close=100.0, minutes_offset=i, high=100.5, low=99.5)
            )
        assert len(chain.delivered_alerts) == 0

        # Bar with range slightly below 2x ATR — should not fire
        await chain.publish(
            BTC, make_aggregate(BTC, close=100.0, minutes_offset=6, high=100.8, low=99.2)
        )
        assert len(chain.delivered_alerts) == 0

        # Bar with range >> ATR — should fire
        await chain.publish(
            BTC, make_aggregate(BTC, close=105.0, minutes_offset=7, high=110.0, low=95.0)
        )
        assert len(chain.delivered_alerts) == 1
        assert chain.delivered_alerts[0].kind == "average_true_range_move"
        extra = chain.delivered_alerts[0].extra
        assert extra["range_multiple"] >= 2.0

    @pytest.mark.asyncio
    async def test_sma_deviation(self) -> None:
        # period="10m" so 10 minutes of history, threshold=0.05 (5%)
        chain = build_chain([SMADeviationDetector(period="10m", threshold=0.05)])

        # 10 bars at 100.0 establish the SMA
        for i in range(10):
            await chain.publish(BTC, make_aggregate(BTC, close=100.0, minutes_offset=i))
        assert len(chain.delivered_alerts) == 0

        # 3% above SMA — below 5% threshold
        await chain.publish(BTC, make_aggregate(BTC, close=103.0, minutes_offset=10))
        assert len(chain.delivered_alerts) == 0

        # 10% above SMA — above threshold
        await chain.publish(BTC, make_aggregate(BTC, close=110.0, minutes_offset=11))
        assert len(chain.delivered_alerts) == 1
        assert chain.delivered_alerts[0].kind == "SMA_deviation"
        extra = chain.delivered_alerts[0].extra
        assert extra["deviation_percent"] >= 5.0

    @pytest.mark.asyncio
    async def test_volume_spike(self) -> None:
        # period="10m", threshold=2.0 (volume >= 2x average)
        chain = build_chain([VolumeSpikeDetector(period="10m", threshold=2.0)])

        # 10 bars with volume=1000
        for i in range(10):
            await chain.publish(
                BTC, make_aggregate(BTC, close=100.0, minutes_offset=i, volume=1000.0)
            )
        assert len(chain.delivered_alerts) == 0

        # 1.5x average — below 2x threshold
        await chain.publish(
            BTC, make_aggregate(BTC, close=100.0, minutes_offset=10, volume=1500.0)
        )
        assert len(chain.delivered_alerts) == 0

        # 3x average — above threshold
        await chain.publish(
            BTC, make_aggregate(BTC, close=100.0, minutes_offset=11, volume=3000.0)
        )
        assert len(chain.delivered_alerts) == 1
        assert chain.delivered_alerts[0].kind == "volume_spike"
        extra = chain.delivered_alerts[0].extra
        assert extra["current_volume"] == 3000.0

    @pytest.mark.asyncio
    async def test_zscore_return(self) -> None:
        # period="10m", threshold=2.0
        chain = build_chain([ZScoreReturnDetector(period="10m", threshold=2.0)])

        # 10 bars with tiny stable returns
        for i in range(10):
            await chain.publish(
                BTC, make_aggregate(BTC, close=100.0 + i * 0.01, minutes_offset=i)
            )
        assert len(chain.delivered_alerts) == 0

        # Modest return within normal distribution — should not fire
        await chain.publish(BTC, make_aggregate(BTC, close=100.10, minutes_offset=10))
        assert len(chain.delivered_alerts) == 0

        # Huge return: jump to 120 — well beyond 2 std devs
        await chain.publish(BTC, make_aggregate(BTC, close=120.0, minutes_offset=11))
        assert len(chain.delivered_alerts) == 1
        assert chain.delivered_alerts[0].kind == "zscore_return"
        extra = chain.delivered_alerts[0].extra
        assert abs(extra["z_score"]) >= 2.0

    @pytest.mark.asyncio
    async def test_zscore_volume(self) -> None:
        # period="10m", threshold=1.0
        chain = build_chain([ZScoreVolumeDetector(period="10m", threshold=1.0)])

        # 10 bars with uniform volume
        for i in range(10):
            await chain.publish(
                BTC, make_aggregate(BTC, close=100.0, minutes_offset=i, volume=1000.0)
            )
        assert len(chain.delivered_alerts) == 0

        # Identical volume — z-score=0, should not fire
        await chain.publish(
            BTC, make_aggregate(BTC, close=100.0, minutes_offset=10, volume=1000.0)
        )
        assert len(chain.delivered_alerts) == 0

        # Volume spike well above 1 std dev
        await chain.publish(
            BTC, make_aggregate(BTC, close=100.0, minutes_offset=11, volume=5000.0)
        )
        assert len(chain.delivered_alerts) == 1
        assert chain.delivered_alerts[0].kind == "zscore_volume"
        extra = chain.delivered_alerts[0].extra
        assert extra["z_score"] > 1.0

    @pytest.mark.asyncio
    async def test_all_detectors_no_false_positives_on_stable_data(self) -> None:
        """All 7 detectors wired together produce no alerts on flat data."""
        chain = build_chain([
            PercentChangeFromPreviousCloseDetector(),
            PercentChangeDetector(period="10m"),
            AverageTrueRangeMoveDetector(period=5),
            SMADeviationDetector(period="10m"),
            VolumeSpikeDetector(period="10m"),
            ZScoreReturnDetector(period="10m"),
            ZScoreVolumeDetector(period="10m"),
        ])

        # 20 bars of completely flat price and volume
        for i in range(20):
            await chain.publish(
                BTC,
                make_aggregate(
                    BTC, close=100.0, minutes_offset=i, high=100.0, low=100.0, volume=1000.0
                ),
            )

        assert len(chain.delivered_alerts) == 0
