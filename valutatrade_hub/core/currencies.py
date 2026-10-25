"""Модели валют и реестр поддерживаемых валют."""

import math
from abc import ABC, abstractmethod

from .exceptions import CurrencyNotFoundError


class Currency(ABC):
    """Абстрактный базовый класс валюты."""

    def __init__(self, name: str, code: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не должно быть пустым.")

        if not isinstance(code, str):
            raise TypeError("Код валюты должен быть строкой.")

        code = code.strip().upper()
        if not 2 <= len(code) <= 5 or not code.isalnum():
            raise ValueError(
                "Код валюты должен содержать от 2 до 5 символов без пробелов."
            )

        self.name = name.strip()
        self.code = code

    @abstractmethod
    def get_display_info(self) -> str:
        """Вернуть строковое представление валюты."""


class FiatCurrency(Currency):
    """Фиатная валюта, выпускаемая страной или валютной зоной."""

    def __init__(
        self,
        name: str,
        code: str,
        issuing_country: str,
    ) -> None:
        super().__init__(name, code)

        if not isinstance(issuing_country, str) or not issuing_country.strip():
            raise ValueError("Страна или зона эмиссии не должна быть пустой.")

        self.issuing_country = issuing_country.strip()

    def get_display_info(self) -> str:
        """Вернуть информацию о фиатной валюте."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта с алгоритмом и рыночной капитализацией."""

    def __init__(
        self,
        name: str,
        code: str,
        algorithm: str,
        market_cap: float,
    ) -> None:
        super().__init__(name, code)

        if not isinstance(algorithm, str) or not algorithm.strip():
            raise ValueError("Алгоритм не должен быть пустым.")

        if (
            isinstance(market_cap, bool)
            or not isinstance(market_cap, (int, float))
            or not math.isfinite(market_cap)
            or market_cap < 0
        ):
            raise ValueError(
                "Капитализация должна быть конечным неотрицательным числом."
            )

        self.algorithm = algorithm.strip()
        self.market_cap = float(market_cap)

    def get_display_info(self) -> str:
        """Вернуть информацию о криптовалюте."""
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {self.market_cap:.2e})"
        )


_CURRENCY_REGISTRY: dict[str, Currency] = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "GBP": FiatCurrency("British Pound", "GBP", "United Kingdom"),
    "JPY": FiatCurrency("Japanese Yen", "JPY", "Japan"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Proof of Stake", 4.5e11),
}


def get_currency(code: str) -> Currency:
    """Вернуть валюту по коду или вызвать CurrencyNotFoundError."""
    if not isinstance(code, str):
        raise TypeError("Код валюты должен быть строкой.")

    normalized_code = code.strip().upper()
    if not normalized_code:
        raise ValueError("Код валюты не должен быть пустым.")

    try:
        return _CURRENCY_REGISTRY[normalized_code]
    except KeyError as err:
        raise CurrencyNotFoundError(
            f"Валюта с кодом '{normalized_code}' не найдена."
        ) from err
