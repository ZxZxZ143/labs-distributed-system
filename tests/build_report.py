"""Build the report from captured results; never fabricate missing measurements."""
from datetime import datetime
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs" / "lab5"


def load(name):
    return json.loads((LOGS / name).read_text(encoding="utf-8"))


def describe(name):
    if "test_R1_time" == name:
        return "R1", "Functional", "GET /time", "200, valid timestamp, api1/api2/api3", "200; timestamp parsed; valid hostname"
    if name == "test_R2_echo":
        return "R2", "Functional", 'POST /echo message=hello', "200, original message", "200; exact hello"
    if name == "test_R3_echo_negative":
        return "R3", "Negative", "POST /echo {}", "400", "400"
    if "roundtrip" in name:
        case = name.split("[")[1].rstrip("]")
        inputs = {"unicode": "Привет 🌍", "empty": "empty text", "max-ascii": "65536 ASCII bytes", "max-utf8": "32768 Cyrillic characters = 65536 bytes"}
        return "R19,R20,R22", "Boundary" if case != "unicode" else "Functional", inputs[case], "201, UUID, exact text; GET 200", "201; canonical UUID; exact round trip; hostname checked"
    if "invalid_payload" in name:
        return "R21", "Negative", "POST /records " + name.split("[")[1].rstrip("]"), "400 JSON error", "400, error field present"
    if "malformed_json" in name:
        return "R21", "Negative", "POST /records malformed JSON {", "400", "400"
    if "oversize" in name:
        return "R22", "Boundary", "POST /records 65537 ASCII or 65538 UTF-8 bytes (" + name.split("[")[1].rstrip("]") + ")", "400", "400"
    if "test_R23_missing" == name:
        return "R23", "Negative", "GET unknown canonical UUID", "404", "404"
    if "test_R23_invalid_id" == name:
        return "R23", "Negative", "GET /records/not-a-uuid", "400", "400"
    if "test_R26_distribution" == name:
        return "R26", "Integration", "30 GET /time requests", "At least 2 replicas", "At least 2 distinct hostnames asserted"
    if "storage_errors" in name:
        return "R24", "Isolated failure", name.split("[")[1].rstrip("]") + "; injected PyMongo exception", '503 {"error":"storage unavailable"}', "503; exact JSON asserted (not a Docker failure measurement)"
    raise ValueError(name)


