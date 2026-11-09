"""Read-only invariant check against an existing application database."""
import argparse
import json
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/tradelab.db")
    args = parser.parse_args()
    uri = Path(args.db).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT p.id, p.name, p.initial_stock, p.stock, COALESCE(SUM(CASE WHEN "
                            "o.status IN ('pending', 'paid') THEN i.quantity ELSE 0 END), 0) AS reserved "
                            "FROM products p LEFT JOIN order_items i ON i.product_id = p.id "
                            "LEFT JOIN orders o ON o.id = i.order_id GROUP BY p.id").fetchall()
        results = [{**dict(row), "consistent": row["stock"] >= 0 and row["stock"] + row["reserved"] == row["initial_stock"]} for row in rows]
        print(json.dumps(results, ensure_ascii=False, indent=2))
        if not all(row["consistent"] for row in results):
            raise SystemExit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
