"""Тесты расчёта. FastAPI здесь не нужен: проверяем чистые функции."""
import pytest

from app import calc


def test_estimate_known_value():
    # 9000 ₽/м² * 50 м² * 1,25 = 562 500; коридор ±10% и округление до тысяч
    assert calc.estimate("repair_capital", 50, "standard") == (506000, 619000)


def test_higher_level_costs_more():
    low = calc.estimate("house_frame", 100, "economy")
    high = calc.estimate("house_frame", 100, "premium")
    assert high[0] > low[0] and high[1] > low[1]


def test_min_is_less_than_max():
    low, high = calc.estimate("repair_cosmetic", 40, "economy")
    assert 0 < low < high


@pytest.mark.parametrize(
    "args",
    [
        ("unknown", 50, "standard"),
        ("repair_capital", 50, "gold"),
        ("house_frame", 20, "standard"),     # меньше минимальной площади дома
        ("repair_capital", 301, "standard"),  # больше максимальной площади
    ],
)
def test_rejects_bad_input(args):
    with pytest.raises(calc.CalcError):
        calc.estimate(*args)


def test_public_rates_hide_prices():
    data = calc.public_rates()
    assert data["types"] and data["levels"]
    for item in data["types"] + data["levels"]:
        assert "price_m2" not in item and "k" not in item


def test_describe():
    text = calc.describe("house_frame", 120, "standard", 4800000, 5900000)
    assert text == "Каркасный дом, 120 м², стандарт: 4 800 000–5 900 000 ₽"
    assert calc.describe("house_frame", 120, "standard", None, None) == ""
