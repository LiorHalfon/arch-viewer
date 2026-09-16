"""An abstraction owned by the domain: infra implements it (A9, V8)."""

from typing import Protocol


class OrderStore(Protocol):
    def save(self, order_id: int) -> None: ...
