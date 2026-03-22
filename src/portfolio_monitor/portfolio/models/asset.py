from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from portfolio_monitor.core.currency import Currency
from portfolio_monitor.service.types import AssetSymbol, AssetTypes

from .lot import Lot
from ._helpers import format_number

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
