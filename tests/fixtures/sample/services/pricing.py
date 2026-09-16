"""Relative import of a sibling package, plus a function-level import."""

from ..domain import model


def total(order: "model.Order") -> int:
    from sample.infra.cache import get_rate

    return order.amount * get_rate()
