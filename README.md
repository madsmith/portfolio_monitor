# Nexus Portfolio Monitor

A Python application for monitoring investment portfolios using financial market data from Polygon.io.

## Description

Nexus Portfolio Monitor is a tool designed to track and monitor investment portfolios across various assets. It leverages the Polygon.io API to fetch real-time and historical market data for stocks and cryptocurrencies.

## Features

- Financial data integration via Polygon.io API
- Portfolio tracking from configuration files

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/nexus-portfolio-monitor.git

# Navigate to the project directory
cd nexus-portfolio-monitor

# Install the package in development mode
pip install -e .
```

## Configuration

The application uses YAML configuration files:

1. `config.yaml` - Main configuration file
2. `config_private.yaml` - Private configuration file with API keys

Example configuration:

```yaml
nexus:
  portfolios:
    - name: "Personal"
      assets:
        - ticker: "AAPL"
          lots:
            - amount: 10
              price: 150.00

polygon:
  api-key: "${private.polygon.api-key}"
```

## Usage

```bash
# Run the portfolio monitor service
portfolio-monitor
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
