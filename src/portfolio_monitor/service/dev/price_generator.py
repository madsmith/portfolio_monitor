import math
import random
from dataclasses import dataclass
from enum import Enum


class Regime(Enum):
    CALM = "calm"
    VOLATILE = "volatile"


@dataclass
class RegimeParams:
    drift_annual: float  # annualized drift (mu)
    volatility_annual: float  # annualized volatility (sigma)
    base_volume: float  # base volume per tick
    volume_sensitivity: float  # how much volume scales with |price_change|


REGIME_DEFAULTS: dict[Regime, RegimeParams] = {
    Regime.CALM: RegimeParams(
        drift_annual=0.05,
        volatility_annual=0.15,
        base_volume=100_000,
        volume_sensitivity=5.0,
    ),
    Regime.VOLATILE: RegimeParams(
        drift_annual=0.0,
        volatility_annual=0.45,
        base_volume=200_000,
        volume_sensitivity=10.0,
    ),
}


@dataclass
class SymbolState:
    price: float
    regime: Regime = Regime.CALM
    bias: float = 0.0  # cumulative bias, decays each tick
    bias_decay: float = 0.0  # multiplicative decay factor per tick (e.g. 0.7)


class PriceGenerator:
    """Generates synthetic OHLCV data using Geometric Brownian Motion."""

    # Seconds in a trading year (252 days * 6.5 hours)
    _TRADING_YEAR_SECONDS = 252 * 6.5 * 3600

    def __init__(self, tick_interval_seconds: float = 5.0) -> None:
        self._tick_interval = tick_interval_seconds
        self._dt: float = tick_interval_seconds / self._TRADING_YEAR_SECONDS
        self._states: dict[str, SymbolState] = {}

    @property
    def tick_interval(self) -> float:
        return self._tick_interval

    @tick_interval.setter
    def tick_interval(self, value: float) -> None:
        self._tick_interval = value
        self._dt = value / self._TRADING_YEAR_SECONDS

    def register_symbol(self, ticker: str, initial_price: float) -> None:
        self._states[ticker] = SymbolState(price=initial_price)

    def add_bias(self, ticker: str, bias_pct: float) -> None:
        """Add a decaying bias (e.g. 0.03 for +3%).

        The bias is cumulative — calling multiple times stacks.
        It decays exponentially over a random 3-7 tick window.
        """
        if ticker in self._states:
            state = self._states[ticker]
            state.bias += bias_pct
            # Pick a decay rate so bias reaches ~5% of original in 3-7 ticks
            # decay^n ≈ 0.05  →  decay = 0.05^(1/n)
            n = random.randint(3, 7)
            state.bias_decay = 0.05 ** (1 / n)

    def set_regime(self, ticker: str, regime: Regime) -> None:
        if ticker in self._states:
            self._states[ticker].regime = regime

    def set_global_regime(self, regime: Regime) -> None:
        for state in self._states.values():
            state.regime = regime

    def get_price(self, ticker: str) -> float | None:
        state = self._states.get(ticker)
        return state.price if state else None

    def tick(self, ticker: str) -> tuple[float, float, float, float, float]:
        """Generate next OHLCV bar. Returns (open, high, low, close, volume)."""
        state = self._states[ticker]
        params = REGIME_DEFAULTS[state.regime]

        open_price = state.price
        sigma = params.volatility_annual
        mu = params.drift_annual

        # Apply decaying bias
        bias = state.bias
        if abs(bias) > 1e-8:
            state.bias *= state.bias_decay
        else:
            state.bias = 0.0

        # GBM step: S(t+dt) = S(t) * exp((mu - sigma^2/2)*dt + sigma*sqrt(dt)*Z + bias)
        z = random.gauss(0, 1)
        drift_term = (mu - 0.5 * sigma**2) * self._dt + bias
        diffusion_term = sigma * math.sqrt(self._dt) * z
        close_price = open_price * math.exp(drift_term + diffusion_term)

        # Intra-bar high/low
        intra_spread = abs(close_price - open_price) * 0.5
        high = max(open_price, close_price) + abs(random.gauss(0, 1)) * intra_spread * 0.3
        low = min(open_price, close_price) - abs(random.gauss(0, 1)) * intra_spread * 0.3

        # Volume correlated with price movement
        pct_change = abs(close_price - open_price) / open_price
        volume = params.base_volume * (1 + params.volume_sensitivity * pct_change)
        volume *= 0.8 + 0.4 * random.random()  # noise

        state.price = close_price
        return (open_price, high, low, close_price, volume)
