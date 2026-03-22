from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from portfolio_monitor.core.currency import Currency
from portfolio_monitor.core.datetime import parse_date

from ._helpers import format_number

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