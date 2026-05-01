from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
from typing import Any

from portfolio_monitor.core import Currency, CurrencyType
from portfolio_monitor.core.permissions import PermissionMap, PermissionsHost
from portfolio_monitor.service.types import AssetSymbol

from .asset import Asset

@dataclass
class Portfolio(PermissionsHost):
    """
    Represents a portfolio of assets.
    A portfolio can contain stocks and cryptocurrencies.
    """

    name: str
    id: str = ""
    owner: str = "default"
    stocks: list[Asset] = field(default_factory=list)
    currencies: list[Asset] = field(default_factory=list)
    crypto: list[Asset] = field(default_factory=list)
    permissions: PermissionMap | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = hashlib.sha256(self.name.encode()).hexdigest()[:16]

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
    def from_dict(cls, data: dict[str, Any], id_hash_seed: str | None = None, owner: str = "default") -> "Portfolio":
        """Create a Portfolio from a dictionary."""
        if id_hash_seed:
            portfolio_id = hashlib.sha256(id_hash_seed.encode()).hexdigest()[:16]
        else:
            portfolio_id = data.get("id", "")

        perm_data = data.get("permissions")
        permissions = PermissionMap.from_yaml(perm_data) if perm_data is not None else None

        portfolio = cls(name=data["name"], id=portfolio_id, owner=owner, permissions=permissions)

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
