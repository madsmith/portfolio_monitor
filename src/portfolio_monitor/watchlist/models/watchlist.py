from dataclasses import dataclass, field
import hashlib
from typing import Any

from .watchlist_entry import WatchlistEntry


@dataclass
class Watchlist:
    """A named collection of watched symbols owned by a user."""

    name: str
    id: str = ""
    owner: str = "default"
    entries: list[WatchlistEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = hashlib.sha256(f"{self.owner}:{self.name}".encode()).hexdigest()[:16]

    def get_entry(self, ticker: str) -> WatchlistEntry | None:
        for e in self.entries:
            if e.symbol.ticker == ticker:
                return e
        return None

    @classmethod
    def from_dict(cls, data: dict[str, Any], owner: str = "default", id_hash_seed: str | None = None) -> "Watchlist":
        if id_hash_seed:
            watchlist_id = hashlib.sha256(id_hash_seed.encode()).hexdigest()[:16]
        else:
            watchlist_id = data.get("id", "")

        wl = cls(name=data["name"], id=watchlist_id, owner=owner)
        for entry_data in data.get("entries", []):
            wl.entries.append(WatchlistEntry.from_dict(entry_data))
        return wl

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "id": self.id,
            "entries": [e.to_dict() for e in self.entries],
        }
