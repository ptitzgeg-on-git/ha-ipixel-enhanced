"""Test harness for ha-ipixel-enhanced.

The integration lives inside Home Assistant, but most of its logic is pure
Python (image rendering, colour parsing, BLE frame encoding, playlist
sequencing). To exercise that logic without a full HA install we stub the
handful of `homeassistant.*` modules the imported files touch, then load the
real package by path.

What is NOT covered here (and cannot be, without hardware): the BLE transport
(`bluetooth/`, `api.connect`/send) and anything requiring the `pypixelcolor`
package. Those are validated on the real panel — see the project notes.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PKG_DIR = REPO / "custom_components" / "ipixel_enhanced"


def _stub(name: str, is_pkg: bool = False) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        if is_pkg:
            mod.__path__ = []  # mark as package so submodules can be added
        sys.modules[name] = mod
    return mod


class _Stub:
    """Permissive stand-in for HA base classes the modules subclass."""

    def __init__(self, *args, **kwargs):
        pass


def _install_homeassistant_stubs() -> None:
    """Register the minimal slice of `homeassistant` the pure modules import."""
    ha = _stub("homeassistant", is_pkg=True)

    core = _stub("homeassistant.core", is_pkg=True)
    core.HomeAssistant = _Stub
    core.callback = lambda fn: fn  # decorator no-op

    comps = _stub("homeassistant.components", is_pkg=True)
    for sub in ("text", "switch", "select", "number", "button", "light", "sensor"):
        m = _stub(f"homeassistant.components.{sub}", is_pkg=True)
        # Entity base classes referenced as `XEntity`
        setattr(m, f"{sub.capitalize()}Entity", _Stub)
    sys.modules["homeassistant.components.text"].TextEntity = _Stub
    sys.modules["homeassistant.components.text"].TextMode = _Stub
    setattr(comps, "text", sys.modules["homeassistant.components.text"])

    cfg = _stub("homeassistant.config_entries")
    cfg.ConfigEntry = _Stub

    helpers = _stub("homeassistant.helpers", is_pkg=True)
    entity = _stub("homeassistant.helpers.entity")
    entity.DeviceInfo = dict  # DeviceInfo behaves like a dict for our asserts

    class _EntityCategory:
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    entity.EntityCategory = _EntityCategory
    restore = _stub("homeassistant.helpers.restore_state")
    restore.RestoreEntity = _Stub
    platform = _stub("homeassistant.helpers.entity_platform")
    platform.AddEntitiesCallback = _Stub
    aioclient = _stub("homeassistant.helpers.aiohttp_client")
    aioclient.async_get_clientsession = lambda hass: None
    event = _stub("homeassistant.helpers.event")
    event.async_call_later = lambda hass, delay, cb: (lambda: None)
    dispatcher = _stub("homeassistant.helpers.dispatcher")
    dispatcher.async_dispatcher_send = lambda hass, signal, *a: None
    dispatcher.async_dispatcher_connect = lambda hass, signal, cb: (lambda: None)
    storage = _stub("homeassistant.helpers.storage")
    storage.Store = _Stub

    tmpl = _stub("homeassistant.helpers.template")
    tmpl.Template = _Template

    er = _stub("homeassistant.helpers.entity_registry")
    er.async_get = lambda hass: types.SimpleNamespace(entities={})
    dr = _stub("homeassistant.helpers.device_registry")
    dr.async_get = lambda hass: types.SimpleNamespace(async_get=lambda _id: None)

    helpers.entity = entity
    helpers.template = tmpl
    helpers.entity_registry = er
    helpers.device_registry = dr

    aiohttp = _stub("aiohttp")
    aiohttp.ClientError = type("ClientError", (Exception,), {})


class _Template:
    """Tiny Jinja-ish stand-in: resolves ``states('x')`` from a fixed dict and
    leaves unknown templates as the empty string (matching the engine's
    "never let a bad template kill the page" behaviour)."""

    _states = {
        "sensor.temperature": "21",
        "sensor.rain": "70",
        "binary_sensor.flag": "on",
    }

    def __init__(self, tpl, hass=None):
        self.tpl = tpl

    def async_render(self, parse_result=False):
        import re

        out = self.tpl
        out = re.sub(
            r"\{\{\s*states\('([^']+)'\)\s*\}\}",
            lambda m: self._states.get(m.group(1), ""),
            out,
        )
        # Anything still templated (unknown construct) collapses to "".
        if "{{" in out or "{%" in out:
            return ""
        return out


def _load_package() -> None:
    """Expose the real integration as an importable `ipixel_enhanced` package."""
    if "ipixel_enhanced" in sys.modules:
        return
    pkg = types.ModuleType("ipixel_enhanced")
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules["ipixel_enhanced"] = pkg
    for sub in ("display", "device", "bluetooth"):
        subpkg = types.ModuleType(f"ipixel_enhanced.{sub}")
        subpkg.__path__ = [str(PKG_DIR / sub)]
        sys.modules[f"ipixel_enhanced.{sub}"] = subpkg


_install_homeassistant_stubs()
_load_package()


@pytest.fixture(scope="session")
def repo_path() -> Path:
    return REPO


@pytest.fixture(scope="session")
def pkg_path() -> Path:
    return PKG_DIR


def _import(modname: str):
    return importlib.import_module(modname)


@pytest.fixture(scope="session")
def widget_renderer():
    return _import("ipixel_enhanced.display.widget_renderer")


@pytest.fixture(scope="session")
def fonts_mod():
    return _import("ipixel_enhanced.fonts")


@pytest.fixture(scope="session")
def color_mod():
    return _import("ipixel_enhanced.color")


@pytest.fixture(scope="session")
def commands_mod():
    return _import("ipixel_enhanced.device.commands")


@pytest.fixture(scope="session")
def pages_mod():
    return _import("ipixel_enhanced.pages")
