
import subprocess
import time

import requests

BASE = "http://127.0.0.1:5000"
WRITES = 10
TIMEOUT = 30

session = requests.Session()


def redis_cli(*args):
    cmd = [
        "docker", "compose", "exec", "-T",
        "redis-replica", "redis-cli", *args
    ]

    print("$", " ".join(cmd), flush=True)

    result = subprocess.run(
        cmd, capture_output=True, text=True
    )

    if result.stdout.strip():
        print(result.stdout.strip())

    if result.stderr.strip():
        print(result.stderr.strip())

    result.check_returncode()
    return result.stdout


def read_counter(source):
    response = session.get(
        f"{BASE}/counter",
        params={"from": source},
        timeout=5
    )
    response.raise_for_status()
    return response.json()["value"]


def increment():
    response = session.post(
        f"{BASE}/counter/increment",
        timeout=5
    )
    response.raise_for_status()
    return response.json()["value"]


def main():
    print("=== E2: Replication Lag ===", flush=True)

    # 1. Check initial synchronization
    info = redis_cli("INFO", "replication")

    if "master_link_status:up" not in info:
        raise RuntimeError("Replica is not connected")

    for _ in range(30):
        before_primary = read_counter("primary")
        before_replica = read_counter("replica")

        if before_primary == before_replica:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Replica not synchronized")

    print(
        f"BEFORE: primary={before_primary}, "
        f"replica={before_replica}"
    )

    detached = False

    try:
        # 2. Disconnect replica
        print("\n=== Disconnecting replica ===")
        redis_cli("REPLICAOF", "127.0.0.1", "1")
        detached = True

        redis_cli("INFO", "replication")

        # 3. Perform 10 writes
        print("\n=== Performing 10 writes ===")

        for i in range(1, WRITES + 1):
            value = increment()
            print(f"Write {i}: {value}")

        # 4. Read both nodes
        stale_primary = read_counter("primary")
        stale_replica = read_counter("replica")

        print("\n=== DISCONNECTED STATE ===")
        print(f"Primary: {stale_primary}")
        print(f"Replica: {stale_replica}")
        print(f"Difference: {stale_primary - stale_replica}")

        if stale_primary == stale_replica:
            print("WARNING: No stale value observed")

    finally:
        # 5. Always attempt restoration
        if detached:
            print("\n=== Restoring replication ===")

            start = time.perf_counter()

            redis_cli(
                "REPLICAOF", "redis-primary", "6379"
            )

            recovered = False

            while time.perf_counter() - start < TIMEOUT:
                current_primary = read_counter("primary")
                current_replica = read_counter("replica")

                if current_primary == current_replica:
                    info = redis_cli("INFO", "replication")

                    if (
                        "master_link_status:up" in info
                        and "master_sync_in_progress:0" in info
                    ):
                        recovered = True
                        break

                time.sleep(0.1)

            elapsed = time.perf_counter() - start

            print("\n=== RECOVERY RESULT ===")
            print(f"Recovered: {recovered}")
            print(f"Primary: {current_primary}")
            print(f"Replica: {current_replica}")
            print(f"Recovery time: {elapsed:.3f} seconds")

            if not recovered:
                raise RuntimeError(
                    "Replica did not recover within timeout"
                )


if __name__ == "__main__":
    main()
