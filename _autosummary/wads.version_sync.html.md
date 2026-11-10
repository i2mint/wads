# wads.version_sync

One version number for a Python package and its npm twin (i2mint/wads#210).

A repo that publishes the same code to PyPI and npm lists, in `pyproject.toml`,
the manifests that carry the Python version too:

```default
[tool.wads.ci.version]
sync = ["ts/package.json"]
```

Two things follow, both in uv-ci:

- **Release:** right after the publish job bumps `[project].version`, it writes
  that version into each listed manifest (and the `package-lock.json` beside
  it), so the bump commit carries all of them.
- **Check:** the setup job fails when a listed manifest’s version differs from
  `[project].version`, so a hand edit on one side shows up before a release.

And one in npm-ci: npm packs the commit that was pushed, which comes *before* the
bump commit of the Python release the same push cuts, so it would carry the
previous release’s number with newer code. [`npm_publish_refusal()`](#wads.version_sync.npm_publish_refusal) refuses
that publish (see its docstring).

Only `package.json` is supported: a Rust crate usually keeps its own version
line. This module imports only the standard library (and `wads.ci_config`, which
does too), because the CI scripts load it by path from the wads checkout
(`wads/scripts/_checkout_import.py`).

### Module Attributes

| [`SYNCABLE_MANIFESTS`](#wads.version_sync.SYNCABLE_MANIFESTS)   | Manifest file names `[tool.wads.ci.version].sync` may list.                        |
|-----------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`NPM_LOCKFILE`](#wads.version_sync.NPM_LOCKFILE)         | The lockfile npm keeps beside a `package.json`; its own version fields follow.     |
| [`SEMVER`](#wads.version_sync.SEMVER)               | A semver version, the only kind npm accepts (PEP 440 forms like `1.0rc1` are not). |

### Functions

| [`caller_workflow_path`](#wads.version_sync.caller_workflow_path)(workflow_ref)              | The repo-relative workflow file in `github.workflow_ref`; `None` if there is none.   |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`check_versions_agree`](#wads.version_sync.check_versions_agree)(repo_dir, pyproject_data)  | Raise `ValueError` naming every listed manifest whose version differs.               |
| [`npm_publish_refusal`](#wads.version_sync.npm_publish_refusal)(pyproject_data, ...[, ...]) | Why npm-ci must not publish `package_dir` from this push, or `None` when it may.     |
| [`pypi_release_expected`](#wads.version_sync.pypi_release_expected)(pyproject_data, subject)  | Whether uv-ci's publish job releases to PyPI for a push with this commit `subject`.  |
| [`set_json_version`](#wads.version_sync.set_json_version)(path, version)                 | Write `version` into one `package.json` or `package-lock.json`, as npm would.        |
| [`set_manifest_version`](#wads.version_sync.set_manifest_version)(manifest, version)         | Write `version` into `manifest` and the npm lockfile beside it.                      |
| [`static_project_version`](#wads.version_sync.static_project_version)(pyproject_data)          | `[project].version`, which `sync` needs: CI bumps and copies that line.              |
| [`sync_files`](#wads.version_sync.sync_files)(pyproject_data)                      | The manifests `[tool.wads.ci.version].sync` lists, validated.                        |
| [`sync_version`](#wads.version_sync.sync_version)(repo_dir, files, version)          | Write `version` into every listed manifest under `repo_dir`.                         |
| [`version_mismatches`](#wads.version_sync.version_mismatches)(repo_dir, pyproject_data)    | `(path, its version, [project].version)` for each listed manifest that differs.      |

### wads.version_sync.NPM_LOCKFILE *= 'package-lock.json'*

The lockfile npm keeps beside a `package.json`; its own version fields follow.

### wads.version_sync.SEMVER *= re.compile('^(0|[1-9]\\\\d\*)\\\\.(0|[1-9]\\\\d\*)\\\\.(0|[1-9]\\\\d\*)(?:-[0-9A-Za-z-]+(?:\\\\.[0-9A-Za-z-]+)\*)?(?:\\\\+[0-9A-Za-z-]+(?:\\\\.[0-9A-Za-z-]+)\*)?$')*

A semver version, the only kind npm accepts (PEP 440 forms like `1.0rc1` are not).

### wads.version_sync.SYNCABLE_MANIFESTS *= ('package.json',)*

Manifest file names `[tool.wads.ci.version].sync` may list.

### wads.version_sync.caller_workflow_path(workflow_ref)

The repo-relative workflow file in `github.workflow_ref`; `None` if there is none.

In a reusable workflow, `github.workflow_ref` names the *caller’s* file
(`owner/repo/.github/workflows/npm-ci.yml@refs/heads/main`): the npm stub.

```pycon
>>> caller_workflow_path("i2mint/demo/.github/workflows/npm-ci.yml@refs/heads/main")
'.github/workflows/npm-ci.yml'
>>> caller_workflow_path("") is None
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.version_sync.check_versions_agree(repo_dir, pyproject_data)

Raise `ValueError` naming every listed manifest whose version differs.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.version_sync.npm_publish_refusal(pyproject_data, package_dir, changed_files, subject, , also_inside=())

Why npm-ci must not publish `package_dir` from this push, or `None` when it may.

It refuses only when all of these hold:

- `[tool.wads.ci.version].sync` lists a manifest inside `package_dir` (so
  its version comes from the Python release);
- this push also cuts a PyPI release ([`pypi_release_expected()`](#wads.version_sync.pypi_release_expected)), whose
  bump commit comes after the commit npm packs;
- the push changes files outside `package_dir` (`changed_files`, repo
  relative). A push that changes only the npm package publishes the version
  the last Python release wrote. When the npm package is the repo root,
  every change counts as outside it. Files in `also_inside` (the npm stub’s
  own workflow file, which the Python stub’s paths filter ignores) count as
  inside.

```pycon
>>> data = {"project": {"version": "1.2.3"},
...         "tool": {"wads": {"ci": {"version": {"sync": ["ts/package.json"]}}}}}
>>> npm_publish_refusal(data, "ts", ["ts/src/a.ts"], "Release [publish-npm]") is None
True
>>> print(npm_publish_refusal(data, "ts", ["ts/src/a.ts", "pkg/b.py"], "Release [publish-npm]"))
This push also releases the Python package, so npm would get the previous release's number (1.2.3) with newer code: uv-ci writes the new number into ts/package.json in its bump commit, after this one. Publish npm from a commit that changes only ts/ (or carries the skip-publish marker '[skip publish]'). Changed outside ts/: pkg/b.py
>>> npm_publish_refusal(data, "ts", ["pkg/b.py"], "Release [publish-npm] [skip publish]") is None
True
>>> npm_publish_refusal({}, "ts", ["pkg/b.py"], "Release [publish-npm]") is None
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.version_sync.pypi_release_expected(pyproject_data, subject)

Whether uv-ci’s publish job releases to PyPI for a push with this commit `subject`.

Mirrors uv-ci’s gates (markers match the subject case-insensitively, like
GitHub’s `contains()`): the skip-ci and skip-publish markers suppress the
release; with `[tool.wads.ci.publish].enabled = false` only the publish
marker cuts one; in on-demand trigger mode only the deploy marker does, or
the run-ci marker when `run_ci_publishes` is on.

```pycon
>>> pypi_release_expected({}, "Fix a typo")
True
>>> pypi_release_expected({}, "Fix a typo [Skip Publish]")
False
>>> off = {"tool": {"wads": {"ci": {"publish": {"enabled": False}}}}}
>>> pypi_release_expected(off, "Fix a typo"), pypi_release_expected(off, "Fix [publish]")
(False, True)
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### wads.version_sync.set_json_version(path, version)

Write `version` into one `package.json` or `package-lock.json`, as npm would.

A lockfile carries the version twice: at the top and on its root package
(`packages[""]`); dependencies’ versions are left alone. Everything else in
the file, and its layout, is kept. Used by the release ([`set_manifest_version()`](#wads.version_sync.set_manifest_version))
and by the git-commit action’s push-back conflict resolver.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.version_sync.set_manifest_version(manifest, version)

Write `version` into `manifest` and the npm lockfile beside it.

Returns the files written. Refuses a version npm would reject, before writing.

```pycon
>>> import tempfile
>>> d = Path(tempfile.mkdtemp())
>>> _ = (d / "package.json").write_text('{\n  "name": "x",\n  "version": "0.0.1"\n}\n')
>>> [p.name for p in set_manifest_version(d / "package.json", "0.0.2")]
['package.json']
>>> print((d / "package.json").read_text(), end="")
{
  "name": "x",
  "version": "0.0.2"
}
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### wads.version_sync.static_project_version(pyproject_data)

`[project].version`, which `sync` needs: CI bumps and copies that line.

```pycon
>>> static_project_version({"project": {"version": "1.2.3"}})
'1.2.3'
>>> static_project_version({"project": {"dynamic": ["version"]}})
Traceback (most recent call last):
  ...
ValueError: [tool.wads.ci.version].sync needs a static [project].version in pyproject.toml, and this project's version is dynamic. Make it static, or remove the sync key (and keep the npm version by hand).
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.version_sync.sync_files(pyproject_data)

The manifests `[tool.wads.ci.version].sync` lists, validated.

```pycon
>>> sync_files({"tool": {"wads": {"ci": {"version": {"sync": ["ts/package.json"]}}}}})
['ts/package.json']
>>> sync_files({})
[]
>>> sync_files({"tool": {"wads": {"ci": {"version": {"sync": ["rust/core/Cargo.toml"]}}}}})
Traceback (most recent call last):
  ...
ValueError: [tool.wads.ci.version].sync: 'rust/core/Cargo.toml' is not one of ('package.json',); a Rust crate keeps its own version line.
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.version_sync.sync_version(repo_dir, files, version)

Write `version` into every listed manifest under `repo_dir`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### wads.version_sync.version_mismatches(repo_dir, pyproject_data)

`(path, its version, [project].version)` for each listed manifest that differs.

A missing manifest counts as a mismatch (its version is `None`).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)]
