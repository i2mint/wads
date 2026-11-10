# wads.profiles

Declarative generation *profiles* and *overlays* built on the engine.

A *profile* is a named declarative description of a project setup expressed as a
list of [`wads.templating.Artifact`](wads.templating.html.md#wads.templating.Artifact). The default profile (`python-lib`)
is produced by [`wads.populate`](wads.populate.html.md#module-wads.populate).

This module hosts two opt-in overlays added *on top of* an existing project:

- The **frontend profile registry** (issue #39): a small registry of
  language/toolchain profiles – `js` (the original #32 overlay, the
  back-compat anchor), `ts` (single-package TypeScript), and `ts-monorepo`
  (pnpm workspaces + turbo). A project may declare several frontend components
  (e.g. `js` *and* `ts`); each lives in its own subdir with its own
  path-filtered workflow, so they never collide. Selected via
  `populate --frontend <profile>[,<profile>]` (`--with-npm` stays as an
  alias for `--frontend js`). Profiles are extensible through
  [`register_frontend_profile()`](#wads.profiles.register_frontend_profile).
- The **tests-folder overlay** (issue #4): scaffolds a `tests/` package.
- The **native-core registry** (issue #214): a Rust core built by maturin behind
  a Python facade (`populate --native maturin`); see [`apply_native()`](#wads.profiles.apply_native).

Nothing here runs by default; the Python `populate` path and the
`name/name/` root layout are untouched.

### Module Attributes

| [`DFLT_SHARED_FIXTURES_DIR`](#wads.profiles.DFLT_SHARED_FIXTURES_DIR)   | Where a Python package and its npm twin keep the golden cases both test suites run (i2mint/wads#209).                                   |
|-----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_RUST_DIR`](#wads.profiles.DFLT_RUST_DIR)              | Where a Rust core lives in the native (maturin) layout; when present, a change there runs the npm CI too (a wasm build may compile it). |
| [`LICENSE_FILENAMES`](#wads.profiles.LICENSE_FILENAMES)          | Root licence file names a frontend component copies, in order of preference.                                                            |
| [`FRONTEND_PROFILES`](#wads.profiles.FRONTEND_PROFILES)          | The frontend profile registry.                                                                                                          |
| [`NATIVE_PROFILES`](#wads.profiles.NATIVE_PROFILES)            | The native-backend registry.                                                                                                            |

### Functions

| [`apply_frontend`](#wads.profiles.apply_frontend)(pkg_dir, \*[, profile, ...])        | Apply one frontend profile component to an existing project directory.        |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`apply_native`](#wads.profiles.apply_native)(pkg_dir, \*[, backend, license, ...]) | Scaffold a native core (`backend`) into the project at `pkg_dir`.             |
| [`apply_npm_overlay`](#wads.profiles.apply_npm_overlay)(pkg_dir, \*, project_name)       | Deprecated alias for `apply_frontend(profile="js", ...)` (issue #32 surface). |
| [`apply_tests_overlay`](#wads.profiles.apply_tests_overlay)(pkg_dir, \*, project_name)     | Scaffold a `tests/` folder in an existing project (issue #4).                 |
| [`default_npm_watch_paths`](#wads.profiles.default_npm_watch_paths)([repo_dir])                | Inputs outside its subdir an npm component's CI should run on.                |
| [`find_license_file`](#wads.profiles.find_license_file)(repo_dir, \*[, names])           | `(file name, text)` of the repo's root licence, or `None` if it has none.     |
| [`frontend_context`](#wads.profiles.frontend_context)(\*, profile_name, project_name)   | Build the render context shared by all frontend-profile templates.            |
| [`get_frontend_profile`](#wads.profiles.get_frontend_profile)(name)                         | Look up a registered profile, with an informative error if unknown.           |
| [`get_native_profile`](#wads.profiles.get_native_profile)(name)                           | Look up a registered native profile, with an informative error if unknown.    |
| [`make_tests_overlay_artifacts`](#wads.profiles.make_tests_overlay_artifacts)(project_name, \*)     | Artifacts that scaffold a `tests/` folder for a project.                      |
| [`merge_native_pyproject`](#wads.profiles.merge_native_pyproject)(pyproject, fragment, \*)    | A copy of `pyproject` with a native `fragment` merged in (for a NEW package). |
| [`native_artifacts`](#wads.profiles.native_artifacts)(backend, project_name, \*[, ...]) | The `Artifact` list a native backend writes for `project_name`.               |
| [`native_facade_todo`](#wads.profiles.native_facade_todo)(pkg_dir, project_name, \*)      | The lines a kept (real) facade lacks for the template's tests ('' if none).   |
| [`native_licence`](#wads.profiles.native_licence)(pkg_dir)                            | The SPDX expression the package at `pkg_dir` declares, or `None`.             |
| [`native_names`](#wads.profiles.native_names)(project_name, \*[, license, backend]) | Map the template tokens to their values for `project_name`.                   |
| [`native_pyproject_fragment`](#wads.profiles.native_pyproject_fragment)(project_name, \*[, ...]) | The pyproject tables `backend` needs, for `project_name`.                     |
| [`native_pyproject_gaps`](#wads.profiles.native_pyproject_gaps)(pyproject, project_name, \*) | `(required, recommended)`: what an EXISTING pyproject lacks for `backend`.    |
| [`native_pyproject_todo`](#wads.profiles.native_pyproject_todo)(pyproject, project_name, \*) | What an EXISTING pyproject needs for `backend`, as TOML text ('' if nothing). |
| [`npm_overlay_artifacts`](#wads.profiles.npm_overlay_artifacts)([npm_subdir])                | Deprecated: the `js` overlay artifacts.                                       |
| [`npm_overlay_context`](#wads.profiles.npm_overlay_context)(\*, project_name[, ...])       | Deprecated: render context for the `js` overlay.                              |
| [`register_frontend_profile`](#wads.profiles.register_frontend_profile)(profile)                 | Register (or override) a frontend profile by name.                            |
| [`register_native_profile`](#wads.profiles.register_native_profile)(profile)                   | Register (or override) a native profile by name.                              |

### Classes

| [`FrontendProfile`](#wads.profiles.FrontendProfile)(name, default_subdir, ...[, ...])   | A declarative frontend language/toolchain profile.                           |
|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`NativeProfile`](#wads.profiles.NativeProfile)(name, template_dir, ...[, ...])       | A native (compiled-extension) backend that `populate --native` can scaffold. |

### wads.profiles.DFLT_RUST_DIR *= 'rust'*

Where a Rust core lives in the native (maturin) layout; when present, a change
there runs the npm CI too (a wasm build may compile it).

### wads.profiles.DFLT_SHARED_FIXTURES_DIR *= 'fixtures'*

Where a Python package and its npm twin keep the golden cases both test suites
run (i2mint/wads#209). A change there runs the npm CI as well as the Python CI.

### wads.profiles.FRONTEND_PROFILES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)* *= {'js': FrontendProfile(name='js', default_subdir='js', default_package_manager='npm', artifacts=<function \_js_artifacts>, description='JavaScript single package (the original #32 overlay).'), 'ts': FrontendProfile(name='ts', default_subdir='ts', default_package_manager='npm', artifacts=<function \_ts_artifacts>, description='TypeScript single package (tsconfig + tsup build + vitest).'), 'ts-monorepo': FrontendProfile(name='ts-monorepo', default_subdir='ts', default_package_manager='pnpm', artifacts=<function \_ts_monorepo_artifacts>, description='TypeScript monorepo (pnpm workspaces + turbo).')}*

The frontend profile registry. Extend it via [`register_frontend_profile()`](#wads.profiles.register_frontend_profile).

### *class* wads.profiles.FrontendProfile(name, default_subdir, default_package_manager, artifacts, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A declarative frontend language/toolchain profile.

* **Parameters:**
  * **name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – registry key (e.g. `"js"`, `"ts"`, `"ts-monorepo"`).
  * **default_subdir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – subdir the component lives in when unspecified.
  * **default_package_manager** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – `"npm"` or `"pnpm"`.
  * **artifacts** ([`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)]) – `context -> list[Artifact]` builder for this profile.
  * **description** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – one-line human summary.

### wads.profiles.LICENSE_FILENAMES *= ('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'LICENCE', 'COPYING')*

Root licence file names a frontend component copies, in order of preference.

### wads.profiles.NATIVE_PROFILES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)* *= {'maturin': NativeProfile(name='maturin', template_dir='/home/runner/work/wads/wads/wads/data/native/maturin', pyproject_fragment='/home/runner/work/wads/wads/wads/data/native/maturin_pyproject.toml', replaces=('build-system',), drops=('tool.hatch',), facade='tmpl_pkg/_\_init_\_.py', new_package_only=('tmpl_pkg/py.typed',), gitignore_patterns=('target', '\*.so'), lockfile='Cargo.lock', lockfile_command=('cargo', 'generate-lockfile', '--quiet'), lockfile_env=(('RUSTUP_AUTO_INSTALL', '0'),), missing_toolchain=('is not installed', 'rustup toolchain install'), toolchain_pin=('rust-toolchain.toml', 'toolchain', 'channel'), toolchain_list=('rustup', 'toolchain', 'list'), unlicensed=(('license = "tmpl-license"', '# license = "<SPDX id>"'), ('license.workspace = true', '# license.workspace = true')), description='Rust core (rust/core) + PyO3 binding (rust/py) built by maturin.')}*

The native-backend registry. Extend it via [`register_native_profile()`](#wads.profiles.register_native_profile).

### *class* wads.profiles.NativeProfile(name, template_dir, pyproject_fragment, replaces=(), drops=(), facade='', new_package_only=(), gitignore_patterns=(), lockfile='', lockfile_command=(), lockfile_env=(), missing_toolchain=(), toolchain_pin=(), toolchain_list=(), unlicensed=(), description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A native (compiled-extension) backend that `populate --native` can scaffold.

Paths are template paths (with the tokens); pyproject tables are dotted
(`"tool.hatch"`).

* **Parameters:**
  * **name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – registry key; also the backend name `wads.native_build` knows.
  * **template_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – folder of files written at their (token-substituted) paths.
  * **pyproject_fragment** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – TOML file of the pyproject tables the backend needs.
  * **replaces** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – fragment tables that replace the pyproject’s whole (rather than
    merge into it), e.g. `"build-system"`.
  * **drops** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – tables a NEW pyproject loses, because they configure what
    `replaces` replaced (e.g. `"tool.hatch"`); an existing one is told to.
  * **facade** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – the package’s `__init__.py` template. A missing or blank one is
    written; a real one is kept and the lines the template tests need are reported.
  * **new_package_only** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – files written only when the package is new (no real facade).
  * **gitignore_patterns** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – `.gitignore` entries the layout relies on.
  * **lockfile** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – lockfile the build needs (`--locked`), generated when missing.
  * **lockfile_command** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – command generating `lockfile`, run in the project root.
  * **lockfile_env** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – `(name, value)` pairs added to that command’s environment.
  * **missing_toolchain** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – `(marker, command)`: when the lockfile command’s stderr
    has `marker`, the pinned toolchain is missing and `command` installs it.
  * **toolchain_pin** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – `(file, table, key)` naming the pinned toolchain channel
    (checked against `toolchain_list` before the lockfile command runs).
  * **toolchain_list** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – command listing the installed toolchains, one per line.
  * **unlicensed** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – `(text, replacement)` pairs applied to the templates when the
    package’s licence cannot be determined (the crates then declare none).
  * **description** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – one-line human summary.

### wads.profiles.apply_frontend(pkg_dir, , profile='js', project_name, description='', license=None, subdir=None, package_name=None, version='0.0.1', package_manager=None, workspace_glob='packages/\*', example_package_name=None, watch_paths=None, overwrite=(), on_add=None, on_skip=None)

Apply one frontend profile component to an existing project directory.

`subdir` and `package_manager` default to the selected profile’s
defaults. `watch_paths` are the inputs outside the subdir that also run the
component’s CI (default [`default_npm_watch_paths()`](#wads.profiles.default_npm_watch_paths) of `pkg_dir`).
Returns the [`wads.templating.GenerationResult`](wads.templating.html.md#wads.templating.GenerationResult).

```pycon
>>> import tempfile
>>> d = tempfile.mkdtemp()
>>> res = apply_frontend(d, profile="ts", project_name="widget")
>>> sorted(res.added)
['.github/workflows/npm-ci-ts.yml', 'ts/package.json', 'ts/src/index.test.ts',
 'ts/src/index.ts', 'ts/tsconfig.json', 'ts/tsconfig.test.json']
```

* **Return type:**
  [`GenerationResult`](wads.templating.html.md#wads.templating.GenerationResult)

### wads.profiles.apply_native(pkg_dir, \*, backend='maturin', project_name, license=None, overwrite=(), generate_lockfile=True, lockfile_timeout=300, on_add=None, on_skip=None, on_error=None, on_attention=<function \_warn_attention>)

Scaffold a native core (`backend`) into the project at `pkg_dir`.

Writes the backend’s template files that do not exist yet (`overwrite` names the
ones to replace). A missing or blank facade (`__init__.py`) is written; a real one
is kept, the files of a new package only (`py.typed`) are left out, and the lines
the template’s tests need are reported. `on_attention(filename, reason)` also gets
missing `.gitignore` entries and a lockfile it could not generate. pyproject.toml is
not touched here: `populate` merges [`native_pyproject_fragment()`](#wads.profiles.native_pyproject_fragment) into a new
one and reports [`native_pyproject_todo()`](#wads.profiles.native_pyproject_todo) for an existing one.

```pycon
>>> import tempfile
>>> d = tempfile.mkdtemp()
>>> res = apply_native(
...     d, project_name="fast_thing", generate_lockfile=False, on_attention=None
... )
>>> [t for t in res.added if t.startswith("rust/")]
['rust/core/Cargo.toml', 'rust/core/src/lib.rs', 'rust/py/Cargo.toml',
 'rust/py/src/lib.rs']
```

* **Return type:**
  [`GenerationResult`](wads.templating.html.md#wads.templating.GenerationResult)

### wads.profiles.apply_npm_overlay(pkg_dir, , project_name, description='', license=None, npm_subdir='js', npm_package_name=None, npm_version='0.0.1', npm_package_manager='npm', overwrite=(), on_add=None, on_skip=None)

Deprecated alias for `apply_frontend(profile="js", ...)` (issue #32 surface).

Kept so existing callers and tests keep working; new code should call
[`apply_frontend()`](#wads.profiles.apply_frontend).

### wads.profiles.apply_tests_overlay(pkg_dir, , project_name, with_data_util=True, overwrite=(), on_add=None, on_skip=None)

Scaffold a `tests/` folder in an existing project (issue #4).

### wads.profiles.default_npm_watch_paths(repo_dir=None)

Inputs outside its subdir an npm component’s CI should run on.

The shared fixtures directory always (a pattern that matches nothing costs
nothing), and the Rust core when `repo_dir` has one.

```pycon
>>> default_npm_watch_paths()
['fixtures/**']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### wads.profiles.find_license_file(repo_dir, , names=('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'LICENCE', 'COPYING'))

`(file name, text)` of the repo’s root licence, or `None` if it has none.

```pycon
>>> import tempfile
>>> d = tempfile.mkdtemp()
>>> find_license_file(d) is None
True
>>> _ = open(os.path.join(d, "LICENSE.md"), "w").write("MIT")
>>> find_license_file(d)
('LICENSE.md', 'MIT')
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)]

### wads.profiles.frontend_context(, profile_name, project_name, description='', license=None, subdir, package_name=None, version='0.0.1', package_manager='npm', workspace_glob='packages/\*', example_package_name=None, license_file=None, watch_paths=None)

Build the render context shared by all frontend-profile templates.

The returned mapping is a superset: it carries the keys every profile’s
templates may reference (single-package and monorepo). Unused keys are
harmless under Jinja `StrictUndefined` because that only errors on keys a
template *references* yet are missing.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.profiles.get_frontend_profile(name)

Look up a registered profile, with an informative error if unknown.

* **Return type:**
  [`FrontendProfile`](#wads.profiles.FrontendProfile)

### wads.profiles.get_native_profile(name)

Look up a registered native profile, with an informative error if unknown.

* **Return type:**
  [`NativeProfile`](#wads.profiles.NativeProfile)

### wads.profiles.make_tests_overlay_artifacts(project_name, , with_data_util=True)

Artifacts that scaffold a `tests/` folder for a project.

Writes `tests/__init__.py`, `tests/test_<project_name>.py` (a smoke
test), and optionally `tests/util.py` (a `tests/data` accessor, per #4).
The smoke-test filename embeds the package name, so it is built here where
the name is known.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### wads.profiles.merge_native_pyproject(pyproject, fragment, , backend='maturin')

A copy of `pyproject` with a native `fragment` merged in (for a NEW package).

The profile’s `replaces` tables are replaced and its `drops` tables removed; the
other tables merge, lists gaining the items they lack.

```pycon
>>> new = merge_native_pyproject(
...     {"build-system": {"requires": ["hatchling"], "build-backend": "hatchling.build"},
...      "project": {"optional-dependencies": {"dev": ["pytest"]}},
...      "tool": {"hatch": {"build": {}}, "ruff": {}}},
...     native_pyproject_fragment("fast_thing"),
... )
>>> new["build-system"]["build-backend"], sorted(new["tool"])
('maturin', ['maturin', 'pytest', 'ruff', 'uv'])
>>> new["project"]["optional-dependencies"]["dev"]
['pytest', 'hypothesis']
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.profiles.native_artifacts(backend, project_name, , license=None, skip=())

The `Artifact` list a native backend writes for `project_name`.

`skip` names template paths to leave out.

```pycon
>>> sorted(a.target for a in native_artifacts("maturin", "fast_thing"))[:3]
['Cargo.toml', 'clippy.toml', 'fast_thing/__init__.py']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### wads.profiles.native_facade_todo(pkg_dir, project_name, , backend='maturin', license=None)

The lines a kept (real) facade lacks for the template’s tests (’’ if none).

```pycon
>>> import tempfile
>>> d = tempfile.mkdtemp()
>>> os.makedirs(os.path.join(d, "fast_thing"))
>>> _ = open(os.path.join(d, "fast_thing", "__init__.py"), "w").write("X = 1\n")
>>> print(native_facade_todo(d, "fast_thing"))
from importlib.metadata import version as _version

from fast_thing import _core
...
def hamming(a: str, b: str) -> int:
...
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.profiles.native_licence(pkg_dir)

The SPDX expression the package at `pkg_dir` declares, or `None`.

Metadata only, never a guess from a licence document: `[project].license` as a
string or `{text = ...}`, canonicalised; else the `License ::` classifiers,
joined with `OR` (`None` if any is not recognised). `{file = ...}` or
`license-files` alone say no SPDX id, so `None`.

```pycon
>>> import tempfile
>>> d = tempfile.mkdtemp()
>>> native_licence(d) is None
True
>>> _ = open(os.path.join(d, "pyproject.toml"), "w").write(
...     '[project]\nclassifiers = ["License :: OSI Approved :: MIT License",'
...     ' "License :: OSI Approved :: Apache Software License"]\n'
... )
>>> native_licence(d)
'MIT OR Apache-2.0'
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.profiles.native_names(project_name, , license=None, backend='maturin')

Map the template tokens to their values for `project_name`.

The project name is the import name (`populate` makes `<name>/<name>/`), so it
must be a lowercase identifier; Cargo package names are its kebab-case form.
`license` is the package’s SPDX id; without one the crates declare no licence
(the profile’s `unlicensed` edits) rather than a guessed one.

```pycon
>>> native_names("fast_thing", license="Apache-2.0")
{'tmpl_pkg': 'fast_thing', 'tmpl-pkg': 'fast-thing', 'tmpl-license': 'Apache-2.0'}
>>> native_names("fast_thing")['license = "tmpl-license"']
'# license = "<SPDX id>"'
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.profiles.native_pyproject_fragment(project_name, , backend='maturin')

The pyproject tables `backend` needs, for `project_name`.

```pycon
>>> frag = native_pyproject_fragment("fast_thing")
>>> frag["build-system"]["build-backend"], frag["tool"]["maturin"]["module-name"]
('maturin', 'fast_thing._core')
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.profiles.native_pyproject_gaps(pyproject, project_name, , backend='maturin')

`(required, recommended)`: what an EXISTING pyproject lacks for `backend`.

Required: absent keys and missing list items, and a `replaces` table whose
scalars differ (another build backend) or are absent, given whole. Recommended:
values set otherwise than the template’s (a deliberate choice stays yours), and a
`replaces` table that only lacks list items (e.g. an older `requires` pin).

```pycon
>>> required, recommended = native_pyproject_gaps(
...     {"build-system": {"requires": ["maturin>=1.9.4,<2"], "build-backend": "maturin"}},
...     "fast_thing",
... )
>>> "build-system" in required, recommended["build-system"]["build-backend"]
(False, 'maturin')
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)

### wads.profiles.native_pyproject_todo(pyproject, project_name, , backend='maturin')

What an EXISTING pyproject needs for `backend`, as TOML text (’’ if nothing).

`populate` never rewrites an existing pyproject.toml; it reports this instead. Two
blocks, each valid TOML: `# Required` and `# Recommended`
([`native_pyproject_gaps()`](#wads.profiles.native_pyproject_gaps)).

```pycon
>>> print(native_pyproject_todo({}, "fast_thing"))
# Required: merge into pyproject.toml (lists: add the items shown).
# [build-system] replaces yours.
[build-system]
requires = [...]
build-backend = "maturin"
...
module-name = "fast_thing._core"
...
>>> pyproject = merge_native_pyproject({}, native_pyproject_fragment("fast_thing"))
>>> native_pyproject_todo(pyproject, "fast_thing")
''
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.profiles.npm_overlay_artifacts(npm_subdir='js')

Deprecated: the `js` overlay artifacts. Use the `js` frontend profile.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### wads.profiles.npm_overlay_context(, project_name, description='', license=None, npm_subdir='js', npm_package_name=None, npm_version='0.0.1', npm_package_manager='npm')

Deprecated: render context for the `js` overlay. Use [`apply_frontend()`](#wads.profiles.apply_frontend).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.profiles.register_frontend_profile(profile)

Register (or override) a frontend profile by name. Returns the profile.

* **Return type:**
  [`FrontendProfile`](#wads.profiles.FrontendProfile)

### wads.profiles.register_native_profile(profile)

Register (or override) a native profile by name. Returns the profile.

* **Return type:**
  [`NativeProfile`](#wads.profiles.NativeProfile)
