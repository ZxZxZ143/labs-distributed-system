# Laboratory Work 5 — NoSQL, Fault Tolerance and Load Balancing

**Specification version:** 4  
**Course:** Distributed & Cloud Computing (Fall 2026–2027)  
**Service:** Flask REST API behind nginx on `http://127.0.0.1:18080` (configurable `LAB5_PORT`)  
**Storage variant:** A-2 — RustFS (S3-compatible object storage)

## 1. Purpose and scope

Version 3 extends the Flask API from Laboratory Work 3 with external object storage and a replicated Redis counter. The existing `GET /time` and `POST /echo` behavior is retained. For Lab 4 the Flask service is started locally with `python app/app.py`, while RustFS, Redis primary, and Redis replica run in Docker Compose. The former Lab 3 Docker/Kubernetes manifests are historical artifacts and are not used for the Lab 4 experiments.

The Lab 2 asynchronous job/queue functionality is separate and is **not** part of this Lab 4 Flask API. This document specifies only the endpoints listed below.

Previous specifications did not assign `R` identifiers. Version 3 introduces stable identifiers for the retained endpoints (R1–R3) and the new Lab 4 requirements (R4 onward), to support traceability in Laboratory Work 5.

## 2. Architecture and configuration

| Component | Location | Purpose |
|---|---|---|
| Flask API (`app/app.py`) | Host, port `5000` | HTTP endpoints; no file storage on the service's disk |
| RustFS (`s3`) | Docker, host ports `9000` (S3) and `9001` (console) | Stores text-file objects in bucket `lab4-files` |
| Docker named volume (`s3-data`) | Docker-managed | Preserves RustFS objects across container recreation |
| Redis primary (`redis-primary`) | Docker, host port `16379`, internal port `6379` | Accepts counter writes and supports reads |
| Redis replica (`redis-replica`) | Docker, host port `16380`, internal port `6379` | Asynchronously replicates the primary and serves reads |

Flask uses environment variables rather than embedded node addresses or credentials:

| Variable | Lab 4 local value / default | Meaning |
|---|---|---|
| `BUCKET` | `lab4-files` | S3 bucket name |
| `S3_ENDPOINT` | `http://127.0.0.1:9000` | RustFS S3 endpoint; unset when using AWS S3 |
| `AWS_REGION` | `us-east-1` | S3 client region |
| `AWS_ACCESS_KEY_ID` | Set locally | RustFS training access key; never commit real credentials |
| `AWS_SECRET_ACCESS_KEY` | Set locally | RustFS training secret key; never commit real credentials |
| `REDIS_HOST` | `127.0.0.1` | Hostname for local Redis connections |
| `REDIS_PRIMARY_PORT` | `16379` | Host-exposed current primary port |
| `REDIS_REPLICA_PORT` | `16380` | Host-exposed replica port |

The Compose replica uses `--replicaof redis-primary 6379`: `6379` is the **internal Docker port** and is independent of the host mappings. Local training credentials may be configured in Compose; actual AWS credentials must never appear in code, screenshots, or the submission archive.

## 3. REST API contract (v3)

### 3.1 Existing endpoints (unchanged from v2)

| Method and path | Request | Success | Failure |
|---|---|---|---|
| `GET /time` | No body | `200`: `{"time":"YYYY-MM-DD HH:MM:SS","served_by":"<hostname>"}` | — |
| `POST /echo` | JSON containing `message` | `200`: `{"message":<original value>}` | `400`: `{"error":"field 'message' is required"}` if field is absent or JSON is invalid |

`/time` uses the server's local time. `served_by` is obtained from the operating-system hostname. The existing `/echo` code checks field presence and does not introduce new type or whitespace validation.

### 3.2 Object storage endpoints

| Method and path | Request | Success | Failure |
|---|---|---|---|
| `POST /files` | JSON object with string `content` | `201`: `{"file_id":"<uuid>","size_bytes":<integer>}` | `400` for invalid input or exceeded size; `503` if S3 is unavailable |
| `GET /files/{file_id}` | Canonical UUID path parameter | `200`: `{"file_id":"<uuid>","content":"<text>"}` | `400` for invalid UUID; `404` for missing object; `503` if S3 is unavailable |

