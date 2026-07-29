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
        "pc.collectors",
        "pc.collectors.system",
        "pc.config",
        "pc.main",
        "pi",
        "pi.config",
        "pi.display",
        "pi.main",
    ],
)
def test_module_imports(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None
