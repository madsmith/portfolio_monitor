"""Tests for UserAlertConfig, AlertRule, ChannelConfig, RuleChannelOverride."""

import pytest

from portfolio_monitor.service.alerts.models import (
    AlertRule,
    ChannelConfig,
    RuleChannelOverride,
    UserAlertConfig,
)


# ---------------------------------------------------------------------------
# AlertRule
# ---------------------------------------------------------------------------

class TestAlertRule:
    def test_create_generates_id(self) -> None:
        r = AlertRule.create("BTC", "percent_change", {"threshold": 5.0})
        assert len(r.id) == 32  # uuid4().hex
        assert r.ticker == "BTC"
        assert r.kind == "percent_change"
        assert r.args == {"threshold": 5.0}

    def test_create_no_args_defaults_to_empty(self) -> None:
        r = AlertRule.create("", "percent_change")
        assert r.args == {}

    def test_roundtrip(self) -> None:
        r = AlertRule.create("ETH", "percent_change", {"threshold": 3.0})
        assert AlertRule.from_dict(r.to_dict()) == r

    def test_from_dict_missing_fields_use_defaults(self) -> None:
        r = AlertRule.from_dict({"id": "abc123"})
        assert r.ticker == ""
        assert r.kind == ""
        assert r.args == {}


# ---------------------------------------------------------------------------
# ChannelConfig
# ---------------------------------------------------------------------------

class TestChannelConfig:
    def test_defaults(self) -> None:
        ch = ChannelConfig(name="dashboard", type="dashboard")
        assert ch.enabled is True
        assert ch.default is True
        assert ch.params == {}

    def test_roundtrip(self) -> None:
        ch = ChannelConfig(
            name="matrix", type="matrix", enabled=True, default=False,
            params={"room": "#alerts"},
        )
        assert ChannelConfig.from_dict(ch.to_dict()) == ch

    def test_from_dict_missing_optional_fields(self) -> None:
        ch = ChannelConfig.from_dict({"name": "dashboard", "type": "dashboard"})
        assert ch.enabled is True
        assert ch.default is True
        assert ch.params == {}


# ---------------------------------------------------------------------------
# RuleChannelOverride
# ---------------------------------------------------------------------------

class TestRuleChannelOverride:
    def test_roundtrip(self) -> None:
        o = RuleChannelOverride(rule_id="abc", channel_name="matrix", include=False)
        assert RuleChannelOverride.from_dict(o.to_dict()) == o


# ---------------------------------------------------------------------------
# UserAlertConfig
# ---------------------------------------------------------------------------

class TestUserAlertConfig:
    def _make_config(self) -> UserAlertConfig:
        ch_dash = ChannelConfig(name="dashboard", type="dashboard", default=True)
        ch_matrix = ChannelConfig(name="matrix", type="matrix", default=False)
        rule = AlertRule.create("BTC", "percent_change", {"threshold": 5.0})
        override = RuleChannelOverride(rule_id=rule.id, channel_name="matrix", include=True)
        return UserAlertConfig(
            channels=[ch_dash, ch_matrix],
            rules=[rule],
            overrides=[override],
        )

    def test_empty_roundtrip(self) -> None:
        cfg = UserAlertConfig()
        assert UserAlertConfig.from_dict(cfg.to_dict()) == cfg

    def test_roundtrip(self) -> None:
        cfg = self._make_config()
        assert UserAlertConfig.from_dict(cfg.to_dict()) == cfg

    def test_from_dict_none(self) -> None:
        cfg = UserAlertConfig.from_dict(None)
        assert cfg.channels == []
        assert cfg.rules == []
        assert cfg.overrides == []

    # ------------------------------------------------------------------
    # effective_channels
    # ------------------------------------------------------------------

    def test_effective_channels_default_true_included(self) -> None:
        ch = ChannelConfig(name="dashboard", type="dashboard", default=True)
        rule = AlertRule.create("BTC", "percent_change")
        cfg = UserAlertConfig(channels=[ch], rules=[rule])
        assert cfg.effective_channels(rule) == [ch]

    def test_effective_channels_default_false_excluded(self) -> None:
        ch = ChannelConfig(name="matrix", type="matrix", default=False)
        rule = AlertRule.create("BTC", "percent_change")
        cfg = UserAlertConfig(channels=[ch], rules=[rule])
        assert cfg.effective_channels(rule) == []

    def test_effective_channels_override_include(self) -> None:
        ch = ChannelConfig(name="matrix", type="matrix", default=False)
        rule = AlertRule.create("BTC", "percent_change")
        override = RuleChannelOverride(rule_id=rule.id, channel_name="matrix", include=True)
        cfg = UserAlertConfig(channels=[ch], rules=[rule], overrides=[override])
        assert cfg.effective_channels(rule) == [ch]

    def test_effective_channels_override_exclude(self) -> None:
        ch = ChannelConfig(name="dashboard", type="dashboard", default=True)
        rule = AlertRule.create("BTC", "percent_change")
        override = RuleChannelOverride(rule_id=rule.id, channel_name="dashboard", include=False)
        cfg = UserAlertConfig(channels=[ch], rules=[rule], overrides=[override])
        assert cfg.effective_channels(rule) == []

    def test_effective_channels_disabled_channel_excluded(self) -> None:
        ch = ChannelConfig(name="dashboard", type="dashboard", enabled=False, default=True)
        rule = AlertRule.create("BTC", "percent_change")
        cfg = UserAlertConfig(channels=[ch], rules=[rule])
        assert cfg.effective_channels(rule) == []

    def test_effective_channels_override_only_applies_to_matching_rule(self) -> None:
        ch = ChannelConfig(name="matrix", type="matrix", default=False)
        rule_a = AlertRule.create("BTC", "percent_change")
        rule_b = AlertRule.create("ETH", "percent_change")
        # Force-include matrix for rule_a only
        override = RuleChannelOverride(rule_id=rule_a.id, channel_name="matrix", include=True)
        cfg = UserAlertConfig(channels=[ch], rules=[rule_a, rule_b], overrides=[override])
        assert cfg.effective_channels(rule_a) == [ch]
        assert cfg.effective_channels(rule_b) == []  # matrix still default=False for rule_b

    # ------------------------------------------------------------------
    # delete_rule
    # ------------------------------------------------------------------

    def test_delete_rule_returns_true_and_removes(self) -> None:
        cfg = self._make_config()
        rule_id = cfg.rules[0].id
        assert cfg.delete_rule(rule_id) is True
        assert cfg.rules == []

    def test_delete_rule_cascades_overrides(self) -> None:
        cfg = self._make_config()
        rule_id = cfg.rules[0].id
        assert len(cfg.overrides) == 1
        cfg.delete_rule(rule_id)
        assert cfg.overrides == []

    def test_delete_rule_unknown_id_returns_false(self) -> None:
        cfg = self._make_config()
        assert cfg.delete_rule("nonexistent") is False
        assert len(cfg.rules) == 1  # unchanged

    def test_delete_rule_does_not_touch_other_rules(self) -> None:
        rule_a = AlertRule.create("BTC", "percent_change")
        rule_b = AlertRule.create("ETH", "percent_change")
        cfg = UserAlertConfig(rules=[rule_a, rule_b])
        cfg.delete_rule(rule_a.id)
        assert cfg.rules == [rule_b]
