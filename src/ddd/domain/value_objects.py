"""Value objects shared across the domain.

Value objects are immutable and compared by value, not identity.
They encapsulate validation so that an invalid value object can never exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum


class Currency(str, Enum):
    """Supported currencies for the personal investment application."""

    GBP = "GBP"
    USD = "USD"
    EUR = "EUR"


class DomainError(Exception):
    """Base class for all domain rule violations."""


class InvariantViolation(DomainError):
    """Raised when an aggregate or value-object invariant is broken."""


@dataclass(frozen=True, slots=True)
class Money:
    """An immutable amount of money in a single currency.

    Money is a classic Value Object: it has no identity, is immutable and is
    equal to another Money when both amount and currency match.
    """

    amount: Decimal
    currency: Currency = Currency.GBP

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise InvariantViolation("Money.amount must be a Decimal")
        # Normalise to two decimal places (minor units) on construction.
        normalised = self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", normalised)
        if not isinstance(self.currency, Currency):
            object.__setattr__(self, "currency", Currency(self.currency))

    @classmethod
    def zero(cls, currency: Currency = Currency.GBP) -> "Money":
        return cls(Decimal("0"), currency)

    def _assert_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise InvariantViolation(
                f"Cannot combine {self.currency} with {other.currency}"
            )

    def __add__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int) -> "Money":
        return Money(self.amount * Decimal(factor), self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def is_negative(self) -> bool:
        return self.amount < 0

    def __str__(self) -> str:
        return f"{self.currency.value} {self.amount:,.2f}"


@dataclass(frozen=True, slots=True)
class Ticker:
    """A validated stock ticker symbol, e.g. ``AAPL``.

    Guarantees a normalised (upper-case, 1-10 letters) symbol so that the
    rest of the domain never has to worry about formatting.
    """

    symbol: str

    def __post_init__(self) -> None:
        normalised = self.symbol.strip().upper()
        if not normalised or not normalised.isalpha() or len(normalised) > 10:
            raise InvariantViolation(f"Invalid ticker symbol: {self.symbol!r}")
        object.__setattr__(self, "symbol", normalised)

    def __str__(self) -> str:
        return self.symbol


@dataclass(frozen=True, slots=True)
class Quantity:
    """A non-negative number of shares/units.

    Zero is permitted so that a holding can represent a flat (fully sold)
    position. Trade operations that require a positive amount validate
    separately.
    """

    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise InvariantViolation("Quantity.value must be a Decimal")
        if self.value < 0:
            raise InvariantViolation("Quantity must not be negative")

    def __str__(self) -> str:
        return str(self.value)
