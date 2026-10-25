"""Клиенты для взаимодействия с внешними API."""

import logging
import math
from abc import ABC, abstractmethod
from typing import Any

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class ApiRequestError(Exception):
    """Ошибка получения или обработки данных внешнего API."""


class BaseApiClient(ABC):
    """Абстрактный базовый клиент для получения курсов валют."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Получает курсы и возвращает их в унифицированном формате."""
        raise NotImplementedError

    def read_json_by_url(self, url: str) -> dict[str, Any]:
        """Выполняет GET-запрос, проверяет ответ и читает JSON."""
        try:
            response = requests.get(
                url,
                timeout=self.config.REQUEST_TIMEOUT,
            )

            if not response.ok:
                message = (
                    f"Ошибка API. HTTP {response.status_code}: "
                    f"{response.reason}"
                )
                raise ApiRequestError(f"{message}. URL: {url}")

            data = response.json()

        except RequestException as err:
            logger.exception("Ошибка запроса к API: %s", url)
            raise ApiRequestError(
                f"Не удалось выполнить запрос к {url}: {err}"
            ) from err
        except ValueError as err:
            logger.exception("API вернул некорректный JSON: %s", url)
            raise ApiRequestError(
                f"Не удалось разобрать JSON от {url}: {err}"
            ) from err

        if not isinstance(data, dict):
            raise ApiRequestError(
                f"API вернул данные неожиданного формата: {url}"
            )

        return data


class CoinGeckoClient(BaseApiClient):
    """Клиент для получения курсов криптовалют через CoinGecko."""

    def __init__(self, config) -> None:
        super().__init__(
            "https://api.coingecko.com/api/v3/simple/price"
        )
        self.config = config

    def fetch_rates(self) -> dict[str, float]:
        crypto_id_map = self.config.CRYPTO_ID_MAP
        crypto_ids = ",".join(crypto_id_map.values())
        fiat_currencies = self.config.FIAT_CURRENCIES

        params = {
            "ids": crypto_ids,
            "vs_currencies": ",".join(fiat_currencies).lower(),
        }

        try:
            response = requests.get(
                self.base_url,
                params=params,
                timeout=self.config.REQUEST_TIMEOUT,
            )

            if not response.ok:
                raise ApiRequestError(
                    "CoinGecko вернул HTTP "
                    f"{response.status_code}: {response.reason}"
                )

            data = response.json()

        except RequestException as err:
            logger.exception("Ошибка запроса к CoinGecko")
            raise ApiRequestError(
                f"Не удалось получить курсы CoinGecko: {err}"
            ) from err
        except ValueError as err:
            logger.exception("Некорректный JSON от CoinGecko")
            raise ApiRequestError(
                f"Не удалось разобрать ответ CoinGecko: {err}"
            ) from err

        if not isinstance(data, dict):
            raise ApiRequestError(
                "CoinGecko вернул данные неожиданного формата."
            )

        rates: dict[str, float] = {}

        for symbol, crypto_id in crypto_id_map.items():
            crypto_data = data.get(crypto_id)

            if not isinstance(crypto_data, dict):
                logger.warning(
                    "В ответе CoinGecko отсутствует %s (%s)",
                    symbol,
                    crypto_id,
                )
                continue

            for fiat in fiat_currencies:
                value = crypto_data.get(fiat.lower())

                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value <= 0
                ):
                    logger.warning(
                        "Некорректный курс %s_%s от CoinGecko",
                        symbol,
                        fiat,
                    )
                    continue

                rates[f"{symbol}_{fiat}"] = float(value)

        if not rates:
            raise ApiRequestError(
                "CoinGecko не вернул ни одного корректного курса."
            )

        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Клиент для получения курсов фиатных валют."""

    def __init__(self, config) -> None:
        super().__init__(
            "https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}"
        )
        self.config = config

    def fetch_rates(self) -> dict[str, float]:
        api_key = self.config.EXCHANGERATE_API_KEY
        base_currency = self.config.BASE_FIAT_CURRENCY.upper()

        if not api_key:
            raise ApiRequestError(
                "Не задан API-ключ ExchangeRate-API. "
                "Установите переменную окружения "
                "EXCHANGERATE_API_KEY."
            )

        url = self.base_url.format(
            api_key=api_key,
            base=base_currency,
        )
        data = self.read_json_by_url(url)

        if data.get("result") != "success":
            error_type = data.get("error-type", "неизвестная ошибка")
            raise ApiRequestError(
                f"ExchangeRate-API вернул ошибку: {error_type}"
            )

        if data.get("base_code") != base_currency:
            raise ApiRequestError(
                "ExchangeRate-API вернул неожиданный базовый код валюты."
            )

        raw_rates = data.get("conversion_rates")

        if not isinstance(raw_rates, dict):
            raise ApiRequestError(
                "В ответе ExchangeRate-API отсутствует "
                "словарь conversion_rates."
            )

        rates: dict[str, float] = {}

        for currency in self.config.FIAT_CURRENCIES:
            currency = currency.upper()

            if currency == base_currency:
                continue

            value = raw_rates.get(currency)

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                logger.warning(
                    "Некорректный курс %s к %s от ExchangeRate-API",
                    currency,
                    base_currency,
                )
                continue

            # API возвращает, сколько единиц целевой валюты
            # можно получить за одну единицу базовой.
            # Здесь преобразуем курс в формат EUR_USD, RUB_USD и т. п.
            rates[f"{currency}_{base_currency}"] = 1.0 / value

        if not rates:
            raise ApiRequestError(
                "ExchangeRate-API не вернул ни одного "
                "корректного курса."
            )

        return rates
