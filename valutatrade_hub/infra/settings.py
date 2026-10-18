"""Загрузка и кеширование настроек приложения."""

import tomllib
from pathlib import Path
from typing import Any


class SettingsLoader:
    """Единый экземпляр загрузчика настроек приложения."""

    _instance: "SettingsLoader | None" = None
    _initialized = False

    def __new__(cls) -> "SettingsLoader":
        # __new__ проще метакласса и гарантирует единый экземпляр класса.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Повторный вызов конструктора не должен сбрасывать кеш настроек.
        if self._initialized:
            return

        self._project_root = Path(__file__).resolve().parents[2]
        self._settings: dict[str, Any] = {}
        self.reload()
        self._initialized = True

    def get(self, key: str, default: Any = None) -> Any:
        """Получить настройку по ключу или вернуть значение по умолчанию."""
        return self._settings.get(key, default)

    def reload(self) -> None:
        """Перезагрузить настройки из pyproject.toml."""
        config_path = self._project_root / "pyproject.toml"

        with config_path.open("rb") as config_file:
            config = tomllib.load(config_file)

        settings = {
            "data_dir": "data",
            "users_file": "data/users.json",
            "portfolios_file": "data/portfolios.json",
            "rates_file": "data/rates.json",
            "rates_ttl_seconds": 300,
            "log_format": "%(asctime)s %(levelname)s %(message)s",
            "base_currency": "USD",
        }

        settings.update(config.get("tool", {}).get("valutatrade", {}))

        # Преобразуем пути в абсолютные, чтобы запуск не зависел
        # от текущего рабочего каталога терминала.
        for key in (
            "data_dir",
            "users_file",
            "portfolios_file",
            "rates_file",
        ):
            path = Path(settings[key])
            if not path.is_absolute():
                path = self._project_root / path
            settings[key] = path.resolve()

        self._settings = settings
