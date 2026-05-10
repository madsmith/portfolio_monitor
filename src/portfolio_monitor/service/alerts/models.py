from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4


ChannelType = Literal["dashboard", "openclaw_ws", "openclaw_http", "matrix"]


@dataclass
class AlertRule:
    """A single detector rule belonging to a user."""

    id: str
    ticker: str                  # "" means apply to all symbols
    kind: str                    # detector kind, e.g. "percent_change"
    args: dict[str, Any] = field(default_factory=dict)
    asset_type: str | None = None  # None = all types; "stock" / "crypto" / "currency"

    @classmethod
    def create(cls, ticker: str, kind: str, args: dict[str, Any] | None = None, asset_type: str | None = None) -> "AlertRule":
        """Create a new rule with a freshly-generated UUID."""
        return cls(id=uuid4().hex, ticker=ticker, kind=kind, args=args or {}, asset_type=asset_type)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "ticker": self.ticker, "asset_type": self.asset_type, "kind": self.kind, "args": self.args}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AlertRule":
        return cls(
            id=d["id"],
            ticker=d.get("ticker", ""),
            kind=d.get("kind", ""),
            args=d.get("args") or {},
            asset_type=d.get("asset_type"),
        )


@dataclass
class ChannelConfig:
    """Configuration for a single delivery channel belonging to a user."""

    name: str            # user-defined stable identifier, e.g. "matrix", "dashboard"
    type: str            # ChannelType literal
    enabled: bool = True
    default: bool = True  # True = receives all alerts unless a rule override says otherwise
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "enabled": self.enabled,
            "default": self.default,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ChannelConfig":
        return cls(
            name=d["name"],
            type=d["type"],
            enabled=d.get("enabled", True),
            default=d.get("default", True),
            params=d.get("params") or {},
        )


@dataclass
class RuleChannelOverride:
    """Deviates from a channel's default routing for a specific rule."""

    rule_id: str         # references AlertRule.id
    channel_name: str    # references ChannelConfig.name
    include: bool        # True = force-include; False = force-exclude

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "channel_name": self.channel_name, "include": self.include}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RuleChannelOverride":
        return cls(
            rule_id=d["rule_id"],
            channel_name=d["channel_name"],
            include=bool(d["include"]),
        )


@dataclass
class UserAlertConfig:
    """Complete alert configuration for one user."""

    channels: list[ChannelConfig] = field(default_factory=list)
    rules: list[AlertRule] = field(default_factory=list)
    overrides: list[RuleChannelOverride] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "channels": [c.to_dict() for c in self.channels],
            "rules": [r.to_dict() for r in self.rules],
            "overrides": [o.to_dict() for o in self.overrides],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "UserAlertConfig":
        if not d:
            return cls()
        return cls(
            channels=[ChannelConfig.from_dict(c) for c in d.get("channels") or []],
            rules=[AlertRule.from_dict(r) for r in d.get("rules") or []],
            overrides=[RuleChannelOverride.from_dict(o) for o in d.get("overrides") or []],
        )

    def effective_channels(self, rule: AlertRule) -> list[ChannelConfig]:
        """Return the channels that should receive alerts for this rule."""
        rule_overrides = {
            o.channel_name: o.include
            for o in self.overrides
            if o.rule_id == rule.id
        }
        return [
            ch for ch in self.channels
            if ch.enabled and rule_overrides.get(ch.name, ch.default)
        ]

    def delete_rule(self, rule_id: str) -> bool:
        """Remove a rule and cascade-delete its overrides. Returns True if found."""
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        self.overrides = [o for o in self.overrides if o.rule_id != rule_id]
        return len(self.rules) < before
