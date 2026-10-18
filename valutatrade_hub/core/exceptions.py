"""Пользовательские исключения, выкидываемые программой"""

class InsufficientFundsError(ValueError):
    """Исключение при недостаточном балансе кошелька."""

    def __init__(
        self,
        available: float,
        required: float,
        code: str,
    ) -> None:
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {available:g} {code}, "
            f"требуется {required:g} {code}"
        )


class CurrencyNotFoundError(LookupError):
    """Исключение для неизвестного кода валюты."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class ApiRequestError(RuntimeError):
    """Исключение при ошибке обращения к внешнему API."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")
