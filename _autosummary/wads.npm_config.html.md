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

### Module Attributes

| [`NPM_CI_DEFAULTS`](#wads.npm_config.NPM_CI_DEFAULTS)            | Defaults applied when a field is absent from `wads.ci`.           |
|-----------------------------------------------------------------------------|-------------------------------------------------------------------|
| [`SUPPORTED_PACKAGE_MANAGERS`](#wads.npm_config.SUPPORTED_PACKAGE_MANAGERS) | Package managers the reusable npm CI workflow knows how to drive. |
| [`NPM_PUBLISH_DEFAULTS`](#wads.npm_config.NPM_PUBLISH_DEFAULTS)       | Defaults for the nested `wads.ci.publish` block.                  |
| [`TRIGGER_MODES`](#wads.npm_config.TRIGGER_MODES)              | `wads.ci.trigger.mode` values the reusable workflow understands.  |
| [`NPM_TRIGGER_DEFAULTS`](#wads.npm_config.NPM_TRIGGER_DEFAULTS)       | Defaults for the nested `wads.ci.trigger` block.                  |

### Classes

| [`NpmCIConfig`](#wads.npm_config.NpmCIConfig)(package_json_data)   | Typed accessors over a `package.json` `wads.ci` configuration block.   |
|-----------------------------------------------------------------------------------|------------------------------------------------------------------------|

### wads.npm_config.NPM_CI_DEFAULTS *= {'buildCommand': 'npm run build --if-present', 'lintCommand': 'npm run lint --if-present', 'nodeVersions': ['20', '22', '24'], 'packageManager': 'npm', 'publishNode': '24', 'subdir': 'js', 'testCommand': 'npm test --if-present'}*

Defaults applied when a field is absent from `wads.ci`.

`packageManager` is `"npm"` here for the typed Python accessor, but in CI
an *absent* field triggers auto-detection (a `pnpm-lock.yaml` in the
package dir selects pnpm); an explicit value always wins. So existing npm
consumers — no field, no `pnpm-lock.yaml` — keep byte-identical behavior.

### wads.npm_config.NPM_PUBLISH_DEFAULTS *= {'access': 'public', 'enabled': False, 'marker': '[publish-npm]', 'provenance': True, 'registry': 'https://registry.npmjs.org', 'trustedPublishing': True}*

Defaults for the nested `wads.ci.publish` block.

### wads.npm_config.NPM_TRIGGER_DEFAULTS *= {'mode': 'auto', 'runCiMarker': '[run ci]'}*

Defaults for the nested `wads.ci.trigger` block. Same values as the Python
side (`wads.ci_config.DFLT_TRIGGER_MODE` / `DFLT_RUN_CI_MARKER`) so a repo
with both a pyproject.toml and a package.json can use one marker convention.

### *class* wads.npm_config.NpmCIConfig(package_json_data)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Typed accessors over a `package.json` `wads.ci` configuration block.

#### *classmethod* from_file(package_json_path)

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

#### *property* run_ci_marker *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Commit-subject substring that runs CI in `"on-demand"` mode.

Defaults to `"[run ci]"` (same default as the Python side). Must be a
non-empty single line: an empty marker would match every subject and
silently turn on-demand back into auto.

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

### wads.npm_config.SUPPORTED_PACKAGE_MANAGERS *= ('npm', 'pnpm')*

Package managers the reusable npm CI workflow knows how to drive.

### wads.npm_config.TRIGGER_MODES *= ('auto', 'on-demand')*

`wads.ci.trigger.mode` values the reusable workflow understands. Mirrors
`wads.ci_config.TRIGGER_MODES` (the Python/pyproject.toml side).
