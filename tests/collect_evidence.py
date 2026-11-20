"""Capture real CLI output and construct local pages for evidence screenshots."""
import argparse
import os
from collections import Counter
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import platform
import subprocess

import requests

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs" / "lab5"
SHOTS = ROOT / "screenshots" / "lab5"


def command(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True, timeout=60).stdout


def page(name, title, text):
    body = "<!doctype html><meta charset='utf-8'><title>" + html.escape(title) + "</title>"
    body += "<style>body{background:#101820;color:#e9f0f5;margin:32px;font:17px Consolas,monospace}h1{font:26px Arial;color:#9bd6ff}pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.45}small{color:#adbdcc}</style>"
    body += "<h1>" + html.escape(title) + "</h1><small>Lab 5 | kurlykov yevgenii | captured CLI / experiment results</small><pre>" + html.escape(text) + "</pre>"
    (SHOTS / (name + ".html")).write_text(body, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("BASE_URL", "http://127.0.0.1:18080"))
    args = parser.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    state = command("docker", "compose", "exec", "-T", "mongo1", "mongosh", "--quiet", "--eval", "rs.status().members.map(m => m.name + ' ' + m.stateStr)")
    ps = command("docker", "compose", "ps")
    hosts = Counter(requests.get(args.base + "/time", timeout=6).json()["served_by"] for _ in range(30))
    environment = timestamp + "\n" + platform.platform() + "\n" + command("docker", "version") + command("docker", "info", "--format", "CPUs={{.NCPU}} Memory={{.MemTotal}} OS={{.OperatingSystem}}")
    environment += "\nContainer packages:\n" + command("docker", "compose", "exec", "-T", "api1", "pip", "freeze")
    for filename, content in (("replica_state.txt", state), ("compose_ps.txt", ps), ("environment.txt", environment), ("distribution.json", json.dumps(hosts, indent=2))):
        (LOGS / filename).write_text(content, encoding="utf-8")
    page("replica_state", "MongoDB replica set state", timestamp + "\n$ docker compose exec -T mongo1 mongosh --quiet --eval rs.status().members...\n" + state)
    page("compose_ps", "Docker Compose services", timestamp + "\n$ docker compose ps\n" + ps)
    page("distribution", "30 requests through nginx", timestamp + "\nGET " + args.base + "/time\n" + json.dumps(hosts, indent=2))
    summaries = [json.loads((LOGS / f"load_{n}_summary.json").read_text()) for n in (10, 50, 100)]
    load = "users | requests | errors | RPS | p50 ms | p95 ms | result\n"
    for s in summaries:
        load += f"{s['users']:5} | {s['request_count']:8} | {s['failure_count']:6} | {s['rps']:6.2f} | {s['median_ms']:6.2f} | {s['p95_ms']:6.2f} | {'PASS' if s['pass'] else 'FAIL'}\n"
    load += "\nSource: logs/lab5/load_*_summary.json\nDuration: 60 seconds each; custom load_test.py; raw request CSV retained."
    page("load_results", "Measured load test results", load)
    for scenario in ("api_down", "primary_down"):
        result = json.loads((LOGS / ("fault_" + scenario + ".json")).read_text())
        text = "Node: " + result["node"] + "\nStop requested UTC: " + result["stop_requested_utc"]
        text += "\nErrors: " + str(result["total_errors"]) + "\nRead / write recovery:\n" + json.dumps(result["operation_recovery"], indent=2)
        text += "\nAcknowledged records verified: " + str(result["acknowledged_records_checked"])
        text += "\nIntegrity errors: " + str(len(result["integrity_errors"]))
        text += "\nPassed: " + str(result["pass"])
        page("fault_" + scenario, "Failure evidence: " + scenario, text)
    print(state, ps, json.dumps(hosts), load)
