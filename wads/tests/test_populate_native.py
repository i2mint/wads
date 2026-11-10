"""``populate --native maturin`` scaffolds the Rust-core layout wads' native CI builds (#214).

The generated project must be exactly what ``wads.native_build`` and the native CI path
read: a root Cargo workspace (``rust/core`` + the ``rust/py`` binding cdylib named
``_core``), abi3 pyo3, a maturin pyproject whose ``module-name`` is the facade's
``<pkg>._core``, and the ``[tool.wads.ci.build.native]`` table. An existing pyproject is
never rewritten: what it lacks is reported, and the report must be enough to fix it.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from wads import native_build, profiles
from wads.populate import populate_pkg_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

NAME = "fast_thing"
KEBAB = "fast-thing"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def no_cargo(monkeypatch):
    """No toolchain: the lockfile step reports instead of reaching the network."""
    monkeypatch.setattr(profiles, "_find_executable", lambda name: None)


def _toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _populate(pkg_dir: Path, **kw):
    pkg_dir.mkdir(parents=True, exist_ok=True)
    kw = {
        "root_url": "https://example.com/someone",
        "skip_ci_def_gen": True,
        "verbose": False,
        **kw,
    }
    return populate_pkg_dir(str(pkg_dir), **kw)


@pytest.fixture
def native_pkg(tmp_path, no_cargo) -> Path:
    pkg_dir = tmp_path / NAME
    _populate(pkg_dir, native="maturin")
    return pkg_dir


def test_new_package_gets_the_native_layout(native_pkg):
    for rel in [
        "Cargo.toml",
        "rust-toolchain.toml",
        "rust/core/Cargo.toml",
        "rust/core/src/lib.rs",
        "rust/py/Cargo.toml",
        "rust/py/src/lib.rs",
        f"{NAME}/__init__.py",
        f"{NAME}/_core.pyi",
        f"{NAME}/_reference.py",
        f"{NAME}/py.typed",
        "tests/test_api.py",
        "tests/test_differential.py",
    ]:
        assert (native_pkg / rel).is_file(), rel

    leftovers = [
        str(p.relative_to(native_pkg))
        for p in native_pkg.rglob("*")
        if "tmpl" in p.name or (p.is_file() and "tmpl" in p.read_text("utf-8"))
    ]
    assert leftovers == []


def test_cargo_workspace_matches_maturin_config(native_pkg):
    workspace = _toml(native_pkg / "Cargo.toml")
    core = _toml(native_pkg / "rust/core/Cargo.toml")
    binding = _toml(native_pkg / "rust/py/Cargo.toml")
    maturin = _toml(native_pkg / "pyproject.toml")["tool"]["maturin"]

    assert workspace["workspace"]["members"] == ["rust/core", "rust/py"]
    assert core["package"]["name"] == f"{KEBAB}-core"
    assert binding["package"]["name"] == f"{KEBAB}-py"
    assert binding["dependencies"][f"{KEBAB}-core"] == {"path": "../core"}
    assert binding["lib"]["crate-type"] == ["cdylib"]
    # The extension module maturin builds is the binding crate's lib name.
    assert maturin["module-name"] == f"{NAME}._core"
    assert maturin["module-name"].rsplit(".", 1)[1] == binding["lib"]["name"]
    assert (native_pkg / maturin["manifest-path"]).resolve() == (
        native_pkg / "rust/py/Cargo.toml"
    ).resolve()
    # abi3: one wheel per platform; CI refuses a non-abi3 wheel.
    pyo3 = workspace["workspace"]["dependencies"]["pyo3"]
    assert "abi3-py310" in pyo3["features"]
    assert "extension-module" not in pyo3["features"]
    assert f"{NAME}_core::" in (native_pkg / "rust/py/src/lib.rs").read_text()
    assert "mod _core" in (native_pkg / "rust/py/src/lib.rs").read_text()


def test_new_pyproject_is_maturin_and_read_by_native_build(native_pkg):
    pyproject = _toml(native_pkg / "pyproject.toml")

    assert pyproject["build-system"] == {
        "requires": ["maturin>=1.16,<2"],
        "build-backend": native_build.NATIVE_BACKENDS["maturin"],
    }
    assert "hatch" not in pyproject["tool"]
    assert pyproject["tool"]["wads"]["ci"]["build"]["native"] == {"backend": "maturin"}
    # The rest of the wads template survives the merge.
    assert pyproject["project"]["name"] == NAME
    assert pyproject["tool"]["wads"]["ci"]["testing"]["python_versions"]
    assert "hypothesis" in pyproject["project"]["optional-dependencies"]["dev"]
    assert pyproject["project"]["requires-python"] == ">=3.10"  # the abi3-py310 floor

    nb = native_build.native_build_config(pyproject)
    assert nb.backend == "maturin"
    assert nb.smoke_import == f"{NAME}._core"
    assert nb.manifest_path == "rust/py/Cargo.toml"
    assert nb.maturin_args == native_build.DFLT_MATURIN_ARGS
    assert [t["name"] for t in nb.matrix()] == list(native_build.DFLT_NATIVE_TARGETS)


def test_facade_replaces_the_empty_init_populate_just_made(native_pkg):
    init = (native_pkg / NAME / "__init__.py").read_text()
    assert f"from {NAME} import _core" in init


def test_combines_with_frontend_ts(tmp_path, no_cargo):
    pkg_dir = tmp_path / NAME
    _populate(pkg_dir, native="maturin", frontend="ts")

    assert (pkg_dir / "ts/package.json").is_file()
    assert (pkg_dir / ".github/workflows/npm-ci-ts.yml").is_file()
    assert (pkg_dir / "rust/py/Cargo.toml").is_file()
    assert _toml(pkg_dir / "pyproject.toml")["build-system"]["build-backend"] == (
        "maturin"
    )


def test_existing_pyproject_is_reported_not_rewritten(tmp_path, no_cargo, capsys):
    pkg_dir = tmp_path / NAME
    _populate(pkg_dir)  # an ordinary hatchling package
    init = pkg_dir / NAME / "__init__.py"
    init.write_text('"""Existing API."""\n')
    before = (pkg_dir / "pyproject.toml").read_bytes()
    capsys.readouterr()

    _populate(pkg_dir, native="maturin", verbose=True)
    out = capsys.readouterr().out

    assert (pkg_dir / "pyproject.toml").read_bytes() == before
    assert init.read_text() == '"""Existing API."""\n'
    assert (pkg_dir / "rust/py/Cargo.toml").is_file()
    assert 'build-backend = "maturin"' in out
    assert f'module-name = "{NAME}._core"' in out
    assert "[tool.hatch" in out  # the hint to move hatchling include/exclude rules


def test_reported_tables_are_enough_to_finish_the_switch(tmp_path):
    pkg_dir = tmp_path / NAME
    _populate(pkg_dir, skip_ci_def_gen=True)
    existing = _toml(pkg_dir / "pyproject.toml")

    todo = profiles.native_pyproject_todo(existing, NAME)
    fixed = profiles.merge_native_pyproject(existing, tomllib.loads(todo))

    assert profiles.native_pyproject_todo(fixed, NAME) == ""
    assert native_build.native_build_config(fixed).smoke_import == f"{NAME}._core"


def test_bad_name_or_backend_fails_before_writing(tmp_path):
    bad_name = tmp_path / "Not-Importable"
    with pytest.raises(ValueError, match="importable name"):
        _populate(bad_name, native="maturin")
    assert list(bad_name.iterdir()) == []

    with pytest.raises(ValueError, match="Unknown native backend 'cmake'"):
        _populate(tmp_path / NAME, native="cmake")
    assert list((tmp_path / NAME).iterdir()) == []


def test_apply_native_reports_what_it_cannot_settle(tmp_path, no_cargo):
    attention = []
    result = profiles.apply_native(
        str(tmp_path),
        project_name=NAME,
        on_attention=lambda f, reason: attention.append((f, reason)),
    )
    reported = dict(attention)

    assert "Cargo.lock" not in result.added
    assert "cargo not found" in reported["Cargo.lock"]
    assert "--locked" in reported["Cargo.lock"]
    assert "target" in reported[".gitignore"] and "*.so" in reported[".gitignore"]


def test_apply_native_skips_existing_files(tmp_path):
    (tmp_path / "Cargo.toml").write_text("# mine\n")
    result = profiles.apply_native(
        str(tmp_path), project_name=NAME, generate_lockfile=False, on_attention=None
    )
    assert "Cargo.toml" in result.skipped
    assert (tmp_path / "Cargo.toml").read_text() == "# mine\n"


def test_every_native_profile_is_a_backend_ci_can_build():
    for name in profiles.NATIVE_PROFILES:
        fragment = profiles.native_pyproject_fragment(NAME, backend=name)
        assert name in native_build.NATIVE_BACKENDS, name
        assert (
            fragment["build-system"]["build-backend"]
            == native_build.NATIVE_BACKENDS[name]
        )


def test_native_templates_are_not_gitignored():
    """A gitignored template would silently drop out of the wheel (hatchling honours it)."""
    if not (REPO_ROOT / ".git").exists() or shutil.which("git") is None:
        pytest.skip("not a git checkout, or git unavailable")
    tpl_root = Path(profiles.get_native_profile("maturin").template_dir)
    files = [str(p.relative_to(REPO_ROOT)) for p in tpl_root.rglob("*") if p.is_file()]
    assert files
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", *files],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.stdout.strip() == ""


def test_cargo_reads_the_generated_workspace(native_pkg):
    """cargo itself parses the workspace; CI's cargo test excludes the binding crate.

    Skipped without cargo, or when the pinned toolchain is not installed (no download).
    """
    cargo = shutil.which("cargo") or os.path.expanduser("~/.cargo/bin/cargo")
    if not os.path.isfile(cargo):
        pytest.skip("cargo not installed")
    manifest = native_pkg / "rust/py/Cargo.toml"
    proc = subprocess.run(
        [cargo, "metadata", "--no-deps", "--format-version", "1"]
        + ["--manifest-path", str(manifest)],
        cwd=native_pkg,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "RUSTUP_AUTO_INSTALL": "0"},
    )
    if proc.returncode != 0:
        pytest.skip(f"cargo metadata unavailable here: {proc.stderr.strip()[-200:]}")
    meta = json.loads(proc.stdout)

    assert {p["name"] for p in meta["packages"]} == {f"{KEBAB}-core", f"{KEBAB}-py"}
    assert native_build.cargo_test_args(meta, binding_manifest=str(manifest)) == [
        "--workspace",
        "--exclude",
        f"{KEBAB}-py",
    ]
