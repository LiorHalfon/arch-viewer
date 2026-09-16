"""Top of the stack: imports services and domain, nothing imports it."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import grimp

from sample.domain import Order
from sample.services import pricing

if TYPE_CHECKING:
    from sample.infra.db import Session


def quote(payload: str) -> str:
    order: Order = json.loads(payload)
    return json.dumps(pricing.total(order), default=str) + grimp.__name__[:0]


def save(session: "Session") -> None:
    session.commit()
