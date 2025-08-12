#!/usr/bin/env python3
"""
Demo script for portfolio functionality.
"""

from decimal import Decimal
import logging
import os
import sys
from pathlib import Path

# Add project root to path to allow running script directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from nexus_portfolio_monitor.core.config import load_config
from nexus_portfolio_monitor.portfolio import load_portfolios, Portfolio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main function to demonstrate portfolio functionality."""
    # Load configuration
    logger.info("Loading configuration...")
    config = load_config()
    
    # Load portfolios
    portfolio_path = Path("docs/examples/")
    logger.info(f"Loading portfolios from path: {portfolio_path}")
    portfolios = load_portfolios(portfolio_path)
    
    # Print portfolio information
    logger.info(f"Loaded {len(portfolios)} portfolios")
    
    for portfolio in portfolios:
        print(f"\nPortfolio: {portfolio.name}")
        
        # Print stocks
        if portfolio.stocks:
            print("  Stocks:")
            for asset in portfolio.stocks:
                lots_info = f"{len(asset.lots)} lots" if asset.lots else "monitoring only"
                print(f"    - {asset.symbol}: {lots_info}")
                for i, lot in enumerate(asset.lots):
                    print(f"      Lot {i+1}: {lot.amount} @ ${lot.price}")
        
        # Print currencies
        if portfolio.currencies:
            print("  Cryptocurrencies:")
            for asset in portfolio.currencies:
                lots_info = f"{len(asset.lots)} lots" if asset.lots else "monitoring only"
                print(f"    - {asset.symbol}: {lots_info}")
                for i, lot in enumerate(asset.lots):
                    print(f"      Lot {i+1}: {lot.amount} @ ${lot.price}")
    
    # Simulate price updates
    print("\nSimulating price updates...")
    price_data = {
        "AAPL": Decimal("175.50"),
        "MSFT": Decimal("310.25"),
        "GOOGL": Decimal("140.75"),
        "X:BTCUSD": Decimal("45000.00"),
    }
    
    for portfolio in portfolios:
        portfolio.update_prices(price_data)
        
        print(f"\nUpdated Portfolio: {portfolio.name}")
        print(f"  Total Value: ${portfolio.total_value:.2f}")
        print(f"  Total Cost Basis: ${portfolio.total_cost_basis:.2f}")
        print(f"  Profit/Loss: ${portfolio.total_profit_loss:.2f} ({portfolio.profit_loss_percentage:.2f}%)")
        
        for asset in portfolio.assets():
            if asset.lots:  # Only show P/L for assets with lots
                current = asset.current_price or Decimal("0")
                print(f"  {asset.symbol}: ${current} (P/L: ${asset.profit_loss:.2f}, {asset.profit_loss_percentage:.2f}%)")


if __name__ == "__main__":
    main()
