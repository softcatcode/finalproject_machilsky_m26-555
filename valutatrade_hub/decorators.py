"""Декораторы для логирования доменных операций."""

from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from inspect import signature
from typing import Any, TypeVar, cast

from valutatrade_hub.logging_config import setup_logging

F = TypeVar("F", bound=Callable[..., Any])

_ACTIONS = {
    "buy_currency": "BUY",
    "buy": "BUY",
    "sell_currency": "SELL",
    "sell": "SELL",
    "register_user": "REGISTER",
    "register": "REGISTER",
    "login_user": "LOGIN",
    "login": "LOGIN",
}


def _get_field(
    arguments: dict[str, Any],
    *names: str,
) -> Any:
    """Получить первое доступное значение из списка имён аргументов."""
    for name in names:
        if name in arguments:
            return arguments[name]
    return None


def _format_value(value: Any) -> str:
    """Подготовить значение для безопасного человекочитаемого лога."""
    if value is None:
        return "-"
    return repr(value)


def log_action[F: Callable[..., Any]](
    func: F | None = None,
    *,
    verbose: bool = False,
) -> F | Callable[[F], F]:
    """Логировать результат доменной операции, не скрывая исключения."""

    def decorator(function: F) -> F:
        logger = setup_logging()

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature(function).bind_partial(*args, **kwargs)
            arguments = bound.arguments

            action = _ACTIONS.get(
                function.__name__,
                function.__name__.upper(),
            )
            username = _get_field(arguments, "username")
            user_id = _get_field(arguments, "user_id")

            if username is None:
                username = _get_field(arguments, "user")
                if username is not None:
                    username = getattr(username, "username", username)

            user = (
                f"username={_format_value(username)}"
                if username is not None
                else f"user_id={_format_value(user_id)}"
            )

            currency = _get_field(
                arguments, "currency_code", "currency"
            )
            if currency is not None:
                currency = getattr(currency, "code", currency)

            amount = _get_field(arguments, "amount")
            rate = _get_field(arguments, "rate")
            base = _get_field(arguments, "base", "base_currency")

            fields = [
                datetime.now(UTC).isoformat(timespec="seconds"),
                action,
                user,
                f"currency={_format_value(currency)}",
                f"amount={_format_value(amount)}",
            ]

            if rate is not None:
                fields.append(f"rate={_format_value(rate)}")
            if base is not None:
                fields.append(f"base={_format_value(base)}")

            try:
                result = function(*args, **kwargs)
            except Exception as error:
                fields.extend(
                    [
                        "result=ERROR",
                        f"error_type={type(error).__name__}",
                        f"error_message={_format_value(str(error))}",
                    ]
                )
                logger.info(" ".join(fields))
                raise

            fields.append("result=OK")

            if verbose:
                fields.append("verbose=True")
                # Подробности добавляем только для безопасных полей,
                # которые явно переданы вызываемой функции.
                for key in ("balance_before", "balance_after"):
                    value = arguments.get(key)
                    if value is not None:
                        fields.append(f"{key}={_format_value(value)}")

            logger.info(" ".join(fields))
            return result

        return cast(F, wrapper)

    if func is None:
        return decorator
    return decorator(func)
