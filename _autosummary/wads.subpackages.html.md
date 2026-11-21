# wads.subpackages

Release a second package that lives in a subdirectory of the repo (i2mint/wads#220).

A repo can hold a pure-Python root package plus a maturin package in a subdirectory
(`thorwhalen/equate`: the root is `equate`, `rust/` is `equate-rust`, which has its
own `pyproject.toml`). The root package keeps the ordinary `publish` job; each
subpackage listed here gets its own native release path:

```default
[[tool.wads.ci.packages]]
dir = "rust"                    # holds a pyproject.toml; required
release = "on-change"           # or "always": every release run
tag_prefix = "equate-rust-v"    # tags are <tag_prefix><version>; default "<name>-v"
```

The subpackage’s own `pyproject.toml` configures it exactly as a root package is
configured (`[tool.wads.ci.build.native]`, `[tool.maturin]`): [`subpackage_configs()`](#wads.subpackages.subpackage_configs)
resolves it with [`wads.native_build.native_build_config()`](wads.native_build.html.md#wads.native_build.native_build_config). With no
`[[tool.wads.ci.packages]]` nothing changes.

Release rule ([`plan_release()`](#wads.subpackages.plan_release)): `on-change` releases a package only when files under
its `dir` changed since its last tag (never tagged: it releases). The version is the next
patch after the last tag, or the version in the subpackage’s `pyproject.toml` when that is
higher, so a hand-raised minor or major is honoured and a stale one never goes backwards.
Tags are `<tag_prefix><version>`, so they do not collide with the root’s bare `X.Y.Z`.

Migrating a package that already releases from a hand-written workflow: create its first
tag (`<tag_prefix><current version>`) before enabling this, or the first run, finding no tag,
releases the version in `pyproject.toml`. Two things are not covered yet: the Rust checks
(fmt, clippy, cargo test) run only for the root native path, not for a subpackage, and the
inline `wads/data/github_ci_uv.yml` has no subpackage jobs (the reusable workflow only).

Everything here is standard library only: the CI jobs load this file by path
(`wads/scripts/_checkout_import.py`), without installing wads.

### Module Attributes

| [`RELEASE_MODES`](#wads.subpackages.RELEASE_MODES)   | when a subpackage is released.   |
|------------------------------------------------------------------|----------------------------------|

### Functions

| [`latest_tag_version`](#wads.subpackages.latest_tag_version)(tags, tag_prefix)              | The highest version among `<tag_prefix>X.Y.Z` tags, or `None`.                                             |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| [`next_version`](#wads.subpackages.next_version)(last_tag, committed)                 | The release version: next patch after the last tag, unless the file is higher.                             |
| [`parse_version`](#wads.subpackages.parse_version)(text)                               | `(major, minor, patch)` of an `X.Y.Z` string, else `None`.                                                 |
| [`plan_release`](#wads.subpackages.plan_release)(package, \*, tags, ...)              | The version to release for `package` now, or `None` when it does not release.                              |
| [`stamp_version`](#wads.subpackages.stamp_version)(pyproject_text, version)            | `pyproject_text` with `[project].version` set to `version`.                                                |
| [`subpackage_configs`](#wads.subpackages.subpackage_configs)(pyproject, \*, read_pyproject) | The repo's [`SubPackage`](#wads.subpackages.SubPackage) list (empty when it declares none). |

### Classes

| [`SubPackage`](#wads.subpackages.SubPackage)(dir, name, release, tag_prefix, ...)   | One entry of `[[tool.wads.ci.packages]]`, resolved against its own pyproject.   |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|

### wads.subpackages.RELEASE_MODES *= ('on-change', 'always')*

when a subpackage is released.

* **Type:**
  `release` values

### *class* wads.subpackages.SubPackage(dir, name, release, tag_prefix, native)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One entry of `[[tool.wads.ci.packages]]`, resolved against its own pyproject.

#### wheel_matrix()

One `sub-wheels` matrix row per target, each carrying what the job needs.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### wads.subpackages.latest_tag_version(tags, tag_prefix)

The highest version among `<tag_prefix>X.Y.Z` tags, or `None`.

```pycon
>>> latest_tag_version(["p-v0.1.2", "p-v0.1.10", "q-v9.0.0", "p-vx"], "p-v")
(0, 1, 10)
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)]

### wads.subpackages.next_version(last_tag, committed)

The release version: next patch after the last tag, unless the file is higher.

```pycon
>>> next_version((0, 1, 2), (0, 1, 0))      # stale file: follow the tags
(0, 1, 3)
>>> next_version((0, 1, 2), (0, 2, 0))      # hand-raised minor: honoured
(0, 2, 0)
>>> next_version(None, (0, 1, 0))           # never tagged: release what the file says
(0, 1, 0)
>>> next_version(None, None)
(0, 0, 1)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)

### wads.subpackages.parse_version(text)

`(major, minor, patch)` of an `X.Y.Z` string, else `None`.

```pycon
>>> parse_version("1.2.3"), parse_version("1.2"), parse_version("v1.2.3")
((1, 2, 3), None, None)
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)]

### wads.subpackages.plan_release(package, , tags, committed_version, changed_since)

The version to release for `package` now, or `None` when it does not release.

`changed_since(tag)` says whether files under the package’s dir changed since `tag`
(called only for `on-change` packages that have a tag).

```pycon
>>> from types import SimpleNamespace as NS
>>> p = NS(dir="rust", release="on-change", tag_prefix="p-v")
>>> plan_release(p, tags=["p-v0.1.0"], committed_version="0.1.0", changed_since=lambda t: False)
>>> plan_release(p, tags=["p-v0.1.0"], committed_version="0.1.0", changed_since=lambda t: True)
'0.1.1'
>>> plan_release(p, tags=[], committed_version="0.1.0", changed_since=lambda t: False)
'0.1.0'
>>> plan_release(NS(dir="r", release="always", tag_prefix="p-v"), tags=["p-v1.0.0"],
...              committed_version="0.1.0", changed_since=lambda t: False)
'1.0.1'
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.subpackages.stamp_version(pyproject_text, version)

`pyproject_text` with `[project].version` set to `version`.

```pycon
>>> stamp_version('[project]\nname = "p"\nversion = "0.1.0"\n[tool.x]\nversion = "9"\n', "0.2.0")
'[project]\nname = "p"\nversion = "0.2.0"\n[tool.x]\nversion = "9"\n'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.subpackages.subpackage_configs(pyproject, , read_pyproject)

The repo’s [`SubPackage`](#wads.subpackages.SubPackage) list (empty when it declares none).

`read_pyproject(dir)` returns the parsed `<dir>/pyproject.toml`. Raises
`ValueError` on an entry that does not parse, as `native_build_config()` does.

```pycon
>>> data = {"tool": {"wads": {"ci": {"packages": [{"dir": "rust"}]}}}}
>>> sub = {"project": {"name": "pkg-rust", "version": "0.1.0"}, "build-system": {"build-backend": "maturin"}}
>>> [(p.dir, p.name, p.release, p.tag_prefix)
...  for p in subpackage_configs(data, read_pyproject=lambda d: sub)]
[('rust', 'pkg-rust', 'on-change', 'pkg-rust-v')]
>>> subpackage_configs({}, read_pyproject=lambda d: sub)
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`SubPackage`](#wads.subpackages.SubPackage)]
