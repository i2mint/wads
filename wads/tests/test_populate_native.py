"""``populate --native maturin`` scaffolds the Rust-core layout wads' native CI builds (#214).

The generated project must be exactly what ``wads.native_build`` and the native CI path
read: a root Cargo workspace (``rust/core`` + the ``rust/py`` binding cdylib named
``_core``), abi3 pyo3, a maturin pyproject whose ``module-name`` is the facade's
``<pkg>._core``. An existing package keeps its pyproject and ``__init__.py``: what they
lack is reported, and applying the report by hand must give a package that builds and
passes its tests. (The ``native-selftest`` workflow compiles a fresh scaffold on every
wheel target; the build test here covers the existing-package path where a toolchain is.)
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from wads import native_build, populate, profiles
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


@pytest.fixture
def attention(monkeypatch) -> list:
    """Every ``(filename, reason)`` populate puts under "Needs attention"."""
    seen = []
    original = populate.PopulateTracker.attention

    def record(self, filename, reason=None):
        seen.append((filename, reason))
        return original(self, filename, reason)

    monkeypatch.setattr(populate.PopulateTracker, "attention", record)
    return seen


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


def _files(root: Path) -> dict:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture
def native_pkg(tmp_path, no_cargo) -> Path:
    pkg_dir = tmp_path / NAME
    _populate(pkg_dir, native="maturin")
    return pkg_dir


# --- a new package ------------------------------------------------------------------


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
        rel for rel, content in _files(native_pkg).items() if b"tmpl" in content
    ]
    assert leftovers == []
    # The facade replaced the empty __init__.py populate itself made.
    assert (
        f"from {NAME} import _core" in (native_pkg / NAME / "__init__.py").read_text()
    )


def test_cargo_workspace_matches_maturin_config(native_pkg):
    workspace = _toml(native_pkg / "Cargo.toml")
    core = _toml(native_pkg / "rust/core/Cargo.toml")
    binding = _toml(native_pkg / "rust/py/Cargo.toml")
    maturin = _toml(native_pkg / "pyproject.toml")["tool"]["maturin"]

    # A glob, so another crate (rust/wasm, ...) joins by being written there.
    assert workspace["workspace"]["members"] == ["rust/*"]
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
    lib_rs = (native_pkg / "rust/py/src/lib.rs").read_text()
    assert f"{NAME}_core::" in lib_rs and "mod _core" in lib_rs


def test_the_crates_carry_the_package_licence(tmp_path, no_cargo):
    pkg_dir = tmp_path / NAME
    _populate(pkg_dir, native="maturin", license="apache-2.0")
    workspace = _toml(pkg_dir / "Cargo.toml")
    assert workspace["workspace"]["package"]["license"] == "Apache-2.0"
    assert _toml(pkg_dir / "pyproject.toml")["project"]["license"] == "Apache-2.0"


def test_new_pyproject_is_maturin_and_read_by_native_build(native_pkg):
    pyproject = _toml(native_pkg / "pyproject.toml")

    assert pyproject["build-system"] == {
        "requires": ["maturin>=1.16,<2"],
        "build-backend": native_build.NATIVE_BACKENDS["maturin"],
    }
    assert "hatch" not in pyproject["tool"]
    # Auto-detected from the backend: no redundant native table.
    assert "native" not in pyproject["tool"]["wads"]["ci"]["build"]
    # The rest of the wads template survives the merge.
    assert pyproject["project"]["name"] == NAME
    assert pyproject["tool"]["wads"]["ci"]["testing"]["python_versions"]
    assert "hypothesis" in pyproject["project"]["optional-dependencies"]["dev"]
    assert pyproject["project"]["requires-python"] == ">=3.10"  # the abi3-py310 floor
    pytest_opts = pyproject["tool"]["pytest"]["ini_options"]
    assert pytest_opts["testpaths"] == ["tests", NAME]  # the facade's doctests run
    assert "--doctest-modules" in pytest_opts["addopts"]

    nb = native_build.native_build_config(pyproject)
    assert nb.backend == "maturin"
    assert nb.smoke_import == f"{NAME}._core"
    assert nb.manifest_path == "rust/py/Cargo.toml"
    assert nb.maturin_args == native_build.DFLT_MATURIN_ARGS
    assert [t["name"] for t in nb.matrix()] == list(native_build.DFLT_NATIVE_TARGETS)


def test_combines_with_frontend_ts_as_two_independent_overlays(tmp_path, no_cargo):
    native_only, ts_only, both = (tmp_path / d / NAME for d in ("a", "b", "c"))
    _populate(native_only, native="maturin")
    _populate(ts_only, frontend="ts")
    _populate(both, native="maturin", frontend="ts")
    native_files, ts_files, both_files = map(_files, (native_only, ts_only, both))

    assert set(both_files) == set(native_files) | set(ts_files)
    # Every file is the one its own overlay writes, pyproject.toml included (maturin).
    for rel, content in native_files.items():
        assert both_files[rel] == content, rel
    for rel in set(ts_files) - set(native_files):
        assert both_files[rel] == ts_files[rel], rel
    assert any(rel.startswith("ts/") for rel in both_files)


# --- an existing package ------------------------------------------------------------


def test_whitespace_only_init_counts_as_new(tmp_path):
    (tmp_path / NAME).mkdir()
    (tmp_path / NAME / "__init__.py").write_text("\n  \n")
    attention = []
    result = profiles.apply_native(
        str(tmp_path),
        project_name=NAME,
        generate_lockfile=False,
        on_attention=lambda f, r: attention.append(f),
    )
    assert f"{NAME}/__init__.py" in result.added
    assert f"{NAME}/py.typed" in result.added
    assert f"{NAME}/__init__.py" not in attention


def test_a_real_init_is_kept_and_its_missing_lines_reported(tmp_path):
    (tmp_path / NAME).mkdir()
    init = tmp_path / NAME / "__init__.py"
    init.write_text('"""Existing API."""\n')
    attention = {}
    result = profiles.apply_native(
        str(tmp_path),
        project_name=NAME,
        generate_lockfile=False,
        on_attention=attention.__setitem__,
    )

    assert init.read_text() == '"""Existing API."""\n'
    assert f"{NAME}/__init__.py" in result.skipped
    assert not (tmp_path / NAME / "py.typed").exists()  # no typing claim for old code
    reason = attention[f"{NAME}/__init__.py"]
    assert f"from {NAME} import _core" in reason
    assert "def hamming(a: str, b: str) -> int:" in reason
    assert "Existing API" not in reason  # the template's docstring is not imposed


def _apply_by_hand(pkg_dir: Path, reported: dict) -> None:
    """Do what the report says, as a person would: no wads merge function involved."""
    import tomli_w

    init = pkg_dir / NAME / "__init__.py"
    init.write_text(
        init.read_text() + "\n" + reported[f"{NAME}/__init__.py"].split("\n", 1)[1]
    )

    toml_text = reported["pyproject.toml"].split("\n", 1)[1]
    required = toml_text.split("# Recommended")[0]
    assert required.startswith("# Required")
    pyproject_path = pkg_dir / "pyproject.toml"
    data = _toml(pyproject_path)
    if "# [build-system] replaces yours." in required:
        data.pop("build-system")
    if "# [tool.hatch]" in required:
        data["tool"].pop("hatch")

    def add(dst, src):
        for key, value in src.items():
            if isinstance(value, dict):
                add(dst.setdefault(key, {}), value)
            elif isinstance(value, list):
                dst.setdefault(key, []).extend(value)
            else:
                dst[key] = value

    add(data, tomllib.loads(required))
    pyproject_path.write_text(tomli_w.dumps(data))


@pytest.fixture
def existing_then_native(tmp_path, attention) -> tuple:
    """An ordinary package with its own API, then ``--native maturin`` over it."""
    pkg_dir = tmp_path / NAME
    _populate(pkg_dir)
    (pkg_dir / NAME / "__init__.py").write_text('"""Existing API."""\n\nANSWER = 42\n')
    before = (pkg_dir / "pyproject.toml").read_bytes()
    attention.clear()
    _populate(pkg_dir, native="maturin")
    return pkg_dir, before, dict(attention)


def test_existing_files_are_kept_and_the_gaps_reported(no_cargo, existing_then_native):
    pkg_dir, before, reported = existing_then_native

    assert (pkg_dir / "pyproject.toml").read_bytes() == before
    assert "ANSWER = 42" in (pkg_dir / NAME / "__init__.py").read_text()
    assert (pkg_dir / "rust/py/Cargo.toml").is_file()
    todo = reported["pyproject.toml"]
    assert 'build-backend = "maturin"' in todo
    assert f'module-name = "{NAME}._core"' in todo
    assert "[tool.hatch]" in todo  # its include/exclude rules must move over


def test_the_report_applied_by_hand_settles_the_switch(no_cargo, existing_then_native):
    pkg_dir, _, reported = existing_then_native
    _apply_by_hand(pkg_dir, reported)
    pyproject = _toml(pkg_dir / "pyproject.toml")

    required, _ = profiles.native_pyproject_gaps(pyproject, NAME)
    assert required == {}
    assert profiles.native_facade_todo(str(pkg_dir), NAME) == ""
    assert native_build.native_build_config(pyproject).smoke_import == f"{NAME}._core"
    assert "hatch" not in pyproject["tool"]


def _toolchain_ready(pkg_dir: Path):
    """cargo, with the pinned toolchain installed (never downloaded here), or None."""
    cargo = shutil.which("cargo") or os.path.expanduser("~/.cargo/bin/cargo")
    if not os.path.isfile(cargo):
        return None
    proc = subprocess.run(
        [cargo, "--version"],
        cwd=pkg_dir,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "RUSTUP_AUTO_INSTALL": "0"},
    )
    return cargo if proc.returncode == 0 else None


def test_the_report_applied_by_hand_builds_and_passes(existing_then_native):
    """The full loop: report -> hand edits -> editable build -> the scaffold's tests.

    Skipped without uv, cargo or the pinned toolchain; needs the network (PyPI, crates).
    """
    pkg_dir, _, reported = existing_then_native
    cargo, uv = _toolchain_ready(pkg_dir), shutil.which("uv")
    if not (cargo and uv):
        pytest.skip("needs uv, cargo and the pinned Rust toolchain")
    assert (pkg_dir / "Cargo.lock").is_file(), reported.get("Cargo.lock")
    _apply_by_hand(pkg_dir, reported)
    env = {
        **os.environ,
        "PATH": os.pathsep.join([str(Path(cargo).parent), os.environ["PATH"]]),
    }
    for var in ("VIRTUAL_ENV", "PYTHONPATH", "UV_CONSTRAINT", "PIP_CONSTRAINT"):
        env.pop(var, None)

    def run(*cmd, timeout=900):
        proc = subprocess.run(
            cmd, cwd=pkg_dir, env=env, capture_output=True, text=True, timeout=timeout
        )
        assert proc.returncode == 0, (cmd, proc.stdout[-2000:], proc.stderr[-2000:])
        return proc

    run(uv, "venv", "-q", "--python", f"{sys.version_info[0]}.{sys.version_info[1]}")
    python = (
        pkg_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    run(uv, "pip", "install", "-q", "--python", str(python), "-e", ".[dev]")
    out = run(str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider").stdout
    assert " passed" in out and "failed" not in out
    assert (
        run(str(python), "-c", f"import {NAME}; print({NAME}.ANSWER)").stdout.strip()
        == "42"
    )


def test_a_maturin_pyproject_is_not_told_to_replace_its_build_system():
    pyproject = {
        "build-system": {"requires": ["maturin>=1.9.4,<2"], "build-backend": "maturin"},
        "project": {"name": NAME},
        "tool": {"wads": {"ci": {"build": {"native": False}}}},
    }
    required, recommended = profiles.native_pyproject_gaps(pyproject, NAME)

    assert "build-system" not in required
    assert recommended["build-system"]["requires"] == ["maturin>=1.16,<2"]
    # An explicit `native = false` is the repo's decision: nothing mentions it.
    todo = profiles.native_pyproject_todo(pyproject, NAME)
    assert "native" not in todo.replace("--native", "")


# --- failure modes ------------------------------------------------------------------


def test_bad_name_or_backend_fails_before_writing(tmp_path):
    bad_name = tmp_path / "Not-Importable"
    with pytest.raises(ValueError, match="importable name"):
        _populate(bad_name, native="maturin")
    assert list(bad_name.iterdir()) == []

    with pytest.raises(ValueError, match="Unknown native backend 'cmake'"):
        _populate(tmp_path / NAME, native="cmake")
    assert list((tmp_path / NAME).iterdir()) == []


def test_apply_native_reports_what_it_cannot_settle(tmp_path, no_cargo):
    attention = {}
    result = profiles.apply_native(
        str(tmp_path), project_name=NAME, on_attention=attention.__setitem__
    )

    assert "Cargo.lock" not in result.added
    assert "cargo not found" in attention["Cargo.lock"]
    assert "--locked" in attention["Cargo.lock"]
    assert "target" in attention[".gitignore"] and "*.so" in attention[".gitignore"]


def test_a_missing_pinned_toolchain_is_reported_not_installed(tmp_path, monkeypatch):
    """The lockfile command runs with auto-install off and says how to install."""
    fake = tmp_path / "bin" / "cargo"
    fake.parent.mkdir()
    fake.write_text(
        "#!/bin/sh\n"
        'if [ "$RUSTUP_AUTO_INSTALL" = "0" ]; then\n'
        "  echo \"error: toolchain '1.99-x' is not installed\" >&2; exit 1\n"
        "fi\n"
        "echo downloading >&2; exit 0\n"
    )
    fake.chmod(0o755)
    if os.name == "nt":
        pytest.skip("POSIX shell script stands in for cargo")
    monkeypatch.setattr(profiles, "_find_executable", lambda name: str(fake))
    attention = {}
    profiles.apply_native(
        str(tmp_path / "pkg"), project_name=NAME, on_attention=attention.__setitem__
    )
    assert "rustup toolchain install" in attention["Cargo.lock"]


def test_an_absent_pinned_toolchain_stops_cargo_from_running(tmp_path, monkeypatch):
    """rustup < 1.28 ignores RUSTUP_AUTO_INSTALL, so the pin is checked before cargo."""
    if os.name == "nt":
        pytest.skip("POSIX shell scripts stand in for rustup and cargo")
    bin_dir, ran = tmp_path / "bin", tmp_path / "cargo-ran"
    bin_dir.mkdir()
    (bin_dir / "rustup").write_text(
        "#!/bin/sh\necho 'stable-x86_64-unknown-linux-gnu (default)'\n"
    )
    (bin_dir / "cargo").write_text(f"#!/bin/sh\ntouch {ran}\n")
    for tool in ("rustup", "cargo"):
        (bin_dir / tool).chmod(0o755)
    monkeypatch.setattr(profiles, "_find_executable", lambda name: str(bin_dir / name))
    attention = {}
    profiles.apply_native(
        str(tmp_path / "pkg"), project_name=NAME, on_attention=attention.__setitem__
    )

    assert not ran.exists(), "cargo ran although the pinned toolchain is absent"
    assert "rustup toolchain install" in attention["Cargo.lock"]


def _with_licence(pkg_dir: Path, *, project_license=None, classifiers=(), text=None):
    """An existing package whose licence is declared the given ways (and only those)."""
    import tomli_w

    _populate(pkg_dir)
    data = _toml(pkg_dir / "pyproject.toml")
    data["project"].pop("license", None)
    if project_license is not None:
        data["project"]["license"] = project_license
    if classifiers:
        data["project"]["classifiers"] = list(classifiers)
    (pkg_dir / "pyproject.toml").write_text(tomli_w.dumps(data))
    (pkg_dir / "LICENSE").unlink()
    if text is not None:
        (pkg_dir / "LICENSE").write_text(text)


@pytest.mark.parametrize(
    "declared",
    [
        {"project_license": {"file": "LICENSE"}, "text": "license_body"},
        {"text": "license_body"},  # no license key at all: the root LICENSE file
        {"classifiers": ["License :: OSI Approved :: Apache Software License"]},
        {"project_license": {"text": "apache-2.0"}},
    ],
)
def test_the_crates_take_the_licence_however_the_package_declares_it(
    tmp_path, no_cargo, declared
):
    from wads.licensing import license_body

    pkg_dir = tmp_path / NAME
    if declared.get("text") == "license_body":
        declared = {**declared, "text": license_body("apache-2.0")}
    _with_licence(pkg_dir, **declared)
    _populate(pkg_dir, native="maturin")

    workspace = _toml(pkg_dir / "Cargo.toml")["workspace"]["package"]
    assert workspace["license"] == "Apache-2.0"


def test_an_undeterminable_licence_is_omitted_and_reported(
    tmp_path, no_cargo, attention
):
    pkg_dir = tmp_path / NAME
    _with_licence(
        pkg_dir,
        project_license={"file": "LICENSE"},
        text="Copyright (c) 2026 Someone. All rights reserved.\n",
    )
    attention.clear()
    _populate(pkg_dir, native="maturin")
    reported = dict(attention)

    assert "license" not in _toml(pkg_dir / "Cargo.toml")["workspace"]["package"]
    for member in ("core", "py"):
        assert "license" not in _toml(pkg_dir / f"rust/{member}/Cargo.toml")["package"]
    assert "could not be determined" in reported["Cargo.toml"]
    assert "MIT" not in (pkg_dir / "Cargo.toml").read_text()
    cargo = _toolchain_ready(pkg_dir)
    if cargo:  # and cargo still reads the workspace
        proc = subprocess.run(
            [cargo, "metadata", "--no-deps", "--format-version", "1"],
            cwd=pkg_dir,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "RUSTUP_AUTO_INSTALL": "0"},
        )
        assert proc.returncode == 0, proc.stderr


def test_write_errors_reach_the_tracker(tmp_path, no_cargo, monkeypatch):
    errors = []
    monkeypatch.setattr(
        populate.PopulateTracker, "error", lambda self, f, e: errors.append(f)
    )
    pkg_dir = tmp_path / NAME
    (pkg_dir / "rust").mkdir(parents=True)
    (pkg_dir / "rust" / "core").write_text("a file where a folder must go")
    _populate(pkg_dir, native="maturin")
    assert "rust/core/Cargo.toml" in errors


def test_apply_native_skips_existing_files(tmp_path):
    (tmp_path / "Cargo.toml").write_text("# mine\n")
    result = profiles.apply_native(
        str(tmp_path), project_name=NAME, generate_lockfile=False, on_attention=None
    )
    assert "Cargo.toml" in result.skipped
    assert (tmp_path / "Cargo.toml").read_text() == "# mine\n"


# --- registry and packaging ---------------------------------------------------------


def test_every_native_profile_is_a_backend_ci_can_build():
    for name, profile in profiles.NATIVE_PROFILES.items():
        fragment = profiles.native_pyproject_fragment(NAME, backend=name)
        assert name in native_build.NATIVE_BACKENDS, name
        assert (
            fragment["build-system"]["build-backend"]
            == native_build.NATIVE_BACKENDS[name]
        )
        tpl = Path(profile.template_dir)
        assert (tpl / profile.facade).is_file()
        assert all((tpl / p).is_file() for p in profile.new_package_only)


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
    cargo = _toolchain_ready(native_pkg)
    if cargo is None:
        pytest.skip("cargo or the pinned toolchain not installed")
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
    assert proc.returncode == 0, proc.stderr
    meta = json.loads(proc.stdout)

    assert {p["name"] for p in meta["packages"]} == {f"{KEBAB}-core", f"{KEBAB}-py"}
    assert native_build.cargo_test_args(meta, binding_manifest=str(manifest)) == [
        "--workspace",
        "--exclude",
        f"{KEBAB}-py",
    ]
