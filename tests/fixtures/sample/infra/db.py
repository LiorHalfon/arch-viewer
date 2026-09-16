"""Closes a cycle: infra -> services, while services -> infra via cache."""

from sample.services import pricing


class Session:
    def commit(self) -> None:
        pricing.total
