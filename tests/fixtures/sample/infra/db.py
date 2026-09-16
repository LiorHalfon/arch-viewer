"""Closes a cycle: infra -> services, while services -> infra via cache."""

from sample.services import pricing


class Session:
    def commit(self) -> None:
        pricing.total


def store() -> "OrderStore":
    from sample.domain.ports import OrderStore

    return Session()  # type: ignore[return-value]