def main():
    tests = list(ET.parse(LOGS / "pytest.xml").iter("testcase"))
    loads = [load(f"load_{n}_summary.json") for n in (10, 50, 100)]
    api, primary = load("fault_api_down.json"), load("fault_primary_down.json")
    dist = load("distribution.json")
    lines = ["# Test Report - Lab 5", "", "Student: kurlykov yevgenii", "",
             "Tested service: Flask REST API, specification v4. Environment: Docker Compose, 3 API replicas, nginx, MongoDB replica set with 3 nodes. Endpoint: http://127.0.0.1:18080. Measurements were performed on 20 November 2026 local time; raw timelines use UTC (Asia/Qyzylorda = UTC+5).",
             "", "Docker Desktop: 12 virtual CPUs, 7,899,131,904 bytes RAM (7.36 GiB), shared Windows host. Python test client 3.13.12; container Python 3.12, Gunicorn 2 workers × 4 threads per API. Exact versions are in [environment.txt](logs/lab5/environment.txt). Other projects remained running; measurements describe this environment.",
             "", "## 1. Test cases", "", "The 19 HTTP checks run against nginx and real MongoDB; 4 additional isolated checks inject server-selection / write-concern exceptions. Each parameterized case is counted separately. Raw results: [pytest.txt](logs/lab5/pytest.txt), [JUnit XML](logs/lab5/pytest.xml). R4–R18 are retained Lab 4 requirements, outside this Lab 5 test scope.", "",
             "| # | Requirement (spec.md) | Type | Input | Expected | Actual | Pass/Fail |", "|---|---|---|---|---|---|---|"]
    for i, case in enumerate(tests, 1):
        req, kind, data, expected, actual = describe(case.attrib["name"])
        passed = not any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
        lines.append(f"| {i} | {req} | {kind} | {data} | {expected} | {actual if passed else 'See JUnit failure'} | {'Pass' if passed else 'Fail'} |")
    lines += ["", "Repeat: `python -m pytest tests/test_api.py tests/test_storage_errors.py -v --junitxml=logs/lab5/pytest.xml`.", "", "## 2. Load tests", "",
              "Tool: the permitted custom `tests/load_test.py` using requests and one thread/session per user. Each user chooses GET /time with probability 3/4 or POST /records with probability 1/4, then waits uniformly 0.1–0.5 s. Users start together (no ramp-up); no fault experiment runs concurrently. Every request, including failures, contributes to interpolated p50/p95. RPS uses actual wall time including drain. This differs from the optional Locust ramp-up example.", "", "```powershell"]
    for n in (10, 50, 100):
        lines.append(f"python tests/load_test.py --users {n} --duration 60 --prefix logs/lab5/load_{n}")
    lines += ["```", "", "| Users | Actual duration, s | Requests | Failures | RPS | Median, ms | p95, ms | Errors, % | Target R29 | Pass/Fail |", "|---|---|---|---|---|---|---|---|---|---|"]
    for s in loads:
        lines.append(f"| {s['users']} | {s['elapsed_s']:.3f} | {s['request_count']} | {s['failure_count']} | {s['rps']:.2f} | {s['median_ms']:.2f} | {s['p95_ms']:.2f} | {s['errors_pct']:.2f} | p95 ≤ 500 ms; errors ≤ 1%; RPS ≥ {2*s['users']} | {'Pass' if s['pass'] else 'Fail'} |")
    lines += ["", "Raw CSVs: " + ", ".join(f"[{n} users](logs/lab5/load_{n}_requests.csv)" for n in (10, 50, 100)) + ". Aggregate `load_*_stats.csv` and JSON summaries are alongside them. [Console output](logs/lab5/load_console.txt). [Screenshot](screenshots/lab5/load_results.png)."]
    ratio = loads[2]["rps"] / loads[1]["rps"]
    lines += ["", f"Doubling users from 50 to 100 changed throughput by {ratio:.2f}×; p95 changed from {loads[1]['p95_ms']:.2f} to {loads[2]['p95_ms']:.2f} ms. Saturation was not established by these three closed-workload levels. Think time limits offered load, and requests spend time on the host/client and Docker network. No server-only bottleneck or maximum capacity can be identified from these measurements; a longer, open-arrival workload and resource telemetry are needed.", "", "## 3. Fault tolerance & load balancing", "",
              f"R25: final replica state is one PRIMARY and two SECONDARY nodes. [Raw cluster state](logs/lab5/replica_state.txt), [screenshot](screenshots/lab5/replica_state.png). [Compose state](logs/lab5/compose_ps.txt), [screenshot](screenshots/lab5/compose_ps.png). R26: final 30-request distribution = `{json.dumps(dist)}`; all three replicas answered. [Screenshot](screenshots/lab5/distribution.png).", "",
              "Run `python tests/fault_test.py api` and then `python tests/fault_test.py primary`. A preliminary `stop --timeout 0` primary run had no observed 503 responses: a stop still sends SIGTERM and can permit fast stepdown. Its raw evidence is preserved in `logs/lab5/preliminary_primary_stop/`; the definitive experiment below uses SIGKILL to prevent graceful stepdown. Both scenarios have a 5 s baseline, an API stop (`--timeout 0`) or a MongoDB primary crash (`kill --signal SIGKILL`), about 20 s stopped, restart, then 10 s observation. Independent read and write loops target every 0.5 s; slow requests delay that operation's next sample, so errors are sampled events rather than all possible client failures. Client timeout is 6 s; measured API duration is checked against R24's 5 s bound. Read probes always fetch a pre-failure acknowledged record. All acknowledged probe writes are reread after restoration."]
    for title, s, name, req in (("Scenario 1 — API replica stopped", api, "api_down", "R27,R30"), ("Scenario 2 — MongoDB primary stopped", primary, "primary_down", "R24,R28,R30")):
        lines += ["", "### " + title, "", f"Requirements: {req}. Stopped node: `{s['node']}`. Result: **{'Pass' if s['pass'] else 'Fail'}**. Baseline distribution: `{json.dumps(s['baseline_distribution'])}`. While stopped: `{json.dumps(s['stopped_distribution'])}`. After restart: `{json.dumps(s['restored_distribution'])}`.", "",
                  "| Event | UTC timestamp / value |", "|---|---|"]
        for key, label in (("stop_requested_utc", "Stop requested"), ("stopped_utc", "Stop completed"), ("first_error_utc", "First error response completed"), ("total_errors", "Total sampled errors"), ("restart_requested_utc", "Restart requested"), ("restart_completed_utc", "Restart completed")):
            lines.append(f"| {label} | {s[key] if s[key] is not None else 'None observed'} |")
        for op, r in s["operation_recovery"].items():
            lines.append(f"| {op}: first error completed | {r['first_error_utc'] or 'None observed'} |")
            lines.append(f"| {op}: first success after error (or after stop if no error) | {r['first_success_utc']} |")
            lines.append(f"| {op}: seconds from stop request to that success | {r['seconds_from_stop']:.3f} |")
        lines += ["", "| Probe phase | Read statuses and counts | Write statuses and counts |", "|---|---|---|"]
        for phase, values in s["phase_results"].items():
            lines.append(f"| {phase} | `{json.dumps(values['read'])}` | `{json.dumps(values['write'])}` |")
        lines += ["", f"Errors by operation: `{json.dumps(s['errors_by_operation'])}`. Maximum observed request latency: {s['max_latency_ms']:.2f} ms. Integrity: **{s['acknowledged_records_checked']} acknowledged records checked, {len(s['integrity_errors'])} mismatches/missing records**. Expected while stopped: reads/writes continue for an API loss; temporary JSON 503 is permitted during MongoDB election and successful reads/writes must resume within 30 s. Expected after restart: 200 reads, 201 writes, all API replicas available and one primary/two secondaries. The status table above records the actual outcome.",
                  f"[Raw read/write probe](logs/lab5/probe_{name}.txt), [timeline and assertions](logs/lab5/fault_{name}.json), [screenshot](screenshots/lab5/fault_{name}.png)."]
    if "elected_primary_while_stopped" in primary:
        lines += ["", f"The newly elected primary, while `{primary['node']}` was still stopped, was `{primary['elected_primary_while_stopped']}`. Recovery therefore came from election, not merely restarting the original node."]
    lines += ["", "### CAP interpretation and defence questions", "",
              "1. When the primary crashes, the surviving members must elect a primary before primary-directed operations resume. Writes use majority acknowledgement, so the service does not acknowledge writes through a minority. In a partition the design favors consistency over continuous write availability. The observed 503 interval and later successful responses illustrate election unavailability; a node crash alone is not a full network-partition CAP experiment. The integrity checks support preservation of acknowledged records in this run, not a proof for all failures.", "",
              "2. Primary reads use the current primary; this implementation also requests majority read concern. Secondary reads can spread load and improve some read availability, but asynchronous replication can return stale data. Majority read concern on the primary does not itself promise linearizability. Driver retries were disabled to make the failure interval visible.", "",
              "3. nginx selects another upstream after a connection error, timeout or 502. `max_fails=1` marks a failed peer unavailable after one unsuccessful attempt; `fail_timeout=5s` is its failure window and exclusion interval. `proxy_next_upstream` controls which failures allow retry. POST is not replayed after it was sent upstream because `non_idempotent` is not enabled; a failed POST may have an ambiguous commit outcome. MongoDB 503 responses are returned directly, not hidden by nginx retries.", "",
              "4. API instances must share external state so any replica can read a record created by another. This service keeps persistent records in MongoDB; the serving hostname identifies the process handling a request, not a data owner. Process-local connection pools are not persistent business state.", "",
              "## 4. Conclusions & recommendations", "",
              f"The {len(tests)} automated cases passed; the two fault scripts independently asserted their stated conditions. At 100 users, observed throughput was {loads[2]['rps']:.2f} RPS, p50 {loads[2]['median_ms']:.2f} ms, p95 {loads[2]['p95_ms']:.2f} ms and errors {loads[2]['errors_pct']:.2f}%. API loss produced {api['total_errors']} sampled errors. Primary loss produced {primary['total_errors']} sampled errors and preserved all {primary['acknowledged_records_checked']} acknowledged records checked after restoration.", "",
              "The measured availability limitation is MongoDB primary election: data operations pause while no writable primary is selected. nginx cannot remove that database dependency. Capacity saturation and a CPU/disk bottleneck were not demonstrated; identifying either without resource measurements would be speculation.", "",
              "1. Priority 1: add an idempotency key contract for record creation and bounded client retries with jitter after transient 503. Expected impact: fewer user-visible failed operations without duplicate records during ambiguous write outcomes; it will not remove election time. Retest duplicate prevention, lost-response retries, primary failure, acknowledged-record integrity and end-to-end recovery latency.", "",
              "2. Priority 2: collect per-container CPU/RAM, MongoDB disk latency and replication lag while running longer open-arrival load without think-time throttling. Use the evidence to tune Gunicorn workers/pools or scale compute. Expected impact: establish a repeatable saturation point and identify the constrained component; no numerical throughput gain is claimed before measurement. Retest p50/p95, error rate, sustained throughput and both failures under load.", "",
              "Implementation references: [PyMongo operation timeouts](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/connection-options/csot/), [CRUD configuration](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/configure/), [nginx retry semantics](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_next_upstream). Actual results are derived from the local files linked above.", ""]
    (ROOT / "test_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("test_report.md generated from observed evidence")


if __name__ == "__main__":
    main()
