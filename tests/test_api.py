"""Black-box HTTP tests; requirement IDs are kept in test names."""
import os
import uuid
from datetime import datetime

import pytest
import requests

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:18080")


def test_R1_time():
    r = requests.get(f"{BASE}/time", timeout=6)
    assert r.status_code == 200
    datetime.strptime(r.json()["time"], "%Y-%m-%d %H:%M:%S")
    assert r.json()["served_by"] in {"api1", "api2", "api3"}


def test_R2_echo():
    r = requests.post(f"{BASE}/echo", json={"message": "hello"}, timeout=6)
    assert r.status_code == 200 and r.json() == {"message": "hello"}


def test_R3_echo_negative():
    r = requests.post(f"{BASE}/echo", json={}, timeout=6)
    assert r.status_code == 400


@pytest.mark.parametrize("text", ["Привет 🌍", "", "x" * 65536, "я" * 32768],
                         ids=["unicode", "empty", "max-ascii", "max-utf8"])
def test_R19_R20_R22_roundtrip(text):
    r = requests.post(f"{BASE}/records", json={"text": text}, timeout=6)
    assert r.status_code == 201
    data = r.json()
    assert str(uuid.UUID(data["id"])) == data["id"]
    assert data["text"] == text and data["served_by"] in {"api1", "api2", "api3"}
    r = requests.get(f"{BASE}/records/{data['id']}", timeout=6)
    assert r.status_code == 200
    assert r.json()["text"] == text and r.json()["id"] == data["id"]


@pytest.mark.parametrize("payload", [{}, {"text": None}, {"text": 12},
                                     ["text"], "text", {"text": []}],
                         ids=["missing", "null", "number", "array", "string", "list-value"])
def test_R21_invalid_payload(payload):
    r = requests.post(f"{BASE}/records", json=payload, timeout=6)
    assert r.status_code == 400 and "error" in r.json()


def test_R21_malformed_json():
    r = requests.post(f"{BASE}/records", data="{", headers={"Content-Type": "application/json"}, timeout=6)
    assert r.status_code == 400


@pytest.mark.parametrize("text", ["x" * 65537, "я" * 32769], ids=["ascii", "utf8"])
def test_R22_oversize(text):
    r = requests.post(f"{BASE}/records", json={"text": text}, timeout=6)
    assert r.status_code == 400


def test_R23_missing():
    r = requests.get(f"{BASE}/records/{uuid.uuid4()}", timeout=6)
    assert r.status_code == 404


def test_R23_invalid_id():
    r = requests.get(f"{BASE}/records/not-a-uuid", timeout=6)
    assert r.status_code == 400


def test_R26_distribution():
    hosts = [requests.get(f"{BASE}/time", timeout=6).json()["served_by"] for _ in range(30)]
    assert len(set(hosts)) >= 2
