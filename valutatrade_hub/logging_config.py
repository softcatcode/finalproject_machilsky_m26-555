"""Настройка логирования доменных операций."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


def setup_logging(debug: bool = False) -> logging.Logger:
    """Настроить логирование операций с ротацией файла."""
    settings = SettingsLoader()
    log_dir = Path(settings.get("log_dir", "logs"))

    if not log_dir.is_absolute():
        log_dir = Path(__file__).resolve().parents[1] / log_dir

    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("valutatrade_hub.actions")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False

    # Не добавляем обработчики повторно при повторной настройке.
    if logger.handlers:
        return logger

    handler = RotatingFileHandler(
        log_dir / "actions.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG if debug else logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "%(levelname)s %(message)s",
        )
    )
    logger.addHandler(handler)

    return logger