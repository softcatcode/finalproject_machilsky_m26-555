from datetime import UTC, datetime

import pytest

from valutatrade_hub.core import usecases as u


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setattr(u, "users_file", tmp_path / "users.json")
    monkeypatch.setattr(u, "portfolios_file", tmp_path / "portfolios.json")
    monkeypatch.setattr(u, "rates_file", tmp_path / "rates.json")
    return u


def test_register_user_creates_portfolio(isolated_data):
    result = isolated_data.register_user("test_user", "pass123")

    assert "зарегистрирован" in result
    user = isolated_data.login_user("test_user", "pass123")
    assert user.username == "test_user"

    portfolio = isolated_data._load_portfolio(user)
    assert portfolio.wallets["USD"].balance == 10_000


def test_login_rejects_wrong_password(isolated_data):
    isolated_data.register_user("test_user", "pass123")

    with pytest.raises(ValueError, match="Неверное имя пользователя или пароль"):
        isolated_data.login_user("test_user", "wrong_pass")


def test_register_rejects_duplicate_username(isolated_data):
    isolated_data.register_user("test_user", "pass123")

    with pytest.raises(ValueError, match="уже существует"):
        isolated_data.register_user("TEST_USER", "pass456")


def test_register_rejects_short_password(isolated_data):
    with pytest.raises(ValueError, match="минимум 4 символа"):
        isolated_data.register_user("test_user", "123")


def test_buy_currency_updates_balances(isolated_data):
    isolated_data.register_user("buyer", "pass123")
    user = isolated_data.login_user("buyer", "pass123")

    isolated_data._write_json(
        isolated_data.rates_file,
        {
            "pairs": {"EUR_USD": {"rate": 2.0}},
            "last_refresh": datetime.now(UTC).isoformat(),
        },
    )

    result = isolated_data.buy_currency(user.user_id, "EUR", 100)
    portfolio = isolated_data._load_portfolio(user)

    assert "Куплено 100 EUR" in result
    assert "списано 200 USD" in result
    assert portfolio.wallets["USD"].balance == 9800
    assert portfolio.wallets["EUR"].balance == 100


def test_sell_currency_updates_balances(isolated_data):
    isolated_data.register_user("seller", "pass123")
    user = isolated_data.login_user("seller", "pass123")

    isolated_data._write_json(
        isolated_data.rates_file,
        {
            "pairs": {"EUR_USD": {"rate": 2.0}},
            "last_refresh": datetime.now(UTC).isoformat(),
        },
    )

    isolated_data.buy_currency(user.user_id, "EUR", 100)
    result = isolated_data.sell_currency(user.user_id, "EUR", 40)
    portfolio = isolated_data._load_portfolio(user)

    assert "Продано 40 EUR" in result
    assert "зачислено 80 USD" in result
    assert portfolio.wallets["USD"].balance == 9880
    assert portfolio.wallets["EUR"].balance == 60
