import hashlib
import math
import secrets
from datetime import datetime


class User:
    """Пользователь системы."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ) -> None:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("ID пользователя должен быть положительным целым числом.")

        self._user_id = user_id
        self.username = username

        if not isinstance(hashed_password, str) or not hashed_password:
            raise ValueError("Хеш пароля не должен быть пустым.")

        if not isinstance(salt, str) or not salt:
            raise ValueError("Соль не должна быть пустой.")

        if not isinstance(registration_date, datetime):
            raise TypeError("Дата регистрации должна иметь тип datetime.")

        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @property
    def user_id(self) -> int:
        """Возвращает ID пользователя."""
        return self._user_id

    @property
    def username(self) -> str:
        """Возвращает имя пользователя."""
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не должно быть пустым.")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """Возвращает хеш пароля, но не исходный пароль."""
        return self._hashed_password

    @property
    def salt(self) -> str:
        """Возвращает соль пользователя."""
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """Возвращает дату регистрации."""
        return self._registration_date

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """Создаёт SHA-256 хеш пароля с солью."""
        salted_pwd = (password + salt).encode("utf-8")
        return hashlib.sha256(salted_pwd).hexdigest()

    def change_password(self, new_password: str) -> None:
        """Устанавливает новый пароль и генерирует новую соль."""
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValueError("Пароль должен содержать минимум 4 символа.")

        self._salt = secrets.token_hex(16)
        self._hashed_password = self._hash_password(
            new_password,
            self._salt,
        )

    def verify_password(self, password: str) -> bool:
        """Проверяет соответствие введённого пароля сохранённому хешу."""
        if not isinstance(password, str):
            return False

        candidate_hash = self._hash_password(password, self._salt)
        return secrets.compare_digest(candidate_hash, self._hashed_password)

    def get_user_info(self) -> dict[str, int | str | datetime]:
        """Возвращает информацию о пользователе без пароля и соли."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date,
        }


class Wallet:
    """Кошелёк для хранения одной валюты."""

    def __init__(
        self,
        currency_code: str,
        balance: float = 0.0,
    ) -> None:
        self.currency_code = currency_code
        self.balance = balance

    @property
    def currency_code(self) -> str:
        """Возвращает код валюты."""
        return self._currency_code

    @currency_code.setter
    def currency_code(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("Код валюты должен быть строкой.")

        value = value.strip().upper()

        if not value or not value.isalnum():
            raise ValueError("Некорректный код валюты.")

        self._currency_code = value

    @property
    def balance(self) -> float:
        """Возвращает текущий баланс."""
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом.")

        if not math.isfinite(value):
            raise ValueError("Баланс должен быть конечным числом.")

        if value < 0:
            raise ValueError("Баланс не может быть отрицательным.")

        self._balance = float(value)

    @staticmethod
    def _validate_amount(amount: float) -> float:
        """Проверяет сумму операции и возвращает её как float."""
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("Сумма должна быть числом.")

        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Сумма должна быть конечным положительным числом.")

        return float(amount)

    def deposit(self, amount: float) -> None:
        """Пополняет кошелёк."""
        amount = self._validate_amount(amount)
        self.balance = self.balance + amount

    def withdraw(self, amount: float) -> None:
        """Снимает средства, если их достаточно."""
        amount = self._validate_amount(amount)

        if amount > self.balance:
            raise ValueError("Недостаточно средств на балансе.")

        self.balance = self.balance - amount

    def get_balance_info(self) -> dict[str, str | float]:
        """Возвращает информацию о кошельке."""
        return {
            "currency_code": self.currency_code,
            "balance": self.balance,
        }


class Portfolio:
    """Портфель пользователя, содержащий валютные кошельки."""

    def __init__(
        self,
        user: User,
        wallets: dict[str, Wallet] | None = None,
    ) -> None:
        if not isinstance(user, User):
            raise TypeError("Портфель должен принадлежать объекту User.")

        self._user = user
        self._user_id = user.user_id
        self._wallets: dict[str, Wallet] = {}

        if wallets is not None:
            for currency_code, wallet in wallets.items():
                if not isinstance(wallet, Wallet):
                    raise TypeError("Каждый кошелёк должен быть объектом Wallet.")

                if currency_code.strip().upper() != wallet.currency_code:
                    raise ValueError(
                        "Ключ словаря должен совпадать с кодом валюты кошелька."
                    )

                self.add_currency(wallet.currency_code)
                self._wallets[wallet.currency_code] = wallet

    @property
    def user(self) -> User:
        """Возвращает пользователя портфеля."""
        return self._user

    @property
    def user_id(self) -> int:
        """Возвращает ID владельца портфеля."""
        return self._user_id

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Возвращает копию словаря кошельков."""
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> Wallet:
        """Создаёт кошелёк для валюты, если его ещё нет."""
        if not isinstance(currency_code, str):
            raise TypeError("Код валюты должен быть строкой.")

        wallet = Wallet(currency_code)

        if wallet.currency_code in self._wallets:
            raise ValueError(f"Кошелёк {wallet.currency_code} уже существует.")

        self._wallets[wallet.currency_code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet:
        """Возвращает кошелёк по коду валюты."""
        if not isinstance(currency_code, str):
            raise TypeError("Код валюты должен быть строкой.")

        code = currency_code.strip().upper()

        try:
            return self._wallets[code]
        except KeyError:
            raise ValueError(f"Кошелёк {code} не найден.") from None

    def get_total_value(
        self, exchange_rates: dict[str, float], base_currency: str = "USD"
    ) -> float:
        """Рассчитывает стоимость портфеля в указанной валюте."""
        if not isinstance(base_currency, str):
            raise TypeError("Код базовой валюты должен быть строкой.")

        base_code = base_currency.strip().upper()

        if base_code not in exchange_rates:
            raise ValueError(f"Нет курса для базовой валюты {base_code}.")

        base_rate = exchange_rates[base_code]
        total = 0.0

        for wallet in self._wallets.values():
            currency_code = wallet.currency_code

            if currency_code not in exchange_rates:
                raise ValueError(f"Нет курса для валюты {currency_code}.")

            value_in_usd = wallet.balance * exchange_rates[currency_code]
            total += value_in_usd / base_rate

        return total
