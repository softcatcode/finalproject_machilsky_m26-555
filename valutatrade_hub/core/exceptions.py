"""Исключения, выкидываемые программой"""

class CurrencyNotFoundError(LookupError):
    """Исключение для неизвестного кода валюты."""