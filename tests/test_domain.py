"""Pure domain tests: no database, no framework, just the model.

These tests exercise the aggregate and value objects directly. They run
instantaneously and prove that business rules live in the domain and are
not tangled up with persistence.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ddd.domain.entities import Holding
from ddd.domain.events import SharesBought, SharesSold
from ddd.domain.portfolio import Portfolio
from ddd.domain.value_objects import (
    Currency,
    InvariantViolation,
    Money,
    Quantity,
    Ticker,
)


class TestMoney:
    def test_money_quantises_to_two_places(self) -> None:
        assert Money(Decimal("10.005")).amount == Decimal("10.01")

    def test_money_addition_keeps_currency(self) -> None:
        total = Money(Decimal("10.00")) + Money(Decimal("5.50"))
        assert total == Money(Decimal("15.50"), Currency.GBP)

    def test_money_cannot_mix_currencies(self) -> None:
        with pytest.raises(InvariantViolation):
            Money(Decimal("1"), Currency.GBP) + Money(Decimal("1"), Currency.USD)

    def test_money_is_a_value_object(self) -> None:
        assert Money(Decimal("2.00")) == Money(Decimal("2.00"))
        assert hash(Money(Decimal("2.00"))) == hash(Money(Decimal("2.00")))


class TestTicker:
    def test_ticker_is_normalised(self) -> None:
        assert Ticker(" aapl ").symbol == "AAPL"

    @pytest.mark.parametrize("bad", ["", "  ", "AA1", "TOOLONGTICKER"])
    def test_invalid_tickers_rejected(self, bad: str) -> None:
        with pytest.raises(InvariantViolation):
            Ticker(bad)


class TestQuantity:
    def test_quantity_allows_zero_for_flat_holdings(self) -> None:
        assert Quantity(Decimal("0")).value == Decimal("0")

    def test_quantity_must_not_be_negative(self) -> None:
        with pytest.raises(InvariantViolation):
            Quantity(Decimal("-1"))


class TestHolding:
    def test_buy_accumulates_quantity_and_cost(self) -> None:
        holding = Holding(Ticker("AAPL"))
        holding.buy(Quantity(Decimal("10")), Money(Decimal("5.00")))
        holding.buy(Quantity(Decimal("10")), Money(Decimal("7.00")))
        assert holding.quantity.value == Decimal("20")
        assert holding.cost_basis == Money(Decimal("120.00"))

    def test_sell_reduces_basis_proportionally(self) -> None:
        holding = Holding(Ticker("AAPL"))
        holding.buy(Quantity(Decimal("10")), Money(Decimal("10.00")))
        proceeds = holding.sell(Quantity(Decimal("5")), Money(Decimal("12.00")))
        assert proceeds == Money(Decimal("60.00"))
        assert holding.quantity.value == Decimal("5")
        assert holding.cost_basis == Money(Decimal("50.00"))

    def test_cannot_sell_more_than_held(self) -> None:
        holding = Holding(Ticker("AAPL"))
        holding.buy(Quantity(Decimal("5")), Money(Decimal("10.00")))
        with pytest.raises(InvariantViolation):
            holding.sell(Quantity(Decimal("6")), Money(Decimal("10.00")))

    def test_unrealised_gain(self) -> None:
        holding = Holding(Ticker("AAPL"))
        holding.buy(Quantity(Decimal("10")), Money(Decimal("10.00")))
        assert holding.unrealised_gain(Money(Decimal("15.00"))) == Money(
            Decimal("50.00")
        )

    def test_events_recorded_on_trade(self) -> None:
        holding = Holding(Ticker("AAPL"))
        holding.buy(Quantity(Decimal("10")), Money(Decimal("10.00")))
        holding.sell(Quantity(Decimal("4")), Money(Decimal("12.00")))
        events = holding.pull_events()
        assert [type(e).__name__ for e in events] == ["SharesBought", "SharesSold"]
        assert isinstance(events[0], SharesBought)
        assert isinstance(events[1], SharesSold)
        # pulling clears the buffer
        assert holding.pull_events() == []


class TestPortfolioAggregate:
    def test_new_portfolio_starts_empty(self) -> None:
        portfolio = Portfolio(name="ISA", currency=Currency.GBP)
        assert portfolio.cash_balance == Money.zero(Currency.GBP)
        assert portfolio.holdings == ()

    def test_name_must_not_be_empty(self) -> None:
        with pytest.raises(InvariantViolation):
            Portfolio(name="   ")

    def test_deposit_increases_cash(self) -> None:
        portfolio = Portfolio(name="ISA")
        portfolio.deposit_cash(Money(Decimal("1000.00")))
        assert portfolio.cash_balance == Money(Decimal("1000.00"))

    def test_cannot_withdraw_more_than_balance(self) -> None:
        portfolio = Portfolio(name="ISA")
        portfolio.deposit_cash(Money(Decimal("100.00")))
        with pytest.raises(InvariantViolation):
            portfolio.withdraw_cash(Money(Decimal("100.01")))

    def test_buy_debits_cash_and_creates_holding(self) -> None:
        portfolio = Portfolio(name="ISA")
        portfolio.deposit_cash(Money(Decimal("1000.00")))
        portfolio.buy_shares(
            Ticker("AAPL"), Quantity(Decimal("10")), Money(Decimal("20.00"))
        )
        assert portfolio.cash_balance == Money(Decimal("800.00"))
        holding = portfolio.holding_for(Ticker("AAPL"))
        assert holding is not None
        assert holding.quantity.value == Decimal("10")

    def test_buy_without_cash_is_rejected(self) -> None:
        portfolio = Portfolio(name="ISA")
        with pytest.raises(InvariantViolation):
            portfolio.buy_shares(
                Ticker("AAPL"), Quantity(Decimal("1")), Money(Decimal("20.00"))
            )

    def test_sell_credits_cash_and_closes_holding_when_flat(self) -> None:
        portfolio = Portfolio(name="ISA")
        portfolio.deposit_cash(Money(Decimal("1000.00")))
        portfolio.buy_shares(
            Ticker("AAPL"), Quantity(Decimal("10")), Money(Decimal("20.00"))
        )
        proceeds = portfolio.sell_shares(
            Ticker("AAPL"), Quantity(Decimal("10")), Money(Decimal("25.00"))
        )
        assert proceeds == Money(Decimal("250.00"))
        assert portfolio.holding_for(Ticker("AAPL")) is None

    def test_total_value_includes_cash_and_holdings(self) -> None:
        portfolio = Portfolio(name="ISA")
        portfolio.deposit_cash(Money(Decimal("1000.00")))
        portfolio.buy_shares(
            Ticker("AAPL"), Quantity(Decimal("10")), Money(Decimal("20.00"))
        )
        total = portfolio.total_value({"AAPL": Money(Decimal("30.00"))})
        # 800 cash + 10 * 30 = 1100
        assert total == Money(Decimal("1100.00"))

    def test_holdings_view_is_immutable(self) -> None:
        portfolio = Portfolio(name="ISA")
        portfolio.deposit_cash(Money(Decimal("100.00")))
        portfolio.buy_shares(
            Ticker("AAPL"), Quantity(Decimal("1")), Money(Decimal("20.00"))
        )
        assert isinstance(portfolio.holdings, tuple)

    def test_aggregate_surfaces_child_events(self) -> None:
        portfolio = Portfolio(name="ISA")
        portfolio.deposit_cash(Money(Decimal("100.00")))
        portfolio.buy_shares(
            Ticker("AAPL"), Quantity(Decimal("1")), Money(Decimal("20.00"))
        )
        events = portfolio.pull_events()
        assert any(isinstance(e, SharesBought) for e in events)

    def test_reconstitute_rebuilds_state(self) -> None:
        holding = Holding(Ticker("AAPL"))
        holding.buy(Quantity(Decimal("10")), Money(Decimal("20.00")))
        holding.pull_events()
        portfolio = Portfolio.reconstitute(
            id=Portfolio(name="x").id,
            name="ISA",
            currency=Currency.GBP,
            cash_balance=Money(Decimal("800.00")),
            holdings=[holding],
        )
        assert portfolio.holding_for(Ticker("AAPL")) is not None
        assert portfolio.cash_balance == Money(Decimal("800.00"))
