# Nexus Portfolio Monitor

A Python application for monitoring investment portfolios.

## Description

Nexus Portfolio Monitor is a tool designed to help users track their investment portfolios across various assets including stocks, cryptocurrencies, and more.

## Features

- Portfolio tracking
- Performance analytics
- Asset allocation visualization
- Historical data tracking

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/nexus-portfolio-monitor.git

# Navigate to the project directory
cd nexus-portfolio-monitor

# Install the package
pip install -e .
```

## Usage

```python
from nexus_portfolio_monitor import Portfolio

# Create a new portfolio
portfolio = Portfolio("My Portfolio")

# Add assets
portfolio.add_asset("AAPL", amount=10, price=150.00)
portfolio.add_asset("MSFT", amount=5, price=300.00)

# View portfolio summary
portfolio.summary()
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
