# Test Report - Lab 5

Student: kurlykov yevgenii

Tested service: Flask REST API, specification v4. Environment: Docker Compose, 3 API replicas, nginx, MongoDB replica set with 3 nodes. Endpoint: http://127.0.0.1:18080. Measurements were performed on 20 November 2026 local time; raw timelines use UTC (Asia/Qyzylorda = UTC+5).

Docker Desktop: 12 virtual CPUs, 7,899,131,904 bytes RAM (7.36 GiB), shared Windows host. Python test client 3.13.12; container Python 3.12, Gunicorn 2 workers × 4 threads per API. Exact versions are in [environment.txt](logs/lab5/environment.txt). Other projects remained running; measurements describe this environment.

## 1. Test cases

The 19 HTTP checks run against nginx and real MongoDB; 4 additional isolated checks inject server-selection / write-concern exceptions. Each parameterized case is counted separately. Raw results: [pytest.txt](logs/lab5/pytest.txt), [JUnit XML](logs/lab5/pytest.xml). R4–R18 are retained Lab 4 requirements, outside this Lab 5 test scope.

| # | Requirement (spec.md) | Type | Input | Expected | Actual | Pass/Fail |
|---|---|---|---|---|---|---|
| 1 | R1 | Functional | GET /time | 200, valid timestamp, api1/api2/api3 | 200; timestamp parsed; valid hostname | Pass |
| 2 | R2 | Functional | POST /echo message=hello | 200, original message | 200; exact hello | Pass |
| 3 | R3 | Negative | POST /echo {} | 400 | 400 | Pass |
| 4 | R19,R20,R22 | Functional | Привет 🌍 | 201, UUID, exact text; GET 200 | 201; canonical UUID; exact round trip; hostname checked | Pass |
| 5 | R19,R20,R22 | Boundary | empty text | 201, UUID, exact text; GET 200 | 201; canonical UUID; exact round trip; hostname checked | Pass |
| 6 | R19,R20,R22 | Boundary | 65536 ASCII bytes | 201, UUID, exact text; GET 200 | 201; canonical UUID; exact round trip; hostname checked | Pass |
| 7 | R19,R20,R22 | Boundary | 32768 Cyrillic characters = 65536 bytes | 201, UUID, exact text; GET 200 | 201; canonical UUID; exact round trip; hostname checked | Pass |
| 8 | R21 | Negative | POST /records missing | 400 JSON error | 400, error field present | Pass |
| 9 | R21 | Negative | POST /records null | 400 JSON error | 400, error field present | Pass |
| 10 | R21 | Negative | POST /records number | 400 JSON error | 400, error field present | Pass |
| 11 | R21 | Negative | POST /records array | 400 JSON error | 400, error field present | Pass |
| 12 | R21 | Negative | POST /records string | 400 JSON error | 400, error field present | Pass |
| 13 | R21 | Negative | POST /records list-value | 400 JSON error | 400, error field present | Pass |
| 14 | R21 | Negative | POST /records malformed JSON { | 400 | 400 | Pass |
| 15 | R22 | Boundary | POST /records 65537 ASCII or 65538 UTF-8 bytes (ascii) | 400 | 400 | Pass |
| 16 | R22 | Boundary | POST /records 65537 ASCII or 65538 UTF-8 bytes (utf8) | 400 | 400 | Pass |
| 17 | R23 | Negative | GET unknown canonical UUID | 404 | 404 | Pass |
| 18 | R23 | Negative | GET /records/not-a-uuid | 400 | 400 | Pass |
| 19 | R26 | Integration | 30 GET /time requests | At least 2 replicas | At least 2 distinct hostnames asserted | Pass |
| 20 | R24 | Isolated failure | get-error0; injected PyMongo exception | 503 {"error":"storage unavailable"} | 503; exact JSON asserted (not a Docker failure measurement) | Pass |
| 21 | R24 | Isolated failure | get-error1; injected PyMongo exception | 503 {"error":"storage unavailable"} | 503; exact JSON asserted (not a Docker failure measurement) | Pass |
| 22 | R24 | Isolated failure | post-error0; injected PyMongo exception | 503 {"error":"storage unavailable"} | 503; exact JSON asserted (not a Docker failure measurement) | Pass |
| 23 | R24 | Isolated failure | post-error1; injected PyMongo exception | 503 {"error":"storage unavailable"} | 503; exact JSON asserted (not a Docker failure measurement) | Pass |

Repeat: `python -m pytest tests/test_api.py tests/test_storage_errors.py -v --junitxml=logs/lab5/pytest.xml`.

## 2. Load tests

Tool: the permitted custom `tests/load_test.py` using requests and one thread/session per user. Each user chooses GET /time with probability 3/4 or POST /records with probability 1/4, then waits uniformly 0.1–0.5 s. Users start together (no ramp-up); no fault experiment runs concurrently. Every request, including failures, contributes to interpolated p50/p95. RPS uses actual wall time including drain. This differs from the optional Locust ramp-up example.

```powershell
python tests/load_test.py --users 10 --duration 60 --prefix logs/lab5/load_10
python tests/load_test.py --users 50 --duration 60 --prefix logs/lab5/load_50
python tests/load_test.py --users 100 --duration 60 --prefix logs/lab5/load_100
```

| Users | Actual duration, s | Requests | Failures | RPS | Median, ms | p95, ms | Errors, % | Target R29 | Pass/Fail |
|---|---|---|---|---|---|---|---|---|---|
| 10 | 60.007 | 1923 | 0 | 32.05 | 6.27 | 26.84 | 0.00 | p95 ≤ 500 ms; errors ≤ 1%; RPS ≥ 20 | Pass |
| 50 | 60.024 | 9580 | 0 | 159.60 | 7.77 | 34.97 | 0.00 | p95 ≤ 500 ms; errors ≤ 1%; RPS ≥ 100 | Pass |
| 100 | 60.054 | 18536 | 0 | 308.66 | 13.03 | 80.10 | 0.00 | p95 ≤ 500 ms; errors ≤ 1%; RPS ≥ 200 | Pass |

Raw CSVs: [10 users](logs/lab5/load_10_requests.csv), [50 users](logs/lab5/load_50_requests.csv), [100 users](logs/lab5/load_100_requests.csv). Aggregate `load_*_stats.csv` and JSON summaries are alongside them. [Console output](logs/lab5/load_console.txt). [Screenshot](screenshots/lab5/load_results.png).

Doubling users from 50 to 100 changed throughput by 1.93×; p95 changed from 34.97 to 80.10 ms. Saturation was not established by these three closed-workload levels. Think time limits offered load, and requests spend time on the host/client and Docker network. No server-only bottleneck or maximum capacity can be identified from these measurements; a longer, open-arrival workload and resource telemetry are needed.

## 3. Fault tolerance & load balancing

R25: final replica state is one PRIMARY and two SECONDARY nodes. [Raw cluster state](logs/lab5/replica_state.txt), [screenshot](screenshots/lab5/replica_state.png). [Compose state](logs/lab5/compose_ps.txt), [screenshot](screenshots/lab5/compose_ps.png). R26: final 30-request distribution = `{"api3": 10, "api2": 10, "api1": 10}`; all three replicas answered. [Screenshot](screenshots/lab5/distribution.png).

Run `python tests/fault_test.py api` and then `python tests/fault_test.py primary`. A preliminary `stop --timeout 0` primary run had no observed 503 responses: a stop still sends SIGTERM and can permit fast stepdown. Its raw evidence is preserved in `logs/lab5/preliminary_primary_stop/`; the definitive experiment below uses SIGKILL to prevent graceful stepdown. Both scenarios have a 5 s baseline, an API stop (`--timeout 0`) or a MongoDB primary crash (`kill --signal SIGKILL`), about 20 s stopped, restart, then 10 s observation. Independent read and write loops target every 0.5 s; slow requests delay that operation's next sample, so errors are sampled events rather than all possible client failures. Client timeout is 6 s; measured API duration is checked against R24's 5 s bound. Read probes always fetch a pre-failure acknowledged record. All acknowledged probe writes are reread after restoration.

### Scenario 1 — API replica stopped

Requirements: R27,R30. Stopped node: `api2`. Result: **Pass**. Baseline distribution: `{"api2": 10, "api3": 10, "api1": 10}`. While stopped: `{"api1": 15, "api3": 15}`. After restart: `{"api3": 10, "api2": 10, "api1": 10}`.

| Event | UTC timestamp / value |
|---|---|
| Stop requested | 2026-11-20T16:32:33.240+00:00 |
| Stop completed | 2026-11-20T16:32:35.502+00:00 |
| First error response completed | None observed |
| Total sampled errors | 0 |
| Restart requested | 2026-11-20T16:32:55.810+00:00 |
| Restart completed | 2026-11-20T16:33:02.068+00:00 |
| read: first error completed | None observed |
| read: first success after error (or after stop if no error) | 2026-11-20T16:32:33.319+00:00 |
| read: seconds from stop request to that success | 0.079 |
| write: first error completed | None observed |
| write: first success after error (or after stop if no error) | 2026-11-20T16:32:33.354+00:00 |
| write: seconds from stop request to that success | 0.114 |

| Probe phase | Read statuses and counts | Write statuses and counts |
|---|---|---|
| baseline | `{"200": 10}` | `{"201": 10}` |
| stopping | `{"200": 5}` | `{"201": 5}` |
| stopped | `{"200": 40}` | `{"201": 37}` |
| restarting | `{"200": 12}` | `{"201": 12}` |
| restored | `{"200": 20}` | `{"201": 20}` |

Errors by operation: `{}`. Maximum observed request latency: 1030.04 ms. Integrity: **85 acknowledged records checked, 0 mismatches/missing records**. Expected while stopped: reads/writes continue for an API loss; temporary JSON 503 is permitted during MongoDB election and successful reads/writes must resume within 30 s. Expected after restart: 200 reads, 201 writes, all API replicas available and one primary/two secondaries. The status table above records the actual outcome.
[Raw read/write probe](logs/lab5/probe_api_down.txt), [timeline and assertions](logs/lab5/fault_api_down.json), [screenshot](screenshots/lab5/fault_api_down.png).

### Scenario 2 — MongoDB primary stopped

Requirements: R24,R28,R30. Stopped node: `mongo2`. Result: **Pass**. Baseline distribution: `{"api3": 10, "api2": 10, "api1": 10}`. While stopped: `{"api2": 10, "api1": 10, "api3": 10}`. After restart: `{"api1": 10, "api3": 10, "api2": 10}`.

| Event | UTC timestamp / value |
|---|---|
| Stop requested | 2026-11-20T16:35:06.057+00:00 |
| Stop completed | 2026-11-20T16:35:06.857+00:00 |
| First error response completed | 2026-11-20T16:35:10.136+00:00 |
| Total sampled errors | 6 |
| Restart requested | 2026-11-20T16:35:28.402+00:00 |
| Restart completed | 2026-11-20T16:35:29.500+00:00 |
| read: first error completed | 2026-11-20T16:35:10.136+00:00 |
| read: first success after error (or after stop if no error) | 2026-11-20T16:35:18.203+00:00 |
| read: seconds from stop request to that success | 12.146 |
| write: first error completed | 2026-11-20T16:35:10.539+00:00 |
| write: first success after error (or after stop if no error) | 2026-11-20T16:35:18.208+00:00 |
| write: seconds from stop request to that success | 12.151 |

| Probe phase | Read statuses and counts | Write statuses and counts |
|---|---|---|
| baseline | `{"200": 10}` | `{"201": 10}` |
| stopping | `{"200": 1, "503": 1}` | `{"201": 1, "503": 1}` |
| stopped | `{"503": 2, "200": 22}` | `{"503": 2, "201": 22}` |
| restarting | `{"200": 2}` | `{"201": 2}` |
| restored | `{"200": 20}` | `{"201": 19}` |

Errors by operation: `{"read": 3, "write": 3}`. Maximum observed request latency: 3909.15 ms. Integrity: **55 acknowledged records checked, 0 mismatches/missing records**. Expected while stopped: reads/writes continue for an API loss; temporary JSON 503 is permitted during MongoDB election and successful reads/writes must resume within 30 s. Expected after restart: 200 reads, 201 writes, all API replicas available and one primary/two secondaries. The status table above records the actual outcome.
[Raw read/write probe](logs/lab5/probe_primary_down.txt), [timeline and assertions](logs/lab5/fault_primary_down.json), [screenshot](screenshots/lab5/fault_primary_down.png).

The newly elected primary, while `mongo2` was still stopped, was `mongo1:27017`. Recovery therefore came from election, not merely restarting the original node.

### CAP interpretation and defence questions

1. When the primary crashes, the surviving members must elect a primary before primary-directed operations resume. Writes use majority acknowledgement, so the service does not acknowledge writes through a minority. In a partition the design favors consistency over continuous write availability. The observed 503 interval and later successful responses illustrate election unavailability; a node crash alone is not a full network-partition CAP experiment. The integrity checks support preservation of acknowledged records in this run, not a proof for all failures.

2. Primary reads use the current primary; this implementation also requests majority read concern. Secondary reads can spread load and improve some read availability, but asynchronous replication can return stale data. Majority read concern on the primary does not itself promise linearizability. Driver retries were disabled to make the failure interval visible.

3. nginx selects another upstream after a connection error, timeout or 502. `max_fails=1` marks a failed peer unavailable after one unsuccessful attempt; `fail_timeout=5s` is its failure window and exclusion interval. `proxy_next_upstream` controls which failures allow retry. POST is not replayed after it was sent upstream because `non_idempotent` is not enabled; a failed POST may have an ambiguous commit outcome. MongoDB 503 responses are returned directly, not hidden by nginx retries.

4. API instances must share external state so any replica can read a record created by another. This service keeps persistent records in MongoDB; the serving hostname identifies the process handling a request, not a data owner. Process-local connection pools are not persistent business state.

## 4. Conclusions & recommendations

The 23 automated cases passed; the two fault scripts independently asserted their stated conditions. At 100 users, observed throughput was 308.66 RPS, p50 13.03 ms, p95 80.10 ms and errors 0.00%. API loss produced 0 sampled errors. Primary loss produced 6 sampled errors and preserved all 55 acknowledged records checked after restoration.

The measured availability limitation is MongoDB primary election: data operations pause while no writable primary is selected. nginx cannot remove that database dependency. Capacity saturation and a CPU/disk bottleneck were not demonstrated; identifying either without resource measurements would be speculation.

1. Priority 1: add an idempotency key contract for record creation and bounded client retries with jitter after transient 503. Expected impact: fewer user-visible failed operations without duplicate records during ambiguous write outcomes; it will not remove election time. Retest duplicate prevention, lost-response retries, primary failure, acknowledged-record integrity and end-to-end recovery latency.

2. Priority 2: collect per-container CPU/RAM, MongoDB disk latency and replication lag while running longer open-arrival load without think-time throttling. Use the evidence to tune Gunicorn workers/pools or scale compute. Expected impact: establish a repeatable saturation point and identify the constrained component; no numerical throughput gain is claimed before measurement. Retest p50/p95, error rate, sustained throughput and both failures under load.

Implementation references: [PyMongo operation timeouts](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/connection-options/csot/), [CRUD configuration](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/configure/), [nginx retry semantics](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_next_upstream). Actual results are derived from the local files linked above.
