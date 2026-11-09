import pytest


def test_register_login_and_duplicate(system):
    client, _ = system
    data = {"username": "tester", "password": "TestPass123!"}
    assert client.call("POST", "/api/auth/register", data).status_code == 201
    assert client.call("POST", "/api/auth/register", data).status_code == 409
    assert client.call("POST", "/api/auth/login", {**data, "password": "WrongPass!"}).status_code == 401
    result = client.call("POST", "/api/auth/login", data)
    assert result.status_code == 200 and result.json()["expires_in"] == 3600


@pytest.mark.parametrize("body", [
    {"username": "ab", "password": "TestPass123!"},
    {"username": "tester", "password": "short"},
    {"username": " " * 5, "password": "TestPass123!"},
    {"username": 123, "password": "TestPass123!"},
])
def test_invalid_credentials(system, body):
    assert system[0].call("POST", "/api/auth/register", body).status_code == 422


def test_password_is_salted_hash(buyer, sql):
    stored = sql("SELECT password_hash FROM users")[0]["password_hash"]
    assert "TestPass123!" not in stored
    assert len(stored.split(":")) == 2


def test_missing_and_expired_token(system, buyer, sql):
    assert system[0].call("GET", "/api/me").status_code == 401
    assert buyer.call("GET", "/api/me").status_code == 200
    sql("UPDATE sessions SET expires_at = 0")
    assert buyer.call("GET", "/api/me").status_code == 401


def test_sql_injection_does_not_bypass_login(system):
    response = system[0].call("POST", "/api/auth/login", {"username": "' OR 1=1 --", "password": "TestPass123!"})
    assert response.status_code == 401


def test_cart_set_quantity_is_idempotent_and_isolated(buyer, user_factory):
    other = user_factory()
    body = {"product_id": 1, "quantity": 2}
    for _ in range(2):
        response = buyer.call("POST", "/api/cart", body)
        assert response.status_code == 200 and response.json()[0]["quantity"] == 2
    assert other.call("GET", "/api/cart").json() == []
    assert buyer.call("DELETE", "/api/cart/1").json() == []


@pytest.mark.parametrize("quantity", [0, -1, 101, True, 1.5, "2", None])
def test_cart_quantity_boundaries(buyer, quantity):
    assert buyer.call("POST", "/api/cart", {"product_id": 1, "quantity": quantity}).status_code == 422


def test_flash_product_cannot_enter_cart(buyer):
    assert buyer.call("POST", "/api/cart", {"product_id": 2, "quantity": 1}).status_code == 409


def test_invalid_json_and_non_object(system):
    response = system[0].call("POST", "/api/auth/register", data="{broken")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JSON"
    assert system[0].call("POST", "/api/auth/register", body=[]).status_code == 422
