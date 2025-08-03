"""
Portfolio module for Nexus Portfolio Monitor.
Contains classes for portfolios, assets and lots.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Literal
from decimal import Decimal


@dataclass
class Lot:
    """
    Represents a lot of an asset with amount and purchase price.
    """
    amount: Decimal
    price: Decimal
    
    @property
    def cost_basis(self) -> Decimal:
        """Return the cost basis of this lot."""
        return self.amount * self.price
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Lot':
        """Create a Lot from a dictionary."""
        return cls(
            amount=Decimal(parse_number(data.get('amount', 0))),
            price=Decimal(parse_number(data.get('price', 0)))
        )

    def __str__(self) -> str:
        """Return a string representation of this lot."""
        return f"{self.amount} @ ${self.price}"
    
    def __repr__(self) -> str:
        """Return a detailed representation of this lot."""
        return f"Lot(amount={self.amount}, price=${self.price})"


@dataclass
class Asset:
    """
    Represents an asset in a portfolio.
    An asset can be a stock or cryptocurrency with one or more lots.
    """
    ticker: str
    lots: List[Lot] = field(default_factory=list)
    current_price: Decimal | None = None
    asset_type: Literal["stock", "currency"] = "stock"
    
    @property
    def total_amount(self) -> Decimal:
        """Return the total amount of this asset."""
        return Decimal(sum(lot.amount for lot in self.lots))
    
    @property
    def cost_basis(self) -> Decimal:
        """Return the total cost basis of this asset."""
        return Decimal(sum(lot.cost_basis for lot in self.lots))
    
    @property
    def average_price(self) -> Decimal:
        """Return the average purchase price of this asset."""
        total_amount = self.total_amount
        if total_amount == 0:
            return Decimal(0)
        return self.cost_basis / total_amount
    
    @property
    def current_value(self) -> Decimal:
        """Return the current value of this asset."""
        if self.current_price is None or not self.lots:
            return Decimal(0)
        return self.total_amount * self.current_price
    
    @property
    def profit_loss(self) -> Decimal:
        """Return the profit/loss of this asset."""
        if self.current_price is None or not self.lots:
            return - self.cost_basis
        return self.current_value - self.cost_basis
    
    @property
    def profit_loss_percentage(self) -> Decimal | None:
        """Return the profit/loss percentage of this asset."""
        if self.cost_basis == 0 or self.current_price is None or not self.lots:
            return None
        return (self.profit_loss / self.cost_basis) * 100
    
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
        price_info = f" at ${self.current_price}" if self.current_price else ""
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
    
    def update_prices(self, price_data: Dict[str, Decimal]) -> None:
        """Update the prices of all assets in this portfolio."""
        for asset in self.all_assets():
            if asset.ticker in price_data:
                asset.current_price = price_data[asset.ticker]
    
    @property
    def total_value(self) -> Decimal:
        """Return the total value of this portfolio."""
        return Decimal(sum(
            (asset.current_value or Decimal(0)) 
            for asset in self.all_assets()
        ))
    
    @property
    def total_cost_basis(self) -> Decimal:
        """Return the total cost basis of this portfolio."""
        return Decimal(sum(asset.cost_basis for asset in self.all_assets()))
    
    @property
    def total_profit_loss(self) -> Decimal:
        """Return the total profit/loss of this portfolio."""
        return self.total_value - self.total_cost_basis
    
    @property
    def profit_loss_percentage(self) -> Decimal:
        """Return the profit/loss percentage of this portfolio."""
        if self.total_cost_basis == 0:
            return Decimal(0)
        return (self.total_profit_loss / self.total_cost_basis) * 100
    
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
        
    def __str__(self) -> str:
        """Return a string representation of this portfolio."""
        assets_count = len(self.stocks) + len(self.currencies)
        stocks_repr = ", ".join(asset.ticker for asset in self.stocks)
        currencies_repr = ", ".join(asset.ticker for asset in self.currencies)
        total_value = ""
        if self.total_value:
            total_value = f"  Value: ${format_number(self.total_value)}"
        elif self.total_cost_basis:
            total_value = f"  Cost Basis: ${format_number(self.total_cost_basis)}"
        return f"Portfolio '{self.name}' with {assets_count} assets{total_value}\n  Stocks: {stocks_repr}\n  Currencies: {currencies_repr}"
    
    def __repr__(self) -> str:
        """Return a detailed representation of this portfolio."""
        stocks_repr = ", ".join(asset.ticker for asset in self.stocks)
        currencies_repr = ", ".join(asset.ticker for asset in self.currencies)
        return f"Portfolio(name='{self.name}', stocks=[{stocks_repr}], currencies=[{currencies_repr}])"

def parse_number(value: Any) -> Decimal:
    """Parse a number from a string."""
    str_value = str(value)
    return Decimal(str_value.replace(",", ""))

def format_number(value: Decimal) -> str:
    """Format a number as a string with commas."""
    return f"{value:,f}"
    