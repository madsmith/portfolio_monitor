"""
Pytest configuration file for Nexus Portfolio Monitor tests.
"""

from decimal import Decimal  # noqa: F401

import pytest  # noqa: F401

from portfolio_monitor.core.currency import (  # noqa: F401
    CURRENCY_CONFIGS,
    Currency,
    CurrencyType,
)
