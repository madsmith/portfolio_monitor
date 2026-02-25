"""
Portfolio module for Nexus Portfolio Monitor.
Contains classes for portfolios, assets and lots.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from portfolio_monitor.core.currency import Currency, CurrencyType
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

logger = logging.getLogger(__name__)


@dataclass
class Lot:
    """
    Represents a lot of an asset purchased at a specific price.
    """

    quantity: Decimal  # The number of units/shares (not a Currency)
    price: Currency  # Price per unit
    date: datetime | None = None
    fees: Currency | None = None  # Fees associated with acquisition (e.g., commissions)
    rebates: Currency | None = None  # Rebates or refunds of fees

    def value(self) -> Currency:
        """Return the value of this lot at the purchase price."""
        return self.quantity * self.price

    def cost_basis(self) -> Currency:
        """Return the total cost basis including fees (minus rebates)."""
        total_cost = self.quantity * self.price

        if self.fees:
            total_cost += self.fees

        if self.rebates:
            total_cost -= self.rebates

        return total_cost

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Lot":
        """Create a Lot from a dictionary."""
        # Parse quantity as a Decimal, not a Currency
        quantity_str = str(data.get("quantity", data.get("amount", 0)))
        quantity = Decimal(quantity_str.replace(",", ""))

        # Parse fees and rebates if present
        fees = None
        if "fees" in data:
            fees = Currency.parse_number(data["fees"])

        rebates = None
        if "rebates" in data:
            rebates = Currency.parse_number(data["rebates"])

        return cls(
            quantity=quantity,
            price=Currency.parse_number(data.get("price", 0)),
            date=parse_date(data.get("date", "")),
            fees=fees,
            rebates=rebates,
        )

    def __str__(self) -> str:
        """Return a string representation of this lot."""
        base = f"{format_number(self.quantity)} @ {self.price}"
        if self.fees or self.rebates:
            extras = []
            if self.fees:
                extras.append(f"fees: {self.fees}")
            if self.rebates:
                extras.append(f"rebates: {self.rebates}")
            return f"{base} ({', '.join(extras)})"
        return base

    def __repr__(self) -> str:
        """Return a detailed representation of this lot."""
        return f"Lot(quantity={self.quantity}, price={self.price}, fees={self.fees}, rebates={self.rebates})"


@dataclass
class Asset:
    """
    Represents a financial asset with lots.
    """

    symbol: AssetSymbol
    lots: list[Lot] = field(default_factory=list)
    current_price: Currency | None = None
    asset_type: Literal["stock", "currency", "crypto"] = "stock"

    @property
    def total_quantity(self) -> Decimal:
        """Return the total quantity of this asset across all lots."""
        # Sum up all quantities directly (Decimal, not Currency)
        return Decimal(sum(lot.quantity for lot in self.lots))

    @property
    def cost_basis(self) -> Currency:
        """
        Return the total cost basis of this asset.

        If no lots are present, returns a Currency with value 0. Otherwise cost basis is computed in
        the currency of the first lot's price.  All lots must by priced at the same currency.
        Cost basis includes the purchase price plus any fees minus any rebates.
        """
        if not self.lots:
            return Currency(0)

        # Use the currency type of the first lot's price for consistency
        currency_type = self.lots[0].price.currency_type
        # Sum up all lot cost bases
        result = Currency(0, currency_type)
        for lot in self.lots:
            assert Currency.are_equivalent_currencies(
                lot.price.currency_type, currency_type
            ), f"Currency type mismatch: {lot.price.currency_type} != {currency_type}"
            # Use the new cost_basis method which factors in fees and rebates
            result += lot.cost_basis()
        return result

    @property
    def average_cost(self) -> Currency:
        """Return the average cost basis of this asset."""
        total_quantity = self.total_quantity
        if not total_quantity or total_quantity == 0:
            return Currency(0)

        return self.cost_basis / total_quantity

    @property
    def current_value(self) -> Currency | None:
        """Return the current value of this asset, or None if no current price is available."""
        if self.current_price is None:
            return None
        # Calculate value by multiplying quantity by price
        return self.total_quantity * self.current_price

    @property
    def profit_loss(self) -> Currency | None:
        if self.current_price is None or not self.lots:
            return None  # Can't compute PL without lots and a price

        current_value = self.current_value
        if current_value is None:
            return None

        return current_value - self.cost_basis

    @property
    def profit_loss_percentage(self) -> Decimal | None:
        """Return the profit/loss percentage of this asset."""
        if self.profit_loss is None or self.cost_basis == 0:
            return None

        # Need to use ._value here as we want a raw Decimal percentage
        return (self.profit_loss._value / self.cost_basis._value) * 100

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        asset_type: Literal["stock", "currency", "crypto"] = "stock",
    ) -> "Asset":
        """Create an Asset from a dictionary."""
        lots = [Lot.from_dict(lot_data) for lot_data in data.get("lots", [])]
        return cls(
            symbol=AssetSymbol(data["ticker"], AssetTypes(asset_type)),
            lots=lots,
            asset_type=asset_type,
        )

    def __str__(self) -> str:
        """Return a string representation of this asset."""
        lots_info = (
            f" ({len(self.lots)} lot{len(self.lots) == 1 and '' or 's'})"
            if self.lots
            else ""
        )

        profile_loss_info = ""
        if self.lots:
            price_info = f"{format_number(self.total_quantity)}"
            if self.current_price:
                price_info += f" @ {self.current_price} = {self.current_value}"
            else:
                price_info += f" Cost: {self.cost_basis}"
            if self.profit_loss:
                profile_loss_info += f" {self.profit_loss}"
        elif self.current_price:
            price_info = f"{self.current_price}"
        else:
            price_info = ""

        return (
            f"{str(self.symbol):<7} {price_info:<40}{lots_info}{profile_loss_info:>25}"
        )

    def __repr__(self) -> str:
        """Return a detailed representation of this asset."""
        return f"Asset(ticker='{self.symbol}', lots={len(self.lots)}, asset_type='{self.asset_type}')"


@dataclass
class Portfolio:
    """
    Represents a portfolio of assets.
    A portfolio can contain stocks and cryptocurrencies.
    """

    name: str
    stocks: list[Asset] = field(default_factory=list)
    currencies: list[Asset] = field(default_factory=list)
    crypto: list[Asset] = field(default_factory=list)

    def assets(self) -> list[Asset]:
        """Return all assets in this portfolio."""
        return self.stocks + self.currencies + self.crypto

    def update_prices(self, price_data: dict[AssetSymbol, Currency]) -> bool:
        """Update the prices of all assets in this portfolio."""
        data_matched = False
        for asset in self.assets():
            if asset.symbol in price_data:
                price = price_data[asset.symbol]
                assert isinstance(price, Currency)
                asset.current_price = price
                data_matched = True
        return data_matched

    @property
    def total_value(self) -> Currency:
        """Return the total value of this portfolio."""
        total = Currency(0)
        for asset in self.assets():
            if asset.current_value:
                total += asset.current_value
        return total

    @property
    def total_cost_basis(self) -> Currency:
        """Return the total cost basis of this portfolio."""
        total = Currency(0)
        for asset in self.assets():
            total += asset.cost_basis
        return total

    @property
    def total_profit_loss(self) -> Currency:
        """Return the total profit/loss of this portfolio."""
        # Use subtraction directly
        return self.total_value - self.total_cost_basis

    @property
    def profit_loss_percentage(self) -> Decimal | None:
        """Return the profit/loss percentage of this portfolio."""
        if not self.total_cost_basis or self.total_cost_basis._value == 0:
            return None
        # Need to use ._value here as we want a raw Decimal percentage
        return (self.total_profit_loss._value / self.total_cost_basis._value) * 100

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Portfolio":
        """Create a Portfolio from a dictionary."""
        portfolio = cls(name=data["name"])

        # Map asset types to their corresponding attribute names in Portfolio
        asset_type_map = (
            ("stock", "stocks"),
            ("currency", "currencies"),
            ("crypto", "crypto"),
        )

        # Process each asset type
        for asset_type, asset_type_key in asset_type_map:
            source_assets = data.get(asset_type_key, [])
            if source_assets:
                # Get the correct list attribute from portfolio
                asset_list: list[Asset] = getattr(portfolio, asset_type_key)

                # Add each asset to the appropriate list
                for asset_data in source_assets:
                    assert asset_type in ("stock", "currency", "crypto")
                    asset = Asset.from_dict(asset_data, asset_type)
                    asset_list.append(asset)

        return portfolio

    def __str__(self) -> str:
        """Return a string representation of this portfolio."""
        assets_count = len(self.stocks) + len(self.currencies) + len(self.crypto)
        result = [f"Portfolio '{self.name}' with {assets_count} assets"]

        # Add total value or cost basis if available
        if self.total_value > 0:
            result.append(f"Total Value: {self.total_value}")
        # elif self.total_cost_basis > 0:
        #     result.append(f"Total Cost Basis: {self.total_cost_basis}")

        # Add stocks
        if self.stocks:
            result.append("Stocks:")
            for asset in self.stocks:
                result.append(f"  {asset}")

        # Add currencies
        if self.currencies:
            result.append("Currencies:")
            for asset in self.currencies:
                result.append(f"  {asset}")

        # Add crypto
        if self.crypto:
            result.append("Crypto:")
            for asset in self.crypto:
                result.append(f"  {asset}")

        return "\n".join(result)

    def __repr__(self) -> str:
        """Return a detailed representation of this portfolio."""
        stocks_repr = ", ".join(str(asset.symbol) for asset in self.stocks)
        currencies_repr = ", ".join(str(asset.symbol) for asset in self.currencies)
        return f"Portfolio(name='{self.name}', stocks=[{stocks_repr}], currencies=[{currencies_repr}])"


def parse_number(value: Any) -> Currency:
    """
    Parse a number from a string, optionally with currency type.

    Examples:
        "123.45" -> Currency(123.45, USD)
        "123.45 USD" -> Currency(123.45, USD)
        "123.45 BTC" -> Currency(123.45, BTC)

    Note: This is for parsing currency values, not quantities (units/shares).
    """

    str_value = str(value).strip()

    # Check if there's a currency code at the end
    parts = str_value.split()

    # Default to USD if no currency specified
    currency_type = CurrencyType.USD

    # If format is "number CURRENCY", extract the currency type
    if len(parts) >= 2:
        try:
            # Try to get currency from the last part
            currency_code = parts[-1].upper()
            currency_type = CurrencyType[currency_code]
            # Remove the currency part for number parsing
            str_value = " ".join(parts[:-1])
        except (KeyError, ValueError):
            # If the currency code isn't valid, assume it's part of the number or description
            pass

    # Parse the numerical value
    number_value = Decimal(str_value.replace(",", ""))

    # Create and return a Currency object
    return Currency(number_value, currency_type)


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


def parse_date(date_string: str) -> datetime | None:
    """Parse a date string by first matching its pattern, then applying the correct format.

    Args:
        date_string: The date string to parse

    Returns:
        Parsed datetime object or None if parsing fails
    """

    if not date_string or not isinstance(date_string, str):
        return None

    # Remove any leading/trailing whitespace
    date_string = date_string.strip()

    # Define patterns and their corresponding formats
    patterns = [
        # YYYY-MM-DD
        (r"^\d{4}-\d{1,2}-\d{1,2}$", "%Y-%m-%d"),
        # YYYY/MM/DD
        (r"^\d{4}/\d{1,2}/\d{1,2}$", "%Y/%m/%d"),
        # YYYY.MM.DD
        (r"^\d{4}\.\d{1,2}\.\d{1,2}$", "%Y.%m.%d"),
        # MM/DD/YYYY - Attempt US variant format first
        (r"^\d{1,2}/\d{1,2}/\d{4}$", "%m/%d/%Y"),
        # DD/MM/YYYY
        (r"^\d{1,2}/\d{1,2}/\d{4}$", "%d/%m/%Y"),
        # MM-DD-YYYY - Attempt US variant format first
        (r"^\d{1,2}-\d{1,2}-\d{4}$", "%m-%d-%Y"),
        # DD-MM-YYYY
        (r"^\d{1,2}-\d{1,2}-\d{4}$", "%d-%m-%Y"),
        # MM.DD.YYYY - Attempt US variant format first
        (r"^\d{1,2}\.\d{1,2}\.\d{4}$", "%m.%d.%Y"),
        # DD.MM.YYYY
        (r"^\d{1,2}\.\d{1,2}\.\d{4}$", "%d.%m.%Y"),
        # MM/DD/YY HH:MM:SS
        (r"^\d{1,2}/\d{1,2}/\d{2} \d{2}:\d{2}:\d{2}$", "%m/%d/%y %H:%M:%S"),
        # MM/DD/YYYY HH:MM:SS
        (r"^\d{1,2}/\d{1,2}/\d{4} \d{2}:\d{2}:\d{2}$", "%m/%d/%Y %H:%M:%S"),
    ]

    # Try patterns in order, taking first matching pattern
    for pattern, fmt in patterns:
        if re.match(pattern, date_string):
            try:
                return datetime.strptime(date_string, fmt)
            except ValueError:
                # If parsing fails, it might be an invalid date like Feb 30
                continue

    # If we get here, none of the patterns or formats worked
    logger.warning(f"Could not parse date '{date_string}' with any known format")
    return None
