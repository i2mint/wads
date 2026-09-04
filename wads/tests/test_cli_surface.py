"""Characterization tests pinning the ``pack`` and ``populate`` command lines.

Both console scripts were dispatched by ``argh`` up to wads 0.2.19 and are
dispatched by :mod:`cw` from 0.2.20 on. The goldens in ``cli_goldens/`` were
recorded from the **argh** implementation, so what they assert is not "cw does
what cw does" but "the command line a user (and eight fleet CI workflows) type
did not move when the dispatcher underneath it was replaced".

Each golden is replayed as a real subprocess against the installed console
script, resolved next to ``sys.executable`` rather than through ``PATH`` -- a
developer machine may well have an older hand-written ``pack`` shim earlier on
``PATH``, and that shim reports a different ``prog`` to ``argparse``.

What is asserted, per :mod:`cw.testing`'s tier rule: exit code and both streams
in full for every non-``--help`` case, and exit code plus the normalised
``usage:`` line for the ``--help`` cases. The ``--help`` *body* is compared but
reported non-fatally, because CPython rewrites argparse's own option column
between versions (3.13 renders ``-i, --ignore VALUE`` where 3.12 rendered
``-i VALUE, --ignore VALUE``) and wads's CI matrix spans several. The bodies
were verified byte-identical under ``--strict-help`` on CPython 3.12 at
migration time; a body difference here is worth reading, not worth failing a
matrix leg over.

Re-record with::

    python -m cw.testing characterize pack --cases <cases-file> \
        -o wads/tests/cli_goldens/pack.json

and only ever alongside a deliberate, documented change to the CLI.
"""

import json
import os
import sys
from pathlib import Path

import pytest

cw_testing = pytest.importorskip(
    "cw.testing", reason="cw is a core dependency; skip only in a partial install"
)

GOLDENS_DIR = Path(__file__).parent / "cli_goldens"
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Console scripts declared in ``[project.scripts]`` that these goldens pin.
PINNED_SCRIPTS = ("pack", "populate")


def _pinned_env(name):
    """Environment that makes ``name``'s ``--help`` the same on every machine.

    ``populate``'s parser is built from ``populate_pkg_dir``'s defaults, and
    those come from ``wads_configs.json``, which ``wads/__init__.py`` looks up
    at ``$WADS_CONFIGS_FILE`` and falls back to a hardcoded dict for. The two
    do not agree: the file says ``verbose: true`` (so ``--verbose`` is a
    ``store_false`` flag) and the fallback says ``verbose: null`` (so
    ``--verbose VERBOSE`` takes a value). Which one a machine sees depends on
    whether that file is present -- and it is NOT shipped in the built wheel,
    because ``.gitignore`` names it and hatchling honours the VCS ignore file,
    even though the file is tracked in git and so is present in every checkout.

    Pinning the variable makes the assertion be about the dispatcher, which is
    what this file is for. The underlying split -- the same ``populate`` having
    two different grammars depending on install shape -- is a wads packaging
    defect that predates the cw migration and is filed separately.
    """
    if name == "populate":
        return {
            "WADS_CONFIGS_FILE": str(REPO_ROOT / "wads" / "data" / "wads_configs.json")
        }
    return {}


def _console_script(name):
    """The installed console script ``name``, resolved beside ``sys.executable``.

    ``shutil.which`` is deliberately not used: it answers a question about the
    developer's ``PATH``, not about the interpreter running the tests.
    """
    bin_dir = Path(sys.executable).parent
    candidates = [bin_dir / name]
    if os.name == "nt":
        candidates = [bin_dir / f"{name}.exe", bin_dir / "Scripts" / f"{name}.exe"]
    return next((c for c in candidates if c.exists()), None)


@pytest.mark.parametrize("name", PINNED_SCRIPTS)
def test_the_command_line_did_not_move(name):
    """MUTATION: change a flag's name, its ``nargs``, or a command's exit code.

    Eight GitHub Action definitions in the fleet invoke these scripts by name
    with hand-written argument strings. Nothing else in this suite would notice
    a renamed flag, and CI would only find out at the moment a release goes out.
    """
    script = _console_script(name)
    if script is None:
        pytest.skip(f"console script {name!r} is not installed in this environment")
    cw_testing.assert_replay(
        GOLDENS_DIR / f"{name}.json", prog=[str(script)], env=_pinned_env(name)
    )


@pytest.mark.parametrize("name", PINNED_SCRIPTS)
def test_the_golden_carries_no_machine_specific_prog(name):
    """MUTATION: re-record and commit without rewriting ``prog``.

    ``characterize`` stores the command it was given, which on the machine that
    records is an absolute path under somebody's home directory. Committing that
    leaks a local path into a public repo AND makes the golden replay against a
    path that exists on exactly one computer. The recorded ``prog`` must be the
    bare console-script name; the runner above supplies the real path.
    """
    golden = json.loads((GOLDENS_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert golden["prog"] == [name], (
        f"{name}.json records prog={golden['prog']!r}; rewrite it to [{name!r}] "
        "before committing (see this module's docstring)"
    )
