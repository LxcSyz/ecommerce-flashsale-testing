"""Run only against the local TradeLab target. See docs/performance.md."""
import uuid

from locust import HttpUser, between, task
from locust.exception import StopUser


class Buyer(HttpUser):
    wait_time = between(0.2, 0.8)

    def on_start(self):
        credentials = {"username": "load_" + uuid.uuid4().hex[:20], "password": "LoadPass123!"}
        response = self.client.post("/api/auth/register", json=credentials)
        if response.status_code != 201:
            raise StopUser()
        response = self.client.post("/api/auth/login", json=credentials)
        if response.status_code != 200:
            raise StopUser()
        self.client.headers.update({"Authorization": "Bearer " + response.json()["token"]})

    def reserve_and_cancel(self, product_id, flash):
        endpoint = "/api/flash-sale/orders" if flash else "/api/orders"
        order_id = None
        with self.client.post(endpoint, json={"items": [{"product_id": product_id, "quantity": 1}]},
                              headers={"Idempotency-Key": uuid.uuid4().hex}, catch_response=True) as response:
            if response.status_code == 201:
                order_id = response.json()["id"]
            elif response.status_code == 409 and response.json().get("error", {}).get("code") == "OUT_OF_STOCK":
                # Valid business rejection; recorded separately from a successful reservation.
                response.request_meta["name"] = endpoint + " [OUT_OF_STOCK]"
                response.success()
            else:
                response.failure(f"Unexpected order response: {response.status_code} {response.text[:160]}")
        if order_id is not None:
            self.client.post(f"/api/orders/{order_id}/cancel", json={}, name="/api/orders/:id/cancel")

    @task(3)
    def regular_order(self):
        self.reserve_and_cancel(1, False)

    @task(1)
    def flash_order(self):
        self.reserve_and_cancel(2, True)

    @task(2)
    def catalog(self):
        self.client.get("/api/products")
