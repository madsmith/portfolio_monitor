"""
Currency module for Nexus Portfolio Monitor.
"""

from decimal import Decimal, getcontext, Context, ROUND_HALF_UP
from enum import Enum, auto
from dataclasses import dataclass
from typing import ClassVar, Any


class CurrencyType(Enum):
    """
    Enumeration of supported currency types with their properties.
    
    Each currency has:
    - Symbol: The currency symbol
    - Name: The full name of the currency
    - Precision: Default decimal precision for formatting
    - Notes: Additional information about the currency
    """
    # Fiat currencies
    USD = auto()
    EUR = auto()
    GBP = auto()
    JPY = auto()
    CAD = auto()
    AUD = auto()
    
    # Cryptocurrencies
    BTC = auto()
    ETH = auto()
    USDT = auto()
    USDC = auto()
    XRP = auto()
    ADA = auto()
    SOL = auto()
    DOGE = auto()
    LTC = auto()
    
    @property
    def config(self) -> 'CurrencyConfig':
        """Get the configuration for this currency type."""
        return CURRENCY_CONFIGS[self]


@dataclass(frozen=True)
class CurrencyConfig:
    """Configuration for a specific currency type."""
    symbol: str
    name: str
    precision: int


# Define all currency configurations
CURRENCY_CONFIGS: dict[CurrencyType, CurrencyConfig] = {
    # Fiat currencies
    CurrencyType.USD: CurrencyConfig("$", "US Dollar", 2),
    CurrencyType.EUR: CurrencyConfig("€", "Euro", 2),
    CurrencyType.GBP: CurrencyConfig("£", "British Pound", 2),
    CurrencyType.JPY: CurrencyConfig("¥", "Japanese Yen", 0),
    CurrencyType.CAD: CurrencyConfig("C$", "Canadian Dollar", 2),
    CurrencyType.AUD: CurrencyConfig("A$", "Australian Dollar", 2),
    
    # Cryptocurrencies
    CurrencyType.BTC: CurrencyConfig("₿", "Bitcoin", 8),
    CurrencyType.ETH: CurrencyConfig("Ξ", "Ethereum", 18),
    CurrencyType.USDT: CurrencyConfig("USDT", "Tether", 6),
    CurrencyType.USDC: CurrencyConfig("USDC", "USD Coin", 6),
    CurrencyType.XRP: CurrencyConfig("XRP", "Ripple", 6),
    CurrencyType.ADA: CurrencyConfig("ADA", "Cardano", 6),
    CurrencyType.SOL: CurrencyConfig("SOL", "Solana", 9),
    CurrencyType.DOGE: CurrencyConfig("DOGE", "Dogecoin", 8),
    CurrencyType.LTC: CurrencyConfig("LTC", "Litecoin", 8),
}

# Define equivalent currencies for arithmetic operations
# Each entry is a set of currencies that can be used interchangeably
EQUIVALENT_CURRENCIES = {
    # USD and stable coins are treated as equivalent
    frozenset({CurrencyType.USD, CurrencyType.USDT, CurrencyType.USDC}),
}


