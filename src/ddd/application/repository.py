"""Repository ports (interfaces) owned by the application layer.

This is the Dependency Inversion Principle in action: the application
defines the interface it needs, and infrastructure implements it. The
domain and application layers never import a concrete database library.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from ddd.domain.portfolio import Portfolio


class PortfolioNotFoundError(LookupError):
    """Raised when a portfolio cannot be found by id."""


@runtime_checkable
class PortfolioRepository(Protocol):
    """Persistence port for the ``Portfolio`` aggregate.

    Implementations must persist a portfolio and *all* of its holdings
    atomically, and must reconstitute the aggregate exactly as it was.
    """

    def add(self, portfolio: Portfolio) -> None:
        """Persist a brand-new portfolio (and its holdings)."""
        ...

    def update(self, portfolio: Portfolio) -> None:
        """Persist changes to an existing portfolio."""
        ...

    def get(self, portfolio_id: UUID) -> Portfolio:
        """Reconstitute a portfolio or raise ``PortfolioNotFoundError``."""
        ...

    def list_ids(self) -> list[UUID]:
        """Return the ids of all stored portfolios."""
        ...
