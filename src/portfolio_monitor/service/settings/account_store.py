from pathlib import Path
from typing import Any

import yaml

from portfolio_monitor.service.alerts.models import UserAlertConfig
from .models import Account, Role
from .password import PBKDF2PasswordHasher, PasswordHasher


class AccountStore:
    """Loads and persists user accounts from/to settings.yaml.

    The default admin account (from config_private.yaml) is not stored here;
    only named accounts and the default admin's alert config are.
    """

    def __init__(self, settings_path: Path, hasher: PasswordHasher | None = None) -> None:
        self._path: Path = settings_path
        self._hasher: PasswordHasher = hasher or PBKDF2PasswordHasher()
        self._accounts: dict[str, Account] = {}
        self._default_admin_alert_config: UserAlertConfig = UserAlertConfig()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> None:
        if not self._path.exists():
            self._accounts = {}
            self._default_admin_alert_config = UserAlertConfig()
            return

        with self._path.open() as f:
            data = yaml.safe_load(f) or {}

        self._default_admin_alert_config = UserAlertConfig.from_dict(
            data.get("default_admin_alerts")
        )
        raw_accounts = data.get("accounts") or []
        self._accounts = {
            account["username"]: Account(
                username=account["username"],
                password_hash=account["password_hash"],
                role=Role(account["role"]),
                alert_config=UserAlertConfig.from_dict(account.get("alerts")),
            )
            for account in raw_accounts
        }

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "default_admin_alerts": self._default_admin_alert_config.to_dict(),
            "accounts": [
                {
                    "username": account.username,
                    "password_hash": account.password_hash,
                    "role": str(account.role),
                    "alerts": account.alert_config.to_dict(),
                }
                for account in self._accounts.values()
            ],
        }
        with self._path.open("w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    # ------------------------------------------------------------------
    # Default admin alert config
    # ------------------------------------------------------------------

    def get_default_admin_alert_config(self) -> UserAlertConfig:
        return self._default_admin_alert_config

    def set_default_admin_alert_config(self, config: UserAlertConfig) -> None:
        self._default_admin_alert_config = config

    # ------------------------------------------------------------------
    # Account CRUD
    # ------------------------------------------------------------------

    def get_all(self) -> list[Account]:
        return list(self._accounts.values())

    def get(self, username: str) -> Account | None:
        return self._accounts.get(username)

    def create(self, username: str, password: str, role: Role) -> Account:
        if username in self._accounts:
            raise ValueError(f"Account '{username}' already exists")
        account = Account(
            username=username,
            password_hash=self._hasher.hash_password(password),
            role=role,
        )
        self._accounts[username] = account
        return account

    def delete(self, username: str) -> bool:
        return self._accounts.pop(username, None) is not None

    def update_role(self, username: str, role: Role) -> bool:
        account = self._accounts.get(username)
        if account is None:
            return False
        account.role = role
        return True

    def update_password(self, username: str, new_password: str) -> bool:
        account = self._accounts.get(username)
        if account is None:
            return False
        account.password_hash = self._hasher.hash_password(new_password)
        return True

    def update_alert_config(self, username: str, config: UserAlertConfig) -> bool:
        account = self._accounts.get(username)
        if account is None:
            return False
        account.alert_config = config
        return True

    def verify(self, username: str, password: str) -> Account | None:
        account = self.get(username)
        if account is None:
            return None
        if self._hasher.verify_password(password, account.password_hash):
            return account
        return None
