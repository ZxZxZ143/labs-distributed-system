"""Read/write probe, independently sampled every 0.5 s; finite by default."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import threading
import time

import requests


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Probe:
    def __init__(self, base, record, output):
        self.base, self.record, self.output = base, record, output
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.rows = []
        self.phase = "baseline"

    def worker(self, operation):
        with requests.Session() as session:
            while not self.stop_event.is_set():
                started = time.perf_counter()
                row = dict(started_utc=utc(), phase=self.phase, operation=operation,
                           status=0, error="")
                try:
                    if operation == "write":
                        r = session.post(self.base + "/records", json={"text": "probe"}, timeout=6)
                    else:
                        r = session.get(self.base + "/records/" + self.record["id"], timeout=6)
                    row["status"] = r.status_code
                    if r.status_code == (201 if operation == "write" else 200):
                        data = r.json()
                        row["id"] = data["id"]
                        row["served_by"] = data["served_by"]
                        if operation == "read" and data["text"] != self.record["text"]:
                            row["error"] = "record content mismatch"
                    else:
                        row["error"] = r.text[:200]
                except (requests.RequestException, ValueError, KeyError) as exc:
                    row["error"] = str(exc)
                row["completed_utc"] = utc()
                row["latency_ms"] = (time.perf_counter() - started) * 1000
                with self.lock:
                    self.rows.append(row)
                    self.output.write(json.dumps(row) + "\n")
                    self.output.flush()
                self.stop_event.wait(max(0, 0.5 - (time.perf_counter() - started)))

    def start(self):
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.jobs = [self.pool.submit(self.worker, op) for op in ("read", "write")]

    def stop(self):
        self.stop_event.set()
        self.pool.shutdown(wait=True)
        for job in self.jobs:
            job.result()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:18080")
    parser.add_argument("--duration", type=float, default=60)
    args = parser.parse_args()
    r = requests.post(args.base + "/records", json={"text": "before failure"}, timeout=6)
    r.raise_for_status()
    import sys
    probe = Probe(args.base, r.json(), sys.stdout)
    probe.start()
    try:
        time.sleep(args.duration)
    finally:
        probe.stop()
