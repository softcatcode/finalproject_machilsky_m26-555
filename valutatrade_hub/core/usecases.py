"""Сценарии использования приложения ValutaTrade Hub."""

import json
import math
import secrets
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import ApiRequestError, CurrencyNotFoundError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import (
    ApiRequestError as ParserApiRequestError,
)
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage, StorageError
from valutatrade_hub.parser_service.updater import RatesUpdater

settings = SettingsLoader()
users_file = Path(settings.get("users_file"))
portfolios_file = Path(settings.get("portfolios_file"))
rates_file = Path(settings.get("rates_file"))
ttl = int(settings.get("rates_ttl_seconds", 300))
base_currency = str(settings.get("base_currency", "USD")).upper()
STARTING_BALANCE = 10_000.0


def _read_json(path: Path, default: Any) -> Any:
    """Прочитать JSON-файл; вернуть default, если файл ещё не создан."""
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        if path == rates_file:
            raise ApiRequestError(
                f"Не удалось прочитать файл курсов: {error}"
            ) from error
        raise ValueError(f"Не удалось прочитать файл {path.name}: {error}") from error


def _write_json(path: Path, data: Any) -> None:
    """Безопасно сохранить данные в JSON-файл."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write("\n")
        temporary_path.replace(path)
    except (OSError, TypeError, ValueError) as error:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ValueError(f"Не удалось сохранить файл {path.name}: {error}") from error


def _load_users() -> list[dict[str, Any]]:
    """Загрузить записи пользователей."""
    data = _read_json(users_file, [])
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("Файл пользователей должен содержать массив объектов.")
    return data


def _load_portfolios() -> list[dict[str, Any]]:
    """Загрузить записи портфелей."""
    data = _read_json(portfolios_file, [])
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError("Файл портфелей должен содержать массив объектов.")
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
                str(code).upper(): Wallet(str(code), details["balance"])
                for code, details in record.get("wallets", {}).items()
            }
            return Portfolio(user, wallets)
    return Portfolio(user)


def _save_portfolio(portfolio: Portfolio) -> None:
    """Сохранить портфель, не затрагивая портфели других пользователей."""
    records = _load_portfolios()
    serialized = {
        "user_id": portfolio.user_id,
        "wallets": {
            code: {"balance": wallet.balance}
            for code, wallet in portfolio.wallets.items()
        },
    }
    for index, record in enumerate(records):
        if int(record.get("user_id", -1)) == portfolio.user_id:
            records[index] = serialized
            break
    else:
        records.append(serialized)
    _write_json(portfolios_file, records)


def _validate_currency(code: str) -> str:
    """Проверить код валюты; учитывать криптовалюты, поддержанные парсером."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Код валюты не должен быть пустым.")
    normalized = code.strip().upper()
    try:
        get_currency(normalized)
    except CurrencyNotFoundError:
        if normalized not in {item.upper() for item in ParserConfig.CRYPTO_CURRENCIES}:
            raise
    return normalized


def _refresh_rates() -> dict[str, Any]:
    """Получить свежие курсы CoinGecko и сохранить их в локальный кэш."""
    config = ParserConfig()
    storage = RatesStorage(
        rates_file_path=rates_file,
        history_file_path=rates_file.parent / "exchange_rates.json",
    )
    try:
        return RatesUpdater([CoinGeckoClient(config)], storage).run_update()
    except ParserApiRequestError as error:
        raise ApiRequestError(str(error)) from error
    except StorageError as error:
        raise ApiRequestError(f"Не удалось сохранить курсы: {error}") from error
    except RuntimeError as error:
        raise ApiRequestError(str(error)) from error


def _rates_snapshot(force_if_stale: bool = True) -> dict[str, Any]:
    """Загрузить кэш и обновить его, если он пустой или устарел."""
    storage = RatesStorage(
        rates_file_path=rates_file,
        history_file_path=rates_file.parent / "exchange_rates.json",
    )
    snapshot = storage.load_rates()
    last_refresh = snapshot.get("last_refresh")
    stale = not last_refresh
    if last_refresh:
        try:
            refreshed_at = datetime.fromisoformat(
                str(last_refresh).replace("Z", "+00:00")
            )
            if refreshed_at.tzinfo is None:
                refreshed_at = refreshed_at.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - refreshed_at.astimezone(UTC)).total_seconds()
            stale = age < 0 or age > ttl
        except ValueError:
            stale = True
    if force_if_stale and (not snapshot.get("pairs") or stale):
        return _refresh_rates()
    if not snapshot.get("pairs"):
        raise ApiRequestError("Локальный кэш курсов пуст. Выполните update-rates.")
    return snapshot


