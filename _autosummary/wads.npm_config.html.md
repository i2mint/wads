# wads.npm_config

Read NPM CI configuration from a `package.json` `wads.ci` block.

This is the NPM-side analog of [`wads.ci_config.CIConfig`](wads.ci_config.html.md#wads.ci_config.CIConfig) (which reads
`[tool.wads.ci]` from `pyproject.toml`). npm ignores unknown top-level keys,
so wads namespaces its config under a top-level `"wads"` key:

```json
{
  "name": "@scope/my-widget",
  "wads": {
    "ci": {
      "subdir": "js",
      "nodeVersions": ["20", "22", "24"],
      "publish": {"enabled": false, "marker": "[publish-npm]"}
    }
  }
}
```

The reusable workflow (`i2mint/wads/.github/workflows/npm-ci.yml`) parses the
same block in CI via `node`; this class is the parsing/validation surface used
from Python (tests, `populate` validation, inspection tooling).

[`npm_components()`](#wads.npm_config.npm_components) finds a repo’s npm components the way CI does, from the
`.github/workflows` stubs that call a wads `npm-ci*.yml` reusable workflow, and
[`npm_validate_commands()`](#wads.npm_config.npm_validate_commands) says what that workflow’s validate job runs in one of
them: `wads ci-local` runs exactly that.

### Module Attributes

| [`NPM_CI_DEFAULTS`](#wads.npm_config.NPM_CI_DEFAULTS)               | Defaults applied when a field is absent from `wads.ci`.                       |
|--------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`NPM_MONOREPO_COMMAND_DEFAULTS`](#wads.npm_config.NPM_MONOREPO_COMMAND_DEFAULTS) | Command defaults of `npm-ci-monorepo.yml` (pnpm + turbo), which is pnpm-only. |
| [`PACKAGE_JSON`](#wads.npm_config.PACKAGE_JSON)                  | The files the CI workflows look for in a component's directory.               |
| [`SUPPORTED_PACKAGE_MANAGERS`](#wads.npm_config.SUPPORTED_PACKAGE_MANAGERS)    | Package managers the reusable npm CI workflow knows how to drive.             |
| [`NPM_PUBLISH_DEFAULTS`](#wads.npm_config.NPM_PUBLISH_DEFAULTS)          | Defaults for the nested `wads.ci.publish` block.                              |
| [`TRIGGER_MODES`](#wads.npm_config.TRIGGER_MODES)                 | `wads.ci.trigger.mode` values the reusable workflow understands.              |
| [`NPM_TRIGGER_DEFAULTS`](#wads.npm_config.NPM_TRIGGER_DEFAULTS)          | Defaults for the nested `wads.ci.trigger` block.                              |

### Functions

| [`npm_components`](#wads.npm_config.npm_components)([repo_root])                        | The repo's npm components, as CI finds them: sorted [`NpmComponent`](#wads.npm_config.NpmComponent)s.            |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| [`npm_validate_commands`](#wads.npm_config.npm_validate_commands)(package_dir, \*[, monorepo]) | What the npm CI validate job runs in `package_dir`, read through [`NpmCIConfig`](#wads.npm_config.NpmCIConfig). |

### Classes

| [`NpmCIConfig`](#wads.npm_config.NpmCIConfig)(package_json_data, \*[, monorepo])   | Typed accessors over a `package.json` `wads.ci` configuration block.        |
|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`NpmComponent`](#wads.npm_config.NpmComponent)(dir, workflow[, monorepo])          | An npm component CI validates: one caller of a wads `npm-ci*.yml` workflow. |
| [`NpmValidateCommands`](#wads.npm_config.NpmValidateCommands)(package_manager, ...)        | The shell commands the npm validate job runs in a component, in order.      |

### wads.npm_config.NPM_CI_DEFAULTS *= {'buildCommand': 'npm run build --if-present', 'lintCommand': 'npm run lint --if-present', 'nodeVersions': ['20', '22', '24'], 'packageManager': 'npm', 'publishNode': '24', 'subdir': 'js', 'testCommand': 'npm test --if-present'}*

Defaults applied when a field is absent from `wads.ci`.

`packageManager` is `"npm"` here for the typed Python accessor, but in CI
an *absent* field triggers auto-detection (a `pnpm-lock.yaml` in the
package dir selects pnpm); an explicit value always wins. So existing npm
consumers — no field, no `pnpm-lock.yaml` — keep byte-identical behavior.

### wads.npm_config.NPM_MONOREPO_COMMAND_DEFAULTS *= {'buildCommand': 'pnpm turbo run build', 'lintCommand': 'pnpm turbo run lint', 'packageManager': 'pnpm', 'testCommand': 'pnpm turbo run test'}*

Command defaults of `npm-ci-monorepo.yml` (pnpm + turbo), which is pnpm-only.

### wads.npm_config.NPM_PUBLISH_DEFAULTS *= {'access': 'public', 'enabled': False, 'marker': '[publish-npm]', 'provenance': True, 'registry': 'https://registry.npmjs.org', 'trustedPublishing': True}*

Defaults for the nested `wads.ci.publish` block.

### wads.npm_config.NPM_TRIGGER_DEFAULTS *= {'mode': 'auto', 'runCiMarker': '[run ci]'}*

Defaults for the nested `wads.ci.trigger` block. Same values as the Python
side (`wads.ci_config.DFLT_TRIGGER_MODE` / `DFLT_RUN_CI_MARKER`) so a repo
with both a pyproject.toml and a package.json can use one marker convention.

### *class* wads.npm_config.NpmCIConfig(package_json_data, , monorepo=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Typed accessors over a `package.json` `wads.ci` configuration block.

#### *classmethod* from_file(package_json_path, , monorepo=False)

Build from a `package.json` file path (file or its directory).

* **Return type:**
  [`NpmCIConfig`](#wads.npm_config.NpmCIConfig)

#### has_ci_config()

True if the package.json declares a `wads.ci` block.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### *property* package_manager *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The package manager driving install/build (`"npm"` or `"pnpm"`).

Returns the explicit `wads.ci.packageManager` if set, else the default
(`"npm"`). Note the CI workflow additionally *auto-detects* pnpm from a
`pnpm-lock.yaml` when the field is absent — this accessor reports only
the declared value.

#### resolved_package_manager(package_dir)

The package manager CI’s install step uses in `package_dir`.

As the workflow: pnpm for a monorepo; else the declared `packageManager`,
else pnpm when a `pnpm-lock.yaml` is present, else npm; and anything but
pnpm takes the npm branch.

```pycon
>>> NpmCIConfig({}).resolved_package_manager("/nonexistent")
'npm'
>>> NpmCIConfig({"wads": {"ci": {"packageManager": "pnpm"}}}).resolved_package_manager(".")
'pnpm'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### *property* run_ci_marker *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Commit-subject substring that runs CI in `"on-demand"` mode.

Defaults to `"[run ci]"` (same default as the Python side), also when
empty, as the workflows’ `runCiMarker || '[run ci]'` reads it. Must be a
single line, and not blank: a blank marker would match nearly every subject
and silently turn on-demand back into auto.

```pycon
>>> NpmCIConfig({"wads": {"ci": {"trigger": {"runCiMarker": ""}}}}).run_ci_marker
'[run ci]'
```

#### *property* trigger_mode *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`"auto"` (default) or `"on-demand"`.

`"on-demand"` means nothing runs unless the commit *subject line*
contains [`run_ci_marker`](#wads.npm_config.NpmCIConfig.run_ci_marker), or the run is a manual
`workflow_dispatch`. Raises `ValueError` on any other value.

```pycon
>>> NpmCIConfig({}).trigger_mode
'auto'
>>> NpmCIConfig({"wads": {"ci": {"trigger": {"mode": "on-demand"}}}}).trigger_mode
'on-demand'
```

* **Type:**
  When CI runs

### *class* wads.npm_config.NpmComponent(dir, workflow, monorepo=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An npm component CI validates: one caller of a wads `npm-ci*.yml` workflow.

`dir` is repo-relative POSIX (`"."` for the repo root), `workflow` the
caller stub’s file name (e.g. `"npm-ci-ts.yml"`), `monorepo` whether it calls
`npm-ci-monorepo.yml` (pnpm + turbo) rather than `npm-ci.yml`.

### *class* wads.npm_config.NpmValidateCommands(package_manager, install, lint, test, build)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The shell commands the npm validate job runs in a component, in order.

### wads.npm_config.PACKAGE_JSON *= 'package.json'*

The files the CI workflows look for in a component’s directory.

### wads.npm_config.SUPPORTED_PACKAGE_MANAGERS *= ('npm', 'pnpm')*

Package managers the reusable npm CI workflow knows how to drive.

### wads.npm_config.TRIGGER_MODES *= ('auto', 'on-demand')*

`wads.ci.trigger.mode` values the reusable workflow understands. Mirrors
`wads.ci_config.TRIGGER_MODES` (the Python/pyproject.toml side).

### wads.npm_config.npm_components(repo_root='.')

The repo’s npm components, as CI finds them: sorted [`NpmComponent`](#wads.npm_config.NpmComponent)s.

One per job, in a `.github/workflows/*.yml` (or `.yaml`) file, that calls a
wads `npm-ci*.yml` reusable workflow: its `package-dir` input, or the
reusable workflow’s default dir when absent ([`wads.npm_trust.wads_reusable_call()`](wads.npm_trust.html.md#wads.npm_trust.wads_reusable_call)).
An unreadable or invalid workflow file is skipped, and so is a `package-dir`
holding a `${{ }}` expression (not a directory until Actions evaluates it).

Not deduplicated by dir: one entry per calling stub, so a dir two stubs call
appears twice (with their two `workflow` names).

```pycon
>>> import tempfile
>>> root = Path(tempfile.mkdtemp())
>>> (root / ".github/workflows").mkdir(parents=True)
>>> _ = (root / ".github/workflows/npm-ci-ts.yml").write_text(
...     "jobs:\n  npm-ci:\n"
...     "    uses: i2mint/wads/.github/workflows/npm-ci.yml@master\n"
...     "    with:\n      package-dir: ./ts/\n"
... )
>>> npm_components(root)
[NpmComponent(dir='ts', workflow='npm-ci-ts.yml', monorepo=False)]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### wads.npm_config.npm_validate_commands(package_dir, , monorepo=False)

What the npm CI validate job runs in `package_dir`, read through [`NpmCIConfig`](#wads.npm_config.NpmCIConfig).

`monorepo`: as `npm-ci-monorepo.yml` (pnpm, turbo defaults), else as
`npm-ci.yml`. pnpm installs with a frozen lockfile when `pnpm-lock.yaml` is
present and without one otherwise. npm uses `npm ci` when a
`package-lock.json` is present, else `npm install`: the branch CI’s
`npm ci || npm install` ends up taking. The trigger block is validated as the
workflow’s setup job does, so an invalid config fails here as it fails CI
(`ValueError`; `OSError` / `ValueError` for a missing or broken file).

```pycon
>>> import tempfile
>>> d = Path(tempfile.mkdtemp())
>>> _ = (d / "package.json").write_text('{"wads": {"ci": {"testCommand": "vitest"}}}')
>>> npm_validate_commands(d)
NpmValidateCommands(package_manager='npm', install='npm install',
    lint='npm run lint --if-present', test='vitest',
    build='npm run build --if-present')
>>> _ = (d / "pnpm-lock.yaml").write_text("")
>>> npm_validate_commands(d).install
'pnpm install --frozen-lockfile'
```

* **Return type:**
  [`NpmValidateCommands`](#wads.npm_config.NpmValidateCommands)
