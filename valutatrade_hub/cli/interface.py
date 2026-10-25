"""Командный интерфейс ValutaTrade Hub."""

import argparse
import logging
import math
import shlex
import sys

from valutatrade_hub.core import usecases
from valutatrade_hub.core.exceptions import (
    ApiRequestError as CoreApiRequestError,
)
from valutatrade_hub.core.exceptions import (
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.parser_service.api_clients import (
    ApiRequestError as ParserApiRequestError,
)
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage, StorageError
from valutatrade_hub.parser_service.updater import RatesUpdater

logger = logging.getLogger(__name__)
API_ERRORS = (CoreApiRequestError, ParserApiRequestError)


def build_parser() -> argparse.ArgumentParser:
    """Создать парсер аргументов команд."""
    parser = argparse.ArgumentParser(
        prog="wallet",
        description="ValutaTrade Hub — управление валютным портфелем.",
    )
    subparsers = parser.add_subparsers(dest="command")

    register_parser = subparsers.add_parser(
        "register",
        help="Зарегистрировать нового пользователя.",
    )
    register_parser.add_argument("--username", required=True)
    register_parser.add_argument("--password", required=True)

    login_parser = subparsers.add_parser(
        "login",
        help="Войти в систему.",
    )
    login_parser.add_argument("--username", required=True)
    login_parser.add_argument("--password", required=True)

    portfolio_parser = subparsers.add_parser(
        "show-portfolio",
        help="Показать валютный портфель.",
    )
    portfolio_parser.add_argument("--base", default="USD")

    buy_parser = subparsers.add_parser(
        "buy",
        help="Купить валюту.",
    )
    buy_parser.add_argument("--currency", required=True)
    buy_parser.add_argument("--amount", type=float, required=True)

    sell_parser = subparsers.add_parser(
        "sell",
        help="Продать валюту.",
    )
    sell_parser.add_argument("--currency", required=True)
    sell_parser.add_argument("--amount", type=float, required=True)

    rate_parser = subparsers.add_parser(
        "get-rate",
        help="Получить обменный курс.",
    )
    rate_parser.add_argument("--from", dest="from_currency", required=True)
    rate_parser.add_argument("--to", dest="to_currency", required=True)

    update_parser = subparsers.add_parser(
        "update-rates",
        help="Обновить локальный кэш обменных курсов.",
    )
    update_parser.add_argument(
        "--source",
        choices=("coingecko", "exchangerate"),
        default="coingecko",
        help="Источник курсов (по умолчанию: coingecko).",
    )

    show_rates_parser = subparsers.add_parser(
        "show-rates",
        help="Показать курсы из локального кэша.",
    )
    show_rates_parser.add_argument(
        "--currency",
        help="Показать курс указанной валюты относительно --base.",
    )
    show_rates_parser.add_argument(
        "--top",
        type=int,
        help="Показать N криптовалют с наибольшим курсом.",
    )
    show_rates_parser.add_argument(
        "--base",
        default="USD",
        help="Базовая валюта (по умолчанию: USD).",
    )

    return parser


def register(args: argparse.Namespace, session: dict) -> None:
    """Зарегистрировать пользователя."""
    result = usecases.register_user(args.username, args.password)
    if result is not None:
        print(result)


def login(args: argparse.Namespace, session: dict) -> None:
    """Войти в систему и сохранить пользователя в сессии."""
    user = usecases.login_user(args.username, args.password)
    session["user"] = user
    print(f"Вы вошли как '{args.username}'")


def _get_user_id(session: dict) -> int:
    """Получить идентификатор вошедшего пользователя."""
    user = session.get("user")
    if user is None:
        raise ValueError("Сначала выполните login")

    user_id = getattr(user, "user_id", None)
    if user_id is None:
        raise ValueError("Не удалось определить ID пользователя.")

    return user_id


def show_portfolio(args: argparse.Namespace, session: dict) -> None:
    """Показать портфель текущего пользователя."""
    user_id = _get_user_id(session)
    result = usecases.show_portfolio(
        user_id,
        args.base.strip().upper(),
    )
    if result is not None:
        print(result)


def buy(args: argparse.Namespace, session: dict) -> None:
    """Купить указанное количество валюты."""
    user_id = _get_user_id(session)
    if not math.isfinite(args.amount) or args.amount <= 0:
        raise ValueError("Сумма покупки должна быть конечным числом больше нуля.")

    result = usecases.buy_currency(
        user_id,
        args.currency.strip().upper(),
        args.amount,
    )
    if result is not None:
        print(result)


def sell(args: argparse.Namespace, session: dict) -> None:
    """Продать указанное количество валюты."""
    user_id = _get_user_id(session)
    if not math.isfinite(args.amount) or args.amount <= 0:
        raise ValueError("Сумма продажи должна быть конечным числом больше нуля.")

    result = usecases.sell_currency(
        user_id,
        args.currency.strip().upper(),
        args.amount,
    )
    if result is not None:
        print(result)


def get_rate(args: argparse.Namespace, session: dict) -> None:
    """Показать курс одной валюты относительно другой."""
    result = usecases.get_rate(
        args.from_currency.strip().upper(),
        args.to_currency.strip().upper(),
    )
    if result is not None:
        print(result)


def update_rates(args: argparse.Namespace, session: dict) -> None:
    """Обновить кэш курсов с выбранного источника."""
    config = ParserConfig()
    storage = RatesStorage()

    if args.source == "coingecko":
        clients = [CoinGeckoClient(config)]
    else:
        clients = [ExchangeRateApiClient(config)]

    updater = RatesUpdater(clients=clients, storage=storage)
    result = updater.run_update()
    pairs = result.get("pairs", {})
    if not pairs:
        raise RuntimeError("Источник не вернул ни одной корректной пары курсов.")

    sources = sorted(
        {
            str(item.get("source", "неизвестный источник"))
            for item in pairs.values()
            if isinstance(item, dict)
        }
    )
    print(f"Курсы обновлены. Получено пар: {len(pairs)}.")
    if sources:
        print("Источники: " + ", ".join(sources))
    if result.get("last_refresh"):
        print(f"Время обновления (UTC): {result['last_refresh']}")


def _build_rate_graph(pairs: dict) -> dict[str, dict[str, float]]:
    """Построить граф конвертации из записей вида FROM_TO."""
    graph: dict[str, dict[str, float]] = {}
    for pair, record in pairs.items():
        if not isinstance(pair, str) or "_" not in pair:
            continue
        if not isinstance(record, dict):
            continue
        try:
            rate = float(record.get("rate"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(rate) or rate <= 0:
            continue

        from_currency, to_currency = pair.upper().split("_", maxsplit=1)
        graph.setdefault(from_currency, {})[to_currency] = rate
        graph.setdefault(to_currency, {})[from_currency] = 1 / rate
    return graph


def _rate_to_base(
    graph: dict[str, dict[str, float]], currency: str, base: str
) -> float | None:
    """Найти курс валюты относительно базы обходом графа."""
    if currency == base:
        return 1.0
    pending = [(currency, 1.0)]
    visited = {currency}
    while pending:
        current, current_rate = pending.pop(0)
        for neighbour, edge_rate in graph.get(current, {}).items():
            if neighbour in visited:
                continue
            calculated_rate = current_rate * edge_rate
            if neighbour == base:
                return calculated_rate
            visited.add(neighbour)
            pending.append((neighbour, calculated_rate))
    return None


def show_rates(args: argparse.Namespace, session: dict) -> None:
    """Показать курсы из локального кэша без обращения к API."""
    snapshot = RatesStorage().load_rates()
    pairs = snapshot.get("pairs", {})
    if not pairs:
        print("Локальный кэш курсов пуст. Выполните update-rates.")
        return

    base = args.base.strip().upper()
    graph = _build_rate_graph(pairs)
    if base not in graph and args.currency and args.currency.strip().upper() != base:
        raise CurrencyNotFoundError(f"Нет данных для базовой валюты {base}.")

    if args.top is not None and args.top <= 0:
        raise ValueError("Параметр --top должен быть целым числом больше нуля.")

    if args.currency:
        currency = args.currency.strip().upper()
        rate = _rate_to_base(graph, currency, base)
        if rate is None:
            raise CurrencyNotFoundError(
                f"Не найден курс {currency} относительно {base} в локальном кэше."
            )
        print(f"1 {currency} = {rate:.8g} {base}")
    elif args.top is not None:
        crypto_codes = {str(code).upper() for code in ParserConfig.CRYPTO_CURRENCIES}
        ranked = []
        for currency in crypto_codes:
            rate = _rate_to_base(graph, currency, base)
            if rate is not None:
                ranked.append((currency, rate))
        ranked.sort(key=lambda item: item[1], reverse=True)
        if not ranked:
            print(f"В кэше нет курсов криптовалют относительно {base}.")
            return
        for currency, rate in ranked[: args.top]:
            print(f"1 {currency} = {rate:.8g} {base}")
    else:
        for currency in sorted(graph):
            rate = _rate_to_base(graph, currency, base)
            if rate is not None:
                print(f"1 {currency} = {rate:.8g} {base}")

    if snapshot.get("last_refresh"):
        print(f"Последнее обновление (UTC): {snapshot['last_refresh']}")


commands = {
    "register": register,
    "login": login,
    "show-portfolio": show_portfolio,
    "buy": buy,
    "sell": sell,
    "get-rate": get_rate,
    "update-rates": update_rates,
    "show-rates": show_rates,
}


def execute_command(
    args: argparse.Namespace,
    session: dict,
) -> bool:
    """Выполнить команду, показать понятную ошибку и вернуть статус."""
    command = getattr(args, "command", None)

    try:
        commands[command](args, session)
    except InsufficientFundsError as error:
        if command == "sell":
            print(f"Не удалось продать валюту: недостаточно средств. {error}")
        else:
            print(f"Недостаточно средств: {error}")
        return False
    except CurrencyNotFoundError as error:
        if command == "get-rate":
            print(f"Не удалось получить курс: {error}")
        else:
            print(f"Не удалось выполнить команду '{command}': {error}")
        return False
    except API_ERRORS as error:
        if command == "get-rate":
            print(
                "Не удалось получить актуальный курс. "
                f"Проверьте соединение и повторите попытку позже. Подробности: {error}"
            )
        else:
            print(f"Не удалось выполнить команду '{command}': {error}")
        return False
    except (StorageError, RuntimeError, ValueError, TypeError, OSError) as error:
        if command == "buy":
            print(f"Не удалось купить валюту: {error}")
        elif command == "sell":
            print(f"Не удалось продать валюту: {error}")
        elif command == "get-rate":
            print(f"Не удалось получить курс: {error}")
        else:
            print(f"Ошибка: {error}")
        return False

    return True


def main(argv: list[str] | None = None) -> None:
    """Запустить CLI в интерактивном или однокомандном режиме."""
    parser = build_parser()
    session: dict = {"user": None}

    # Если аргументы не переданы, запускаем интерактивный режим.
    interactive = argv is None and len(sys.argv) == 1

    if not interactive:
        args = parser.parse_args(argv)
        if args.command is None:
            parser.print_help()
            return

        execute_command(args, session)
        return

    print("ValutaTrade Hub. Введите help для справки, exit для выхода.")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        if line.lower() in {"exit", "quit"}:
            print("До свидания!")
            break

        if line.lower() in {"help", "?"}:
            parser.print_help()
            continue

        try:
            args = parser.parse_args(shlex.split(line))
            if args.command is not None:
                execute_command(args, session)
        except SystemExit:
            continue


if __name__ == "__main__":
    main()
