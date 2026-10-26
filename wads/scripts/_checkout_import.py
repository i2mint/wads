"""Import a stdlib-only wads module from this checkout, never from site-packages.

Composite actions run their scripts by path from the action's own checkout, so
the script and the code it needs are always the same ref. A plain
``from wads.ci_config import ...`` would instead resolve to whatever wads wheel
the runner has (stale, or absent), and importing the ``wads`` package would
need its third-party dependencies. Loading the module by file path avoids both.
"""

import importlib.util
import sys
from pathlib import Path

WADS_PACKAGE_DIR = Path(__file__).resolve().parent.parent


def load_wads_module(name: str):
    """Load ``wads/<name>.py`` from this checkout (it must import only the stdlib)."""
    qualified = f"_wads_checkout_{name}"
    if qualified in sys.modules:
        return sys.modules[qualified]
    spec = importlib.util.spec_from_file_location(
        qualified, WADS_PACKAGE_DIR / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module  # before exec: dataclasses look the module up
    spec.loader.exec_module(module)
    return module
