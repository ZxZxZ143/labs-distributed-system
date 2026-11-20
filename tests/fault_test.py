"""Stop one LAB5 service, measure read/write behavior and always restart it."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import subprocess
import time

import requests
from probe import Probe, utc

ROOT = Path(__file__).resolve().parents[1]


def compose(*args):
    return subprocess.run(["docker", "compose", "-p", "lab5", *args], cwd=ROOT,
                          text=True, capture_output=True, check=True, timeout=120).stdout.strip()


def distribution(base):
    counts = Counter()
    for _ in range(30):
        r = requests.get(base + "/time", timeout=6)
        r.raise_for_status()
        counts[r.json()["served_by"]] += 1
    return dict(counts)


def cluster_state():
    raw = compose("exec", "-T", "mongo1", "mongosh", "--quiet", "--eval",
                  "JSON.stringify(rs.status().members.map(m => ({name:m.name,state:m.stateStr})))")
    return json.loads(raw)


def seconds(a, b):
    return (datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds()


def run(base, scenario):
    logs = ROOT / "logs" / "lab5"
    logs.mkdir(parents=True, exist_ok=True)
    name = "api_down" if scenario == "api" else "primary_down"
    before = distribution(base)
    record_response = requests.post(base + "/records", json={"text": "acknowledged before " + name}, timeout=6)
    record_response.raise_for_status()
    record = record_response.json()
    node = "api2"
    if scenario == "primary":
        raw = compose("exec", "-T", "mongo1", "mongosh", "--quiet", "--eval", "db.hello().primary")
        node = raw.strip().split(":")[0]
        if node not in {"mongo1", "mongo2", "mongo3"}:
            raise RuntimeError("Unexpected primary: " + raw)
    events = dict(scenario=scenario, node=node, baseline_distribution=before,
                  record_before_failure=record, command="docker compose -p lab5 stop --timeout 0 " + node)
    with (logs / ("probe_" + name + ".txt")).open("w", encoding="utf-8") as output:
        probe = Probe(base, record, output)
        probe.start()
        stopped = False
        try:
            time.sleep(5)
            probe.phase = "stopping"
            events["stop_requested_utc"] = utc()
            stopped = True  # set before command so errors still trigger restoration
            compose("stop", "--timeout", "0", node)
            events["stopped_utc"] = utc()
            probe.phase = "stopped"
            events["stopped_distribution"] = distribution(base)
            time.sleep(20)
            if scenario == "primary":
                survivor = next(n for n in ("mongo1", "mongo2", "mongo3") if n != node)
                events["elected_primary_while_stopped"] = compose("exec", "-T", survivor, "mongosh", "--quiet", "--eval", "db.hello().primary")
            probe.phase = "restarting"
            events["restart_requested_utc"] = utc()
            compose("start", node)
            stopped = False
            events["restart_completed_utc"] = utc()
            probe.phase = "restored"
            time.sleep(10)
        finally:
            try:
                if stopped:
                    compose("start", node)
            finally:
                probe.stop()
    events["restored_distribution"] = distribution(base)
    rows = probe.rows
    failures = [r for r in rows if r["error"]]
    post_stop = [r for r in rows if r["started_utc"] >= events["stop_requested_utc"]]
    events["errors_by_operation"] = dict(Counter(r["operation"] for r in failures))
    events["total_errors"] = len(failures)
    events["first_error_utc"] = min((r["completed_utc"] for r in failures), default=None)
    events["max_latency_ms"] = max(r["latency_ms"] for r in rows)
    events["operation_recovery"] = {}
    for op in ("read", "write"):
        op_errors = [r for r in failures if r["operation"] == op]
        first_error = min((r["completed_utc"] for r in op_errors), default=None)
        recovered = [r for r in post_stop if r["operation"] == op and not r["error"] and (first_error is None or r["started_utc"] > first_error)]
        first_ok = min((r["completed_utc"] for r in recovered), default=None)
        events["operation_recovery"][op] = dict(first_error_utc=first_error, first_success_utc=first_ok,
                                                 seconds_from_stop=seconds(first_ok, events["stop_requested_utc"]) if first_ok else None)
    events["phase_results"] = {}
    for phase in ("baseline", "stopping", "stopped", "restarting", "restored"):
        events["phase_results"][phase] = {op: dict(Counter(str(r["status"]) for r in rows if r["phase"] == phase and r["operation"] == op)) for op in ("read", "write")}
    # Verify EVERY acknowledged probe write, plus the pre-failure record.
    expected = {record["id"]: record["text"]}
    expected.update({r["id"]: "probe" for r in rows if r["operation"] == "write" and not r["error"]})
    integrity_errors = []
    for record_id, text in expected.items():
        r = requests.get(base + "/records/" + record_id, timeout=6)
        if r.status_code != 200 or r.json().get("text") != text:
            integrity_errors.append(record_id)
    events["acknowledged_records_checked"] = len(expected)
    events["integrity_errors"] = integrity_errors
    events["final_cluster_state"] = cluster_state()
    recovered_ok = all(v["seconds_from_stop"] is not None and v["seconds_from_stop"] <= 30 for v in events["operation_recovery"].values())
    restored_ok = all(events["phase_results"]["restored"][op] and set(events["phase_results"]["restored"][op]) == {str(code)} for op, code in (("read", 200), ("write", 201)))
    stopped_ok = all(events["phase_results"]["stopped"][op].get(str(code), 0) > 0 for op, code in (("read", 200), ("write", 201)))
    cluster_ok = Counter(m["state"] for m in events["final_cluster_state"]) == Counter({"PRIMARY": 1, "SECONDARY": 2})
    events["pass"] = (not integrity_errors and recovered_ok and restored_ok and stopped_ok
                      and events["max_latency_ms"] < 5000 and cluster_ok
                      and set(events["restored_distribution"]) == {"api1", "api2", "api3"}
                      and all(r["status"] == 503 and json.loads(r["error"]) == {"error": "storage unavailable"} for r in failures))
    if scenario == "api":
        events["pass"] = events["pass"] and not failures and "api2" not in events["stopped_distribution"]
    (logs / ("fault_" + name + ".json")).write_text(json.dumps(events, indent=2), encoding="utf-8")
    print(json.dumps(events, indent=2))
    return events["pass"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=["api", "primary"])
    parser.add_argument("--base", default="http://127.0.0.1:18080")
    args = parser.parse_args()
    raise SystemExit(0 if run(args.base, args.scenario) else 1)
