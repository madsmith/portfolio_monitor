"""
Portfolio module for Nexus Portfolio Monitor.
Contains classes for portfolios, assets and lots.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Literal
from nexus_portfolio_monitor.core.currency import Currency


@dataclass
class Lot:
    """
    Represents a lot of an asset purchased at a specific price.
    """
    quantity: Decimal  # The number of units/shares (not a Currency)
    price: Currency    # Price per unit
    date: datetime | None = None
    
    def value(self) -> Currency:
        """Return the value of this lot at the purchase price."""
        return self.quantity * self.price
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Lot':
        """Create a Lot from a dictionary."""
        # Parse quantity as a Decimal, not a Currency
        quantity_str = str(data.get('quantity', data.get('amount', 0)))
        quantity = Decimal(quantity_str.replace(',', ''))
        
        return cls(
            quantity=quantity,
            price=Currency.parse_number(data.get('price', 0)),
            date=datetime.strptime(data.get('date', ''), '%Y-%m-%d') if data.get('date', '') else None
        )

    def __str__(self) -> str:
        """Return a string representation of this lot."""
        return f"{self.quantity} @ {self.price}"
    
    def __repr__(self) -> str:
        """Return a detailed representation of this lot."""
        return f"Lot(quantity={self.quantity}, price={self.price})"


@dataclass
class Asset:
    """
    Represents a financial asset with lots.
    """
    ticker: str
    lots: List[Lot] = field(default_factory=list)
    current_price: Currency | None = None
    asset_type: Literal["stock", "currency"] = "stock"
    
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
        """
        if not self.lots:
            return Currency(0)
        
        # Use the currency type of the first lot's price for consistency
        currency_type = self.lots[0].price.currency_type
        # Sum up all lot values directly
        result = Currency(0, currency_type)
        for lot in self.lots:
            assert lot.value().currency_type == currency_type, f"Currency type mismatch: {lot.value().currency_type} != {currency_type}"
            result += lot.value()
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
        """Return the profit/loss of this asset."""
        if self.current_price is None or not self.lots:
            # No need for .value as Currency constructor can handle Currency
            return Currency(-self.cost_basis, self.cost_basis.currency_type)
        # Use subtraction directly
        return self.current_value - self.cost_basis
    
    @property
    def profit_loss_percentage(self) -> Decimal | None:
        """Return the profit/loss percentage of this asset."""
        if self.profit_loss is None or self.cost_basis == 0:
            return None
        
        # Need to use ._value here as we want a raw Decimal percentage
        return (self.profit_loss._value / self.cost_basis._value) * 100
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], asset_type: Literal["stock", "currency"] = "stock") -> 'Asset':
        """Create an Asset from a dictionary."""
        lots = [Lot.from_dict(lot_data) for lot_data in data.get('lots', [])]
        return cls(
            ticker=data['ticker'],
            lots=lots,
            asset_type=asset_type
        )

    def __str__(self) -> str:
        """Return a string representation of this asset."""
        lots_info = f"{len(self.lots)} lots" if self.lots else "monitoring only"
        price_info = f" at {self.current_price}" if self.current_price else ""
        return f"{self.ticker} ({lots_info}{price_info})"
    
    def __repr__(self) -> str:
        """Return a detailed representation of this asset."""
        return f"Asset(ticker='{self.ticker}', lots={len(self.lots)}, asset_type='{self.asset_type}')"


@dataclass
class Portfolio:
    """
    Represents a portfolio of assets.
    A portfolio can contain stocks and cryptocurrencies.
    """
    name: str
    stocks: List[Asset] = field(default_factory=list)
    currencies: List[Asset] = field(default_factory=list)
    
    def all_assets(self) -> List[Asset]:
        """Return all assets in this portfolio."""
        return self.stocks + self.currencies
    
    def update_prices(self, price_data: Dict[str, Currency]) -> None:
        """Update the prices of all assets in this portfolio."""
        for asset in self.all_assets():
            if asset.ticker in price_data:
                price = price_data[asset.ticker]
                assert isinstance(price, Currency)
                asset.current_price = price
    
    @property
    def total_value(self) -> Currency:
        """Return the total value of this portfolio."""
        total = Currency(0)
        for asset in self.all_assets():
            if asset.current_value:
                total += asset.current_value
        return total
    
    @property
    def total_cost_basis(self) -> Currency:
        """Return the total cost basis of this portfolio."""
        total = Currency(0)
        for asset in self.all_assets():
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
    def from_dict(cls, data: Dict[str, Any]) -> 'Portfolio':
        """Create a Portfolio from a dictionary."""
        portfolio = cls(name=data['name'])
        
        # Load stocks
        stocks_data = data.get('stocks', [])
        for stock_data in stocks_data:
            portfolio.stocks.append(Asset.from_dict(stock_data, "stock"))
            
        # Load currencies
        currencies_data = data.get('currencies', [])
        for currency_data in currencies_data:
            portfolio.currencies.append(Asset.from_dict(currency_data, "currency"))
            
        return portfolio
        
    def __str__(self, with_basis=False) -> str:
        """Return a string representation of this portfolio."""
        assets_count = len(self.stocks) + len(self.currencies)
        result = [f"Portfolio '{self.name}' with {assets_count} assets"]
        
        # Add total value or cost basis if available
        if self.total_value:
            result.append(f"Total Value: {self.total_value}")
        if with_basis:
            result.append(f"Total Cost Basis: {self.total_cost_basis}")
        
        # Add stocks
        if self.stocks:
            result.append("Stocks:")
            for asset in self.stocks:
                value_str = ""
                if asset.current_value is not None:
                    value_str = f" - Value: {asset.current_value}"
                elif asset.cost_basis:
                    value_str = f" - Cost Basis: {asset.cost_basis}"
                result.append(f"  {asset.ticker}{value_str}")
        
        # Add currencies
        if self.currencies:
            result.append("Currencies:")
            for asset in self.currencies:
                value_str = ""
                if asset.current_value:
                    value_str = f" - Value: {asset.current_value}"
                elif asset.cost_basis:
                    value_str = f" - Cost Basis: {asset.cost_basis}"
                result.append(f"  {asset.ticker}{value_str}")
                
        return "\n".join(result)
    
    def __repr__(self) -> str:
        """Return a detailed representation of this portfolio."""
        stocks_repr = ", ".join(asset.ticker for asset in self.stocks)
        currencies_repr = ", ".join(asset.ticker for asset in self.currencies)
        return f"Portfolio(name='{self.name}', stocks=[{stocks_repr}], currencies=[{currencies_repr}])"

def parse_number(value: Any) -> Currency:
    """Parse a number from a string, optionally with currency type.
    
    Examples:
        "123.45" -> Currency(123.45, USD)
        "123.45 USD" -> Currency(123.45, USD)
        "123.45 BTC" -> Currency(123.45, BTC)
    
    Note: This is for parsing currency values, not quantities (units/shares).
    """
    from ..core.currency import Currency, CurrencyType
    
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
            str_value = ' '.join(parts[:-1])
        except (KeyError, ValueError):
            # If the currency code isn't valid, assume it's part of the number or description
            pass
    
    # Parse the numerical value
    number_value = Decimal(str_value.replace(",", ""))
    
    # Create and return a Currency object
    return Currency(number_value, currency_type)

def format_number(value: Any) -> str:
    """Format a number as a string with commas.
    
    Can handle both Decimal and Currency objects.
    """
    from ..core.currency import Currency
    
    if isinstance(value, Currency):
        # Use the Currency's own formatting if it's a Currency object
        return str(value)
    else:
        # Handle Decimal or other numeric types
        return f"{value:,f}"
    