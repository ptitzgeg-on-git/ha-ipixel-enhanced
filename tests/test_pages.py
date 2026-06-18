"""Page library + per-device playlist runner logic (pages.py).

Storage and scheduling are faked; this checks the pure sequencing/migration
logic, not disk I/O or the event loop.
"""
import asyncio
import types

import pytest


def run(coro):
    return asyncio.run(coro)


class FakeStore:
    """Stand-in for homeassistant.helpers.storage.Store."""

    def __init__(self, initial=None):
        self.saved = None
        self._initial = initial

    async def async_load(self):
        return self._initial

    async def async_save(self, data):
        self.saved = data


def make_store(pages_mod, initial=None, hass=None):
    store = pages_mod.PageStore(hass=hass or object())
    store._store = FakeStore(initial)
    return store


def make_hass_with_api(pages_mod, api, entry_id="entry1"):
    return types.SimpleNamespace(data={pages_mod.DOMAIN: {entry_id: api}})


class FakeAPI:
    def __init__(self):
        self.shown = []

    async def display_widgets(self, page):
        self.shown.append(page)
        return True


# --- PageStore ------------------------------------------------------------
def test_save_and_delete_page(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.save_page("weather", {"widgets": []}))
    assert "weather" in store.pages
    run(store.delete_page("weather"))
    assert "weather" not in store.pages


def test_delete_page_removes_it_from_playlists(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.save_page("a", {"widgets": []}))
    run(store.save_named_playlist("pl", [{"name": "a", "duration": 5}]))
    run(store.start_named_playlist("pl", ["entry1"]))
    run(store.delete_page("a"))
    assert all(it["name"] != "a" for it in store.playlists["pl"]["items"])


def test_legacy_playlist_is_migrated_to_named(pages_mod):
    initial = {
        "pages": {"a": {"widgets": []}},
        "playlist": {"enabled": True, "items": [{"name": "a", "duration": 5}], "target": None},
        "active": "Default",
    }
    store = make_store(pages_mod, initial)
    run(store.async_load())
    assert "Default" in store.playlists
    assert store.playlists["Default"]["items"][0]["name"] == "a"
    # target was None, so we can't know the panel — runs stays empty.
    assert store.runs == {}


def test_legacy_playlist_with_target_populates_runs(pages_mod):
    initial = {
        "pages": {"a": {"widgets": []}},
        "playlists": {"pl": {"items": [{"name": "a", "duration": 5}], "targets": []}},
        "playlist": {"enabled": True, "items": [], "target": "entry1"},
        "active": "pl",
    }
    hass = make_hass_with_api(pages_mod, FakeAPI(), "entry1")
    store = make_store(pages_mod, initial, hass=hass)
    run(store.async_load())
    assert store.runs == {"entry1": "pl"}


def test_legacy_playlist_target_field_folds_into_targets(pages_mod):
    initial = {"playlists": {"pl": {"items": [], "target": "dev1"}}}
    store = make_store(pages_mod, initial)
    run(store.async_load())
    assert store.playlists["pl"]["targets"] == ["dev1"]
    assert "target" not in store.playlists["pl"]


