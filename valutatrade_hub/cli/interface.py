"""Командный интерфейс ValutaTrade Hub."""

import argparse
import shlex
import sys

from valutatrade_hub.core import usecases
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)


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
    if args.amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")

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
    if args.amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")

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


commands = {
    "register": register,
    "login": login,
    "show-portfolio": show_portfolio,
    "buy": buy,
    "sell": sell,
    "get-rate": get_rate,
}


def execute_command(
    args: argparse.Namespace,
    session: dict,
) -> bool:
    """Выполнить команду, обработать ошибки и вернуть статус."""
    try:
        commands[args.command](args, session)
    except InsufficientFundsError as error:
        print(error)
        return False
    except CurrencyNotFoundError as error:
        print(f"{error}. Используйте get-rate --from USD --to EUR.")
        return False
    except ApiRequestError as error:
        print(f"{error}. Повторите попытку позже и проверьте соединение.")
        return False
    except (ValueError, TypeError, OSError) as error:
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
