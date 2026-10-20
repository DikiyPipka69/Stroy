"""Расчёт ориентировочной стоимости. Чистые функции без FastAPI, их легко тестировать."""
import json
from pathlib import Path

RATES = json.loads((Path(__file__).parent / "rates.json").read_text("utf-8"))
TYPES = {t["id"]: t for t in RATES["types"]}
LEVELS = {lv["id"]: lv for lv in RATES["levels"]}


class CalcError(ValueError):
    """Неизвестный тип работ или уровень, либо площадь вне допустимого диапазона."""


def _round(value: float, step: int = 1000) -> int:
    return int(round(value / step) * step)


def estimate(work_type: str, area: int, level: str) -> tuple[int, int]:
    """Возвращает (минимум, максимум) в рублях."""
    kind = TYPES.get(work_type)
    lvl = LEVELS.get(level)
    if kind is None or lvl is None:
        raise CalcError("неизвестный тип работ или уровень")
    if not kind["min_area"] <= area <= kind["max_area"]:
        raise CalcError("площадь вне допустимого диапазона")
    base = kind["price_m2"] * area * lvl["k"]
    spread = RATES["spread"]
    return _round(base * (1 - spread)), _round(base * (1 + spread))


def public_rates() -> dict:
    """То, что можно отдать браузеру: без цен за метр и коэффициентов."""
    return {
        "types": [
            {k: t[k] for k in ("id", "group", "name", "min_area", "max_area")}
            for t in RATES["types"]
        ],
        "levels": [{"id": lv["id"], "name": lv["name"]} for lv in RATES["levels"]],
    }


def describe(work_type, area, level, low, high) -> str:
    """Текст для админки: «Каркасный дом, 120 м², стандарт: 4 800 000–5 900 000 ₽»."""
    kind, lvl = TYPES.get(work_type), LEVELS.get(level)
    if not (kind and lvl and low and high):
        return ""
    money = lambda n: f"{n:,}".replace(",", " ")
    return f"{kind['name']}, {area} м², {lvl['name'].lower()}: {money(low)}–{money(high)} ₽"
