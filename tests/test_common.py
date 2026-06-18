"""Shared auto-update gate (common.trigger_auto_update).

This is the helper every settings entity now calls, so its gating logic
(Auto Update switch on/off, optional mode restriction) is locked here.
"""
import asyncio
import types

import pytest


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def common(monkeypatch):
    import importlib

    mod = importlib.import_module("ipixel_enhanced.common")
    return mod


class FakeStates:
    def __init__(self, mapping):
        # mapping: entity_id -> state string
        self._m = mapping

    def get(self, entity_id):
        if entity_id in self._m:
            return types.SimpleNamespace(state=self._m[entity_id])
        return None


def patch_lookup(monkeypatch, common):
    """Map (suffix) -> entity_id so the registry lookup is deterministic."""
    monkeypatch.setattr(
        common, "get_entity_id_by_unique_id",
        lambda hass, address, suffix, platform=None: f"{platform}.{suffix}",
    )


def make_calls_recorder(monkeypatch, common):
    calls = []

    async def fake_update(hass, device_name, api, text=None):
        calls.append(device_name)
        return True

    monkeypatch.setattr(common, "update_ipixel_display", fake_update)
    return calls


def test_no_update_when_auto_off(common, monkeypatch):
    patch_lookup(monkeypatch, common)
    calls = make_calls_recorder(monkeypatch, common)
    hass = types.SimpleNamespace(states=FakeStates({"switch.auto_update": "off"}))
    run(common.trigger_auto_update(hass, "addr", "Panel", object()))
    assert calls == []


def test_update_when_auto_on_no_mode_filter(common, monkeypatch):
    patch_lookup(monkeypatch, common)
    calls = make_calls_recorder(monkeypatch, common)
    hass = types.SimpleNamespace(states=FakeStates({"switch.auto_update": "on"}))
    run(common.trigger_auto_update(hass, "addr", "Panel", object()))
    assert calls == ["Panel"]


def test_update_respects_matching_mode(common, monkeypatch):
    patch_lookup(monkeypatch, common)
    calls = make_calls_recorder(monkeypatch, common)
    hass = types.SimpleNamespace(states=FakeStates({
        "switch.auto_update": "on",
        "select.mode_select": "clock",
    }))
    run(common.trigger_auto_update(hass, "addr", "Panel", object(), only_modes=("clock",)))
    assert calls == ["Panel"]


def test_no_update_when_mode_does_not_match(common, monkeypatch):
    patch_lookup(monkeypatch, common)
    calls = make_calls_recorder(monkeypatch, common)
    hass = types.SimpleNamespace(states=FakeStates({
        "switch.auto_update": "on",
        "select.mode_select": "text",
    }))
    run(common.trigger_auto_update(hass, "addr", "Panel", object(), only_modes=("clock",)))
    assert calls == []


def test_no_update_when_auto_switch_missing(common, monkeypatch):
    patch_lookup(monkeypatch, common)
    calls = make_calls_recorder(monkeypatch, common)
    hass = types.SimpleNamespace(states=FakeStates({}))  # no auto_update entity
    run(common.trigger_auto_update(hass, "addr", "Panel", object()))
    assert calls == []