class Currency:
    """
    A class representing a monetary amount with a specific currency type.
    
    This class uses composition with Decimal for value representation and 
    adds currency-specific functionality.
    """
    
    @staticmethod
    def are_equivalent_currencies(currency_type1: CurrencyType, currency_type2: CurrencyType) -> bool:
        """Check if two currency types are equivalent for arithmetic operations."""
        if currency_type1 == currency_type2:
            return True
            
        # Check if they're in any equivalent currency set
        for equivalent_set in EQUIVALENT_CURRENCIES:
            if currency_type1 in equivalent_set and currency_type2 in equivalent_set:
                return True
                
        return False
    
    # Default currency settings
    DEFAULT_PRECISION: ClassVar[int] = 4
    DEFAULT_CURRENCY_TYPE: ClassVar[CurrencyType] = CurrencyType.USD
    
    def __init__(
        self, 
        value: Any, 
        currency_type: CurrencyType | str | None = None,
        context: Context | None = None
    ):
        """        
        Create a new Currency instance.
        
        Args:
            value: A number, string, or Currency representing the monetary amount
            currency_type: The type of currency (CurrencyType enum or string like "USD", "$", etc.)
                If a string is provided, it will attempt to match it to a known currency type
                or raise ValueError if not found
            context: Optional decimal context for precision control
        """
        
        # Set default context with appropriate precision if not provided
        if context is None:
            context = getcontext().copy()
            context.prec = self.DEFAULT_PRECISION
            context.rounding = ROUND_HALF_UP
        
        # If value is already a Currency, extract its decimal value
        if isinstance(value, Currency):
            self._value = value._value
            # Use the provided currency_type or default to the source currency's type
            if isinstance(currency_type, str):
                self.currency_type = self._parse_currency_type(currency_type)
            elif currency_type is None:
                if value.currency_type is None:
                    self.currency_type = self.DEFAULT_CURRENCY_TYPE
                self.currency_type = value.currency_type
            else:
                self.currency_type = currency_type
        else:
            # Store the value as a Decimal
            if isinstance(value, float):
                # Convert float to string to avoid precision issues
                self._value = Decimal(str(value), context)
            else:
                self._value = Decimal(value, context)
            # Parse string currency_type if provided
            if isinstance(currency_type, str):
                self.currency_type = self._parse_currency_type(currency_type)
            elif currency_type is None:
                self.currency_type = self.DEFAULT_CURRENCY_TYPE
            else:
                self.currency_type = currency_type
    
    def _parse_currency_type(self, currency_str: str) -> CurrencyType:
        """Parse a currency type from a string.
        
        Args:
            currency_str: String representation of currency type (e.g., "USD", "BTC")
        
        Returns:
            CurrencyType enum member matching the string
            
        Raises:
            ValueError: If the string does not match any known currency type
        """
        # First try direct match with enum name
        try:
            return CurrencyType[currency_str.upper()]
        except KeyError:
            pass
        
        # Try to match by symbol
        for currency_type in CurrencyType:
            config = CURRENCY_CONFIGS[currency_type]
            if config.symbol.strip() == currency_str.strip():
                return currency_type
        
        # If we got here, no match found
        valid_currencies = ', '.join([ct.name for ct in CurrencyType])
        raise ValueError(f"Unknown currency type: '{currency_str}'. Valid values are: {valid_currencies}")
    
    @property
    def symbol(self) -> str:
        """Get the currency symbol."""
        return self.currency_type.config.symbol
    
    @property
    def name(self) -> str:
        """Get the full currency name."""
        return self.currency_type.config.name
    
    @property
    def precision(self) -> int:
        """Get the default precision for this currency."""
        return self.currency_type.config.precision
    
    def format(self, places: int | None = None, show_currency: bool = True) -> str:
        """
        Format the currency value as a string.
        
        Args:
            places: Number of decimal places to show (uses currency default if None)
            show_currency: Whether to include the currency symbol
            
        Returns:
            Formatted string representation
        """
        # Use default precision for this currency type if not specified
        if places is None:
            places = self.precision
        
        # Format the number with commas and specified decimal places
        formatted = f"{self._value:,.{places}f}"
        
        # Add currency symbol if requested
        if show_currency:
            symbol = self.symbol
            # Prefix symbols like $ and £, suffix others
            return f"{symbol}{formatted}" if symbol in ["$", "£"] else f"{formatted} {symbol}"
        
        return formatted
    
    def convert_to(self, target_currency: CurrencyType, rate: Decimal) -> 'Currency':
        """
        Convert this currency to another currency using the provided exchange rate.
        
        Args:
            target_currency: The target currency type
            rate: The exchange rate from this currency to the target currency
            
        Returns:
            A new Currency instance in the target currency
        """
        return Currency(self._value * rate, target_currency)
    
    def __str__(self) -> str:
        """Return formatted string representation."""
        return self.format()
    
    def __repr__(self) -> str:
        """Return technical representation."""
        return f"Currency({self._value}, {self.currency_type.name})"
    
    def __add__(self, other) -> 'Currency':
        """Add two Currency objects or a Currency and a number."""
        if isinstance(other, Currency):
            if not self.are_equivalent_currencies(self.currency_type, other.currency_type):
                raise ValueError(f"Cannot add currencies of different types: {self.currency_type.name} and {other.currency_type.name}")
            # Keep the calling currency's type when doing math between equivalent currencies
            return Currency(self._value + other._value, self.currency_type)
        # Adding with a number or Decimal
        return Currency(self._value + other, self.currency_type)
    
    def __sub__(self, other) -> 'Currency':
        """Subtract two Currency objects or a Currency and a number."""
        if isinstance(other, Currency):
            if not self.are_equivalent_currencies(self.currency_type, other.currency_type):
                raise ValueError(f"Cannot subtract currencies of different types: {self.currency_type.name} and {other.currency_type.name}")
            # Keep the calling currency's type when doing math between equivalent currencies
            return Currency(self._value - other._value, self.currency_type)
        # Subtracting a number or Decimal
        return Currency(self._value - other, self.currency_type)
    
    def __mul__(self, other) -> 'Currency':
        """Multiply a Currency by a number."""
        # If multiplying by another Currency, use the left operand's currency type
        if isinstance(other, Currency):
            return Currency(self._value * other._value, self.currency_type)
        # Otherwise return a Currency
        return Currency(self._value * other, self.currency_type)
    
    def __truediv__(self, other: Any) -> "Currency":
        """Division operation."""
        if isinstance(other, Currency):
            # We could raise a ValueError here if currency types don't match
            # But for now, just return the result as a raw numeric value
            return Currency(self._value / other._value, self.currency_type)
        elif isinstance(other, (int, float, Decimal)):
            return Currency(self._value / Decimal(other), self.currency_type)
        else:
            return NotImplemented
            
    def __neg__(self) -> "Currency":
        """Negation operation."""
        return Currency(-self._value, self.currency_type)
        
    def __abs__(self) -> "Currency":
        """Absolute value operation."""
        return Currency(abs(self._value), self.currency_type)
    
    def __radd__(self, other) -> 'Currency':
        """Add a number to a Currency."""
        return Currency(other + self._value, self.currency_type)
    
    def __rsub__(self, other) -> 'Currency':
        """Subtract a Currency from a number."""
        return Currency(other - self._value, self.currency_type)
    
    def __rmul__(self, other) -> 'Currency':
        """Multiply a number by a Currency."""
        return Currency(other * self._value, self.currency_type)
    
    
    # Enable comparison operations with the wrapped decimal value
    def __eq__(self, other) -> bool:
        if isinstance(other, Currency):
            return (self.currency_type == other.currency_type and
                    self._value == other._value)
        return self._value == other

    def __lt__(self, other) -> bool:
        if isinstance(other, Currency):
            if not self.are_equivalent_currencies(self.currency_type, other.currency_type):
                raise ValueError(f"Cannot compare currencies of different types: {self.currency_type.name} and {other.currency_type.name}")
            return self._value < other._value
        return self._value < other
    
    def __le__(self, other) -> bool:
        if isinstance(other, Currency):
            if not self.are_equivalent_currencies(self.currency_type, other.currency_type):
                raise ValueError(f"Cannot compare currencies of different types: {self.currency_type.name} and {other.currency_type.name}")
            return self._value <= other._value
        return self._value <= other
    
    def __gt__(self, other) -> bool:
        if isinstance(other, Currency):
            if not self.are_equivalent_currencies(self.currency_type, other.currency_type):
                raise ValueError(f"Cannot compare currencies of different types: {self.currency_type.name} and {other.currency_type.name}")
            return self._value > other._value
        return self._value > other
    
    def __ge__(self, other) -> bool:
        if isinstance(other, Currency):
            if not self.are_equivalent_currencies(self.currency_type, other.currency_type):
                raise ValueError(f"Cannot compare currencies of different types: {self.currency_type.name} and {other.currency_type.name}")
            return self._value >= other._value
        return self._value >= other
    
    # Provide access to decimal's numeric methods
    def __float__(self) -> float:
        return float(self._value)
    
    def __int__(self) -> int:
        return int(self._value)
    
    # Allow accessing the underlying decimal value directly
    @property
    def value(self) -> Decimal:
        """Get the underlying decimal value."""
        return self._value

    @classmethod
    def parse_number(cls, value: Any) -> 'Currency':
        """Parse a number from a string, optionally with currency type.
    
        Examples:
            "123.45" -> Currency(123.45, USD)
            "123.45 USD" -> Currency(123.45, USD)
            "123.45 BTC" -> Currency(123.45, BTC)
            "$123.45" -> Currency(123.45, USD)
            "€123.45" -> Currency(123.45, EUR)
        """
        str_value = str(value).strip()
        
        # Create a mapping of currency symbols to currency types
        symbol_to_currency = {config.symbol: currency_type for currency_type, config in CURRENCY_CONFIGS.items()}
        
        # Check for currency symbols at the beginning
        for symbol, curr_type in symbol_to_currency.items():
            if str_value.startswith(symbol):
                # Remove the symbol and parse the remaining numeric value
                str_value = str_value[len(symbol):].strip()
                currency_type = curr_type
                break
        else:  # No symbol found at beginning, check for currency code at the end
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
        return cls(number_value, currency_type)
    
    # Convenience factory methods
    @classmethod
    def usd(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a USD Currency."""
        return cls(amount, CurrencyType.USD)

    @classmethod
    def btc(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a BTC Currency."""
        return cls(amount, CurrencyType.BTC)

    @classmethod
    def eur(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a EUR Currency."""
        return cls(amount, CurrencyType.EUR)

    @classmethod
    def gbp(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a GBP Currency."""
        return cls(amount, CurrencyType.GBP)

    @classmethod
    def jpy(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a JPY Currency."""
        return cls(amount, CurrencyType.JPY)

    @classmethod
    def cad(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a CAD Currency."""
        return cls(amount, CurrencyType.CAD)

    @classmethod
    def aud(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a AUD Currency."""
        return cls(amount, CurrencyType.AUD)

    @classmethod
    def usdt(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a USDT Currency."""
        return cls(amount, CurrencyType.USDT)
        
    @classmethod
    def usdc(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a USDC Currency."""
        return cls(amount, CurrencyType.USDC)

    @classmethod
    def eth(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a ETH Currency."""
        return cls(amount, CurrencyType.ETH)

    @classmethod
    def ada(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create an ADA Currency."""
        return cls(amount, CurrencyType.ADA)

    @classmethod
    def sol(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a SOL Currency."""
        return cls(amount, CurrencyType.SOL)

    @classmethod
    def doge(cls, amount: int | float | str | Decimal) -> 'Currency':
        """Convenience method to create a DOGE Currency."""
        return cls(amount, CurrencyType.DOGE)

# Allow accessing the underlying decimal value directly
@property
def value(self) -> Decimal:
    """Get the underlying decimal value."""
    return self._value

@classmethod
def parse_number(cls, value: Any) -> 'Currency':
    """Parse a number from a string, optionally with currency type.
    
    Examples:
        "123.45" -> Currency(123.45, USD)
        "123.45 USD" -> Currency(123.45, USD)
        "123.45 BTC" -> Currency(123.45, BTC)
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
            str_value = ' '.join(parts[:-1])
        except (KeyError, ValueError):
            # If the currency code isn't valid, assume it's part of the number or description
            pass
    
    # Parse the numerical value
    number_value = Decimal(str_value.replace(",", ""))
    
    # Create and return a Currency object
    return cls(number_value, currency_type)

# Convenience factory methods
@classmethod
def usd(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a USD Currency."""
    return cls(amount, CurrencyType.USD)

@classmethod
def btc(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a BTC Currency."""
    return cls(amount, CurrencyType.BTC)

@classmethod
def eur(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a EUR Currency."""
    return cls(amount, CurrencyType.EUR)

@classmethod
def gbp(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a GBP Currency."""
    return cls(amount, CurrencyType.GBP)

@classmethod
def jpy(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a JPY Currency."""
    return cls(amount, CurrencyType.JPY)

@classmethod
def cad(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a CAD Currency."""
    return cls(amount, CurrencyType.CAD)

@classmethod
def aud(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a AUD Currency."""
    return cls(amount, CurrencyType.AUD)

@classmethod
def usdt(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a USDT Currency."""
    return cls(amount, CurrencyType.USDT)

@classmethod
def usdc(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a USDC Currency."""
    return cls(amount, CurrencyType.USDC)

@classmethod
def eth(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a ETH Currency."""
    return cls(amount, CurrencyType.ETH)

@classmethod
def ada(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create an ADA Currency."""
    return cls(amount, CurrencyType.ADA)

@classmethod
def sol(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a SOL Currency."""
    return cls(amount, CurrencyType.SOL)

@classmethod
def doge(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create a DOGE Currency."""
    return cls(amount, CurrencyType.DOGE)

@classmethod
def ltc(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create an LTC Currency."""
    return cls(amount, CurrencyType.LTC)

@classmethod
def xrp(cls, amount: int | float | str | Decimal) -> 'Currency':
    """Convenience method to create an XRP Currency."""
    return cls(amount, CurrencyType.XRP)
# End of Currency class