**Object storage rules:**

- The file identifier is a newly generated UUID and is used to form the S3 object key `files/{file_id}.txt`.
- Only UTF-8 text is accepted. An empty text string is allowed.
- The maximum **encoded file content size** is `1,048,576` bytes (1 MiB). The limit is measured after UTF-8 encoding, not by character count.
- The HTTP request body limit is `2,097,152` bytes (2 MiB); exceeding it is mapped to an HTTP `400` JSON error by this implementation.
- Invalid JSON, missing/non-string `content`, and oversize content return `400` without writing an object.
- A well-formed but unknown UUID returns `404`. A malformed identifier returns `400`.
- S3 client/connection failures return `503`, not a fabricated successful write or read.
- Objects are never written to the Flask service container or working directory. RustFS uses the `s3-data` Docker named volume.

### 3.3 Redis counter endpoints (retained from Lab 4)

| Method and path | Request | Success | Failure |
|---|---|---|---|
| `POST /counter/increment` | No body required | `200`: `{"value":<integer>,"source":"primary"}` | `503` if the configured primary cannot be reached |
| `GET /counter?from=primary` | Optional source; `primary` is the default | `200`: `{"value":<integer>,"source":"primary"}` | `503` if the selected Redis node cannot be reached |
| `GET /counter?from=replica` | Read from the configured replica | `200`: `{"value":<integer>,"source":"replica"}` | `503` if the selected Redis node cannot be reached |

**Counter rules:**

- The Redis key is `counter`. If it is missing, a read returns integer `0`.
- Increment is atomic via Redis `INCR` and always targets the configured **primary**, never a replica.
- The API returns the selected source in the JSON response. A `from` value other than `primary` or `replica` returns `400` (target validation for the upcoming counter implementation).
- Redis connection/command errors return `{"error":"storage unavailable"}` with HTTP `503`.
- When the replica is detached, its read may return a value older than the primary's current value.
- Endpoint host and ports are configurable via environment variables; changing the current primary must not require editing source code.

## 4. Numbered, verifiable requirements

| ID | Requirement | Planned verification |
|---|---|---|
| **R1** | `GET /time` returns `200` with `time` and `served_by`. | HTTP GET response and field inspection |
| **R2** | Valid `POST /echo` returns `200` and the submitted `message`. | HTTP POST valid JSON |
| **R3** | Missing `message` or malformed JSON to `/echo` returns `400`. | HTTP POST invalid payloads |
| **R4** | `POST /files` stores UTF-8 content in RustFS and returns `201`, UUID and byte size. | Upload and inspect RustFS object |
| **R5** | `GET /files/{file_id}` retrieves the exact stored text and returns `200`. | GET with returned UUID |
| **R6** | A well-formed unknown file UUID returns `404`; invalid UUID returns `400`. | Negative HTTP GET tests |
| **R7** | Invalid file payloads and content greater than 1 MiB return `400`. | Missing/wrong-type content and boundary tests |
| **R8** | S3 failures return `503` rather than a successful response. | Stop/unreachable S3 and HTTP check |
| **R9** | Stored files remain readable after Flask restart and RustFS container recreation. | Reuse the same UUID before and after restarts |
| **R10** | Redis primary and replica are running and replication is established. | `INFO replication`: `connected_slaves:1`, `master_link_status:up` |
| **R11** | `POST /counter/increment` atomically increments on the primary and returns the new value. | Consecutive HTTP POST calls |
| **R12** | `GET /counter` supports primary/replica reads; default is primary; invalid source returns `400`. | HTTP GET with each `from` value |
| **R13** | A Redis access failure returns HTTP `503`. | Stop selected Redis node and call API |
| **R14** | Experiment E1 runs 100 increments and compares immediate reads from both nodes. | Script output with measured stale-read count |
| **R15** | Experiment E2 demonstrates stale reads while the replica is detached and eventual catch-up after restoration. | Redis commands, values and recovery-time log |
| **R16** | Experiment E3 compares primary and replica values immediately after each of three writes while detached. | Three pairs of recorded values |
| **R17** | Experiment E4 manually promotes the replica and redirects API writes after primary failure. | API checks and role information before/after failover |
| **R18** | The report explains the risk of two independent masters when the old primary returns and how it can be demoted to a replica. | `INFO replication` output and reflection answer |

