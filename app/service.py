import hashlib
import hmac
import json
import secrets
import time

from app.db import connect, transaction


class APIError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def positive_int(value, name, maximum=100):
    if type(value) is not int or not 1 <= value <= maximum:
        raise APIError(422, "INVALID_ARGUMENT", f"{name} 必须是 1 到 {maximum} 的整数")
    return value


def credentials(body):
    username, password = body.get("username"), body.get("password")
    if not isinstance(username, str) or not 3 <= len(username.strip()) <= 32:
        raise APIError(422, "INVALID_ARGUMENT", "用户名长度为 3 到 32")
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise APIError(422, "INVALID_ARGUMENT", "密码长度为 8 到 128")
    return username.strip(), password


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return salt + ":" + digest


def register(path, body):
    import sqlite3
    username, password = credentials(body)
    encoded = password_hash(password)
    try:
        with transaction(path) as conn:
            cursor = conn.execute("INSERT INTO users(username, password_hash) VALUES (?, ?)", (username, encoded))
            return {"id": cursor.lastrowid, "username": username}
    except sqlite3.IntegrityError:
        raise APIError(409, "USERNAME_EXISTS", "用户名已存在")


def login(path, body):
    username, password = credentials(body)
    conn = connect(path)
    try:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()
    # Run the KDF even if the user does not exist.
    stored = user["password_hash"] if user else "0" * 32 + ":" + "0" * 64
    if not hmac.compare_digest(password_hash(password, stored.split(":")[0]), stored) or not user:
        raise APIError(401, "INVALID_CREDENTIALS", "用户名或密码错误")
    token = secrets.token_urlsafe(32)
    with transaction(path) as conn:
        conn.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token, user["id"], time.time() + 3600))
    return {"token": token, "expires_in": 3600, "username": username}


def authenticate(path, authorization):
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    conn = connect(path)
    try:
        user = conn.execute(
            "SELECT u.id, u.username FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ?", (token, time.time()),
        ).fetchone()
    finally:
        conn.close()
    if not user:
        raise APIError(401, "UNAUTHORIZED", "请先登录，或重新登录")
    return dict(user)


def products(path):
    conn = connect(path)
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM products ORDER BY id")]
    finally:
        conn.close()


def cart(path, user_id, body=None, delete_id=None):
    with transaction(path) as conn:
        if body is not None:
            pid = positive_int(body.get("product_id"), "product_id", 1000000)
            quantity = positive_int(body.get("quantity"), "quantity")
            product = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
            if not product:
                raise APIError(404, "PRODUCT_NOT_FOUND", "商品不存在")
            if product["kind"] != "regular":
                raise APIError(409, "FLASH_ONLY", "秒杀商品请使用秒杀入口")
            if quantity > product["stock"]:
                raise APIError(409, "OUT_OF_STOCK", "库存不足")
            # Set quantity, rather than increment: retries are harmless.
            conn.execute("INSERT INTO cart VALUES (?, ?, ?) ON CONFLICT(user_id, product_id) "
                         "DO UPDATE SET quantity = excluded.quantity", (user_id, pid, quantity))
        if delete_id is not None:
            conn.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, delete_id))
        rows = conn.execute("SELECT p.id AS product_id, p.name, p.price_cents, c.quantity "
                            "FROM cart c JOIN products p ON c.product_id = p.id WHERE user_id = ? "
                            "ORDER BY p.id", (user_id,))
        return [dict(row) for row in rows]


def normalize_items(body, kind):
    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise APIError(422, "INVALID_ARGUMENT", "items 必须包含 1 到 20 个商品")
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise APIError(422, "INVALID_ARGUMENT", "商品项必须是对象")
        normalized.append((positive_int(item.get("product_id"), "product_id", 1000000),
                           positive_int(item.get("quantity"), "quantity")))
    if len({pid for pid, _ in normalized}) != len(normalized):
        raise APIError(422, "DUPLICATE_PRODUCT", "商品不能重复")
    if kind == "flash" and (len(normalized) != 1 or normalized[0][1] != 1):
        raise APIError(422, "FLASH_LIMIT", "秒杀每次只能抢购一件")
    return sorted(normalized)


