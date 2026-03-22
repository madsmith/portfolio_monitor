from typing import Any

from portfolio_monitor.core.currency import Currency


def format_number(value: Any) -> str:
    """
    Format a number as a string with commas.

    Can handle both Decimal and Currency objects.
    """

    if isinstance(value, Currency):
        # Use the Currency's own formatting if it's a Currency object
        return str(value)
    else:
        # Handle Decimal or other numeric types
        return f"{value:,f}"
