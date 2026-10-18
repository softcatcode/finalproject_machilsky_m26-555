from valutatrade_hub.infra.settings import SettingsLoader

settings = SettingsLoader()
users_file = settings.get("users_file")
portfolios_file = settings.get("portfolios_file")
rates_file = settings.get("rates_file")
ttl = settings.get("rates_ttl_seconds")
base_currency = settings.get("base_currency", "USD")