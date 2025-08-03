"""
Tests for the Portfolio module in Nexus Portfolio Monitor.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from nexus_portfolio_monitor.core.currency import Currency, CurrencyType
from nexus_portfolio_monitor.portfolio.portfolio import Lot, Asset, Portfolio


class TestLot:
    """Test suite for the Lot class."""

    def test_initialization(self):
        """Test Lot initialization."""
        # Basic initialization
        lot = Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD))
        assert lot.quantity == Decimal("10")
        assert lot.price._value == Decimal("100")
        assert lot.price.currency_type == CurrencyType.USD
        assert lot.date is None

        # With date
        date = datetime(2023, 1, 1)
        lot = Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD), date=date)
        assert lot.date == date

    def test_value(self):
        """Test Lot.value() method."""
        # USD lot
        lot = Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD))
        value = lot.value()
        assert isinstance(value, Currency)
        assert value._value == Decimal("1000")
        assert value.currency_type == CurrencyType.USD

        # BTC lot
        lot = Lot(quantity=Decimal("2.5"), price=Currency(40000, CurrencyType.USD))
        value = lot.value()
        assert value._value == Decimal("100000")
        assert value.currency_type == CurrencyType.USD

    def test_from_dict(self):
        """Test Lot.from_dict method."""
        # Basic dictionary
        data = {
            "quantity": "10",
            "price": "100 USD",
            "date": "2023-01-01"
        }
        lot = Lot.from_dict(data)
        assert lot.quantity == Decimal("10")
        assert lot.price._value == Decimal("100")
        assert lot.price.currency_type == CurrencyType.USD
        assert lot.date == datetime(2023, 1, 1)

        # Test with 'amount' instead of 'quantity' (backward compatibility)
        data = {
            "amount": "10",
            "price": "100 USD"
        }
        lot = Lot.from_dict(data)
        assert lot.quantity == Decimal("10")
        
        # Test with comma formatting
        data = {
            "quantity": "1,000",
            "price": "50.25 USD"
        }
        lot = Lot.from_dict(data)
        assert lot.quantity == Decimal("1000")
        assert lot.price._value == Decimal("50.25")

        # Test with symbol formatting
        data = {
            "quantity": "1,000",
            "price": "$50.25"
        }
        lot = Lot.from_dict(data)
        assert lot.quantity == Decimal("1000")
        assert lot.price._value == Decimal("50.25")

    def test_string_representation(self):
        """Test string representation of Lot."""
        lot = Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD))
        assert str(lot) == "10 @ $100.00"
        assert repr(lot) == "Lot(quantity=10, price=$100.00)"


class TestAsset:
    """Test suite for the Asset class."""

    @pytest.fixture
    def sample_lots(self):
        """Create sample lots for testing."""
        return [
            Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD)),
            Lot(quantity=Decimal("5"), price=Currency(120, CurrencyType.USD)),
            Lot(quantity=Decimal("15"), price=Currency(90, CurrencyType.USD))
        ]

    def test_initialization(self, sample_lots):
        """Test Asset initialization."""
        asset = Asset(ticker="AAPL", lots=sample_lots)
        assert asset.ticker == "AAPL"
        assert len(asset.lots) == 3
        assert asset.current_price is None
        assert asset.asset_type == "stock"
        
        # Test with different asset_type
        crypto_asset = Asset(ticker="BTC", lots=sample_lots, asset_type="currency")
        assert crypto_asset.asset_type == "currency"

    def test_total_quantity(self, sample_lots):
        """Test Asset.total_quantity property."""
        asset = Asset(ticker="AAPL", lots=sample_lots)
        assert asset.total_quantity == Decimal("30")  # 10 + 5 + 15

        # Empty asset
        empty_asset = Asset(ticker="AAPL", lots=[])
        assert empty_asset.total_quantity == Decimal("0")

    def test_cost_basis(self, sample_lots):
        """Test Asset.cost_basis property."""
        asset = Asset(ticker="AAPL", lots=sample_lots)
        # (10 * 100) + (5 * 120) + (15 * 90) = 1000 + 600 + 1350 = 2950
        assert asset.cost_basis._value == Decimal("2950")
        assert asset.cost_basis.currency_type == CurrencyType.USD

        # Empty asset
        empty_asset = Asset(ticker="AAPL", lots=[])
        assert empty_asset.cost_basis._value == Decimal("0")

    def test_average_cost(self, sample_lots):
        """Test Asset.average_cost property."""
        asset = Asset(ticker="AAPL", lots=sample_lots)
        # Total cost: 2950, Total quantity: 30, Average cost: 2950/30 = 98.33...
        assert asset.average_cost._value == Decimal("2950") / Decimal("30")
        assert asset.average_cost.currency_type == CurrencyType.USD

        # Empty asset
        empty_asset = Asset(ticker="AAPL", lots=[])
        assert empty_asset.average_cost._value == Decimal("0")

    def test_current_value(self, sample_lots):
        """Test Asset.current_value property."""
        asset = Asset(ticker="AAPL", lots=sample_lots)
        
        # No current price
        assert asset.current_value is None
        
        # With current price
        asset.current_price = Currency(150, CurrencyType.USD)

        assert asset.current_value is not None

        # Total quantity: 30, Current price: 150, Current value: 30 * 150 = 4500
        assert asset.current_value._value == Decimal("4500")
        assert asset.current_value.currency_type == CurrencyType.USD

    def test_profit_loss(self, sample_lots):
        """Test Asset.profit_loss property."""
        asset = Asset(ticker="AAPL", lots=sample_lots)
        
        # No current price
        pl = asset.profit_loss

        assert pl is not None

        assert pl._value == Decimal("-2950")  # Negative cost basis
        
        # With current price
        asset.current_price = Currency(150, CurrencyType.USD)

        assert asset.profit_loss is not None

        # Current value: 4500, Cost basis: 2950, Profit/Loss: 4500 - 2950 = 1550
        assert asset.profit_loss._value == Decimal("1550")
        assert asset.profit_loss.currency_type == CurrencyType.USD

    def test_profit_loss_percentage(self, sample_lots):
        """Test Asset.profit_loss_percentage property."""
        asset = Asset(ticker="AAPL", lots=sample_lots)
        
        # No current price
        assert asset.profit_loss_percentage is None
        
        # With current price
        asset.current_price = Currency(150, CurrencyType.USD)
        # Profit: 1550, Cost basis: 2950, Percentage: 1550/2950 * 100 = 52.54%
        expected_percentage = (Decimal("1550") / Decimal("2950")) * 100
        assert asset.profit_loss_percentage == expected_percentage

    def test_from_dict(self):
        """Test Asset.from_dict method."""
        data = {
            "ticker": "AAPL",
            "lots": [
                {
                    "quantity": "10",
                    "price": "100 USD",
                    "date": "2023-01-01"
                },
                {
                    "quantity": "5",
                    "price": "120 USD",
                    "date": "2023-02-01"
                }
            ]
        }
        
        asset = Asset.from_dict(data)
        assert asset.ticker == "AAPL"
        assert len(asset.lots) == 2
        assert asset.lots[0].quantity == Decimal("10")
        assert asset.lots[0].price._value == Decimal("100")
        assert asset.lots[1].quantity == Decimal("5")
        assert asset.lots[1].price._value == Decimal("120")
        
        # Test with asset_type
        crypto_data = {
            "ticker": "BTC",
            "lots": [
                {
                    "quantity": "1.5",
                    "price": "40000 USD",
                    "date": "2023-03-01"
                }
            ]
        }
        
        crypto_asset = Asset.from_dict(crypto_data, "currency")
        assert crypto_asset.ticker == "BTC"
        assert crypto_asset.asset_type == "currency"


class TestPortfolio:
    """Test suite for the Portfolio class."""

    @pytest.fixture
    def sample_assets(self):
        """Create sample assets for testing."""
        apple_lots = [
            Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD)),
            Lot(quantity=Decimal("5"), price=Currency(120, CurrencyType.USD))
        ]
        btc_lots = [
            Lot(quantity=Decimal("2"), price=Currency(30000, CurrencyType.USD))
        ]
        
        apple = Asset(ticker="AAPL", lots=apple_lots)
        btc = Asset(ticker="BTC", lots=btc_lots, asset_type="currency")
        
        return {"stocks": [apple], "currencies": [btc]}

    def test_initialization(self, sample_assets):
        """Test Portfolio initialization."""
        portfolio = Portfolio(
            name="Test Portfolio",
            stocks=sample_assets["stocks"],
            currencies=sample_assets["currencies"]
        )
        assert portfolio.name == "Test Portfolio"
        assert len(portfolio.stocks) == 1
        assert len(portfolio.currencies) == 1
        assert portfolio.stocks[0].ticker == "AAPL"
        assert portfolio.currencies[0].ticker == "BTC"

    def test_all_assets(self, sample_assets):
        """Test Portfolio.all_assets method."""
        portfolio = Portfolio(
            name="Test Portfolio",
            stocks=sample_assets["stocks"],
            currencies=sample_assets["currencies"]
        )
        all_assets = portfolio.all_assets()
        assert len(all_assets) == 2
        assert all_assets[0].ticker == "AAPL"
        assert all_assets[1].ticker == "BTC"

    def test_update_prices(self, sample_assets):
        """Test Portfolio.update_prices method."""
        portfolio = Portfolio(
            name="Test Portfolio",
            stocks=sample_assets["stocks"],
            currencies=sample_assets["currencies"]
        )
        
        price_data = {
            "AAPL": Currency(150, CurrencyType.USD),
            "BTC": Currency(35000, CurrencyType.USD),
            "MSFT": Currency(200, CurrencyType.USD)  # Not in portfolio
        }
        
        portfolio.update_prices(price_data)

        assert portfolio.stocks[0].current_price is not None
        assert portfolio.currencies[0].current_price is not None

        assert portfolio.stocks[0].current_price._value == Decimal("150")
        assert portfolio.currencies[0].current_price._value == Decimal("35000")

    def test_total_value(self, sample_assets):
        """Test Portfolio.total_value property."""
        portfolio = Portfolio(
            name="Test Portfolio",
            stocks=sample_assets["stocks"],
            currencies=sample_assets["currencies"]
        )
        
        # No current prices
        assert portfolio.total_value._value == Decimal("0")
        
        # Update prices
        portfolio.stocks[0].current_price = Currency(150, CurrencyType.USD)
        portfolio.currencies[0].current_price = Currency(35000, CurrencyType.USD)
        
        # Stock value: (10 + 5) * 150 = 2250
        # BTC value: 2 * 35000 = 70000
        # Total value: 2250 + 70000 = 72250
        assert portfolio.total_value._value == Decimal("72250")

    def test_total_cost_basis(self, sample_assets):
        """Test Portfolio.total_cost_basis property."""
        portfolio = Portfolio(
            name="Test Portfolio",
            stocks=sample_assets["stocks"],
            currencies=sample_assets["currencies"]
        )
        
        # Stock cost basis: 10*100 + 5*120 = 1000 + 600 = 1600
        # BTC cost basis: 2*30000 = 60000
        # Total: 1600 + 60000 = 61600
        assert portfolio.total_cost_basis._value == Decimal("61600")

    def test_total_profit_loss(self, sample_assets):
        """Test Portfolio.total_profit_loss property."""
        portfolio = Portfolio(
            name="Test Portfolio",
            stocks=sample_assets["stocks"],
            currencies=sample_assets["currencies"]
        )
        
        # Update prices
        portfolio.stocks[0].current_price = Currency(150, CurrencyType.USD)
        portfolio.currencies[0].current_price = Currency(35000, CurrencyType.USD)
        
        # Total value: 72250
        # Total cost basis: 61600
        # Total profit/loss: 72250 - 61600 = 10650
        assert portfolio.total_profit_loss._value == Decimal("10650")

    def test_profit_loss_percentage(self, sample_assets):
        """Test Portfolio.profit_loss_percentage property."""
        portfolio = Portfolio(
            name="Test Portfolio",
            stocks=sample_assets["stocks"],
            currencies=sample_assets["currencies"]
        )
        
        # Update prices
        portfolio.stocks[0].current_price = Currency(150, CurrencyType.USD)
        portfolio.currencies[0].current_price = Currency(35000, CurrencyType.USD)
        
        # Profit: 10650, Cost basis: 61600
        # Percentage: 10650/61600 * 100 = 17.29%
        expected_percentage = (Decimal("10650") / Decimal("61600")) * 100
        assert portfolio.profit_loss_percentage == expected_percentage

    def test_from_dict(self):
        """Test Portfolio.from_dict method."""
        data = {
            "name": "Test Portfolio",
            "stocks": [
                {
                    "ticker": "AAPL",
                    "lots": [
                        {
                            "quantity": "10",
                            "price": "100 USD",
                            "date": "2023-01-01"
                        }
                    ]
                }
            ],
            "currencies": [
                {
                    "ticker": "BTC",
                    "lots": [
                        {
                            "quantity": "2",
                            "price": "30000 USD",
                            "date": "2023-01-01"
                        }
                    ]
                }
            ]
        }
        
        portfolio = Portfolio.from_dict(data)
        assert portfolio.name == "Test Portfolio"
        assert len(portfolio.stocks) == 1
        assert portfolio.stocks[0].ticker == "AAPL"
        assert len(portfolio.currencies) == 1
        assert portfolio.currencies[0].ticker == "BTC"
