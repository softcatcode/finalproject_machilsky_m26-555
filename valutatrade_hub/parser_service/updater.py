"""Координация получения и сохранения курсов валют."""

import logging
import math
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class RatesUpdater:
    """Получает курсы от API-клиентов и обновляет локальный кэш.

    Хранилище должно предоставлять метод ``save_rates(data)`` или ``save(data)``.
    """

    def __init__(self, clients: list[Any] | tuple[Any, ...], storage: Any) -> None:
        self.clients = list(clients)
        self.storage = storage

    def run_update(self) -> dict[str, Any]:
        """Обновляет кэш; ошибка одного клиента не мешает остальным."""
        last_refresh = self._utc_now()
        logger.info("Начато обновление курсов валют.")

        pairs: dict[str, dict[str, Any]] = {}
        successful_clients = 0
        failed_clients = 0

        for client in self.clients:
            source = self._get_source(client)
            logger.info("Запрос курсов у клиента %s начат.", source)
            try:
                response = client.fetch_rates()
                client_pairs = self._normalize_rates(response, client, source)
                if not client_pairs:
                    logger.warning(
                        "Клиент %s не вернул корректных курсов.", source
                    )
                    failed_clients += 1
                    continue

                pairs.update(client_pairs)
                successful_clients += 1
                logger.info(
                    "Клиент %s успешно вернул %d пар валют.",
                    source,
                    len(client_pairs),
                )
            except Exception:
                failed_clients += 1
                logger.exception("Ошибка при запросе курсов у клиента %s.", source)

        if not pairs:
            logger.error("Обновление не выполнено: нет корректных курсов.")
            # Не затираем предыдущий кэш пустыми данными.
            raise RuntimeError("Не удалось получить ни одного корректного курса.")

        payload = {"pairs": pairs, "last_refresh": last_refresh}
        try:
            self._save(payload)
        except Exception:
            logger.exception("Не удалось сохранить обновлённые курсы.")
            raise

        logger.info(
            "Обновление завершено. Успешных клиентов: %d; с ошибками: %d; пар: %d.",
            successful_clients,
            failed_clients,
            len(pairs),
        )
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        save_method = getattr(self.storage, "save_rates", None)
        if not callable(save_method):
            save_method = getattr(self.storage, "save", None)
        if not callable(save_method):
            raise TypeError(
                "Storage должен предоставлять метод save_rates(data) или save(data)."
            )
        save_method(payload)

    @staticmethod
    def _get_source(client: Any) -> str:
        explicit_source = getattr(client, "source", None)
        if explicit_source:
            return str(explicit_source)
        class_name = type(client).__name__.lower()
        if "coingecko" in class_name:
            return "CoinGecko"
        if "exchangerate" in class_name:
            return "ExchangeRate-API"
        return type(client).__name__

    def _normalize_rates(
        self, response: Any, client: Any, source: str
    ) -> dict[str, dict[str, Any]]:
        """Поддерживает нормализованные словари и исходные ответы обоих API."""
        if not isinstance(response, dict):
            raise ValueError("Ответ API должен быть JSON-объектом.")

        timestamp = self._utc_now()
        result: dict[str, dict[str, Any]] = {}

        # Формат клиентов вида {"BTC_USD": 59337.21}.
        if response and all(
            isinstance(key, str) and "_" in key for key in response
        ):
            for pair, value in response.items():
                rate = self._valid_rate(value)
                if rate is None:
                    logger.warning("Пропущен некорректный курс для %s.", pair)
                    continue
                result[pair.upper()] = {
                    "rate": rate,
                    "updated_at": timestamp,
                    "source": source,
                }
            return result

        # CoinGecko: {"bitcoin": {"usd": 59337.21}, ...}.
        if "coingecko" in type(client).__name__.lower():
            try:
                from .config import ParserConfig

                id_map = {
                    str(coin_id).lower(): str(code).upper()
                    for code, coin_id in ParserConfig.CRYPTO_ID_MAP.items()
                }
            except (ImportError, AttributeError):
                id_map = {}

            for coin_id, currency_rates in response.items():
                crypto_code = id_map.get(str(coin_id).lower())
                if not crypto_code or not isinstance(currency_rates, dict):
                    continue
                for fiat_code, value in currency_rates.items():
                    rate = self._valid_rate(value)
                    if rate is None:
                        continue
                    result[f"{crypto_code}_{str(fiat_code).upper()}"] = {
                        "rate": rate,
                        "updated_at": timestamp,
                        "source": source,
                    }
            return result

        # ExchangeRate-API: rates показывает количество валюты за 1 base_code.
        # Для кэша EUR_USD сохраняем USD за 1 EUR, то есть обратный курс.
        rates = response.get("rates")
        if isinstance(rates, dict):
            base_code = str(response.get("base_code", "USD")).upper()
            for currency_code, value in rates.items():
                currency_code = str(currency_code).upper()
                if currency_code == base_code:
                    continue
                raw_rate = self._valid_rate(value)
                if raw_rate is None:
                    logger.warning("Пропущен некорректный курс для %s.", currency_code)
                    continue
                result[f"{currency_code}_{base_code}"] = {
                    "rate": 1 / raw_rate,
                    "updated_at": timestamp,
                    "source": source,
                }
            return result

        raise ValueError("Неизвестный формат ответа API.")

    @staticmethod
    def _valid_rate(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        rate = float(value)
        if not math.isfinite(rate) or rate <= 0:
            return None
        return rate

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
