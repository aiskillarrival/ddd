"""The Portfolio aggregate root.

The ``Portfolio`` is the consistency boundary for the whole investment
model. All mutations go through the aggregate root, which is the only
object the repository is allowed to load or save. A portfolio owns a set
of ``Holding`` entities and enforces the rules that must hold at all times.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

from .entities import Holding
from .events import DomainEvent
from .value_objects import (
    Currency,
    InvariantViolation,
    Money,
    Quantity,
    Ticker,
)


@dataclass
class Portfolio:
    """A named collection of investments owned by one person.

    Invariants enforced by this aggregate:

    * A portfolio always has a non-empty name.
    * Every currency used inside a portfolio is consistent; mixing
      currencies within a single portfolio is rejected.
    * Cash can never go negative.
    """

    name: str
    currency: Currency = Currency.GBP
    id: UUID = field(default_factory=uuid4)
    cash_balance: Money = field(default_factory=Money.zero)
    _holdings: dict[str, Holding] = field(default_factory=dict, repr=False)
    _events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise InvariantViolation("Portfolio name must not be empty")
        if self.cash_balance.currency != self.currency:
            self.cash_balance = Money(self.cash_balance.amount, self.currency)

    @classmethod
    def reconstitute(
        cls,
        *,
        id: UUID,
        name: str,
        currency: Currency,
        cash_balance: Money,
        holdings: list[Holding],
    ) -> "Portfolio":
        """Rebuild a portfolio from persisted state.

        Used by repositories when loading an aggregate. It bypasses the
        command methods (which would re-raise events) but still runs the
        normal ``__post_init__`` invariants.
        """
        portfolio = cls(
            id=id,
            name=name,
            currency=currency,
            cash_balance=cash_balance,
        )
        for holding in holdings:
            portfolio._holdings[holding.ticker.symbol] = holding
        return portfolio

    # -- Queries -----------------------------------------------------------

    @property
    def holdings(self) -> tuple[Holding, ...]:
        """A read-only view of the holdings (aggregate encapsulation)."""
        return tuple(self._holdings.values())

    def holding_for(self, ticker: Ticker) -> Holding | None:
        return self._holdings.get(ticker.symbol)

    def total_invested(self) -> Money:
        total = Money.zero(self.currency)
        for holding in self._holdings.values():
            total = total + holding.cost_basis
        return total

    def total_value(self, prices: dict[str, Money]) -> Money:
        """Total market value, using the supplied price map."""
        total = self.cash_balance
        for holding in self._holdings.values():
            price = prices.get(holding.ticker.symbol)
            if price is None:
                # Fall back to cost basis when no market price is known.
                price = Money(
                    holding.cost_basis.amount / holding.quantity.value,
                    self.currency,
                )
            total = total + holding.market_value(price)
        return total

    # -- Commands ----------------------------------------------------------

    def deposit_cash(self, amount: Money) -> None:
        if amount.is_negative():
            raise InvariantViolation("Deposit amount must not be negative")
        if amount.currency != self.currency:
            raise InvariantViolation(
                f"Deposit currency {amount.currency} does not match "
                f"portfolio currency {self.currency}"
            )
        self.cash_balance = self.cash_balance + amount

    def withdraw_cash(self, amount: Money) -> None:
        if amount.is_negative():
            raise InvariantViolation("Withdrawal amount must not be negative")
        if amount.currency != self.currency:
            raise InvariantViolation(
                f"Withdrawal currency {amount.currency} does not match "
                f"portfolio currency {self.currency}"
            )
        if amount.amount > self.cash_balance.amount:
            raise InvariantViolation("Insufficient cash for withdrawal")
        self.cash_balance = self.cash_balance - amount

    def buy_shares(self, ticker: Ticker, quantity: Quantity, price: Money) -> None:
        """Buy shares, debiting cash and creating/updating the holding."""
        cost = price * quantity.value
        if cost.amount > self.cash_balance.amount:
            raise InvariantViolation(
                f"Insufficient cash to buy {quantity} of {ticker}: "
                f"need {cost}, have {self.cash_balance}"
            )
        holding = self._holdings.get(ticker.symbol)
        if holding is None:
            holding = Holding(ticker=ticker, cost_basis=Money.zero(self.currency))
            self._holdings[ticker.symbol] = holding
        holding.buy(quantity, price)
        self.cash_balance = self.cash_balance - cost
        self._absorb_events(holding)

    def sell_shares(self, ticker: Ticker, quantity: Quantity, price: Money) -> Money:
        """Sell shares, crediting cash and realising the proceeds."""
        holding = self._holdings.get(ticker.symbol)
        if holding is None:
            raise InvariantViolation(f"No holding for {ticker} to sell")
        proceeds = holding.sell(quantity, price)
        self.cash_balance = self.cash_balance + proceeds
        self._absorb_events(holding)
        if holding.quantity.value == 0:
            del self._holdings[ticker.symbol]
        return proceeds

    # -- Domain events -----------------------------------------------------

    def _absorb_events(self, holding: Holding) -> None:
        self._events.extend(holding.pull_events())

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events
