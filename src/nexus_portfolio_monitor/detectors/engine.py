

from nexus_portfolio_monitor.data.aggregate_cache import Aggregate
from nexus_portfolio_monitor.detectors.base import Alert, Detector
from datetime import datetime, timedelta

class DeviationEngine:

    def __init__(
        self, detectors: list[Detector],
        cooldown: timedelta = timedelta(minutes=15),
        extended_hours: bool = False
    ):
        self.detectors = detectors
        self.cooldown = cooldown
        self.extended_hours = extended_hours
        self.last_alert_at: dict[tuple[str, str], datetime] = {}

    def process(self, ticker: str, aggregate: Aggregate) -> list[Alert] | None:
        alerts: list[Alert] = []
        for det in self.detectors:
            alert = det.update(ticker, aggregate)
            if not alert:
                continue

            # Check alert for cooldown
            key = (alert.ticker, alert.kind)
            last = self.last_alert_at.get(key, None)
            if last and (alert.at - last) < self.cooldown:
                continue
            self.last_alert_at[key] = alert.at

            alerts.append(alert)
        return alerts