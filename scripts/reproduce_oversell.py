"""Controlled race experiment in a TEMP database, never the application database."""
import argparse
import json
import platform
import sqlite3
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


def experiment(fixed, buyers=24, initial=10):
    with tempfile.TemporaryDirectory(prefix="tradelab-race-") as directory:
        path = str(Path(directory) / "lab.db")
        conn = sqlite3.connect(path)
        # Deliberately no CHECK constraint in this isolated defective specimen.
        conn.execute("CREATE TABLE inventory(stock INTEGER)")
        conn.execute("INSERT INTO inventory VALUES (?)", (initial,))
        conn.execute("CREATE TABLE reservations(id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        start = threading.Barrier(buyers)
        read_gate = threading.Barrier(buyers)

        def buy(_):
            db = sqlite3.connect(path, timeout=30, isolation_level=None)
            try:
                start.wait(timeout=20)
                if fixed:
                    db.execute("BEGIN IMMEDIATE")
                    success = db.execute("UPDATE inventory SET stock = stock - 1 WHERE stock > 0").rowcount == 1
                else:
                    available = db.execute("SELECT stock FROM inventory").fetchone()[0]
                    # Force all buyers to see the same pre-deduction snapshot.
                    read_gate.wait(timeout=20)
                    db.execute("BEGIN IMMEDIATE")
                    success = available > 0
                    if success:
                        db.execute("UPDATE inventory SET stock = stock - 1")
                if success:
                    db.execute("INSERT INTO reservations DEFAULT VALUES")
                db.commit()
                return success
            finally:
                db.close()

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=buyers) as executor:
            successes = sum(executor.map(buy, range(buyers)))
        elapsed = time.perf_counter() - started
        conn = sqlite3.connect(path)
        remaining = conn.execute("SELECT stock FROM inventory").fetchone()[0]
        reserved = conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
        conn.close()
        return {"buyers": buyers, "initial_stock": initial, "successful_reservations": successes,
                "remaining_stock": remaining, "reservation_rows": reserved,
                "oversold_units": max(0, successes - initial), "elapsed_seconds": round(elapsed, 4)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/defect-replay.json")
    args = parser.parse_args()
    result = {"recorded_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "platform": platform.platform(), "note": "Controlled isolated specimen; not a production benchmark",
              "defective": experiment(False), "fixed": experiment(True)}
    assert result["defective"]["oversold_units"] == 14
    assert result["fixed"]["successful_reservations"] == 10
    assert result["fixed"]["remaining_stock"] == 0
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
