"""End-to-end tests for the application service over a real SQLite store.

These are the "show how it works" tests: a portfolio is opened, funded,
traded and valued, with every step persisted to SQLite through the
repository port and reloaded fresh from the database to prove persistence.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ddd.application.repository import PortfolioNotFoundError
from ddd.application.service import PortfolioService
from ddd.domain.events import SharesBought, SharesSold
from ddd.domain.value_objects import (
    Currency,
    InvariantViolation,
    Money,
    Ticker,
)
from ddd.infrastructure.sqlite_repository import SqlitePortfolioRepository


def test_full_investment_workflow(
    service: PortfolioService, repository: SqlitePortfolioRepository
) -> None:
    # Open and fund a portfolio.
    portfolio_id = service.open_portfolio("Stocks & Shares ISA", Currency.GBP)
    service.deposit_cash(portfolio_id, Decimal("5000.00"))

    # Buy two positions.
    service.buy_shares(portfolio_id, "AAPL", Decimal("10"), Decimal("150.00"))
    service.buy_shares(portfolio_id, "MSFT", Decimal("5"), Decimal("300.00"))

    # Reload from SQLite to confirm it persisted.
    portfolio = repository.get(portfolio_id)
    # 5000 - 10*150 - 5*300 = 5000 - 1500 - 1500 = 2000
    assert portfolio.cash_balance == Money(Decimal("2000.00"))
    assert len(portfolio.holdings) == 2
    aapl = portfolio.holding_for(Ticker("AAPL"))
    assert aapl is not None and aapl.quantity.value == Decimal("10")

    # Value the portfolio at current market prices.
    total = service.total_value(
        portfolio_id,
        {
            "AAPL": Money(Decimal("160.00")),
            "MSFT": Money(Decimal("320.00")),
        },
    )
    # 2000 cash + 10*160 + 5*320 = 2000 + 1600 + 1600 = 5200
    assert total == Money(Decimal("5200.00"))


def test_sell_realises_cash_and_persists(
    service: PortfolioService, repository: SqlitePortfolioRepository
) -> None:
    portfolio_id = service.open_portfolio("Trading")
    service.deposit_cash(portfolio_id, Decimal("2000.00"))
    service.buy_shares(portfolio_id, "TSLA", Decimal("4"), Decimal("250.00"))

    proceeds = service.sell_shares(portfolio_id, "TSLA", Decimal("4"), Decimal("300.00"))
    assert proceeds == Money(Decimal("1200.00"))

    reloaded = repository.get(portfolio_id)
    assert reloaded.holding_for(Ticker("TSLA")) is None
    assert reloaded.cash_balance == Money(Decimal("2200.00"))


def test_insufficient_funds_propagates_as_domain_error(
    service: PortfolioService,
) -> None:
    portfolio_id = service.open_portfolio("Broke")
    service.deposit_cash(portfolio_id, Decimal("100.00"))
    with pytest.raises(InvariantViolation):
        service.buy_shares(portfolio_id, "AAPL", Decimal("100"), Decimal("50.00"))


def test_missing_portfolio_raises(
    service: PortfolioService,
) -> None:
    from uuid import uuid4

    with pytest.raises(PortfolioNotFoundError):
        service.deposit_cash(uuid4(), Decimal("10.00"))


def test_domain_events_are_surfaced_by_service(
    service: PortfolioService,
) -> None:
    portfolio_id = service.open_portfolio("Events")
    service.deposit_cash(portfolio_id, Decimal("1000.00"))
    service.buy_shares(portfolio_id, "AAPL", Decimal("2"), Decimal("100.00"))
    service.sell_shares(portfolio_id, "AAPL", Decimal("1"), Decimal("120.00"))

    kinds = [type(e).__name__ for e in service.dispatched_events]
    assert "SharesBought" in kinds
    assert "SharesSold" in kinds
    assert any(isinstance(e, SharesBought) for e in service.dispatched_events)
    assert any(isinstance(e, SharesSold) for e in service.dispatched_events)
