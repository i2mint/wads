"""Guards that ``wads/data`` files a wads install needs actually reach the wheel.

``wads/data/wads_configs.json`` was tracked in git yet matched by ``.gitignore``.
Hatchling honours the VCS ignore file, so ``[tool.hatch.build.targets.wheel]
include = ["wads/data/*"]`` could not pull it back and the published wheel
shipped without it. ``wads/__init__.py`` then fell through to its hardcoded
fallback, whose ``populate_dflts`` disagree with the file (``verbose`` ``True``
vs ``None``, so ``populate --verbose`` was a bare flag on a source install and
an option demanding a value on a wheel install), and the ``i2mint``/``thor``
config sections vanished entirely.

These tests pin the facts that keep source and wheel in agreement.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import wads

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_REL_PATH = "wads/data/wads_configs.json"

#: These assertions are about the repo's packaging config, so they need the
#: checkout; running the suite out of an installed wheel has no pyproject.toml.
needs_checkout = pytest.mark.skipif(
    not (REPO_ROOT / "pyproject.toml").exists(),
    reason="not running from a wads checkout",
)


def _git_available() -> bool:
    if not (REPO_ROOT / ".git").exists():
        return False
    try:
        subprocess.run(
            ["git", "--version"], capture_output=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


@needs_checkout
def test_wads_configs_is_not_gitignored():
    """The configs file must not match .gitignore — hatchling honours it.

    A tracked-but-ignored file is invisible to the build backend, so it silently
    drops out of the wheel and the sdist while staying present in every checkout.
    """
    if not _git_available():
        pytest.skip("not a git checkout, or git unavailable")

    result = subprocess.run(
        ["git", "check-ignore", "-v", "--no-index", CONFIGS_REL_PATH],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0, (
        f"{CONFIGS_REL_PATH} is matched by a .gitignore pattern "
        f"({result.stdout.strip()}), so it cannot reach the built wheel"
    )


def _build_wheel(out_dir: Path) -> Path:
    """Build wads's own wheel into `out_dir` and return its path.

    Prefers hatchling in-process (fast, no network); falls back to `python -m
    build`, which CI always has (it is in the `create` extra this repo installs).
    """
    try:
        from hatchling.builders.wheel import WheelBuilder
    except ImportError:
        pytest.importorskip("build", reason="need hatchling or build to make a wheel")
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            timeout=600,
        )
    else:
        list(WheelBuilder(str(REPO_ROOT)).build(directory=str(out_dir)))

    wheels = sorted(out_dir.glob("*.whl"))
    assert wheels, "no wheel produced"
    return wheels[-1]


@needs_checkout
def test_wads_configs_reaches_the_built_wheel(tmp_path):
    """Build a real wheel and assert the configs file is inside it."""
    with zipfile.ZipFile(_build_wheel(tmp_path)) as zf:
        names = zf.namelist()

    assert any(name.endswith(CONFIGS_REL_PATH) for name in names), (
        f"{CONFIGS_REL_PATH} missing from the built wheel; "
        f"{sum('wads/data/' in n for n in names)} other wads/data files shipped"
    )


def test_wads_configs_values_are_the_ones_the_file_declares():
    """The loaded config must be the file's, not ``__init__``'s bare fallback.

    ``verbose is True`` is what makes ``populate --verbose`` a bare flag; the
    ``i2mint`` section exists only in the file.
    """
    assert wads.wads_configs["populate_dflts"]["verbose"] is True
    assert wads.wads_configs["populate_dflts"]["keywords"] == []
    assert wads.wads_configs["populate_dflts"]["install_requires"] == []
    assert "i2mint" in wads.wads_configs
