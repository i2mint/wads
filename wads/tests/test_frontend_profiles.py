"""Tests for the frontend profile registry (issue #39).

Covers:
- the ``js`` profile stays byte-compatible with the pre-#39 overlay (golden
  files under ``wads/tests/data/golden/frontend_js/``);
- the ``ts`` single-package profile;
- the ``ts-monorepo`` profile (pnpm workspaces + turbo);
- multiple components (``js`` + ``ts``) coexisting without workflow collision;
- the registry surface and the ``populate --frontend`` CLI integration.

The ``js`` golden anchors the back-compat acceptance; if you *intentionally*
change ``js`` output, regenerate the goldens and review the diff in the PR.
"""

import json
import subprocess
from pathlib import Path

import pytest

from wads.npm_config import NpmCIConfig
from wads.profiles import (
    FRONTEND_PROFILES,
    FrontendProfile,
    apply_frontend,
    get_frontend_profile,
    register_frontend_profile,
    _workflow_basename,
)
from wads.populate import populate_pkg_dir

GOLDEN_DIR = Path(__file__).parent / "data" / "golden" / "frontend_js"


def _git_init(pkg_dir, url):
    subprocess.run(["git", "init", "-q"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=pkg_dir, check=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=pkg_dir, check=True)


# --- registry ------------------------------------------------------------------


def test_registry_has_builtin_profiles():
    assert set(FRONTEND_PROFILES) >= {"js", "ts", "ts-monorepo"}
    assert get_frontend_profile("js").default_subdir == "js"
    assert get_frontend_profile("ts").default_subdir == "ts"
    assert get_frontend_profile("ts-monorepo").default_package_manager == "pnpm"


def test_unknown_profile_is_informative():
    with pytest.raises(ValueError, match="Unknown frontend profile 'nope'"):
        get_frontend_profile("nope")


def test_workflow_basename_scheme():
    # js is the back-compat anchor; everything else is per-subdir.
    assert _workflow_basename("js") == "npm-ci.yml"
    assert _workflow_basename("ts") == "npm-ci-ts.yml"
    assert _workflow_basename("frontend") == "npm-ci-frontend.yml"


def test_register_custom_profile_roundtrip():
    sentinel = FrontendProfile(
        name="_test_custom",
        default_subdir="x",
        default_package_manager="npm",
        artifacts=lambda ctx: [],
    )
    try:
        register_frontend_profile(sentinel)
        assert get_frontend_profile("_test_custom") is sentinel
    finally:
        FRONTEND_PROFILES.pop("_test_custom", None)


# --- js profile: byte-compatible back-compat anchor ----------------------------


def test_js_profile_matches_golden(tmp_path):
    apply_frontend(
        str(tmp_path),
        profile="js",
        project_name="mypkg",
        description="A widget",
        license="apache-2.0",
    )
    for golden in GOLDEN_DIR.rglob("*"):
        if not golden.is_file():
            continue
        rel = golden.relative_to(GOLDEN_DIR)
        produced = (tmp_path / rel).read_text()
        assert produced == golden.read_text(), f"js output drifted for {rel}"


def test_js_via_apply_frontend_default_profile(tmp_path):
    # profile defaults to "js"
    result = apply_frontend(str(tmp_path), project_name="mypkg")
    assert "js/package.json" in result.added
    assert ".github/workflows/npm-ci.yml" in result.added


# --- ts single-package profile -------------------------------------------------


def test_ts_profile_writes_expected_files(tmp_path):
    result = apply_frontend(str(tmp_path), profile="ts", project_name="widget")
    assert set(result.added) == {
        "ts/package.json",
        "ts/tsconfig.json",
        "ts/tsconfig.test.json",
        "ts/src/index.ts",
        "ts/src/index.test.ts",
        ".github/workflows/npm-ci-ts.yml",
    }

    pkg_json = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert pkg_json["type"] == "module"
    assert pkg_json["scripts"]["test"] == "vitest run"
    assert "tsup" in pkg_json["scripts"]["build"]
    # esbuild build-script allowlist so pnpm >=10 can build tsup's esbuild (#41).
    assert pkg_json["pnpm"]["onlyBuiltDependencies"] == ["esbuild"]

    # A passing starter test ships so the `test` step is green out of the box
    # (vitest exits 1 with no test files, issue #41).
    test_src = (tmp_path / "ts" / "src" / "index.test.ts").read_text()
    assert "vitest" in test_src and "hello" in test_src

    # Same wads.ci SSOT + publish model as js: validate-always, publish-opt-in.
    cfg = NpmCIConfig(pkg_json)
    assert cfg.subdir == "ts"
    assert cfg.publish_enabled is False
    assert cfg.publish_marker == "[publish-npm]"
    assert cfg.provenance is True

    tsconfig = json.loads((tmp_path / "ts" / "tsconfig.json").read_text())
    assert tsconfig["compilerOptions"]["strict"] is True

    workflow = (tmp_path / ".github" / "workflows" / "npm-ci-ts.yml").read_text()
    assert "name: NPM CI (ts)" in workflow
    assert "package-dir: ts" in workflow
    assert "i2mint/wads/.github/workflows/npm-ci.yml@master" in workflow
    assert "<<" not in workflow and ">>" not in workflow


def test_ts_profile_pnpm_package_manager(tmp_path):
    apply_frontend(
        str(tmp_path), profile="ts", project_name="widget", package_manager="pnpm"
    )
    pkg_json = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert NpmCIConfig(pkg_json).package_manager == "pnpm"


@pytest.mark.parametrize(
    "profile, pkg_dir", [("ts", "ts"), ("ts-monorepo", "ts/packages/core")]
)
def test_ts_types_resolve_per_condition(tmp_path, profile, pkg_dir):
    """CommonJS consumers get the .d.cts tsup builds, not the ESM .d.ts (#215)."""
    apply_frontend(str(tmp_path), profile=profile, project_name="widget")
    pkg_json = json.loads((tmp_path / pkg_dir / "package.json").read_text())
    exports = pkg_json["exports"]["."]
    assert exports["import"] == {
        "types": "./dist/index.d.ts",
        "default": "./dist/index.js",
    }
    assert exports["require"] == {
        "types": "./dist/index.d.cts",
        "default": "./dist/index.cjs",
    }
    assert "types" not in exports  # no single entry masquerading for both


@pytest.mark.parametrize(
    "profile, pkg_dir", [("ts", "ts"), ("ts-monorepo", "ts/packages/core")]
)
def test_ts_tests_typechecked_apart_from_library(tmp_path, profile, pkg_dir):
    """Tests leave the library build; a test tsconfig checks them with Node types."""
    apply_frontend(str(tmp_path), profile=profile, project_name="widget")
    lib = json.loads((tmp_path / pkg_dir / "tsconfig.json").read_text())
    assert "src/**/*.test.ts" in lib["exclude"]
    assert lib["compilerOptions"]["types"] == []  # no Node globals in src/
    test_cfg = json.loads((tmp_path / pkg_dir / "tsconfig.test.json").read_text())
    assert test_cfg["extends"] == "./tsconfig.json"
    assert test_cfg["compilerOptions"]["types"] == ["node"]
    assert "src/**/*.test.ts" not in test_cfg["exclude"]
    pkg_json = json.loads((tmp_path / pkg_dir / "package.json").read_text())
    assert "tsc -p tsconfig.test.json" in pkg_json["scripts"]["lint"]
    assert "@types/node" in pkg_json["devDependencies"]


@pytest.mark.parametrize(
    "profile, pkg_dir",
    [("js", "js"), ("ts", "ts"), ("ts-monorepo", "ts/packages/core")],
)
def test_root_license_lands_in_the_published_package_dir(tmp_path, profile, pkg_dir):
    """npm packs the LICENSE beside package.json; the root one is outside it (#215)."""
    result = apply_frontend(str(tmp_path), profile=profile, project_name="widget")
    assert f"{pkg_dir}/LICENSE" not in result.added  # no root licence, no copy

    (tmp_path / "LICENSE").write_text("MIT License\n\nCopyright (c) someone\n")
    result = apply_frontend(str(tmp_path), profile=profile, project_name="widget")
    assert result.added == [f"{pkg_dir}/LICENSE"]  # everything else already there
    assert (tmp_path / pkg_dir / "LICENSE").read_text() == (
        tmp_path / "LICENSE"
    ).read_text()


def test_package_license_follows_a_changed_root_license(tmp_path):
    """The copy is derived: a re-run rewrites it, never ships the old licence."""
    (tmp_path / "LICENSE").write_text("MIT License\n")
    apply_frontend(str(tmp_path), profile="ts", project_name="widget")
    (tmp_path / "LICENSE").write_text("Apache License 2.0\n")
    result = apply_frontend(str(tmp_path), profile="ts", project_name="widget")
    assert "ts/LICENSE" in result.added
    assert (tmp_path / "ts" / "LICENSE").read_text() == "Apache License 2.0\n"
    # an unchanged copy is left alone
    result = apply_frontend(str(tmp_path), profile="ts", project_name="widget")
    assert "ts/LICENSE" in result.skipped


def test_root_license_under_another_name_is_copied_as_is(tmp_path):
    (tmp_path / "LICENSE.md").write_text("MIT\n")
    result = apply_frontend(str(tmp_path), profile="ts", project_name="widget")
    assert "ts/LICENSE.md" in result.added


# --- ts-monorepo profile -------------------------------------------------------


def test_ts_monorepo_profile_structure(tmp_path):
    result = apply_frontend(str(tmp_path), profile="ts-monorepo", project_name="widget")
    assert set(result.added) == {
        "ts/package.json",
        "ts/pnpm-workspace.yaml",
        "ts/turbo.json",
        "ts/tsconfig.base.json",
        "ts/packages/core/package.json",
        "ts/packages/core/tsconfig.json",
        "ts/packages/core/tsconfig.test.json",
        "ts/packages/core/src/index.ts",
        "ts/packages/core/src/index.test.ts",
        ".github/workflows/npm-ci-ts.yml",
    }

    root = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert root["private"] is True
    assert root["packageManager"].startswith("pnpm@")
    assert NpmCIConfig(root).package_manager == "pnpm"
    # esbuild build-script allowlist for pnpm >=10 (#41).
    assert root["pnpm"]["onlyBuiltDependencies"] == ["esbuild"]
    assert NpmCIConfig(root).publish_enabled is False  # opt-in, same model

    workspace = (tmp_path / "ts" / "pnpm-workspace.yaml").read_text()
    assert "packages/*" in workspace

    pkg = json.loads(
        (tmp_path / "ts" / "packages" / "core" / "package.json").read_text()
    )
    assert pkg["name"] == "widget"

    # The monorepo stub calls the *monorepo* reusable workflow.
    workflow = (tmp_path / ".github" / "workflows" / "npm-ci-ts.yml").read_text()
    assert "i2mint/wads/.github/workflows/npm-ci-monorepo.yml@master" in workflow
    assert "<<" not in workflow and ">>" not in workflow


# --- multiple components coexist without collision -----------------------------


def test_js_and_ts_components_no_collision(tmp_path):
    apply_frontend(str(tmp_path), profile="js", project_name="widget")
    apply_frontend(str(tmp_path), profile="ts", project_name="widget")

    assert (tmp_path / "js" / "package.json").exists()
    assert (tmp_path / "ts" / "package.json").exists()
    workflows = sorted(p.name for p in (tmp_path / ".github" / "workflows").iterdir())
    assert workflows == ["npm-ci-ts.yml", "npm-ci.yml"]

    js_wf = (tmp_path / ".github" / "workflows" / "npm-ci.yml").read_text()
    ts_wf = (tmp_path / ".github" / "workflows" / "npm-ci-ts.yml").read_text()
    assert 'paths:\n      - "js/**"' in js_wf
    assert 'paths:\n      - "ts/**"' in ts_wf


# --- populate --frontend CLI integration --------------------------------------


def test_populate_frontend_ts(tmp_path):
    pkg_dir = tmp_path / "widget"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/widget")

    populate_pkg_dir(
        str(pkg_dir),
        description="Has a TS lib",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
        frontend="ts",
    )
    assert (pkg_dir / "pyproject.toml").exists()  # Python side untouched
    assert (pkg_dir / "ts" / "tsconfig.json").exists()
    assert (pkg_dir / ".github" / "workflows" / "npm-ci-ts.yml").exists()
    assert not (pkg_dir / "js").exists()
    # populate writes the root LICENSE first, so the npm tarball gets it too (#215)
    assert (pkg_dir / "ts" / "LICENSE").read_text() == (pkg_dir / "LICENSE").read_text()


def test_populate_frontend_multi(tmp_path):
    pkg_dir = tmp_path / "widget"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/widget")

    populate_pkg_dir(
        str(pkg_dir),
        description="JS and TS",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
        frontend="js,ts",
    )
    assert (pkg_dir / "js" / "package.json").exists()
    assert (pkg_dir / "ts" / "package.json").exists()
    assert (pkg_dir / ".github" / "workflows" / "npm-ci.yml").exists()
    assert (pkg_dir / ".github" / "workflows" / "npm-ci-ts.yml").exists()


def test_populate_with_npm_is_js_alias(tmp_path):
    pkg_dir = tmp_path / "widget"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/widget")

    populate_pkg_dir(
        str(pkg_dir),
        description="Legacy flag",
        root_url="https://github.com/myorg",
        version="0.1.0",
        verbose=False,
        with_npm=True,
    )
    assert (pkg_dir / "js" / "package.json").exists()
    assert (pkg_dir / ".github" / "workflows" / "npm-ci.yml").exists()




def _populate_ts_on_existing_python_pkg(tmp_path, pyproject, **kwargs):
    pkg_dir = tmp_path / "widget"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/widget")
    (pkg_dir / "pyproject.toml").write_text(pyproject)
    populate_pkg_dir(
        str(pkg_dir),
        root_url="https://github.com/myorg",
        verbose=False,
        frontend="ts",
        **kwargs,
    )
    return json.loads((pkg_dir / "ts" / "package.json").read_text())


_EXISTING = '[project]\nname = "widget"\nversion = "0.3.12"\ndescription = "Does widgets"\n'


def test_frontend_twin_of_an_existing_python_pkg_starts_at_its_version(tmp_path):
    """#224: the twin's package.json takes [project].version and description."""
    pkg = _populate_ts_on_existing_python_pkg(tmp_path, _EXISTING)
    assert pkg["version"] == "0.3.12"
    assert pkg["description"] == "Does widgets"
    # ...so a twin that opts into the polyglot version sync passes its guard
    from wads.version_sync import check_versions_agree

    check_versions_agree(
        tmp_path / "widget",
        {
            "project": {"version": "0.3.12"},
            "tool": {"wads": {"ci": {"version": {"sync": ["ts/package.json"]}}}},
        },
    )


def test_an_explicit_npm_version_wins_over_the_python_one(tmp_path):
    pkg = _populate_ts_on_existing_python_pkg(
        tmp_path, _EXISTING, npm_version="1.0.0", description="Mine"
    )
    assert pkg["version"] == "1.0.0"
    assert pkg["description"] == "Mine"


def test_a_description_with_quotes_keeps_package_json_valid(tmp_path):
    pkg = _populate_ts_on_existing_python_pkg(
        tmp_path,
        '[project]\nname = "widget"\nversion = "1.0.0"\ndescription = \'A "dol" for C:\\\\x\'\n',
    )
    assert pkg["description"] == 'A "dol" for C:\\\\x'


def test_a_dynamic_python_version_falls_back_to_the_default(tmp_path):
    pkg = _populate_ts_on_existing_python_pkg(
        tmp_path, '[project]\nname = "widget"\ndynamic = ["version"]\n'
    )
    assert pkg["version"] == "0.0.1"


# --- ts-package: a repo that is only a TypeScript package (#225) --------------


def test_ts_package_populate_writes_no_python_project(tmp_path):
    pkg_dir = tmp_path / "byok"
    pkg_dir.mkdir()
    populate_pkg_dir(
        str(pkg_dir),
        root_url="https://github.com/myorg",
        description="Keys, bring your own",
        verbose=False,
        frontend="ts-package",
    )
    written = {p.relative_to(pkg_dir).as_posix() for p in pkg_dir.rglob("*") if p.is_file()}
    assert {
        "LICENSE",
        "README.md",
        ".gitignore",
        ".gitattributes",
        "package.json",
        "tsconfig.json",
        "tsconfig.test.json",
        "src/index.ts",
        "src/index.test.ts",
        ".github/workflows/npm-ci.yml",
    } == written
    assert not (pkg_dir / "pyproject.toml").exists()
    assert not (pkg_dir / "byok").exists(), "no Python package directory"


def test_ts_package_files_sit_at_the_root_and_pin_node_22(tmp_path):
    apply_frontend(str(tmp_path), profile="ts-package", project_name="byok")
    pkg = json.loads((tmp_path / "package.json").read_text())
    assert pkg["engines"] == {"node": ">=22.12"}
    assert pkg["devDependencies"]["vitest"] == "^5"
    ci = pkg["wads"]["ci"]
    assert ci["subdir"] == "." and ci["nodeVersions"] == ["22", "24"]
    assert ci["publishNode"] == "24"


def test_ts_package_stub_has_no_path_filter_and_builds_the_root(tmp_path):
    apply_frontend(str(tmp_path), profile="ts-package", project_name="byok")
    stub = (tmp_path / ".github" / "workflows" / "npm-ci.yml").read_text()
    assert "paths:" not in stub
    assert "package-dir: ." in stub
    assert "\n  push:\n  pull_request:\n" in stub


def test_the_ts_profile_keeps_its_node_20_matrix_and_has_no_engines(tmp_path):
    """Only ts-package sets a Node floor; ``ts`` still runs where vitest 3 does."""
    apply_frontend(str(tmp_path), profile="ts", project_name="widget")
    pkg = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert "engines" not in pkg
    assert pkg["wads"]["ci"]["nodeVersions"] == ["20", "22", "24"]
    assert pkg["devDependencies"]["vitest"] == "^3"


def test_ts_package_does_not_copy_the_licence_onto_itself(tmp_path):
    (tmp_path / "LICENSE").write_text("MIT")
    res = apply_frontend(str(tmp_path), profile="ts-package", project_name="byok")
    assert "LICENSE" not in res.added
    assert (tmp_path / "LICENSE").read_text() == "MIT"


def test_populate_refuses_native_without_a_python_project(tmp_path):
    with pytest.raises(ValueError, match="native"):
        populate_pkg_dir(
            str(tmp_path), verbose=False, frontend="ts-package", native="maturin"
        )




def test_ts_package_cannot_be_mixed_with_other_profiles(tmp_path):
    for combo in ("ts-package,js", "ts,ts-package"):
        with pytest.raises(ValueError, match="cannot be combined"):
            populate_pkg_dir(str(tmp_path), verbose=False, frontend=combo)
    assert list(tmp_path.iterdir()) == [], "nothing written before the refusal"


def test_ts_package_readme_and_licence_name_the_package_and_its_owner(tmp_path):
    pkg_dir = tmp_path / "byok"
    pkg_dir.mkdir()
    populate_pkg_dir(
        str(pkg_dir),
        root_url="https://github.com/myorg",
        description="Keys",
        verbose=False,
        frontend="ts-package",
    )
    assert "npm install byok" in (pkg_dir / "README.md").read_text()
    assert "myorg" in (pkg_dir / "LICENSE").read_text()


def test_a_root_subdir_spelled_with_a_slash_is_normalised(tmp_path):
    res = apply_frontend(
        str(tmp_path), profile="ts-package", project_name="x", subdir="./"
    )
    assert "package.json" in res.added
    assert (tmp_path / ".github" / "workflows" / "npm-ci.yml").exists()


def test_a_profile_with_a_mistyped_context_default_is_refused():
    with pytest.raises(ValueError, match="engine_node"):
        register_frontend_profile(
            FrontendProfile(
                name="typo",
                default_subdir="x",
                default_package_manager="npm",
                artifacts=lambda ctx: [],
                context_defaults={"engine_node": ">=22"},
            )
        )
    assert "typo" not in FRONTEND_PROFILES


# --- repository field and the monorepo vitest range (#233) --------------------


def test_ts_package_json_carries_the_repository_when_the_url_is_known(tmp_path):
    apply_frontend(
        str(tmp_path),
        profile="ts",
        project_name="widget",
        repository_url="https://github.com/myorg/widget",
    )
    pkg = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert pkg["repository"] == {
        "type": "git",
        "url": "git+https://github.com/myorg/widget.git",
        "directory": "ts",
    }


def test_a_root_package_has_no_repository_directory(tmp_path):
    apply_frontend(
        str(tmp_path),
        profile="ts-package",
        project_name="byok",
        repository_url="https://github.com/myorg/byok.git",
    )
    pkg = json.loads((tmp_path / "package.json").read_text())
    assert pkg["repository"] == {
        "type": "git",
        "url": "git+https://github.com/myorg/byok.git",
    }


def test_no_repository_field_without_a_url(tmp_path):
    apply_frontend(str(tmp_path), profile="ts", project_name="widget")
    assert "repository" not in json.loads((tmp_path / "ts" / "package.json").read_text())


def test_the_monorepo_package_gets_the_repository_and_the_shared_vitest_range(tmp_path):
    apply_frontend(
        str(tmp_path),
        profile="ts-monorepo",
        project_name="mono",
        repository_url="https://github.com/myorg/mono",
    )
    pkg = json.loads((tmp_path / "ts" / "packages" / "core" / "package.json").read_text())
    assert pkg["repository"]["directory"] == "ts/packages/core"
    assert pkg["devDependencies"]["vitest"] == "^3"


def test_populate_passes_the_repository_url_to_the_component(tmp_path):
    pkg_dir = tmp_path / "widget"
    pkg_dir.mkdir()
    _git_init(pkg_dir, "https://github.com/myorg/widget")
    populate_pkg_dir(
        str(pkg_dir),
        root_url="https://github.com/myorg",
        verbose=False,
        frontend="ts",
    )
    pkg = json.loads((pkg_dir / "ts" / "package.json").read_text())
    assert pkg["repository"]["url"] == "git+https://github.com/myorg/widget.git"


def test_the_repository_comes_from_the_git_remote_when_no_root_url_is_given(tmp_path):
    for frontend in ("ts", "ts-package"):
        pkg_dir = tmp_path / frontend / "byok"
        pkg_dir.mkdir(parents=True)
        _git_init(pkg_dir, "git@github.com:myorg/byok.git")
        populate_pkg_dir(str(pkg_dir), verbose=False, frontend=frontend)
        manifest = pkg_dir / ("ts" if frontend == "ts" else ".") / "package.json"
        url = json.loads(manifest.read_text())["repository"]["url"]
        assert url == "git+https://github.com/myorg/byok.git"


def test_a_monorepo_at_the_repo_root_names_its_package_directory(tmp_path):
    apply_frontend(
        str(tmp_path),
        profile="ts-monorepo",
        project_name="mono",
        subdir=".",
        repository_url="https://github.com/myorg/mono",
    )
    pkg = json.loads((tmp_path / "packages" / "core" / "package.json").read_text())
    assert pkg["repository"]["directory"] == "packages/core"


def test_a_url_with_a_quote_cannot_break_package_json(tmp_path):
    apply_frontend(
        str(tmp_path),
        profile="ts",
        project_name="w",
        repository_url='https://github.com/o/r"x',
    )
    pkg = json.loads((tmp_path / "ts" / "package.json").read_text())
    assert pkg["repository"]["url"].endswith('r"x.git')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
