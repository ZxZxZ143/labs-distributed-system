"""Isolated error-contract checks, separate from Docker HTTP evidence."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
from pymongo.errors import ServerSelectionTimeoutError, WTimeoutError

spec = importlib.util.spec_from_file_location("lab5_api", Path(__file__).parents[1] / "app" / "app.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


@pytest.mark.parametrize("error", [ServerSelectionTimeoutError("offline"), WTimeoutError("no majority")])
@pytest.mark.parametrize("method", ["get", "post"])
def test_R24_storage_errors(monkeypatch, error, method):
    records = Mock()
    records.find_one.side_effect = error
    records.insert_one.side_effect = error
    monkeypatch.setattr(api, "get_records", lambda: records)
    client = api.app.test_client()
    r = client.get("/records/00000000-0000-0000-0000-000000000000") if method == "get" else client.post("/records", json={"text": "test"})
    assert r.status_code == 503
    assert r.json == {"error": "storage unavailable"}