def _build_rate_graph(pairs: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Построить граф обмена из пар FROM_TO и обратных курсов."""
    graph: dict[str, dict[str, float]] = {}
    for pair, record in pairs.items():
        if not isinstance(pair, str) or "_" not in pair or not isinstance(record, dict):
            continue
        try:
            rate = float(record["rate"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(rate) or rate <= 0:
            continue
        source, target = pair.upper().split("_", maxsplit=1)
        graph.setdefault(source, {})[target] = rate
        graph.setdefault(target, {})[source] = 1.0 / rate
    return graph


def _find_rate(graph: dict[str, dict[str, float]], source: str, target: str) -> float:
    """Найти курс через BFS; курс означает количество target за одну source."""
    if source == target:
        return 1.0
    pending = deque([(source, 1.0)])
    visited = {source}
    while pending:
        current, accumulated = pending.popleft()
        for neighbour, edge_rate in graph.get(current, {}).items():
            if neighbour in visited:
                continue
            result = accumulated * edge_rate
            if neighbour == target:
                return result
            visited.add(neighbour)
            pending.append((neighbour, result))
    raise CurrencyNotFoundError(
        f"Нет курса {source} к {target} в локальном кэше."
    )


@log_action
def register_user(username: str, password: str) -> str:
    """Зарегистрировать пользователя и создать его портфель."""
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Имя пользователя не должно быть пустым.")
    if not isinstance(password, str) or len(password) < 4:
        raise ValueError("Пароль должен содержать минимум 4 символа.")
    username = username.strip()
    users = _load_users()
    if any(
        str(record.get("username", "")).casefold() == username.casefold()
        for record in users
    ):
        raise ValueError(f"Пользователь '{username}' уже существует.")
    salt = secrets.token_hex(16)
    user_id = max((int(record.get("user_id", 0)) for record in users), default=0) + 1
    now = datetime.now(UTC)
    user = User(
        user_id=user_id,
        username=username,
        hashed_password=User._hash_password(password, salt),
        salt=salt,
        registration_date=now,
    )
    users.append({
        "user_id": user.user_id,
        "username": user.username,
        "hashed_password": user.hashed_password,
        "salt": user.salt,
        "registration_date": user.registration_date.isoformat(),
    })
    _write_json(users_file, users)
    portfolio = Portfolio(
        user, {base_currency: Wallet(base_currency, STARTING_BALANCE)}
    )
    _save_portfolio(portfolio)
    return (
        f"Пользователь '{username}' зарегистрирован. "
        f"Начальный баланс: {STARTING_BALANCE:g} {base_currency}."
    )


@log_action
def login_user(username: str, password: str) -> User:
    """Проверить учётные данные и вернуть пользователя."""
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError("Имя пользователя и пароль должны быть строками.")
    for record in _load_users():
        if str(record.get("username", "")).casefold() == username.strip().casefold():
            user = _user_from_record(record)
            if user.verify_password(password):
                return user
            break
    raise ValueError("Неверное имя пользователя или пароль.")


def show_portfolio(user_id: int, base: str = "USD") -> str:
    """Показать кошельки и общую стоимость портфеля в выбранной валюте."""
    user = _find_user_by_id(user_id)
    base = _validate_currency(base)
    portfolio = _load_portfolio(user)
    if not portfolio.wallets:
        return f"Портфель пользователя '{user.username}' пуст."
    snapshot = _rates_snapshot()
    graph = _build_rate_graph(snapshot.get("pairs", {}))
    lines = [f"Портфель пользователя '{user.username}':"]
    total = 0.0
    for code, wallet in sorted(portfolio.wallets.items()):
        rate = _find_rate(graph, code, base)
        value = wallet.balance * rate
        total += value
        lines.append(f"- {code}: {wallet.balance:.8g} (≈ {value:.8g} {base})")
    lines.append(f"Итого: {total:.8g} {base}")
    return "\n".join(lines)


@log_action
def buy_currency(user_id: int, currency: str, amount: float) -> str:
    """Купить amount единиц валюты, списав эквивалент в базовой валюте."""
    currency = _validate_currency(currency)
    if currency == base_currency:
        raise ValueError("Нельзя покупать базовую валюту за саму себя.")
    amount = Wallet._validate_amount(amount)
    user = _find_user_by_id(user_id)
    portfolio = _load_portfolio(user)
    snapshot = _rates_snapshot()
    rate = _find_rate(
        _build_rate_graph(snapshot.get("pairs", {})), currency, base_currency
    )
    cost = amount * rate
    base_wallet = portfolio.wallets.get(base_currency)
    if base_wallet is None:
        base_wallet = portfolio.add_currency(base_currency)
    base_wallet.withdraw(cost)
    wallet = portfolio.wallets.get(currency)
    if wallet is None:
        wallet = portfolio.add_currency(currency)
    wallet.deposit(amount)
    _save_portfolio(portfolio)
    return (
        f"Куплено {amount:.8g} {currency} по курсу {rate:.8g} {base_currency};"
        f" списано {cost:.8g} {base_currency}."
    )


@log_action
def sell_currency(user_id: int, currency: str, amount: float) -> str:
    """Продать amount единиц валюты и зачислить эквивалент в базовой валюте."""
    currency = _validate_currency(currency)
    if currency == base_currency:
        raise ValueError("Нельзя продавать базовую валюту за саму себя.")
    amount = Wallet._validate_amount(amount)
    user = _find_user_by_id(user_id)
    portfolio = _load_portfolio(user)
    wallet = portfolio.get_wallet(currency)
    snapshot = _rates_snapshot()
    rate = _find_rate(
        _build_rate_graph(snapshot.get("pairs", {})), currency, base_currency
    )
    proceeds = amount * rate
    wallet.withdraw(amount)
    base_wallet = portfolio.wallets.get(base_currency)
    if base_wallet is None:
        base_wallet = portfolio.add_currency(base_currency)
    base_wallet.deposit(proceeds)
    _save_portfolio(portfolio)
    return (
        f"Продано {amount:.8g} {currency} по курсу {rate:.8g}"
        f" {base_currency}; зачислено {proceeds:.8g} {base_currency}."
    )


def get_rate(from_currency: str, to_currency: str) -> str:
    """Получить курс одной валюты относительно другой."""
    source = _validate_currency(from_currency)
    target = _validate_currency(to_currency)
    if source == target:
        return f"1 {source} = 1 {target}"
    snapshot = _rates_snapshot()
    rate = _find_rate(_build_rate_graph(snapshot.get("pairs", {})), source, target)
    return f"1 {source} = {rate:.8g} {target}"