## 5. Replication, consistency and failover assumptions

- Redis primary-to-replica replication is **asynchronous**. A response to `POST /counter/increment` confirms the primary's write; it does not prove that the replica has applied it.
- **Replication lag** is the difference between the primary's latest state and what the replica has applied. A read from the replica may be stale.
- **Eventual consistency** means the replica can converge to the primary's state after writes stop and a healthy replication link is restored. No fixed convergence time is guaranteed.
- E1 may yield `0` stale reads in a local environment because the replica catches up before the subsequent HTTP request.
- During E2 and E3, the replica remains readable after `REPLICAOF 127.0.0.1 1`, but no longer receives updates from the original primary. Restore it with `REPLICAOF redis-primary 6379` and measure catch-up time.
- During E4, stopping the primary should leave replica reads available, while writes directed at the stopped primary return `503`.
- Manual failover requires `REPLICAOF NO ONE` on the remaining replica, then restarting/reconfiguring Flask so `REDIS_PRIMARY_PORT=16380` points at the promoted node. Redis node host ports do **not** change when its role changes.
- On restart, the original `redis-primary` is still an independent master unless explicitly reconfigured. Two masters with divergent `counter` values may receive conflicting writes (split-brain). After recording the required evidence, it can be demoted with `REPLICAOF redis-replica 6379` (issued on the old primary container); verify the roles again. The former master's divergent data may be overwritten during synchronization.
- This lab uses **manual** failover, not Redis Sentinel or Redis Cluster automatic failover. MongoDB replica-set election in Lab 5 will be a separate comparison.
- The `source` field describes which configured API client handled a read. After E4, the old `replica` client may point to the promoted master unless the read configuration is adjusted; this is not evidence that a second read-only replica exists.

## 6. Evidence, tests and submission

Collect **observed**, not invented, measurements:

| Experiment / check | Evidence to retain |
|---|---|
| Part A upload/read | HTTP `201`, HTTP `200`, HTTP `404`, UUID reused after app/storage restarts; RustFS console screenshot |
| Replication setup | Both `INFO replication` outputs showing roles and link status |
| E1 | 100 writes, exact stale-read count and script output |
| E2 | Values before/during/after disconnection and measured recovery time |
| E3 | Three primary/replica read pairs following writes while replica is detached |
| E4 | Failed write (`503`), replica read, promotion, successful write, both masters' roles/values after old primary restarts |

Provide `app.py`, `requirements.txt`, `docker-compose.yml`, `spec.md` (this document), `logs/`, `screenshots/`, and a 1–2 page `report.pdf` in one archive named `Surname_FirstName_Lab4.zip`. In the development repository, Python sources are under `app/`; copy them to the **archive root** when packaging, as required by the submission format. Never include AWS access keys, virtual environments, or Docker volume data.

The report must contain the E1–E4 results table and answers to all four reflection questions: container storage vs. object storage; replication lag/eventual consistency; suitable/unsuitable replica reads; manual vs. automatic failover and old-primary return behavior.


## 7. Lab 5 extension (version 4, normative for this laboratory)

Sections 1–6 preserve the Lab 4 contract and R1–R18 for traceability; their host-run
architecture and manual Redis experiments are historical context. Lab 5 runs three
stateless API replicas (`api1`, `api2`, `api3`) behind nginx, plus MongoDB 7 nodes
`mongo1`, `mongo2`, `mongo3` in replica set `rs0`. Only nginx publishes a host port,
loopback `18080` by default (`LAB5_PORT=8080` may override it on a free port).
MongoDB volumes persist across container recreation; `down -v` intentionally erases
this lab's data. An idempotent one-shot initializer waits for an elected primary.
Legacy S3 and Redis services are retained under Compose profile `lab4`; API storage
clients are initialized lazily so Lab 5 needs neither AWS credentials nor Lab 4 services.
R4–R18 are not evaluated in Lab 5 and remain available with the legacy profile.

### 7.1 Record API

