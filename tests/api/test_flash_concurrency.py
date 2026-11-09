import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

FLASH = [{"product_id": 2, "quantity": 1}]


def parallel(actions):
    gate = threading.Barrier(len(actions))

    def run(action):
        gate.wait(timeout=20)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


def assert_conservation(sql, pid):
    product = sql("SELECT * FROM products WHERE id = ?", (pid,))[0]
    reserved = sql("SELECT COALESCE(SUM(i.quantity), 0) AS n FROM order_items i JOIN orders o "
                   "ON o.id = i.order_id WHERE i.product_id = ? AND o.status IN ('pending', 'paid')", (pid,))[0]["n"]
    assert product["stock"] >= 0
    assert product["stock"] + reserved == product["initial_stock"]


@pytest.mark.parametrize("start,end", [(60, 120), (-120, -60)])
def test_flash_time_window(buyer, sql, start, end):
    now = time.time()
    sql("UPDATE products SET starts_at = ?, ends_at = ? WHERE id = 2", (now + start, now + end))
    response = buyer.order(FLASH, flash=True)
    assert response.status_code == 409 and response.json()["error"]["code"] == "SALE_INACTIVE"
    assert_conservation(sql, 2)


def test_channel_and_quantity_rules(buyer):
    assert buyer.order(FLASH).status_code == 409
    assert buyer.order(flash=True).status_code == 409
    assert buyer.order([{"product_id": 2, "quantity": 2}], flash=True).status_code == 422


def test_cancel_releases_flash_limit(buyer, sql):
    first = buyer.order(FLASH, flash=True).json()
    assert buyer.order(FLASH, flash=True).json()["error"]["code"] == "PURCHASE_LIMIT"
    assert buyer.call("POST", f'/api/orders/{first["id"]}/cancel', {}).status_code == 200
    assert buyer.order(FLASH, flash=True).status_code == 201
    assert_conservation(sql, 2)


@pytest.mark.concurrency
def test_24_buyers_compete_for_10_items(user_factory, sql, record_property):
    buyers = [user_factory() for _ in range(24)]
    started = time.perf_counter()
    results = parallel([lambda client=client: client.order(FLASH, flash=True) for client in buyers])
    elapsed = time.perf_counter() - started
    assert sum(result.status_code == 201 for result in results) == 10
    assert sum(result.status_code == 409 and result.json()["error"]["code"] == "OUT_OF_STOCK" for result in results) == 14
    assert len(sql("SELECT * FROM orders")) == 10
    assert sql("SELECT stock FROM products WHERE id = 2")[0]["stock"] == 0
    assert_conservation(sql, 2)
    record_property("requests", 24)
    record_property("created", 10)
    record_property("sold_out", 14)
    record_property("elapsed_seconds", round(elapsed, 3))


@pytest.mark.concurrency
def test_same_user_parallel_requests_cannot_bypass_limit(buyer, sql):
    results = parallel([lambda: buyer.order(FLASH, flash=True) for _ in range(12)])
    assert sum(result.status_code == 201 for result in results) == 1
    assert sum(result.status_code == 409 and result.json()["error"]["code"] == "PURCHASE_LIMIT" for result in results) == 11
    assert_conservation(sql, 2)


@pytest.mark.concurrency
def test_parallel_same_key_only_deducts_once(buyer, sql):
    results = parallel([lambda: buyer.order(key="retry-key") for _ in range(12)])
    assert all(result.status_code == 201 for result in results)
    assert len({result.json()["id"] for result in results}) == 1
    assert_conservation(sql, 1)
    assert len(sql("SELECT * FROM orders")) == 1


@pytest.mark.concurrency
def test_parallel_cancellation_restock_once(buyer, sql):
    order_id = buyer.order().json()["id"]
    results = parallel([lambda: buyer.call("POST", f"/api/orders/{order_id}/cancel", {}) for _ in range(12)])
    assert all(result.status_code == 200 for result in results)
    assert sql("SELECT stock FROM products WHERE id = 1")[0]["stock"] == 100
    assert_conservation(sql, 1)


@pytest.mark.concurrency
def test_pay_cancel_race_has_one_final_state(buyer, sql):
    order_id = buyer.order().json()["id"]
    results = parallel([lambda: buyer.call("POST", f"/api/orders/{order_id}/pay", {}),
                        lambda: buyer.call("POST", f"/api/orders/{order_id}/cancel", {})])
    assert sorted(result.status_code for result in results) == [200, 409]
    final = buyer.call("GET", f"/api/orders/{order_id}").json()
    assert final["status"] in ("paid", "cancelled")
    expected = 99 if final["status"] == "paid" else 100
    assert sql("SELECT stock FROM products WHERE id = 1")[0]["stock"] == expected
    assert_conservation(sql, 1)
