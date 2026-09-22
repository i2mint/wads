"""Guard that the canonical ``<pkg>/data/skills/<name>/SKILL.md`` path
survives a real sdist -> wheel build (issue #89).

The canonical skill layout (``skill-package-setup``) keeps real files at
``<pkg>/data/skills/<name>`` and a relative symlink from
``.claude/skills/<name>`` pointing at them, for Claude Code's project-local
skill discovery. Hatchling's sdist builder walks the tree with
``followlinks=True`` and skips any real directory it has already visited;
``.claude`` sorts before ``<pkg>`` alphabetically, so the walk visits the
*symlinked* copy first, marks the real target "seen", and drops it from the
sdist when it reaches the canonical path. A wheel built directly from the
working tree looks fine (no sdist step, so the walk never revisits the
already-seen directory) -- only a wheel built *from the sdist* (what CI
actually publishes) shows the drop. This module builds a real sdist and then
a real wheel from it, the way ``python -m build`` and wads's own CI do.
"""

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

needs_checkout = pytest.mark.skipif(
    not (REPO_ROOT / "pyproject.toml").exists(),
    reason="not running from a wads checkout",
)


def _build_sdist(out_dir: Path) -> Path:
    """Build wads's own sdist into `out_dir` and return its path."""
    try:
        from hatchling.builders.sdist import SdistBuilder
    except ImportError:
        pytest.importorskip("build", reason="need hatchling or build to make a sdist")
        subprocess.run(
            [sys.executable, "-m", "build", "--sdist", "--outdir", str(out_dir)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            timeout=600,
        )
    else:
        list(SdistBuilder(str(REPO_ROOT)).build(directory=str(out_dir)))

    sdists = sorted(out_dir.glob("*.tar.gz"))
    assert sdists, "no sdist produced"
    return sdists[-1]


def _build_wheel_from_sdist(sdist_path: Path, work_dir: Path) -> Path:
    """Extract `sdist_path` and build a wheel from the extraction (not the tree)."""
    extract_dir = work_dir / "extracted"
    extract_dir.mkdir()
    with tarfile.open(sdist_path) as tf:
        tf.extractall(extract_dir)  # nosec B202 - our own just-built sdist

    # sdist root is a single top-level "<name>-<version>/" directory.
    (project_dir,) = extract_dir.iterdir()

    out_dir = work_dir / "wheel"
    out_dir.mkdir()
    try:
        from hatchling.builders.wheel import WheelBuilder
    except ImportError:
        pytest.importorskip("build", reason="need hatchling or build to make a wheel")
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir)],
            cwd=project_dir,
            check=True,
            capture_output=True,
            timeout=600,
        )
    else:
        list(WheelBuilder(str(project_dir)).build(directory=str(out_dir)))

    wheels = sorted(out_dir.glob("*.whl"))
    assert wheels, "no wheel produced from the sdist"
    return wheels[-1]


@needs_checkout
def test_skill_layout_survives_sdist_then_wheel(tmp_path):
    """Every real ``wads/data/skills/<name>/SKILL.md`` must reach a
    wheel built from the sdist -- not just a wheel built from the tree.
    """
    skills_dir = REPO_ROOT / "wads" / "data" / "skills"
    expected = sorted(
        p.parent.name for p in skills_dir.glob("*/SKILL.md") if p.is_file()
    )
    assert expected, "no canonical skills found under wads/data/skills to guard"

    sdist_dir = tmp_path / "sdist"
    sdist_dir.mkdir()
    sdist_path = _build_sdist(sdist_dir)

    with tarfile.open(sdist_path) as tf:
        sdist_names = tf.getnames()
    sdist_skill_names = sorted(
        n.split("wads/data/skills/", 1)[1].split("/", 1)[0]
        for n in sdist_names
        if "wads/data/skills/" in n and n.endswith("/SKILL.md")
    )
    assert sdist_skill_names == expected, (
        "skills dropped from the sdist by the .claude/skills symlink-walk "
        f"collision: expected {expected}, sdist has {sdist_skill_names}"
    )

    wheel_path = _build_wheel_from_sdist(sdist_path, tmp_path)
    with zipfile.ZipFile(wheel_path) as zf:
        wheel_names = zf.namelist()
    wheel_skill_names = sorted(
        n.split("wads/data/skills/", 1)[1].split("/", 1)[0]
        for n in wheel_names
        if "wads/data/skills/" in n and n.endswith("/SKILL.md")
    )
    assert wheel_skill_names == expected, (
        "skills present in the sdist but dropped by the wheel-from-sdist build: "
        f"expected {expected}, wheel has {wheel_skill_names}"
    )

    # The symlink source directory must not leak the .claude worktree metadata
    # or duplicate the skill content under .claude/ in the sdist at all --
    # skip-excluded-dirs + the sdist exclude block stop the walk from
    # entering .claude in the first place.
    assert not any(n.startswith("wads-") and "/.claude/" in n for n in sdist_names), (
        ".claude/ leaked into the sdist; expected it excluded by "
        "[tool.hatch.build.targets.sdist].exclude"
    )