| Method/path | Input and types | Success | Errors |
|---|---|---|---|
| `POST /records` | JSON object, `text`: string, 0–65536 UTF-8 bytes | `201`: `id` canonical UUID string, `text` original string, `served_by` hostname string | `400` invalid JSON/object/type/size; `503` storage unavailable |
| `GET /records/{id}` | Canonical UUID string | `200`: `id`, `text`, `served_by` with the same types | `400` malformed ID; `404` unknown UUID; `503` storage unavailable |

Empty text is allowed. Validation happens before accessing MongoDB. Each create gets
a fresh UUID; MongoDB `_id` is not exposed. A failed/ambiguous POST is not blindly
replayed by nginx. Clients must not assume a 503 proves no write occurred.

Writes use `w=majority` and a 2000 ms write-concern timeout. Reads use the primary
and majority read concern. Driver retryable writes are disabled to expose the
failover interval in experiments; application operation timeout is 3500 ms,
server selection 1500 ms, connect 1000 ms and socket 2500 ms. All PyMongo errors
become JSON `503 {"error":"storage unavailable"}`. This bounds request duration;
it does not promise instantaneous responses or linearizability.

### 7.2 New numbered requirements

| ID | Requirement | Verification |
|---|---|---|
| R19 | Valid record creation returns 201, UUID, exact text and serving hostname; write acknowledged by a majority. | Round trip, driver configuration and failover reads |
| R20 | Reading an acknowledged record through nginx returns 200 and exact content. | Create/read through independent requests |
| R21 | Invalid record JSON, non-object payload, missing/non-string text returns 400. | Automated negative cases |
| R22 | Empty text and exactly 65536 UTF-8 bytes are accepted; 65537+ bytes are rejected with 400. | Boundary and multibyte cases |
| R23 | Malformed record ID returns 400; unknown valid UUID returns 404. | Negative reads |
| R24 | Database access errors return JSON 503 within 5 seconds locally. | Failure probes for reads and writes; isolated driver-error tests |
| R25 | Three MongoDB nodes reach one PRIMARY and two SECONDARY states. | rs.status capture before and after failures |
| R26 | At least two of the three API hostnames answer 30 requests through nginx. | Distribution script |
| R27 | While api2 is stopped for about 20 seconds, reads and writes continue with no failed probes; api2 never answers the stopped-window distribution. After restart all replicas become available. | Timestamped read/write probe and distributions |
| R28 | After stopping the actual MongoDB primary, successful reads/writes resume within 30 seconds; previously acknowledged records survive. A temporary 503 interval is allowed and measured. | Dynamic primary detection, timeline and integrity checks |
| R29 | At 10, 50 and 100 concurrent users for 60 seconds each, target p95 <= 500 ms, errors <= 1%, throughput >= 2 requests/s per user. | Mixed 3:1 time/create workload, raw per-request CSV, measured p50/p95/RPS |
| R30 | Failure experiments record UTC timestamps, stop interval, first error, error counts by operation, recovery time, and reads/writes during and after failure; stopped resources are restarted even on test failure. | Repeatable bounded scripts and JSON summaries |

### 7.3 Assumptions, decisions and risks

1. Local Docker Engine with Compose v2, at least 8 GiB RAM and a free loopback port.
   Shared host workloads affect timings: observed performance is not a production SLA.
2. A majority (2/3) remains connected during primary failure. MongoDB elections can
   pause primary reads and writes; majority acknowledgement prioritizes consistency
   and prevents minority writes. Node-stop experiments illustrate election behavior,
   not a complete simulation of an arbitrary network partition (CAP applies under partition).
3. This is a trusted local educational network without MongoDB authentication or TLS.
   MongoDB/API ports are never host-published. Deployment outside this host requires
   authentication, TLS and network controls.
4. A 3:1 GET /time to POST /records workload with 0.1–0.5 second think time is a closed
   workload; increasing users may not saturate the server. Report saturation only if measured.
5. nginx uses passive failure detection (`max_fails=1`, `fail_timeout=5s`) and retries
   connection errors/timeouts/502 on remaining upstreams. `non_idempotent` retries are
   not enabled. Container stop/start retains the address; after container recreation
   restart nginx to refresh upstream DNS resolution.
6. Student/group metadata must be confirmed rather than invented. Git-configured
   identity is recorded as the technical author; missing academic metadata is explicit.
