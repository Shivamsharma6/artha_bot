import json

import pytest

from arthabot.runtime_state import RuntimeStateStore


def test_runtime_state_store_round_trips_versioned_dashboard_payload(tmp_path):
    path = tmp_path / "paper-runtime.json"
    store = RuntimeStateStore(path)
    payload = {"mode": "PAPER", "capital": 5025.5, "total_trades": 2, "positions_list": []}

    store.save(payload)

    assert store.load() == payload
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_runtime_state_store_rejects_corrupt_state(tmp_path):
    path = tmp_path / "paper-runtime.json"
    path.write_text('{"version": 99, "payload": {}}', encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported runtime state version"):
        RuntimeStateStore(path).load()

