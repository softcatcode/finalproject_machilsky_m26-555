"""Хранилище текущих курсов и истории измерений."""

import json
import logging
import math
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PAIR_PATTERN = re.compile(r"^[A-Z0-9]{2,5}_[A-Z0-9]{2,5}$")


class StorageError(Exception):
    """Ошибка чтения, проверки или сохранения курсов."""


class RatesStorage:
    """Работает с кэшем rates.json и историей exchange_rates.json."""

    def __init__(
        self,
        rates_file_path: str | Path | None = None,
        history_file_path: str | Path | None = None,
    ) -> None:
        self.rates_file_path = Path(
            rates_file_path or "data/rates.json"
        )
        self.history_file_path = Path(
            history_file_path or "data/exchange_rates.json"
        )

    def save_rates(self, payload: dict[str, Any]) -> None:
        """Сохраняет новые курсы в кэш и добавляет измерения в историю."""
        try:
            incoming = self._validate_snapshot(payload)

            current_snapshot = self.load_rates()
            current_pairs = current_snapshot["pairs"]

            # Сохраняем для каждой пары только самый свежий курс.
            merged_pairs = dict(current_pairs)

            for pair, value in incoming["pairs"].items():
                existing = merged_pairs.get(pair)

                if existing is None or self._is_newer(
                    value["updated_at"],
                    existing.get("updated_at", ""),
                ):
                    merged_pairs[pair] = value

            snapshot = {
                "pairs": merged_pairs,
                "last_refresh": incoming["last_refresh"],
            }

            history = self.load_history()

            known_ids = {
                entry["id"]
                for entry in history
                if isinstance(entry, dict)
                and isinstance(entry.get("id"), str)
            }

            new_entries = []

            for pair, value in incoming["pairs"].items():
                from_currency, to_currency = pair.split("_", maxsplit=1)
                timestamp = value["updated_at"]

                entry_id = (
                    f"{from_currency}_{to_currency}_{timestamp}"
                )

                if entry_id in known_ids:
                    continue

                new_entries.append(
                    {
                        "id": entry_id,
                        "from_currency": from_currency,
                        "to_currency": to_currency,
                        "rate": value["rate"],
                        "timestamp": timestamp,
                        "source": value["source"],
                        "meta": {},
                    }
                )

                known_ids.add(entry_id)

            # Сначала готовим оба результата в памяти.
            # Каждый файл заменяется атомарно отдельно.
            self._atomic_write_json(
                self.rates_file_path,
                snapshot,
            )

            self._atomic_write_json(
                self.history_file_path,
                history + new_entries,
            )

            logger.info(
                "Кэш сохранён: %d пар. Новых исторических записей: %d.",
                len(snapshot["pairs"]),
                len(new_entries),
            )

        except StorageError:
            logger.exception("Не удалось сохранить курсы.")
            raise
        except (OSError, ValueError, TypeError, KeyError) as error:
            logger.exception("Ошибка при обработке данных хранилища.")
            raise StorageError(
                f"Не удалось сохранить курсы: {error}"
            ) from error

    def save(self, payload: dict[str, Any]) -> None:
        """Псевдоним для совместимости с RatesUpdater."""
        self.save_rates(payload)

    def load_rates(self) -> dict[str, Any]:
        """Возвращает текущий кэш или пустой кэш, если файла нет."""
        data = self._read_json(
            self.rates_file_path,
            default={
                "pairs": {},
                "last_refresh": None,
            },
        )

        if not isinstance(data, dict):
            raise StorageError(
                f"Файл {self.rates_file_path} должен содержать JSON-объект."
            )

        pairs = data.get("pairs", {})

        if not isinstance(pairs, dict):
            raise StorageError(
                f"Поле 'pairs' в {self.rates_file_path} должно быть объектом."
            )

        return {
            "pairs": pairs,
            "last_refresh": data.get("last_refresh"),
        }

    def load_history(self) -> list[dict[str, Any]]:
        """Возвращает историю измерений или пустой список."""
        data = self._read_json(
            self.history_file_path,
            default=[],
        )

        if not isinstance(data, list):
            raise StorageError(
                f"Файл {self.history_file_path} должен содержать JSON-массив."
            )

        if not all(isinstance(entry, dict) for entry in data):
            raise StorageError(
                f"Файл {self.history_file_path} содержит некорректные записи."
            )

        return data

    @staticmethod
    def _validate_snapshot(
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Проверяет структуру и значения перед записью."""
        if not isinstance(payload, dict):
            raise StorageError(
                "Данные для сохранения должны быть JSON-объектом."
            )

        pairs = payload.get("pairs")
        last_refresh = payload.get("last_refresh")

        if not isinstance(pairs, dict):
            raise StorageError(
                "Поле 'pairs' должно содержать словарь валютных пар."
            )

        if not isinstance(last_refresh, str) or not last_refresh:
            raise StorageError(
                "Поле 'last_refresh' должно содержать временную метку."
            )

        normalized_pairs = {}

        for pair, value in pairs.items():
            if (
                not isinstance(pair, str)
                or not PAIR_PATTERN.fullmatch(pair)
            ):
                raise StorageError(
                    f"Некорректный код валютной пары: {pair!r}."
                )

            if not isinstance(value, dict):
                raise StorageError(
                    f"Данные валютной пары {pair} должны быть объектом."
                )

            rate = value.get("rate")

            if (
                isinstance(rate, bool)
                or not isinstance(rate, (int, float))
                or not math.isfinite(rate)
                or rate <= 0
            ):
                raise StorageError(
                    f"Курс для {pair} должен быть конечным числом больше нуля."
                )

            updated_at = value.get("updated_at")
            source = value.get("source")

            if not isinstance(updated_at, str) or not updated_at:
                raise StorageError(
                    f"Для валютной пары {pair} отсутствует updated_at."
                )

            if not isinstance(source, str) or not source:
                raise StorageError(
                    f"Для валютной пары {pair} отсутствует source."
                )

            # Проверяем, что временная метка имеет допустимый ISO-формат.
            RatesStorage._parse_timestamp(updated_at)

            normalized_pairs[pair] = {
                "rate": float(rate),
                "updated_at": updated_at,
                "source": source,
            }

        RatesStorage._parse_timestamp(last_refresh)

        return {
            "pairs": normalized_pairs,
            "last_refresh": last_refresh,
        }

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        """Преобразует ISO-временную метку в datetime."""
        try:
            timestamp = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError as error:
            raise StorageError(
                f"Некорректная временная метка: {value!r}."
            ) from error

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return timestamp.astimezone(UTC)

    @staticmethod
    def _is_newer(incoming: str, existing: str) -> bool:
        """Проверяет, новее ли поступившее измерение текущего."""
        try:
            incoming_dt = RatesStorage._parse_timestamp(incoming)
            existing_dt = RatesStorage._parse_timestamp(existing)
        except StorageError:
            # При некорректной старой записи предпочитаем корректную новую.
            return True

        return incoming_dt > existing_dt

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        """Читает JSON-файл; отсутствующий файл заменяется значением по умолчанию."""
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return default
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(
                f"Не удалось прочитать файл {path}: {error}"
            ) from error

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        """Записывает JSON во временный файл и атомарно заменяет целевой."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = file.name

                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            os.replace(temporary_path, path)

        except (OSError, TypeError, ValueError) as error:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

            raise StorageError(
                f"Не удалось атомарно записать {path}: {error}"
            ) from error