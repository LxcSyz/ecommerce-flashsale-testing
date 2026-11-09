import pytest


def stock(sql, pid=1):
    return sql("SELECT stock FROM products WHERE id = ?", (pid,))[0]["stock"]


def test_cart_checkout_amount_pay_and_inventory(buyer, sql):
    buyer.call("POST", "/api/cart", {"product_id": 1, "quantity": 2})
    response = buyer.order([{"product_id": 1, "quantity": 2}, {"product_id": 3, "quantity": 1}])
    assert response.status_code == 201
    order = response.json()
    assert order["total_cents"] == 2 * 19900 + 8900
    assert order["status"] == "pending" and stock(sql) == 98
    assert buyer.call("GET", "/api/cart").json() == []
    assert buyer.call("POST", f'/api/orders/{order["id"]}/pay', {}).json()["status"] == "paid"
    assert buyer.call("POST", f'/api/orders/{order["id"]}/pay', {}).status_code == 200
    assert stock(sql) == 98
    assert buyer.call("POST", f'/api/orders/{order["id"]}/cancel', {}).status_code == 409


def test_cancel_restock_exactly_once(buyer, sql):
    order = buyer.order().json()
    assert stock(sql) == 99
    for _ in range(3):
        assert buyer.call("POST", f'/api/orders/{order["id"]}/cancel', {}).json()["status"] == "cancelled"
    assert stock(sql) == 100
    assert buyer.call("POST", f'/api/orders/{order["id"]}/pay', {}).status_code == 409


def test_idempotency_replay_and_payload_conflict(buyer, sql):
    first = buyer.order(key="same-key")
    second = buyer.order(key="same-key")
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json() and stock(sql) == 99
    changed = buyer.order([{"product_id": 1, "quantity": 2}], key="same-key")
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_key_required_and_scoped_to_user(buyer, user_factory):
    assert buyer.call("POST", "/api/orders", {"items": [{"product_id": 1, "quantity": 1}]}).status_code == 422
    a = buyer.order(key="shared")
    b = user_factory().order(key="shared")
    assert a.status_code == b.status_code == 201 and a.json()["id"] != b.json()["id"]


def test_order_owner_isolation(buyer, user_factory):
    order_id = buyer.order().json()["id"]
    attacker = user_factory()
    assert attacker.call("GET", "/api/orders").json() == []
    for method, suffix in [("GET", ""), ("POST", "/pay"), ("POST", "/cancel")]:
        assert attacker.call(method, f"/api/orders/{order_id}{suffix}").status_code == 404


def test_multi_item_failure_rolls_back_inventory_and_cart(buyer, sql):
    buyer.call("POST", "/api/cart", {"product_id": 1, "quantity": 1})
    response = buyer.order([{"product_id": 1, "quantity": 1}, {"product_id": 3, "quantity": 51}])
    assert response.status_code == 409
    assert stock(sql) == 100 and stock(sql, 3) == 50
    assert sql("SELECT * FROM orders") == []
    assert len(buyer.call("GET", "/api/cart").json()) == 1


@pytest.mark.parametrize("items", [[], [{"product_id": 1, "quantity": 0}],
    [{"product_id": 1, "quantity": 1}, {"product_id": 1, "quantity": 1}], [None]])
def test_invalid_order_items(buyer, items):
    assert buyer.order(items).status_code == 422


def test_server_price_cannot_be_overridden(buyer):
    result = buyer.order([{"product_id": 1, "quantity": 1, "price_cents": 1}])
    assert result.status_code == 201 and result.json()["total_cents"] == 19900


def test_last_stock_and_sold_out(buyer, sql):
    sql("UPDATE products SET stock = 1, initial_stock = 1 WHERE id = 1")
    assert buyer.order().status_code == 201
    response = buyer.order()
    assert response.status_code == 409 and response.json()["error"]["code"] == "OUT_OF_STOCK"
    assert stock(sql) == 0


def test_unknown_product_and_order(buyer):
    assert buyer.order([{"product_id": 999, "quantity": 1}]).status_code == 404
    assert buyer.call("GET", "/api/orders/999").status_code == 404
