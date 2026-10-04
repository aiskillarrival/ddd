"""SQLite implementation of the ``PortfolioRepository`` port.

This adapter translates between the in-memory domain objects and rows in
SQLite. The repository is the *only* place in the codebase that knows
about SQL and table structure.

Design notes:

* Money is persisted as integer minor units; ``_to_minor``/``_from_minor``
  are the single conversion boundary.
* ``add``/``update`` persist the aggregate root and all its holdings
  inside one transaction, so the aggregate is always consistent on disk.
* ``get`` reconstitutes a fully-formed ``Portfolio`` aggregate.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from ddd.application.repository import PortfolioNotFoundError
from ddd.domain.entities import Holding
from ddd.domain.portfolio import Portfolio
from ddd.domain.value_objects import Currency, Money, Quantity, Ticker
from ddd.infrastructure.schema import initialise_schema

_MINOR = Decimal("100")


def _to_minor(money: Money) -> int:
    """Convert a Money value to an integer number of minor units."""
    return int(
        (money.amount * _MINOR).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def _from_minor(minor: int, currency: Currency) -> Money:
    return Money(Decimal(minor) / _MINOR, currency)


class SqlitePortfolioRepository:
    """A repository backed by a SQLite database.

    The connection is injected, which keeps the adapter testable with an
    in-memory database (``sqlite3.connect(":memory:")``) as well as a real
    file on disk.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        connection.row_factory = sqlite3.Row
        self._connection = connection
        self._connection.execute("PRAGMA foreign_keys = ON")
        initialise_schema(self._connection)

    # -- Repository port ---------------------------------------------------

    def add(self, portfolio: Portfolio) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO portfolios (id, name, currency, cash_minor) "
                "VALUES (?, ?, ?, ?)",
                (
                    str(portfolio.id),
                    portfolio.name,
                    portfolio.currency.value,
                    _to_minor(portfolio.cash_balance),
                ),
            )
            self._write_holdings(portfolio)

    def update(self, portfolio: Portfolio) -> None:
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE portfolios SET name = ?, currency = ?, cash_minor = ? "
                "WHERE id = ?",
                (
                    portfolio.name,
                    portfolio.currency.value,
                    _to_minor(portfolio.cash_balance),
                    str(portfolio.id),
                ),
            )
            if cursor.rowcount == 0:
                raise PortfolioNotFoundError(portfolio.id)
            # Simplest correct strategy for the aggregate: replace children.
            self._connection.execute(
                "DELETE FROM holdings WHERE portfolio_id = ?",
                (str(portfolio.id),),
            )
            self._write_holdings(portfolio)

    def get(self, portfolio_id: UUID) -> Portfolio:
        row = self._connection.execute(
            "SELECT id, name, currency, cash_minor FROM portfolios WHERE id = ?",
            (str(portfolio_id),),
        ).fetchone()
        if row is None:
            raise PortfolioNotFoundError(portfolio_id)

        currency = Currency(row["currency"])
        holdings = [
            Holding(
                ticker=Ticker(holding_row["ticker"]),
                quantity=Quantity(Decimal(holding_row["quantity"])),
                cost_basis=_from_minor(holding_row["cost_minor"], currency),
            )
            for holding_row in self._connection.execute(
                "SELECT ticker, quantity, cost_minor FROM holdings "
                "WHERE portfolio_id = ? ORDER BY ticker",
                (str(portfolio_id),),
            )
        ]
        return Portfolio.reconstitute(
            id=UUID(row["id"]),
            name=row["name"],
            currency=currency,
            cash_balance=_from_minor(row["cash_minor"], currency),
            holdings=holdings,
        )

    def list_ids(self) -> list[UUID]:
        rows = self._connection.execute(
            "SELECT id FROM portfolios ORDER BY name"
        ).fetchall()
        return [UUID(row["id"]) for row in rows]

    # -- Internals ---------------------------------------------------------

    def _write_holdings(self, portfolio: Portfolio) -> None:
        for holding in portfolio.holdings:
            self._connection.execute(
                "INSERT INTO holdings (portfolio_id, ticker, quantity, cost_minor) "
                "VALUES (?, ?, ?, ?)",
                (
                    str(portfolio.id),
                    holding.ticker.symbol,
                    str(holding.quantity.value),
                    _to_minor(holding.cost_basis),
                ),
            )

    # -- Event log ---------------------------------------------------------

    def append_events(self, portfolio_id: UUID, events) -> None:
        """Persist domain events to the append-only event log."""
        import json

        with self._connection:
            for event in events:
                self._connection.execute(
                    "INSERT INTO domain_events "
                    "(portfolio_id, event_type, payload, occurred_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        str(portfolio_id),
                        type(event).__name__,
                        json.dumps(_event_payload(event)),
                        event.occurred_at.isoformat(),
                    ),
                )

    def events_for(self, portfolio_id: UUID) -> list[sqlite3.Row]:
        return list(
            self._connection.execute(
                "SELECT event_type, payload, occurred_at FROM domain_events "
                "WHERE portfolio_id = ? ORDER BY id",
                (str(portfolio_id),),
            )
        )


def _event_payload(event) -> dict[str, str]:
    """Serialise a domain event to a JSON-friendly dict."""
    from ddd.domain.events import SharesBought, SharesSold

    if isinstance(event, (SharesBought, SharesSold)):
        return {
            "ticker": event.ticker.symbol,
            "quantity": str(event.quantity.value),
            "price": str(event.price.amount),
            "currency": event.price.currency.value,
        }
    return {}
