"""Lock in the light-install dependency boundary (issue #32).

A *light* install (``pip install wads`` with only the core dependencies) must be
able to ``import wads`` and use the config-reading + templating modules without
the ``create`` extra (requests / build / wheel / ruamel.yaml) being present.

This test simulates a light install by blocking the create-only third-party
modules at import time and asserting the light surface still imports.
"""

import importlib
import importlib.abc
import sys

import pytest

# Create/publish-only third-party libs that must NOT be needed by the light surface.
CREATE_ONLY = {"requests", "build", "wheel", "ruamel", "ruamel.yaml", "epythet"}

LIGHT_MODULES = [
    "wads",
    "wads.templating",
    "wads.ci_config",
    "wads.toml_util",
    "wads.npm_config",
    "wads.profiles",
    "wads.licensing",
    "wads.util",
]


class _Blocker(importlib.abc.MetaPathFinder):
    """Meta-path finder that makes create-only modules look genuinely absent.

    Uses the modern ``find_spec`` API (the legacy ``find_module`` was removed in
    Python 3.12) and raises ``ModuleNotFoundError`` — exactly what importing a
    truly-uninstalled module raises — so guarded imports
    (``try: import requests / except ModuleNotFoundError``) behave as they would
    in a real light install.
    """

    def find_spec(self, fullname, path=None, target=None):
        top = fullname.split(".")[0]
        if top in CREATE_ONLY or fullname in CREATE_ONLY:
            raise ModuleNotFoundError(
                f"[light-install-test] '{fullname}' is a create-only dependency",
                name=fullname,
            )
        return None


@pytest.fixture
def light_environment():
    """Block create-only modules and purge wads from sys.modules for a clean import."""
    blocker = _Blocker()
    sys.meta_path.insert(0, blocker)
    purged = {
        m: sys.modules.pop(m)
        for m in list(sys.modules)
        if m.split(".")[0] in CREATE_ONLY
    }
    purged.update(
        {m: sys.modules.pop(m) for m in list(sys.modules) if m.startswith("wads")}
    )
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        # Re-import is left to other tests; restore originals to avoid surprises.
        for m, mod in purged.items():
            sys.modules.setdefault(m, mod)


@pytest.mark.parametrize("module", LIGHT_MODULES)
def test_light_surface_imports_without_create_deps(light_environment, module):
    importlib.import_module(module)
