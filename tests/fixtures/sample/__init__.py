"""Sample project: re-exports Order so `from sample import Order` works."""

from sample.domain.model import Order

__all__ = ["Order"]
