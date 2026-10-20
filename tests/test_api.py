import pytest
from fastapi.testclient import TestClient

from app import db, ratelimit
from app.main import app

CALC = {"work_type": "repair_capital", "area": 50, "level": "standard"}
VALID = {
    "name": "Иван",
    "phone": "+7 900 123-45-67",
    "comment": "",
    "consent": True,
    "website": "",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Свежая база на каждый тест и без пароля админки из .env
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    ratelimit.reset()
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_index_and_security_headers(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "default-src 'self'" in res.headers["content-security-policy"]
    assert res.headers["x-content-type-options"] == "nosniff"


def test_rates_do_not_expose_prices(client):
    data = client.get("/api/rates").json()
    assert data["types"] and data["levels"]
    assert "price_m2" not in data["types"][0]


def test_calc_ok(client):
    res = client.post("/api/calc", json=CALC)
    assert res.status_code == 200
    assert res.json() == {"min": 506000, "max": 619000}


@pytest.mark.parametrize(
    "patch",
    [
        {"work_type": "unknown"},
        {"level": "gold"},
        {"area": 5},                                        # меньше общего минимума
        {"work_type": "house_frame", "area": 20},           # меньше минимума для дома
    ],
)
def test_calc_rejects_bad_input(client, patch):
    assert client.post("/api/calc", json={**CALC, **patch}).status_code == 422


def test_lead_without_calc(client):
    assert client.post("/api/lead", json=VALID).status_code == 200
    lead = db.list_leads()[0]
    assert lead["phone"] == "79001234567" and lead["est_min"] is None


def test_lead_with_calc_uses_server_estimate(client):
    # Клиент пытается подсунуть свою сумму: лишние поля игнорируются
    payload = {**VALID, **CALC, "est_min": 1, "est_max": 2}
    assert client.post("/api/lead", json=payload).status_code == 200
    lead = db.list_leads()[0]
    assert (lead["est_min"], lead["est_max"]) == (506000, 619000)


def test_lead_with_partial_calc_rejected(client):
    assert client.post("/api/lead", json={**VALID, "work_type": "repair_capital"}).status_code == 422
    assert db.list_leads() == []


@pytest.mark.parametrize("patch", [{"consent": False}, {"phone": "123"}, {"name": "И"}])
def test_rejects_invalid_lead(client, patch):
    assert client.post("/api/lead", json={**VALID, **patch}).status_code == 422
    assert db.list_leads() == []


def test_honeypot_is_not_saved(client):
    res = client.post("/api/lead", json={**VALID, "website": "http://spam.example"})
    assert res.status_code == 200
    assert db.list_leads() == []


def test_rate_limit(client):
    for _ in range(5):
        assert client.post("/api/lead", json=VALID).status_code == 200
    assert client.post("/api/lead", json=VALID).status_code == 429


def test_admin_disabled_without_password(client):
    assert client.get("/admin").status_code == 404


def test_admin_requires_auth_and_escapes_html(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    client.post("/api/lead", json={**VALID, **CALC, "name": "<b>Хакер</b>"})
    assert client.get("/admin").status_code == 401
    assert client.get("/admin", auth=("admin", "wrong")).status_code == 401
    page = client.get("/admin", auth=("admin", "secret"))
    assert page.status_code == 200
    assert "&lt;b&gt;" in page.text and "<b>Хакер" not in page.text
    assert "Капитальный ремонт, 50 м²" in page.text
