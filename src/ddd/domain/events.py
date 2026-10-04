"""Domain events.

Domain events capture something meaningful that happened in the domain.
They are plain, immutable facts. The domain records them; the application
layer decides what (if anything) to do with them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .value_objects import Money, Quantity, Ticker


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Base class for all domain events."""

    occurred_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class SharesBought(DomainEvent):
    ticker: Ticker
    quantity: Quantity
    price: Money

    def __init__(self, ticker: Ticker, quantity: Quantity, price: Money) -> None:
        # frozen dataclass with a defaulted field: set via object.__setattr__
        object.__setattr__(self, "ticker", ticker)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "occurred_at", _now())


@dataclass(frozen=True, slots=True)
class SharesSold(DomainEvent):
    ticker: Ticker
    quantity: Quantity
    price: Money

    def __init__(self, ticker: Ticker, quantity: Quantity, price: Money) -> None:
        object.__setattr__(self, "ticker", ticker)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "occurred_at", _now())
