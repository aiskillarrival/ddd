"""Application services (use cases) for the personal investment app.

Each method is a single, transactional use case. The service depends on
the ``PortfolioRepository`` port only, so it can be exercised in tests
with either a real SQLite repository or an in-memory fake.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from ddd.application.repository import (
    PortfolioNotFoundError,
    PortfolioRepository,
)
from ddd.domain.events import DomainEvent
from ddd.domain.portfolio import Portfolio
from ddd.domain.value_objects import (
    Currency,
    Money,
    Quantity,
    Ticker,
)


class PortfolioService:
    """Use-case orchestrator for portfolios."""

    def __init__(self, repository: PortfolioRepository) -> None:
        self._repository = repository
        self._dispatched_events: list[DomainEvent] = []

    # -- Use cases ---------------------------------------------------------

    def open_portfolio(self, name: str, currency: Currency = Currency.GBP) -> UUID:
        """Create a new, empty portfolio and persist it."""
        portfolio = Portfolio(name=name, currency=currency)
        self._repository.add(portfolio)
        self._dispatch(portfolio)
        return portfolio.id

    def deposit_cash(self, portfolio_id: UUID, amount: Decimal) -> Money:
        portfolio = self._load(portfolio_id)
        portfolio.deposit_cash(Money(amount, portfolio.currency))
        self._repository.update(portfolio)
        self._dispatch(portfolio)
        return portfolio.cash_balance

    def buy_shares(
        self,
        portfolio_id: UUID,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        portfolio = self._load(portfolio_id)
        portfolio.buy_shares(
            Ticker(symbol),
            Quantity(quantity),
            Money(price, portfolio.currency),
        )
        self._repository.update(portfolio)
        self._dispatch(portfolio)

    def sell_shares(
        self,
        portfolio_id: UUID,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
    ) -> Money:
        portfolio = self._load(portfolio_id)
        proceeds = portfolio.sell_shares(
            Ticker(symbol),
            Quantity(quantity),
            Money(price, portfolio.currency),
        )
        self._repository.update(portfolio)
        self._dispatch(portfolio)
        return proceeds

    def total_value(self, portfolio_id: UUID, prices: dict[str, Money]) -> Money:
        portfolio = self._load(portfolio_id)
        return portfolio.total_value(prices)

    # -- Helpers -----------------------------------------------------------

    def _load(self, portfolio_id: UUID) -> Portfolio:
        try:
            return self._repository.get(portfolio_id)
        except PortfolioNotFoundError:
            raise

    def _dispatch(self, portfolio: Portfolio) -> None:
        """Collect domain events for later publishing.

        A real application would hand these to an event bus; here we simply
        keep them so tests can assert on what the domain produced.
        """
        self._dispatched_events.extend(portfolio.pull_events())

    @property
    def dispatched_events(self) -> tuple[DomainEvent, ...]:
        return tuple(self._dispatched_events)
