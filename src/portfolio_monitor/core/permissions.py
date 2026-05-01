from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UserPermission:
    """Read/write flags for a single user on a permissioned object."""

    read: bool = False
    write: bool = False


class PermissionMap:
    """Per-user permission entries, typically loaded from a YAML ``permissions:`` block.

    Supports two YAML shapes:

    Dict (preferred)::

        permissions:
          martin:
            read: true
            write: true
          alice:
            read: true
            write: false

    List-of-dicts::

        permissions:
          - martin:
              read: true
              write: true
    """

    def __init__(self, entries: dict[str, UserPermission] | None = None) -> None:
        self._entries: dict[str, UserPermission] = entries or {}

    def get(self, username: str) -> UserPermission | None:
        return self._entries.get(username)

    @classmethod
    def from_yaml(cls, data: Any) -> "PermissionMap":
        """Parse a ``permissions:`` value from YAML into a ``PermissionMap``."""
        entries: dict[str, UserPermission] = {}

        if isinstance(data, Mapping):
            pairs: Any = data.items()
        elif isinstance(data, Sequence) and not isinstance(data, str):
            pairs = (
                (username, flags)
                for item in data
                if isinstance(item, Mapping)
                for username, flags in item.items()
            )
        else:
            return cls()

        for username, flags in pairs:
            if isinstance(flags, Mapping):
                entries[str(username)] = UserPermission(
                    read=bool(flags.get("read", False)),
                    write=bool(flags.get("write", False)),
                )

        return cls(entries)

    def to_dict(self) -> dict[str, dict[str, bool]]:
        return {
            username: {"read": p.read, "write": p.write}
            for username, p in self._entries.items()
        }


class PermissionsHost:
    """Mixin that provides ``can(permission, username)`` for objects with ownership.

    Concrete classes (typically dataclasses) that inherit this must declare::

        owner: str
        permissions: PermissionMap | None

    **Resolution order**:

    1. The named owner always has full access (``"default"`` is a virtual owner,
       not a real user, so this check is skipped for it).
    2. If an explicit ``permissions`` block is present, it is consulted for all
       other users — unlisted users are denied.
    3. Implicit fallback (no explicit block):
       - ``owner == "default"``  → everyone can *read*, nobody can *write*.
       - ``owner == <name>``     → only the owner can read **and** write
         (already handled by rule 1).

    Admin bypass (e.g. ``auth.is_admin``) is intentionally kept in the service
    layer so this class stays free of auth concerns.
    """

    # Declared by concrete dataclass subclasses:
    owner: str
    permissions: "PermissionMap | None"

    def can(self, permission: str, username: str) -> bool:
        """Return ``True`` if *username* holds *permission* (``"read"`` or ``"write"``)."""
        # The owner always has full access; "default" is a virtual folder owner, not a user.
        if self.owner != "default" and self.owner == username:
            return True

        if self.permissions is not None:
            entry = self.permissions.get(username)
            if entry is None:
                return False
            return bool(getattr(entry, permission, False))

        # Implicit fallback (no explicit permissions block)
        if self.owner == "default":
            return permission == "read"
        return False
