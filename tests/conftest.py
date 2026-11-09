import threading
import uuid

import pytest
import requests

from app.db import connect
from app.server import create_server


class Client:
    def __init__(self, base, token=""):
        self.base, self.token = base, token

    def call(self, method, path, body=None, key=None, **kwargs):
        headers = {"Authorization": "Bearer " + self.token} if self.token else {}
        if key is not None:
            headers["Idempotency-Key"] = key
        return requests.request(method, self.base + path, json=body, headers=headers, timeout=40, **kwargs)

    def order(self, items=None, key=None, flash=False):
        return self.call("POST", "/api/flash-sale/orders" if flash else "/api/orders",
                         {"items": items if items is not None else [{"product_id": 1, "quantity": 1}]},
                         key=key or uuid.uuid4().hex)


@pytest.fixture
def system(tmp_path):
    db_path = tmp_path / "test.db"
    server = create_server("127.0.0.1", 0, db_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Client(f"http://127.0.0.1:{server.server_port}"), db_path
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture
def user_factory(system):
    anonymous, _ = system

    def create():
        credentials = {"username": "u_" + uuid.uuid4().hex[:16], "password": "TestPass123!"}
        assert anonymous.call("POST", "/api/auth/register", credentials).status_code == 201
        response = anonymous.call("POST", "/api/auth/login", credentials)
        assert response.status_code == 200
        return Client(anonymous.base, response.json()["token"])

    return create


@pytest.fixture
def buyer(user_factory):
    return user_factory()


@pytest.fixture
def sql(system):
    _, path = system

    def execute(statement, parameters=()):
        conn = connect(path)
        try:
            cursor = conn.execute(statement, parameters)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    return execute
