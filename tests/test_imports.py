"""Smoke tests for package boundaries."""

import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "shared",
        "shared.constants",
        "shared.models",
        "shared.protocol",
        "pc",
        "pc.audio",
        "pc.audio.fft",
        "pc.audio.wasapi",
        "pc.assets",
        "pc.assets.album_art",
        "pc.collectors",
        "pc.collectors.media",
        "pc.collectors.system",
        "pc.config",
        "pc.main",
        "pi",
        "pi.assets",
        "pi.config",
        "pi.display",
        "pi.main",
        "pi.themes",
    ],
)
def test_module_imports(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None
