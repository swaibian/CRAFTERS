"""SWE4 tests: settings CRUD + key masking + no-key-in-logs.

Positive: create/list/update/delete profiles, active pointer, gateway
endpoint, Scaico key store, team select, teams passthrough.
Negative: bad payloads, unknown ids, bad URLs; keys masked in every
view-safe dict; raw keys never in log records (caplog).
"""

from __future__ import annotations

import json
import logging

import pytest

from controller.settings import (
    SettingsError,
    SettingsStore,
    key_ref,
    list_teams,
    mask_key,
)

RAW_KEY = "sk-test-SECRETKEY1234567890"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setenv("CRAFTER_SETTINGS_FILE", str(path))
    return SettingsStore(path=path)


def _payload(**over):
    base = {
        "label": "Local v1",
        "api_base": "http://127.0.0.1:4000/v1",
        "api_key": RAW_KEY,
        "default_model": "test-model",
    }
    base.update(over)
    return base


def test_create_and_list_masks_key(store):
    created = store.create_profile(_payload())
    assert created["api_key_masked"] == mask_key(RAW_KEY)
    assert created["api_key_masked"].endswith("7890")
    assert RAW_KEY not in json.dumps(created)
    assert "api_key" not in created
    listed = store.list_profiles()
    assert len(listed) == 1
    assert listed[0]["has_key"] is True
    assert RAW_KEY not in json.dumps(listed)


def test_create_requires_label_and_base(store):
    with pytest.raises(SettingsError):
        store.create_profile(_payload(label=""))
    with pytest.raises(SettingsError):
        store.create_profile(_payload(api_base=""))
    with pytest.raises(SettingsError):
        store.create_profile(_payload(api_base="ftp://x"))


def test_update_keeps_key_when_empty(store):
    created = store.create_profile(_payload())
    updated = store.update_profile(created["id"], {"label": "Renamed", "api_key": ""})
    assert updated["label"] == "Renamed"
    assert updated["api_key_masked"] == mask_key(RAW_KEY)
    full = store.get_profile(created["id"])
    assert full is not None and full.api_key == RAW_KEY


def test_update_unknown_profile(store):
    with pytest.raises(SettingsError):
        store.update_profile("prof_nope", {"label": "x"})


def test_delete_and_active_pointer(store):
    first = store.create_profile(_payload(label="one"))
    second = store.create_profile(_payload(label="two"))
    assert store.active_profile() is not None
    assert store.active_profile().id == first["id"]
    store.set_active_profile(second["id"])
    assert store.active_profile().id == second["id"]
    assert store.delete_profile(second["id"]) is True
    assert store.delete_profile("prof_nope") is False
    with pytest.raises(SettingsError):
        store.set_active_profile("prof_nope")


def test_gateway_endpoint_validation(store):
    assert (
        store.set_gateway_endpoint("http://127.0.0.1:8787/") == "http://127.0.0.1:8787"
    )
    with pytest.raises(SettingsError):
        store.set_gateway_endpoint("not-a-url")


def test_scaico_key_masked_status(store):
    status = store.set_scaico_key(RAW_KEY)
    assert status["api_key_masked"] == mask_key(RAW_KEY)
    assert RAW_KEY not in json.dumps(status)
    view = store.scaico_status()
    assert view["has_key"] is True
    assert view["mailto"] == "contact@swaibian.com"
    assert RAW_KEY not in json.dumps(view)
    assert store.get_scaico_key() == RAW_KEY  # server-side only


def test_team_select_roundtrip(store):
    store.set_selected_team("craft_studio")
    assert store.get_selected_team() == "craft_studio"
    store.set_selected_team(None)
    assert store.get_selected_team() is None


def test_list_teams_reads_shape():
    teams = list_teams()
    assert teams, "expected Scaico_Teams JSONs to be listed"
    studio = next(t for t in teams if t["id"] == "craft_studio")
    assert studio["name"]
    assert studio["agents"], "expected agent shape metadata"
    first = studio["agents"][0]
    assert first["id"] and first["model"]
    assert "runtime_model_name" in first
    assert "api_base_url" in first


def test_keys_never_in_logs(store, caplog):
    with caplog.at_level(logging.INFO, logger="crafter.controller"):
        store.create_profile(_payload())
        store.set_scaico_key(RAW_KEY)
        store.set_gateway_endpoint("http://127.0.0.1:8787")
    records = [r for r in caplog.records if r.name.startswith("crafter.controller")]
    assert records, "expected settings log records"
    for record in records:
        rendered = record.getMessage()
        assert RAW_KEY not in rendered
        assert "SECRETKEY" not in rendered


def test_mask_and_ref_helpers():
    assert mask_key("") == ""
    assert mask_key(RAW_KEY) == "…7890"
    assert key_ref("") == "key_none"
    assert key_ref(RAW_KEY) == "key_…7890"
    assert RAW_KEY not in key_ref(RAW_KEY)
