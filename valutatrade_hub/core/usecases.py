"""Сценарии использования приложения ValutaTrade Hub."""

import json
import math
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.settings import SettingsLoader

settings = SettingsLoader()
users_file = Path(settings.get("users_file"))
portfolios_file = Path(settings.get("portfolios_file"))
rates_file = Path(settings.get("rates_file"))
ttl = settings.get("rates_ttl_seconds", 300)
base_currency = settings.get("base_currency", "USD")


def _read_json(path: Path, default: Any) -> Any:
    """Прочитать JSON-файл; вернуть default, если файл ещё не создан."""
    if not path.exists():
        return default

    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        if path == rates_file:
            raise ApiRequestError(f"не удалось прочитать файл курсов: {error}") from error
        raise ValueError(f"Не удалось прочитать файл {path.name}: {error}") from error


def _write_json(path: Path, data: Any) -> None:
    """Безопасно сохранить данные в JSON-файл."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary_path.replace(path)


def _load_users() -> list[dict[str, Any]]:
    """Загрузить записи пользователей."""
    data = _read_json(users_file, [])
    if not isinstance(data, list):
        raise ValueError("Файл пользователей должен содержать JSON-массив.")
    return data


def _load_portfolios() -> list[dict[str, Any]]:
    """Загрузить записи портфелей."""
    data = _read_json(portfolios_file, [])
    if not isinstance(data, list):
        raise ValueError("Файл портфелей должен содержать JSON-массив.")
    return data


def _user_from_record(record: dict[str, Any]) -> User:
    """Создать объект User из JSON-записи."""
    return User(
        user_id=int(record["user_id"]),
        username=record["username"],
        hashed_password=record["hashed_password"],
        salt=record["salt"],
        registration_date=datetime.fromisoformat(record["registration_date"]),
    )


def _find_user_by_id(user_id: int) -> User:
    """Найти пользователя по идентификатору."""
    for record in _load_users():
        if int(record["user_id"]) == user_id:
            return _user_from_record(record)
    raise ValueError(f"Пользователь с ID {user_id} не найден.")


def _load_portfolio(user: User) -> Portfolio:
    """Восстановить портфель пользователя из JSON."""
    for record in _load_portfolios():
        if int(record["user_id"]) == user.user_id:
            wallets = {
                code: Wallet(code, details["balance"])
                for code, details in record.get("wallets", {}).items()
            }
            return Portfolio(user, wallets)
    return Portfolio(user)
