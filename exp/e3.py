
import subprocess
import time

import requests

BASE = "http://127.0.0.1:5000"
session = requests.Session()


def redis_cli(*args):
    cmd = [
        "docker", "compose", "exec", "-T",
        "redis-replica", "redis-cli", *args
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        check=True, timeout=10
    )
    return result.stdout.strip()


def replication_info():
    output = redis_cli("INFO", "replication")
    return dict(
        line.split(":", 1)
        for line in output.splitlines()
        if ":" in line and not line.startswith("#")
    )


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


def wait_for_sync(timeout=30):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        info = replication_info()

        if (
            info.get("master_link_status") == "up"
            and info.get("master_sync_in_progress", "0") == "0"
            and read_counter("primary")
            == read_counter("replica")
        ):
            return True

        time.sleep(0.2)

    return False


def main():
    print("=== E3: Reading Your Own Write ===")

    if not wait_for_sync():
        raise RuntimeError(
            "Replica is not synchronized before E3"
        )

    initial = read_counter("primary")
    print(f"Initial counter: {initial}")

    detached = False

    try:
        # Disconnect replication
        print("\nDisconnecting replica...")
        detached = True
        print(redis_cli(
            "REPLICAOF", "127.0.0.1", "1"
        ))

        # Wait until link is down
        deadline = time.monotonic() + 10

        while time.monotonic() < deadline:
            if (
                replication_info().get(
                    "master_link_status"
                ) == "down"
            ):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError(
                "Replica did not disconnect"
            )

        print("Replica link: DOWN")
        print("\nWrite | Primary | Replica | RYW")
        print("-" * 43)

        stale_count = 0

        # Three writes, followed by immediate reads
        for i in range(1, 4):
            written = increment()
            primary = read_counter("primary")
            replica = read_counter("replica")

            if primary != written:
                raise RuntimeError(
                    "Primary value differs from write"
                )

            stale = replica != written
            stale_count += int(stale)

            print(
                f"{i:5} | {primary:7} | "
                f"{replica:7} | "
                f"{'NOT on replica' if stale else 'YES'}",
                flush=True
            )

        print("\n=== E3 RESULTS ===")
        print("Primary read-your-writes: YES")
        print(
            f"Replica stale reads: {stale_count}/3"
        )
        print(
            f"Expected primary value: {initial + 3}"
        )
        print(
            f"Final primary value: "
            f"{read_counter('primary')}"
        )

    finally:
        if detached:
            print("\nRestoring replication...")
            print(redis_cli(
                "REPLICAOF", "redis-primary", "6379"
            ))

            synchronized = wait_for_sync()

            print(f"Recovered: {synchronized}")

            if synchronized:
                print(
                    "Final primary: "
                    f"{read_counter('primary')}"
                )
                print(
                    "Final replica: "
                    f"{read_counter('replica')}"
                )
            else:
                raise RuntimeError(
                    "Replica failed to synchronize"
                )


if __name__ == "__main__":
    main()
