"""
Tests for the Currency class in Nexus Portfolio Monitor.
"""

import pytest
import decimal
from decimal import Decimal

from nexus_portfolio_monitor.core.currency import Currency, CurrencyType


class TestCurrency:
    """Test suite for the Currency class."""

    def test_init_with_decimal(self):
        """Test initializing Currency with a Decimal."""
        value = Decimal("100.50")
        currency = Currency(value)
        assert currency._value == value
        assert currency.currency_type == CurrencyType.USD  # Default

    def test_init_with_int(self):
        """Test initializing Currency with an integer."""
        value = 100
        currency = Currency(value)
        assert currency._value == Decimal(value)
        assert currency.currency_type == CurrencyType.USD

    def test_init_with_float(self):
        """Test initializing Currency with a float."""
        value = 100.50
        currency = Currency(value)
        assert currency._value == Decimal(str(value))
        assert currency.currency_type == CurrencyType.USD

    def test_init_with_str(self):
        """Test initializing Currency with a string."""
        value = "100.50"
        currency = Currency(value)
        assert currency._value == Decimal(value)
        assert currency.currency_type == CurrencyType.USD

    def test_init_with_currency(self):
        """Test initializing Currency with another Currency instance."""
        original = Currency(100.50, CurrencyType.BTC)
        copy = Currency(original)
        assert copy._value == original._value
        assert copy.currency_type == original.currency_type

        # Test overriding currency_type
        copy_with_different_type = Currency(original, CurrencyType.EUR)
        assert copy_with_different_type._value == original._value
        assert copy_with_different_type.currency_type == CurrencyType.EUR

    def test_init_with_string_currency_type(self):
        """Test initializing Currency with string currency type."""
        # Test with uppercase currency code
        currency = Currency(100.50, "USD")
        assert currency.currency_type == CurrencyType.USD

        # Test with lowercase currency code
        currency = Currency(100.50, "btc")
        assert currency.currency_type == CurrencyType.BTC

        # Test with symbol
        currency = Currency(100.50, "$")
        assert currency.currency_type == CurrencyType.USD

        # Test with invalid currency
        with pytest.raises(ValueError):
            Currency(100.50, "INVALID")

    def test_string_representation(self):
        """Test string representations of Currency."""
        # USD formatting
        usd = Currency("1234.56", CurrencyType.USD)  # Use string for exact precision
        assert str(usd) == "$1,234.56"
        assert usd._value == Decimal("1234.56")
        
        # EUR formatting
        eur = Currency(1234.56, CurrencyType.EUR)
        # Check for either prefix or suffix format based on implementation
        assert "1,234.56" in str(eur) and "€" in str(eur)

        # BTC formatting
        btc = Currency(1.23456789, CurrencyType.BTC)
        # Just check that the decimal value and symbol are present
        assert "₿" in str(btc) and ("1.2346" in str(btc) or "1.23456789" in str(btc))

    def test_arithmetic_operations(self):
        """Test basic arithmetic operations with Currency."""
        # Setup test currencies
        usd_100 = Currency(100, CurrencyType.USD)
        usd_50 = Currency(50, CurrencyType.USD)
        eur_50 = Currency(50, CurrencyType.EUR)

        # Addition
        result = usd_100 + usd_50
        assert isinstance(result, Currency)
        assert result._value == Decimal(150)
        assert result.currency_type == CurrencyType.USD

        # Addition with different currencies should raise ValueError
        with pytest.raises(ValueError):
            _ = usd_100 + eur_50  # type: ignore

        # Subtraction
        result = usd_100 - usd_50
        assert isinstance(result, Currency)
        assert result._value == Decimal(50)
        assert result.currency_type == CurrencyType.USD

        # Subtraction with different currencies should raise ValueError
        with pytest.raises(ValueError):
            _ = usd_100 - eur_50  # type: ignore

        # Multiplication
        result = usd_100 * 2
        assert isinstance(result, Currency)
        assert result._value == Decimal(200)
        assert result.currency_type == CurrencyType.USD

        # Right multiplication
        result = 2 * usd_100
        assert isinstance(result, Currency)
        assert result._value == Decimal(200)
        assert result.currency_type == CurrencyType.USD

        # Division
        result = usd_100 / 2
        assert isinstance(result, Currency)
        assert result._value == Decimal(50)
        assert result.currency_type == CurrencyType.USD

        # Division by zero
        with pytest.raises(ZeroDivisionError):
            _ = usd_100 / 0  # type: ignore

        # Currency divided by Currency (should return Currency)
        result = usd_100 / usd_50
        assert isinstance(result, Currency)
        assert result._value == Decimal(2)

        # Check division with different currencies - either raises ValueError or returns a valid result
        try:
            result = usd_100 / eur_50
            # If division works, the result should be a Currency with the correct value
            assert isinstance(result, Currency)
        except ValueError:
            # If it raises ValueError, that's acceptable too
            pass

        # Scalar divided by Currency should raise TypeError (not supported)
        with pytest.raises(TypeError):
            _ = 2 / usd_100  # type: ignore

        # Negation
        result = -usd_100
        assert isinstance(result, Currency)
        assert result._value == Decimal(-100)
        assert result.currency_type == CurrencyType.USD

        # Absolute value
        result = abs(Currency(-100, CurrencyType.USD))
        assert isinstance(result, Currency)
        assert result._value == Decimal(100)
        assert result.currency_type == CurrencyType.USD

    def test_comparison_operations(self):
        """Test comparison operations with Currency."""
        usd_100 = Currency(100, CurrencyType.USD)
        usd_50 = Currency(50, CurrencyType.USD)
        usd_100_copy = Currency(100, CurrencyType.USD)
        eur_100 = Currency(100, CurrencyType.EUR)

        # Equal
        assert usd_100 == usd_100_copy
        assert not (usd_100 == usd_50)

        # Not equal
        assert usd_100 != usd_50
        assert not (usd_100 != usd_100_copy)

        # Less than
        assert usd_50 < usd_100
        assert not (usd_100 < usd_50)

        # Greater than
        assert usd_100 > usd_50
        assert not (usd_50 > usd_100)

        # Less than or equal
        assert usd_50 <= usd_100
        assert usd_100 <= usd_100_copy
        assert not (usd_100 <= usd_50)

        # Greater than or equal
        assert usd_100 >= usd_50
        assert usd_100 >= usd_100_copy
        assert not (usd_50 >= usd_100)

        # If the implementation allows comparison between different currencies,
        # just test that the operations don't crash
        try:
            result = usd_100 < eur_100
            # If we get here, the operation didn't raise an exception
        except ValueError:
            # It's also fine if it raises ValueError
            pass
        
        try:
            result = usd_100 == eur_100
            # Either true or false is fine, just shouldn't crash
        except ValueError:
            # It's also fine if it raises ValueError
            pass

    def test_currency_classmethods(self):
        """Test Currency class methods for creating specific currencies."""
        # USD
        usd = Currency.usd(100)
        assert usd.currency_type == CurrencyType.USD
        assert usd._value == Decimal(100)

        # EUR
        eur = Currency.eur(100)
        assert eur.currency_type == CurrencyType.EUR
        assert eur._value == Decimal(100)

        # BTC
        btc = Currency.btc(1.5)
        assert btc.currency_type == CurrencyType.BTC
        assert btc._value == Decimal("1.5")

    def test_parse_number(self):
        """Test Currency.parse_number method."""
        # Simple numeric string
        currency = Currency.parse_number("123.45")
        assert currency._value == Decimal("123.45")
        assert currency.currency_type == CurrencyType.USD  # Default

        # String with currency code
        currency = Currency.parse_number("123.45 USD")
        assert currency._value == Decimal("123.45")
        assert currency.currency_type == CurrencyType.USD

        # String with alternate currency code
        currency = Currency.parse_number("1.5 BTC")
        assert currency._value == Decimal("1.5")
        assert currency.currency_type == CurrencyType.BTC

        # Numeric with comma separator
        currency = Currency.parse_number("1,234.56")
        assert currency._value == Decimal("1234.56")
        assert currency.currency_type == CurrencyType.USD
        
        # Test parsing with USD symbol prefix
        currency = Currency.parse_number("$123.45")
        assert currency._value == Decimal("123.45")
        assert currency.currency_type == CurrencyType.USD
        
        # Test parsing with EUR symbol prefix
        currency = Currency.parse_number("€99.95")
        assert currency._value == Decimal("99.95")
        assert currency.currency_type == CurrencyType.EUR
        
        # Test parsing with GBP symbol prefix
        currency = Currency.parse_number("£45.67")
        assert currency._value == Decimal("45.67")
        assert currency.currency_type == CurrencyType.GBP
        
        # Test parsing with space after the symbol
        currency = Currency.parse_number("$ 50.25")
        assert currency._value == Decimal("50.25")
        assert currency.currency_type == CurrencyType.USD
            
        # Invalid format should raise some kind of error
        with pytest.raises((ValueError, decimal.InvalidOperation)):
            Currency.parse_number("completely invalid")

    def test_formatting(self):
        """Test Currency formatting with different precisions."""
        # USD formatting
        usd = Currency(1234.56, CurrencyType.USD)
        # Check basic formatting - either prefix or suffix is fine
        assert "1,234.56" in str(usd)
        assert "$" in str(usd)

        # Test BTC with higher precision
        btc = Currency(1.23456789, CurrencyType.BTC)
        # Just verify the Bitcoin symbol is included
        assert "₿" in str(btc) 
        # And that some form of the number is included
        assert "1.2346" in str(btc) or "1.23456789" in str(btc) or "1.2345" in str(btc)

        # Test EUR
        eur = Currency(1234.56, CurrencyType.EUR)
        # Check the euro symbol is included
        assert "€" in str(eur)
        # And that the number is included
        assert "1,234.56" in str(eur) or "1234.56" in str(eur)
