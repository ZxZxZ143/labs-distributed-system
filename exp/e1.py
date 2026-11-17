
import os
import time

import requests

BASE = os.getenv("LAB4_API_URL", "http://127.0.0.1:5000")
TOTAL = 100

session = requests.Session()


def get_value(method, endpoint):
    response = session.request(
        method,
        f"{BASE}{endpoint}",
        timeout=5,
    )
    response.raise_for_status()
    return response.json()["value"]


def main():
    stale_reads = 0
    start = time.perf_counter()

    print("Experiment E1 — Normal Replication")
    print(f"Iterations: {TOTAL}")
    print("-" * 55)
    print("Step | Written | Primary | Replica | Result")

    for i in range(1, TOTAL + 1):
        written = get_value("POST", "/counter/increment")

        primary = get_value(
            "GET", "/counter?from=primary"
        )
        replica = get_value(
            "GET", "/counter?from=replica"
        )

        if primary != written:
            raise RuntimeError(
                "Primary changed unexpectedly. "
                "Check for concurrent writers."
            )

        is_stale = replica != primary

        if is_stale:
            stale_reads += 1

        result = "STALE" if is_stale else "OK"

        print(
            f"{i:4} | {written:7} | "
            f"{primary:7} | {replica:7} | {result}"
        )

    duration = time.perf_counter() - start

    print("-" * 55)
    print(f"Stale reads: {stale_reads} out of {TOTAL}")
    print(f"Stale read rate: {stale_reads / TOTAL * 100:.1f}%")
    print(f"Total duration: {duration:.3f} seconds")


if __name__ == "__main__":
    main()