def serialize_order(conn, order_id):
    order = dict(conn.execute("SELECT id, user_id, status, total_cents, kind, created_at "
                              "FROM orders WHERE id = ?", (order_id,)).fetchone())
    order["items"] = [dict(row) for row in conn.execute(
        "SELECT product_id, quantity, price_cents FROM order_items WHERE order_id = ? ORDER BY product_id", (order_id,))]
    return order


def create_order(path, user_id, body, key, kind="regular"):
    if not key or len(key) > 128:
        raise APIError(422, "IDEMPOTENCY_KEY_REQUIRED", "需要 1 到 128 位 Idempotency-Key 请求头")
    items = normalize_items(body, kind)
    fingerprint = json.dumps([kind, items], separators=(",", ":"))
    with transaction(path) as conn:
        existing = conn.execute("SELECT id, fingerprint FROM orders WHERE user_id = ? AND idempotency_key = ?",
                                (user_id, key)).fetchone()
        if existing:
            if existing["fingerprint"] != fingerprint:
                raise APIError(409, "IDEMPOTENCY_CONFLICT", "相同幂等键不能用于不同请求")
            return serialize_order(conn, existing["id"])
        total = 0
        priced = []
        for pid, quantity in items:
            product = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
            if not product:
                raise APIError(404, "PRODUCT_NOT_FOUND", "商品不存在")
            if product["kind"] != kind:
                raise APIError(409, "WRONG_CHANNEL", "商品与下单入口不匹配")
            if kind == "flash":
                now = time.time()
                if now < product["starts_at"] or now >= product["ends_at"]:
                    raise APIError(409, "SALE_INACTIVE", "秒杀活动尚未开始或已结束")
                purchased = conn.execute("SELECT COALESCE(SUM(i.quantity), 0) FROM order_items i "
                    "JOIN orders o ON o.id = i.order_id WHERE o.user_id = ? AND i.product_id = ? "
                    "AND o.status IN ('pending', 'paid')", (user_id, pid)).fetchone()[0]
                if purchased >= 1:
                    raise APIError(409, "PURCHASE_LIMIT", "每位用户限购一件")
            updated = conn.execute("UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                                   (quantity, pid, quantity))
            if updated.rowcount != 1:
                raise APIError(409, "OUT_OF_STOCK", "库存不足")
            total += quantity * product["price_cents"]
            priced.append((pid, quantity, product["price_cents"]))
        cursor = conn.execute("INSERT INTO orders(user_id, status, total_cents, kind, idempotency_key, "
                              "fingerprint, created_at) VALUES (?, 'pending', ?, ?, ?, ?, ?)",
                              (user_id, total, kind, key, fingerprint, time.time()))
        order_id = cursor.lastrowid
        conn.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?)",
                         [(order_id, pid, qty, price) for pid, qty, price in priced])
        if kind == "regular":
            conn.executemany("DELETE FROM cart WHERE user_id = ? AND product_id = ?",
                             [(user_id, pid) for pid, _ in items])
        return serialize_order(conn, order_id)


def orders(path, user_id, order_id=None, action=None):
    with transaction(path) as conn:
        if order_id is None:
            ids = conn.execute("SELECT id FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
            return [serialize_order(conn, row["id"]) for row in ids]
        row = conn.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id)).fetchone()
        if not row:
            raise APIError(404, "ORDER_NOT_FOUND", "订单不存在")
        if action:
            target = "paid" if action == "pay" else "cancelled"
            if row["status"] != target:
                if row["status"] != "pending":
                    raise APIError(409, "INVALID_ORDER_STATE", "当前订单状态不允许此操作")
                conn.execute("UPDATE orders SET status = ? WHERE id = ? AND status = 'pending'", (target, order_id))
                if target == "cancelled":
                    for item in conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall():
                        conn.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (item["quantity"], item["product_id"]))
        return serialize_order(conn, order_id)
