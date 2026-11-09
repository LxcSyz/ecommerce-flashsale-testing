"""Run with: python -m app.server --port 8000 --db data/tradelab.db"""
import argparse
import json
import logging
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from app import service
from app.db import initialize

STATIC = Path(__file__).parent / "static"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logging.info("%s %s", self.address_string(), format % args)

    def respond(self, status, body, content_type="application/json; charset=utf-8"):
        data = json.dumps(body, ensure_ascii=False).encode() if content_type.startswith("application/json") else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 65536:
                raise service.APIError(413, "BODY_TOO_LARGE", "请求体过大")
            body = json.loads(self.rfile.read(length)) if length else {}
        except (ValueError, UnicodeDecodeError):
            raise service.APIError(400, "INVALID_JSON", "JSON 格式错误")
        if not isinstance(body, dict):
            raise service.APIError(422, "INVALID_ARGUMENT", "请求体必须为对象")
        return body

    def handle_request(self):
        try:
            path = urlsplit(self.path).path
            method = self.command
            db = self.server.db_path
            if method == "GET" and path in ("/", "/app.js", "/style.css"):
                filename, mime = {"/": ("index.html", "text/html; charset=utf-8"),
                    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/style.css": ("style.css", "text/css; charset=utf-8")}[path]
                return self.respond(200, (STATIC / filename).read_bytes(), mime)
            if method == "GET" and path == "/api/health":
                return self.respond(200, {"status": "ok", "service": "TradeLab"})
            if method == "GET" and path == "/api/products":
                return self.respond(200, service.products(db))
            if method == "POST" and path in ("/api/auth/register", "/api/auth/login"):
                body = self.read_body()
                result = service.register(db, body) if path.endswith("register") else service.login(db, body)
                return self.respond(201 if path.endswith("register") else 200, result)
            if not path.startswith("/api/"):
                raise service.APIError(404, "NOT_FOUND", "路径不存在")
            user = service.authenticate(db, self.headers.get("Authorization", ""))
            if method == "GET" and path == "/api/me":
                return self.respond(200, user)
            if path == "/api/cart" and method in ("GET", "POST"):
                return self.respond(200, service.cart(db, user["id"], self.read_body() if method == "POST" else None))
            match = re.fullmatch(r"/api/cart/(\d+)", path)
            if method == "DELETE" and match:
                return self.respond(200, service.cart(db, user["id"], delete_id=int(match[1])))
            if method == "POST" and path in ("/api/orders", "/api/flash-sale/orders"):
                order = service.create_order(db, user["id"], self.read_body(), self.headers.get("Idempotency-Key", ""),
                                             "flash" if "flash-sale" in path else "regular")
                return self.respond(201, order)
            if method == "GET" and path == "/api/orders":
                return self.respond(200, service.orders(db, user["id"]))
            match = re.fullmatch(r"/api/orders/(\d+)(?:/(pay|cancel))?", path)
            if match and ((method == "GET" and not match[2]) or (method == "POST" and match[2])):
                return self.respond(200, service.orders(db, user["id"], int(match[1]), match[2]))
            raise service.APIError(404, "NOT_FOUND", "路径不存在")
        except service.APIError as exc:
            self.respond(exc.status, {"error": {"code": exc.code, "message": exc.message}})
        except sqlite3.OperationalError:
            logging.exception("Database unavailable")
            self.respond(503, {"error": {"code": "DATABASE_BUSY", "message": "服务繁忙，请稍后重试"}})
        except Exception:
            logging.exception("Unhandled request error")
            self.respond(500, {"error": {"code": "INTERNAL_ERROR", "message": "服务内部错误"}})

    do_GET = handle_request
    do_POST = handle_request
    do_DELETE = handle_request


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128


def create_server(host, port, db_path):
    initialize(db_path)
    server = Server((host, port), Handler)
    server.db_path = str(db_path)
    return server


def main():
    parser = argparse.ArgumentParser(description="TradeLab 本地测试靶场")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="data/tradelab.db")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    server = create_server(args.host, args.port, args.db)
    print(f"TradeLab: http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
