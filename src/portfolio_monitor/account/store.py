from portfolio_monitor.data.database import AppDatabase
from portfolio_monitor.data.database.accounts import AccountRecord, AccountRole

from .models import Account, Role
from .password import PBKDF2PasswordHasher, PasswordHasher


class AccountStore:
    """Account CRUD backed by AppDatabase. Returns service-layer Account objects."""

    def __init__(self, db: AppDatabase, hasher: PasswordHasher | None = None) -> None:
        self._module = db.accounts
        self._hasher: PasswordHasher = hasher or PBKDF2PasswordHasher()

    def get_all(self) -> list[Account]:
        return [self._to_account(r) for r in self._module.get_all()]

    def get(self, username: str) -> Account | None:
        record = self._module.get(username)
        return self._to_account(record) if record else None

    def create(self, username: str, password: str, role: Role) -> Account:
        if self._module.get(username) is not None:
            raise ValueError(f"Account '{username}' already exists")
        password_hash = self._hasher.hash_password(password)
        record = self._module.create(username, password_hash, AccountRole(role))
        return self._to_account(record)

    def delete(self, username: str) -> bool:
        return self._module.delete(username)

    def update_role(self, username: str, role: Role) -> bool:
        return self._module.update_role(username, AccountRole(role))

    def update_password(self, username: str, new_password: str) -> bool:
        return self._module.update_password(username, self._hasher.hash_password(new_password))

    def verify(self, username: str, password: str) -> Account | None:
        record = self._module.get(username)
        if record is None:
            return None
        if self._hasher.verify_password(password, record.password_hash):
            return self._to_account(record)
        return None

    def save(self) -> None:
        pass  # no-op: writes are immediate in SQLite

    @staticmethod
    def _to_account(record: AccountRecord) -> Account:
        return Account(
            username=record.username,
            password_hash=record.password_hash,
            role=Role(record.role),
        )
