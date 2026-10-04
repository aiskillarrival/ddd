"""Domain entities.

Entities have identity (an id) and a lifecycle. In this model a ``Holding``
is an entity *inside* the ``Portfolio`` aggregate: it is only ever reached
through the aggregate root and never persisted independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .events import DomainEvent, SharesBought, SharesSold
from .value_objects import InvariantViolation, Money, Quantity, Ticker


@dataclass
class Holding:
    """A single position held inside a portfolio.

    A holding tracks a quantity of one instrument together with its
    cost basis. It raises domain events when shares are bought or sold so
    that the application layer can react without the domain knowing about
    persistence or messaging.
    """

    ticker: Ticker
    quantity: Quantity = field(default_factory=lambda: Quantity(Decimal("0")))
    cost_basis: Money = field(default_factory=Money.zero)
    _events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    def buy(self, quantity: Quantity, price: Money) -> None:
        """Increase the position, updating the average cost basis."""
        if quantity.value <= 0:
            raise InvariantViolation("Buy quantity must be positive")
        if price.currency != self.cost_basis.currency:
            raise InvariantViolation(
                f"Price currency {price.currency} does not match "
                f"holding currency {self.cost_basis.currency}"
            )
        additional_cost = price * quantity.value
        new_quantity = self.quantity.value + quantity.value
        new_basis = (self.cost_basis + additional_cost)
        self.quantity = Quantity(new_quantity)
        self.cost_basis = new_basis
        self._events.append(SharesBought(self.ticker, quantity, price))

    def sell(self, quantity: Quantity, price: Money) -> Money:
        """Reduce the position and return the realised proceeds."""
        if quantity.value <= 0:
            raise InvariantViolation("Sell quantity must be positive")
        if quantity.value > self.quantity.value:
            raise InvariantViolation(
                f"Cannot sell {quantity} of {self.ticker}: only "
                f"{self.quantity} held"
            )
        if price.currency != self.cost_basis.currency:
            raise InvariantViolation(
                f"Price currency {price.currency} does not match "
                f"holding currency {self.cost_basis.currency}"
            )
        proceeds = price * quantity.value
        # Reduce cost basis proportionally to the shares sold.
        average_cost = self.cost_basis.amount / self.quantity.value
        self.cost_basis = Money(
            self.cost_basis.amount - average_cost * quantity.value,
            self.cost_basis.currency,
        )
        self.quantity = Quantity(self.quantity.value - quantity.value)
        self._events.append(SharesSold(self.ticker, quantity, price))
        return proceeds

    def market_value(self, price: Money) -> Money:
        """Value the position at the supplied market price."""
        return price * self.quantity.value

    def unrealised_gain(self, price: Money) -> Money:
        return self.market_value(price) - self.cost_basis

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events
