# wads.profiles

Declarative generation *profiles* and *overlays* built on the engine.

A *profile* is a named declarative description of a project setup expressed as a
list of [`wads.templating.Artifact`](wads.templating.md#wads.templating.Artifact). The default profile (`python-lib`)
is produced by [`wads.populate`](wads.populate.md#module-wads.populate).

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

Nothing here runs by default; the Python `populate` path and the
`name/name/` root layout are untouched.

### Module Attributes

| [`FRONTEND_PROFILES`](#wads.profiles.FRONTEND_PROFILES)   | The frontend profile registry.   |
|----------------------------------------------------------------------|----------------------------------|

### Functions

| [`apply_frontend`](#wads.profiles.apply_frontend)(pkg_dir, \*[, profile, ...])      | Apply one frontend profile component to an existing project directory.        |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`apply_npm_overlay`](#wads.profiles.apply_npm_overlay)(pkg_dir, \*, project_name)     | Deprecated alias for `apply_frontend(profile="js", ...)` (issue #32 surface). |
| [`apply_tests_overlay`](#wads.profiles.apply_tests_overlay)(pkg_dir, \*, project_name)   | Scaffold a `tests/` folder in an existing project (issue #4).                 |
| [`frontend_context`](#wads.profiles.frontend_context)(\*, profile_name, project_name) | Build the render context shared by all frontend-profile templates.            |
| [`get_frontend_profile`](#wads.profiles.get_frontend_profile)(name)                       | Look up a registered profile, with an informative error if unknown.           |
| [`make_tests_overlay_artifacts`](#wads.profiles.make_tests_overlay_artifacts)(project_name, \*)   | Artifacts that scaffold a `tests/` folder for a project.                      |
| [`npm_overlay_artifacts`](#wads.profiles.npm_overlay_artifacts)([npm_subdir])              | Deprecated: the `js` overlay artifacts.                                       |
| [`npm_overlay_context`](#wads.profiles.npm_overlay_context)(\*, project_name[, ...])     | Deprecated: render context for the `js` overlay.                              |
| [`register_frontend_profile`](#wads.profiles.register_frontend_profile)(profile)               | Register (or override) a frontend profile by name.                            |

### Classes

| [`FrontendProfile`](#wads.profiles.FrontendProfile)(name, default_subdir, ...[, ...])   | A declarative frontend language/toolchain profile.   |
|------------------------------------------------------------------------------------------------------|------------------------------------------------------|

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

### wads.profiles.apply_frontend(pkg_dir, , profile='js', project_name, description='', license=None, subdir=None, package_name=None, version='0.0.1', package_manager=None, workspace_glob='packages/\*', example_package_name=None, overwrite=(), on_add=None, on_skip=None)

Apply one frontend profile component to an existing project directory.

`subdir` and `package_manager` default to the selected profile’s
defaults. Returns the [`wads.templating.GenerationResult`](wads.templating.md#wads.templating.GenerationResult).

* **Return type:**
  [`GenerationResult`](wads.templating.md#wads.templating.GenerationResult)

```pycon
>>> import tempfile
>>> d = tempfile.mkdtemp()
>>> res = apply_frontend(d, profile="ts", project_name="widget")
>>> sorted(res.added)
['.github/workflows/npm-ci-ts.yml', 'ts/package.json', 'ts/src/index.test.ts',
 'ts/src/index.ts', 'ts/tsconfig.json']
```

### wads.profiles.apply_npm_overlay(pkg_dir, , project_name, description='', license=None, npm_subdir='js', npm_package_name=None, npm_version='0.0.1', npm_package_manager='npm', overwrite=(), on_add=None, on_skip=None)

Deprecated alias for `apply_frontend(profile="js", ...)` (issue #32 surface).

Kept so existing callers and tests keep working; new code should call
[`apply_frontend()`](#wads.profiles.apply_frontend).

### wads.profiles.apply_tests_overlay(pkg_dir, , project_name, with_data_util=True, overwrite=(), on_add=None, on_skip=None)

Scaffold a `tests/` folder in an existing project (issue #4).

### wads.profiles.frontend_context(, profile_name, project_name, description='', license=None, subdir, package_name=None, version='0.0.1', package_manager='npm', workspace_glob='packages/\*', example_package_name=None)

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

### wads.profiles.make_tests_overlay_artifacts(project_name, , with_data_util=True)

Artifacts that scaffold a `tests/` folder for a project.

Writes `tests/__init__.py`, `tests/test_<project_name>.py` (a smoke
test), and optionally `tests/util.py` (a `tests/data` accessor, per #4).
The smoke-test filename embeds the package name, so it is built here where
the name is known.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

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