def test_start_named_playlist_unknown_returns_false(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    assert run(store.start_named_playlist("ghost", ["entry1"])) is False


def test_start_named_playlist_without_targets_returns_false(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.save_named_playlist("pl", [{"name": "a", "duration": 5}]))
    assert run(store.start_named_playlist("pl", [])) is False


def test_start_then_stop_playlist_per_device(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.save_named_playlist("pl", [{"name": "a", "duration": 5}]))
    assert run(store.start_named_playlist("pl", ["entry1"])) is True
    assert store.runs == {"entry1": "pl"}
    assert store.running_on("entry1") == "pl"
    run(store.stop_playlist("entry1"))
    assert store.runs == {}


def test_two_devices_run_independent_playlists(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.save_named_playlist("morning", [{"name": "a", "duration": 5}]))
    run(store.save_named_playlist("night", [{"name": "b", "duration": 5}]))
    run(store.start_named_playlist("morning", ["e1"]))
    run(store.start_named_playlist("night", ["e2"]))
    # Starting the second must NOT clobber the first.
    assert store.runs == {"e1": "morning", "e2": "night"}


def test_one_playlist_on_several_devices(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.save_named_playlist("pl", [{"name": "a", "duration": 5}]))
    run(store.start_named_playlist("pl", ["e1", "e2"]))
    assert store.runs == {"e1": "pl", "e2": "pl"}


def test_editing_named_playlist_keeps_runs(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.save_named_playlist("pl", [{"name": "a", "duration": 5}]))
    run(store.start_named_playlist("pl", ["e1"]))
    run(store.save_named_playlist("pl", [{"name": "b", "duration": 9}]))
    assert store.playlists["pl"]["items"][0]["name"] == "b"
    assert store.runs == {"e1": "pl"}


def test_delete_named_playlist_clears_its_runs(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.save_named_playlist("pl", [{"name": "a", "duration": 5}]))
    run(store.start_named_playlist("pl", ["e1", "e2"]))
    run(store.delete_named_playlist("pl"))
    assert "pl" not in store.playlists
    assert store.runs == {}


# --- device slots ---------------------------------------------------------
def test_set_and_clear_slot(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.set_slot("weather", 3))
    assert store.slots["weather"] == 3
    run(store.set_slot("weather", None))
    assert "weather" not in store.slots


def test_deleting_page_clears_its_slot(pages_mod):
    store = make_store(pages_mod)
    run(store.async_load())
    run(store.save_page("weather", {"widgets": []}))
    run(store.set_slot("weather", 5))
    run(store.delete_page("weather"))
    assert "weather" not in store.slots


def test_slots_persist_through_load(pages_mod):
    store = make_store(pages_mod, {"pages": {}, "slots": {"a": 2, "b": 7}})
    run(store.async_load())
    assert store.slots == {"a": 2, "b": 7}


# --- resolve_targets ------------------------------------------------------
def test_resolve_targets_passes_through_entry_ids(pages_mod):
    hass = make_hass_with_api(pages_mod, FakeAPI(), "entry1")
    assert pages_mod.resolve_targets(hass, "entry1") == ["entry1"]
    assert pages_mod.resolve_targets(hass, ["entry1", "ghost"]) == ["entry1"]
    assert pages_mod.resolve_targets(hass, None) == []


# --- PlaylistRunner -------------------------------------------------------
def _runner_with(pages_mod, api, runs, playlists, pages, entry_id="entry1"):
    hass = make_hass_with_api(pages_mod, api, entry_id)
    store = make_store(pages_mod, hass=hass)
    store.runs = runs
    store.playlists = playlists
    store.pages = pages
    runner = pages_mod.PlaylistRunner(hass, store)
    return runner


def test_runner_cycles_and_wraps_index(pages_mod):
    api = FakeAPI()
    runner = _runner_with(
        pages_mod, api,
        runs={"entry1": "pl"},
        playlists={"pl": {"items": [{"name": "a", "duration": 5}, {"name": "b", "duration": 5}], "targets": []}},
        pages={"a": {"id": "a"}, "b": {"id": "b"}},
    )
    runner._loops["entry1"] = {"index": 0, "cancel": None}
    run(runner._tick("entry1"))   # shows a, index -> 1
    run(runner._tick("entry1"))   # shows b, index -> 2
    run(runner._tick("entry1"))   # wraps to 0, shows a
    assert [p["id"] for p in api.shown] == ["a", "b", "a"]


def test_runner_tick_stops_when_no_run_for_device(pages_mod):
    api = FakeAPI()
    runner = _runner_with(
        pages_mod, api,
        runs={},
        playlists={"pl": {"items": [{"name": "a", "duration": 5}], "targets": []}},
        pages={"a": {"id": "a"}},
    )
    runner._loops["entry1"] = {"index": 0, "cancel": None}
    run(runner._tick("entry1"))
    assert api.shown == []
    assert "entry1" not in runner._loops


def test_runner_resolve_api_by_entry_id(pages_mod):
    api = FakeAPI()
    runner = _runner_with(pages_mod, api, runs={}, playlists={}, pages={})
    assert runner._resolve_api("entry1") is api
    assert runner._resolve_api("nope") is None
