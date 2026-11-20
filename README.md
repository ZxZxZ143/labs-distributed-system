# Laboratory Work 5 — NoSQL, Fault Tolerance and Load Balancing

Student: kurlykov yevgenii

Three stateless Flask API replicas run behind nginx. MongoDB 7 stores records in a
three-node replica set with majority write acknowledgement and automatic primary
election. The specification is [spec.md](spec.md), version 4; measured results and
answers to the defence questions are in [test_report.md](test_report.md).

## Requirements and launch

Docker Engine + Compose v2, Python 3.12 or 3.13, at least 8 GiB RAM and a free
loopback port `18080`. The submission was measured on a shared Windows host with
Docker Desktop (12 virtual CPUs, 7.36 GiB available to Docker).

```powershell
docker compose up -d --build --wait --wait-timeout 180
docker compose ps
docker compose exec -T mongo1 mongosh --quiet --eval "rs.status().members.map(m => m.name + ' ' + m.stateStr)"
Invoke-RestMethod http://127.0.0.1:18080/time
```

Compose automatically initializes `rs0` through `mongo-init` and waits for primary
election. The init script is safe to run again:

```powershell
docker compose exec -T mongo1 mongosh --quiet /scripts/init-replica.js
```

Only nginx publishes a port. MongoDB requires no local training password and is not
published to the host. Default port `18080` avoids another project on `8080`.
To use the assignment's example port instead: set `$env:LAB5_PORT='8080'` before
starting Compose and `$env:BASE_URL='http://127.0.0.1:8080'` before pytest; pass
`--base http://127.0.0.1:8080` to other scripts.

## Tests and repeatable experiments

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r app/requirements.txt -r requirements-test.txt
New-Item -ItemType Directory -Force logs/lab5
.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_storage_errors.py -v --junitxml=logs/lab5/pytest.xml
.venv\Scripts\python.exe tests/load_test.py --users 10 --duration 60 --prefix logs/lab5/load_10
.venv\Scripts\python.exe tests/load_test.py --users 50 --duration 60 --prefix logs/lab5/load_50
.venv\Scripts\python.exe tests/load_test.py --users 100 --duration 60 --prefix logs/lab5/load_100
.venv\Scripts\python.exe tests/fault_test.py api
.venv\Scripts\python.exe tests/fault_test.py primary
.venv\Scripts\python.exe tests/collect_evidence.py
```

On Linux/macOS use `.venv/bin/python` instead. Run these commands **sequentially**;
load and failure experiments must not overlap. Fault tests only operate on Compose
project `lab5`, detect the actual primary, stop the selected node immediately with
`--timeout 0`, sample independent reads and writes, keep it stopped for about 20 s,
and restore it in `finally`. The immediate stop models a crash rather than graceful
primary stepdown. Every acknowledged probe write is reread after restoration.
The scripts return a nonzero status when their specified checks fail.

`tests/probe.py --duration 60` is also available as a standalone finite read/write
probe (one request per operation every 0.5 s, or as soon as the previous request
completes). `tests/locustfile.py` provides an optional equivalent Locust workload;
the submitted load evidence uses `load_test.py`, explicitly permitted by the lab.
The latter logs every latency and computes interpolated p50/p95, wall-clock RPS
including request drain, failure count and percentage. The load starts all users
together; it does not use Locust's ramp-up.

Thirty-request distribution:

```powershell
1..30 | ForEach-Object { (Invoke-RestMethod http://127.0.0.1:18080/time).served_by } | Group-Object | Select-Object Name, Count
```

## Files and evidence

- `docker-compose.yml`, `init-replica.js`, `nginx.conf`: the Lab 5 stack.
- `app/`: API, image definition and dependencies; `/time` and `/echo` are retained.
- `tests/`: functional, error, load and failure checks, evidence and archive helpers.
- `logs/lab5/`: raw request CSVs, summaries, probe JSONL, JUnit and environment output.
- `screenshots/lab5/`: screenshots of captured experiment evidence; see report links.
- `test_report.md`: requirement traceability, actual numbers, timelines, CAP and recommendations.

Existing `logs/E*.txt`, root screenshots, `exp/`, `k8s/` and queue examples are
historical Labs 2–4 artifacts and are excluded from the Lab 5 archive.
`docker-compose.lab4.yml` preserves the previous standalone Lab 4 configuration.
Lab 4 storage endpoints remain in the API; optional `--profile lab4` enables S3
and Redis dependencies internally. They are outside the Lab 5 test scope. Use
`docker compose -p pythonproject4 -f docker-compose.lab4.yml ...` for the old
host-based Lab 4 setup. Do not combine its experiments with Lab 5 measurements.

## Stop and package

```powershell
docker compose down
.venv\Scripts\python.exe tests/package_submission.py
```

The archive is `dist/kurlykov_yevgenii_Lab5.zip`. It excludes Git, virtual environments,
caches, private environment files and historical lab evidence. `down` preserves
MongoDB volumes. `docker compose down -v` erases this lab's data permanently.
After recreating an API container (as opposed to stop/start), restart nginx so
its upstream hostnames resolve to the new container addresses.

The work was prepared with Codex assistance. Dependencies: Flask, PyMongo,
Gunicorn, nginx, MongoDB, requests, pytest; existing Lab 4 code also uses boto3 and
Redis. The report distinguishes measurements from explanations and proposals.
