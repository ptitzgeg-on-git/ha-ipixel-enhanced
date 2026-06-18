"""Font discovery (fonts.py) against the real bundled fonts."""


def test_bundled_fonts_are_discovered(fonts_mod, pkg_path):
    fonts = fonts_mod.get_available_fonts([pkg_path / "fonts"])
    # The repo ships these pixel/display fonts.
    for expected in ("Tiny5.ttf", "5x5.ttf", "OpenSans-Light.ttf", "PressStart2P.ttf"):
        assert expected in fonts, f"{expected} missing from {fonts}"


def test_get_font_path_resolves_bundled(fonts_mod, pkg_path):
    locations = [pkg_path / "fonts"]
    path = fonts_mod.get_font_path("Tiny5", locations)
    assert path is not None and path.exists()
    # extension is auto-appended
    assert path.name == "Tiny5.ttf"


def test_get_font_path_missing_returns_none(fonts_mod, pkg_path):
    assert fonts_mod.get_font_path("does-not-exist", [pkg_path / "fonts"]) is None


def test_scan_empty_dir_falls_back_to_default(fonts_mod, tmp_path):
    fonts = fonts_mod.get_available_fonts([tmp_path])
    assert fonts == ["OpenSans-Light.ttf"]
