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
        assert lot.price == Decimal("100")
        assert lot.price.currency_type == CurrencyType.USD
        assert lot.date is None
        assert lot.fees is None
        assert lot.rebates is None

        # With date
        date = datetime(2023, 1, 1)
        lot = Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD), date=date)
        assert lot.date == date
        
        # With fees and rebates
        lot = Lot(
            quantity=Decimal("10"), 
            price=Currency(100, CurrencyType.USD),
            fees=Currency(10, CurrencyType.USD),
            rebates=Currency(2, CurrencyType.USD)
        )
        assert lot.fees is not None
        assert lot.rebates is not None
        assert lot.fees == Decimal("10")
        assert lot.rebates == Decimal("2")

    def test_value(self):
        """Test Lot.value() method."""
        # USD lot
        lot = Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD))
        value = lot.value()
        assert isinstance(value, Currency)
        assert value == Decimal("1000")
        assert value.currency_type == CurrencyType.USD

        # BTC lot
        lot = Lot(quantity=Decimal("2.5"), price=Currency(40000, CurrencyType.USD))
        value = lot.value()
        assert value == Decimal("100000")
        assert value.currency_type == CurrencyType.USD
        
    def test_cost_basis(self):
        """Test Lot.cost_basis() method."""
        # Basic cost basis (no fees/rebates)
        lot = Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD))
        cost = lot.cost_basis()
        assert isinstance(cost, Currency)
        assert cost == Decimal("1000")
        assert cost.currency_type == CurrencyType.USD
        
        # With fees
        lot = Lot(
            quantity=Decimal("10"), 
            price=Currency(100, CurrencyType.USD),
            fees=Currency(20, CurrencyType.USD)
        )
        cost = lot.cost_basis()
        assert cost == Decimal("1020")  # 1000 + 20
        
        # With rebates
        lot = Lot(
            quantity=Decimal("10"), 
            price=Currency(100, CurrencyType.USD),
            rebates=Currency(15, CurrencyType.USD)
        )
        cost = lot.cost_basis()
        assert cost == Decimal("985")  # 1000 - 15
        
        # With both fees and rebates
        lot = Lot(
            quantity=Decimal("10"), 
            price=Currency(100, CurrencyType.USD),
            fees=Currency(20, CurrencyType.USD),
            rebates=Currency(5, CurrencyType.USD)
        )
        cost = lot.cost_basis()
        assert cost == Decimal("1015")  # 1000 + 20 - 5

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
        assert lot.price == Decimal("100")
        assert lot.price.currency_type == CurrencyType.USD
        assert lot.date == datetime(2023, 1, 1)
        assert lot.fees is None
        assert lot.rebates is None

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
        assert lot.price == Decimal("50.25")

        # Test with symbol formatting
        data = {
            "quantity": "1,000",
            "price": "$50.25"
        }
        lot = Lot.from_dict(data)
        assert lot.quantity == Decimal("1000")
        assert lot.price == Decimal("50.25")
        
        # Test with fees and rebates
        data = {
            "quantity": "10",
            "price": "100 USD",
            "fees": "5 USD",
            "rebates": "2 USD"
        }
        lot = Lot.from_dict(data)
        assert lot.fees is not None
        assert lot.rebates is not None
        assert lot.fees == Decimal("5")
        assert lot.rebates == Decimal("2")

    def test_string_representation(self):
        """Test string representation of Lot."""
        # Basic lot
        lot = Lot(quantity=Decimal("10"), price=Currency(100, CurrencyType.USD))
        assert str(lot) == "10 @ $100.00"
        assert repr(lot) == "Lot(quantity=10, price=$100.00, fees=None, rebates=None)"
        
        # Lot with fees
        lot = Lot(
            quantity=Decimal("10"), 
            price=Currency(100, CurrencyType.USD),
            fees=Currency(5, CurrencyType.USD)
        )
        assert str(lot) == "10 @ $100.00 (fees: $5.00)"
        
        # Lot with rebates
        lot = Lot(
            quantity=Decimal("10"), 
            price=Currency(100, CurrencyType.USD),
            rebates=Currency(3, CurrencyType.USD)
        )
        assert str(lot) == "10 @ $100.00 (rebates: $3.00)"
        
        # Lot with both fees and rebates
        lot = Lot(
            quantity=Decimal("10"), 
            price=Currency(100, CurrencyType.USD),
            fees=Currency(5, CurrencyType.USD),
            rebates=Currency(3, CurrencyType.USD)
        )
        assert str(lot) == "10 @ $100.00 (fees: $5.00, rebates: $3.00)"


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
        
    @pytest.fixture
    def sample_lots_with_fees_rebates(self):
        """Create sample lots with fees and rebates for testing."""
        return [
            Lot(
                quantity=Decimal("10"), 
                price=Currency(100, CurrencyType.USD),
                fees=Currency(20, CurrencyType.USD)
            ),
            Lot(
                quantity=Decimal("5"), 
                price=Currency(120, CurrencyType.USD),
                rebates=Currency(10, CurrencyType.USD)
            ),
            Lot(
                quantity=Decimal("15"), 
                price=Currency(90, CurrencyType.USD),
                fees=Currency(15, CurrencyType.USD),
                rebates=Currency(5, CurrencyType.USD)
            )
        ]

    def test_initialization(self, sample_lots):
        """Test Asset initialization."""
        asset = Asset(symbol="AAPL", lots=sample_lots)
        assert asset.symbol == "AAPL"
        assert len(asset.lots) == 3
        assert asset.current_price is None
        assert asset.asset_type == "stock"
        
        # Test with different asset_type
        crypto_asset = Asset(symbol="BTC", lots=sample_lots, asset_type="currency")
        assert crypto_asset.asset_type == "currency"

    def test_total_quantity(self, sample_lots):
        """Test Asset.total_quantity property."""
        asset = Asset(symbol="AAPL", lots=sample_lots)
        assert asset.total_quantity == Decimal("30")  # 10 + 5 + 15

        # Empty asset
        empty_asset = Asset(symbol="AAPL", lots=[])
        assert empty_asset.total_quantity == Decimal("0")

    def test_cost_basis(self, sample_lots, sample_lots_with_fees_rebates):
        """Test Asset.cost_basis property."""
        # Test with regular lots (no fees/rebates)
        asset = Asset(symbol="AAPL", lots=sample_lots)
        
        # 10*100 + 5*120 + 15*90 = 1000 + 600 + 1350 = 2950
        assert asset.cost_basis == Decimal("2950")
        assert asset.cost_basis.currency_type == CurrencyType.USD
        
        # Empty asset
        empty_asset = Asset(symbol="EMPTY", lots=[])
        assert empty_asset.cost_basis == Decimal("0")
        
        # Test with lots that have fees and rebates
        asset_with_fees = Asset(symbol="AAPL", lots=sample_lots_with_fees_rebates)
        
        # Lot 1: 10*100 + 20 = 1020
        # Lot 2: 5*120 - 10 = 590
        # Lot 3: 15*90 + 15 - 5 = 1360
        # Total: 1020 + 590 + 1360 = 2970
        assert asset_with_fees.cost_basis == Decimal("2970")
        assert asset_with_fees.cost_basis.currency_type == CurrencyType.USD

    def test_average_cost(self, sample_lots):
        """Test Asset.average_cost property."""
        asset = Asset(symbol="AAPL", lots=sample_lots)
        # Total cost: 2950, Total quantity: 30, Average cost: 2950/30 = 98.33...
        assert asset.average_cost == Decimal("2950") / Decimal("30")
        assert asset.average_cost.currency_type == CurrencyType.USD

        # Empty asset
        empty_asset = Asset(symbol="AAPL", lots=[])
        assert empty_asset.average_cost == Decimal("0")

    def test_current_value(self, sample_lots):
        """Test Asset.current_value property."""
        asset = Asset(symbol="AAPL", lots=sample_lots)
        
        # No current price
        assert asset.current_value is None
        
        # With current price
        asset.current_price = Currency(150, CurrencyType.USD)

        assert asset.current_value is not None

        # Total quantity: 30, Current price: 150, Current value: 30 * 150 = 4500
        assert asset.current_value == Decimal("4500")
        assert asset.current_value.currency_type == CurrencyType.USD

    def test_profit_loss(self, sample_lots, sample_lots_with_fees_rebates):
        """Test Asset.profit_loss property."""
        # Test with regular lots (no fees/rebates)
        asset = Asset(symbol="AAPL", lots=sample_lots)
        
        # No current price
        assert asset.profit_loss is None
        
        # Set current price
        asset.current_price = Currency(110, CurrencyType.USD)
        
        # Total quantity: 10 + 5 + 15 = 30
        # Current value: 30 * 110 = 3300
        # Cost basis: 2950
        # Profit: 3300 - 2950 = 350
        assert asset.profit_loss == Decimal("350")
        
        # Try with a lower price (loss)
        asset.current_price = Currency(90, CurrencyType.USD)
        # Current value: 30 * 90 = 2700
        # Profit: 2700 - 2950 = -250
        assert asset.profit_loss == Decimal("-250")
        
        # Test with lots that have fees and rebates
        asset_with_fees = Asset(symbol="AAPL", lots=sample_lots_with_fees_rebates)
        
        # Set current price
        asset_with_fees.current_price = Currency(110, CurrencyType.USD)
        
        # Total quantity: 10 + 5 + 15 = 30
        # Current value: 30 * 110 = 3300
        # Cost basis with fees/rebates: 2970
        # Profit: 3300 - 2970 = 330
        assert asset_with_fees.profit_loss == Decimal("330")
        
        # Try with a lower price (loss)
        asset_with_fees.current_price = Currency(90, CurrencyType.USD)
        # Current value: 30 * 90 = 2700
        # Profit: 2700 - 2970 = -270
        assert asset_with_fees.profit_loss == Decimal("-270")

    def test_profit_loss_percentage(self, sample_lots, sample_lots_with_fees_rebates):
        """Test Asset.profit_loss_percentage property."""
        # Test with regular lots
        asset = Asset(symbol="AAPL", lots=sample_lots)
        
        # No current price
        assert asset.profit_loss_percentage is None
        
        # Set current price
        asset.current_price = Currency(110, CurrencyType.USD)
        
        # Profit: 350, Cost basis: 2950
        # Percentage: 350/2950 * 100 = ~11.86%
        expected_percentage = (Decimal("350") / Decimal("2950")) * 100
        assert asset.profit_loss_percentage == expected_percentage
        
        # Test with lots that have fees and rebates
        asset_with_fees = Asset(symbol="AAPL", lots=sample_lots_with_fees_rebates)
        
        # Set current price
        asset_with_fees.current_price = Currency(110, CurrencyType.USD)
        
        # Profit: 330, Cost basis with fees/rebates: 2970
        # Percentage: 330/2970 * 100 = ~11.11%
        expected_percentage = (Decimal("330") / Decimal("2970")) * 100
        assert asset_with_fees.profit_loss_percentage == expected_percentage

    def test_from_dict(self):
        """Test Asset.from_dict method."""
        # Basic dictionary
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
                    "price": "120 USD"
                }
            ]
        }
        
        asset = Asset.from_dict(data)
        assert asset.symbol == "AAPL"
        assert len(asset.lots) == 2
        assert asset.lots[0].quantity == Decimal("10")
        assert asset.lots[0].price == Decimal("100")
        assert asset.lots[0].date == datetime(2023, 1, 1)
        assert asset.lots[1].quantity == Decimal("5")
        assert asset.lots[1].price == Decimal("120")
        assert asset.asset_type == "stock"
        
        # Test with different asset_type
        currency_data = {
            "ticker": "BTC",
            "lots": [
                {
                    "quantity": "1.5",
                    "price": "40000 USD"
                }
            ]
        }
        
        currency_asset = Asset.from_dict(currency_data, asset_type="currency")
        assert currency_asset.symbol == "BTC"
        assert currency_asset.asset_type == "currency"
        
        # Test with lots that have fees and rebates
        data_with_fees = {
            "ticker": "AAPL",
            "lots": [
                {
                    "quantity": "10",
                    "price": "100 USD",
                    "fees": "5 USD"
                },
                {
                    "quantity": "5",
                    "price": "120 USD",
                    "rebates": "3 USD"
                },
                {
                    "quantity": "15",
                    "price": "90 USD",
                    "fees": "8 USD",
                    "rebates": "2 USD"
                }
            ]
        }
        
        asset_with_fees = Asset.from_dict(data_with_fees)
        assert asset_with_fees.symbol == "AAPL"
        assert len(asset_with_fees.lots) == 3
        assert asset_with_fees.lots[0].fees == Decimal("5")
        assert asset_with_fees.lots[0].rebates is None
        assert asset_with_fees.lots[1].fees is None
        assert asset_with_fees.lots[1].rebates == Decimal("3")
        assert asset_with_fees.lots[2].fees == Decimal("8")
        assert asset_with_fees.lots[2].rebates == Decimal("2")


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
        
        apple = Asset(symbol="AAPL", lots=apple_lots)
        btc = Asset(symbol="BTC", lots=btc_lots, asset_type="currency")
        
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
        assert portfolio.stocks[0].symbol == "AAPL"
        assert portfolio.currencies[0].symbol == "BTC"

    def test_all_assets(self, sample_assets):
        """Test Portfolio.all_assets method."""
        portfolio = Portfolio(
            name="Test Portfolio",
            stocks=sample_assets["stocks"],
            currencies=sample_assets["currencies"]
        )
        all_assets = portfolio.assets()
        assert len(all_assets) == 2
        assert all_assets[0].symbol == "AAPL"
        assert all_assets[1].symbol == "BTC"

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

        assert portfolio.stocks[0].current_price == Decimal("150")
        assert portfolio.currencies[0].current_price == Decimal("35000")

    def test_total_value(self, sample_assets):
        """Test Portfolio.total_value property."""
        portfolio = Portfolio(
            name="Test Portfolio",
            stocks=sample_assets["stocks"],
            currencies=sample_assets["currencies"]
        )
        
        # No current prices
        assert portfolio.total_value == Decimal("0")
        
        # Update prices
        portfolio.stocks[0].current_price = Currency(150, CurrencyType.USD)
        portfolio.currencies[0].current_price = Currency(35000, CurrencyType.USD)
        
        # Stock value: (10 + 5) * 150 = 2250
        # BTC value: 2 * 35000 = 70000
        # Total value: 2250 + 70000 = 72250
        assert portfolio.total_value == Decimal("72250")

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
        assert portfolio.total_cost_basis == Decimal("61600")

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
        assert portfolio.total_profit_loss == Decimal("10650")

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
        assert portfolio.stocks[0].symbol == "AAPL"
        assert len(portfolio.currencies) == 1
        assert portfolio.currencies[0].symbol == "BTC"
