"""Bounded closed-workload load test with raw latency for EVERY request."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import threading
import time

import requests


def percentile(values, p):
    values = sorted(values)
    position = (len(values) - 1) * p
    left = int(position)
    right = min(left + 1, len(values) - 1)
    return values[left] + (values[right] - values[left]) * (position - left)


def run(base, users, duration, prefix):
    barrier = threading.Barrier(users + 1)
    timing = {}

    def user(index):
        rng = random.Random(2026 + index)
        rows = []
        with requests.Session() as session:
            barrier.wait()
            while time.perf_counter() < timing["deadline"]:
                path = "/time" if rng.randrange(4) else "/records"
                started = time.perf_counter()
                timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                error, status = "", 0
                try:
                    r = session.get(base + path, timeout=6) if path == "/time" else session.post(base + path, json={"text": "load"}, timeout=6)
                    status = r.status_code
                    if status != (200 if path == "/time" else 201):
                        error = r.text[:200]
                except requests.RequestException as exc:
                    error = str(exc)
                rows.append([timestamp, index, path, status, (time.perf_counter() - started) * 1000, error])
                remaining = timing["deadline"] - time.perf_counter()
                if remaining > 0:
                    time.sleep(min(rng.uniform(0.1, 0.5), remaining))
        return rows

    with ThreadPoolExecutor(max_workers=users) as pool:
        futures = [pool.submit(user, index) for index in range(users)]
        timing["start"] = time.perf_counter()
        timing["deadline"] = timing["start"] + duration
        barrier.wait()
        rows = [row for future in futures for row in future.result()]
    elapsed = time.perf_counter() - timing["start"]
    rows.sort(key=lambda r: r[0])
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with Path(str(prefix) + "_requests.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_utc", "user", "path", "status", "latency_ms", "error"])
        writer.writerows(rows)
    latencies = [r[4] for r in rows]
    failures = sum(bool(r[5]) for r in rows)
    summary = dict(users=users, requested_duration_s=duration, elapsed_s=elapsed,
                   request_count=len(rows), failure_count=failures,
                   median_ms=percentile(latencies, .5), p95_ms=percentile(latencies, .95),
                   rps=len(rows) / elapsed, errors_pct=failures * 100 / len(rows),
                   workload="3:1 GET /time : POST /records; think time uniform 0.1-0.5 s")
    summary["pass"] = summary["p95_ms"] <= 500 and summary["errors_pct"] <= 1 and summary["rps"] >= 2 * users
    Path(str(prefix) + "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with Path(str(prefix) + "_stats.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Users", "Duration", "Request Count", "Failure Count", "Median Response Time", "95%", "Requests/s"])
        writer.writerow([users, elapsed, len(rows), failures, summary["median_ms"], summary["p95_ms"], summary["rps"]])
    print(json.dumps(summary, indent=2), flush=True)
    return summary["pass"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:18080")
    parser.add_argument("--users", type=int, required=True)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    if args.users < 1 or args.duration <= 0:
        parser.error("users and duration must be positive")
    raise SystemExit(0 if run(args.base, args.users, args.duration, args.prefix) else 1)
