"""
Portfolio loader module for Nexus Portfolio Monitor.
"""

import logging
from pathlib import Path

from omegaconf import OmegaConf

from .portfolio import Portfolio

logger = logging.getLogger(__name__)


def load_portfolios(portfolio_path: Path) -> list[Portfolio]:
    """
    Load all portfolios from YAML files in the configured portfolio path.

    Args:
        config: Application configuration

    Returns:
        A list of Portfolio objects
    """
    portfolios = []

    # Ensure the directory exists
    if not portfolio_path.exists():
        logger.warning(f"Portfolio path {portfolio_path} does not exist")
        return []

    # Find all YAML files in the directory
    yaml_files = list(portfolio_path.glob("*.yaml")) + list(
        portfolio_path.glob("*.yml")
    )

    if not yaml_files:
        logger.warning(f"No portfolio files found in {portfolio_path}")
        return []

    # Load each YAML file
    for yaml_file in yaml_files:
        try:
            with open(yaml_file, "r") as f:
                data = OmegaConf.load(f)

            # Check if the file contains a portfolio
            if "name" not in data:
                logger.warning(f"YAML file does not contain a portfolio: {yaml_file}")
                continue

            portfolio = Portfolio.from_dict(dict(data))
            portfolios.append(portfolio)
            logger.info(f"Loaded portfolio '{portfolio.name}' from {yaml_file}")

        except Exception as e:
            logger.error(f"Error loading portfolio from {yaml_file}: {str(e)}")
            import traceback

            traceback.print_exc()

    return portfolios
