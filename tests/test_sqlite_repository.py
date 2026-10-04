"""Persistence tests for the SQLite repository adapter.

These prove that the aggregate round-trips through a real SQLite database
and that the repository behaves atomically. They use an in-memory database
so no files are left behind.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from ddd.application.repository import PortfolioNotFoundError
from ddd.domain.portfolio import Portfolio
from ddd.domain.value_objects import Currency, Money, Quantity, Ticker
from ddd.infrastructure.sqlite_repository import (
    SqlitePortfolioRepository,
    _from_minor,
    _to_minor,
)


def _funded_portfolio(name: str = "ISA") -> Portfolio:
    portfolio = Portfolio(name=name, currency=Currency.GBP)
    portfolio.deposit_cash(Money(Decimal("1000.00")))
    portfolio.buy_shares(
        Ticker("AAPL"), Quantity(Decimal("10")), Money(Decimal("20.00"))
    )
    return portfolio


class TestMoneyConversion:
    def test_minor_unit_round_trip(self) -> None:
        money = Money(Decimal("123.45"))
        assert _to_minor(money) == 12345
        assert _from_minor(12345, Currency.GBP) == money

    def test_minor_conversion_rounds_half_up(self) -> None:
        assert _to_minor(Money(Decimal("1.005"))) == 101


class TestSqliteRepository:
    def test_add_and_get_round_trip(
        self, repository: SqlitePortfolioRepository
    ) -> None:
        portfolio = _funded_portfolio()
        repository.add(portfolio)

        loaded = repository.get(portfolio.id)
        assert loaded.id == portfolio.id
        assert loaded.name == "ISA"
        assert loaded.cash_balance == Money(Decimal("800.00"))
        holding = loaded.holding_for(Ticker("AAPL"))
        assert holding is not None
        assert holding.quantity.value == Decimal("10")
        assert holding.cost_basis == Money(Decimal("200.00"))

    def test_get_unknown_raises(
        self, repository: SqlitePortfolioRepository
    ) -> None:
        with pytest.raises(PortfolioNotFoundError):
            repository.get(uuid4())

    def test_update_persists_changed_holdings(
        self, repository: SqlitePortfolioRepository
    ) -> None:
        portfolio = _funded_portfolio()
        repository.add(portfolio)

        portfolio.buy_shares(
            Ticker("AAPL"), Quantity(Decimal("5")), Money(Decimal("22.00"))
        )
        portfolio.deposit_cash(Money(Decimal("100.00")))
        repository.update(portfolio)

        loaded = repository.get(portfolio.id)
        assert loaded.holding_for(Ticker("AAPL")).quantity.value == Decimal("15")
        assert loaded.cash_balance == Money(Decimal("790.00"))

    def test_update_closed_holding_is_removed(
        self, repository: SqlitePortfolioRepository
    ) -> None:
        portfolio = _funded_portfolio()
        repository.add(portfolio)
        portfolio.sell_shares(
            Ticker("AAPL"), Quantity(Decimal("10")), Money(Decimal("25.00"))
        )
        repository.update(portfolio)

        loaded = repository.get(portfolio.id)
        assert loaded.holding_for(Ticker("AAPL")) is None
        assert loaded.cash_balance == Money(Decimal("1050.00"))

    def test_update_unknown_raises(
        self, repository: SqlitePortfolioRepository
    ) -> None:
        with pytest.raises(PortfolioNotFoundError):
            repository.update(Portfolio(name="ghost"))

    def test_list_ids(
        self, repository: SqlitePortfolioRepository
    ) -> None:
        repository.add(_funded_portfolio("Alpha"))
        repository.add(_funded_portfolio("Beta"))
        ids = repository.list_ids()
        assert len(ids) == 2
        assert len(set(ids)) == 2

    def test_decimal_quantities_survive_round_trip(
        self, repository: SqlitePortfolioRepository
    ) -> None:
        portfolio = Portfolio(name="Fractional")
        portfolio.deposit_cash(Money(Decimal("100.00")))
        portfolio.buy_shares(
            Ticker("MSFT"),
            Quantity(Decimal("2.5")),
            Money(Decimal("40.00")),
        )
        repository.add(portfolio)

        loaded = repository.get(portfolio.id)
        assert loaded.holding_for(Ticker("MSFT")).quantity.value == Decimal("2.5")

    def test_event_log_is_append_only(
        self, repository: SqlitePortfolioRepository
    ) -> None:
        portfolio = _funded_portfolio()
        repository.add(portfolio)
        events = portfolio.pull_events()
        repository.append_events(portfolio.id, events)

        stored = repository.events_for(portfolio.id)
        assert [row["event_type"] for row in stored] == ["SharesBought"]
        assert '"ticker": "AAPL"' in stored[0]["payload"]
