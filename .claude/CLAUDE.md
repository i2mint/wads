# wads - Python Packaging & CI/CD Tools

## What This Project Does

Wads automates Python project setup, packaging, CI/CD, and migration. It provides:

1. **`populate`** - Create new Python projects with modern tooling (pyproject.toml + Hatchling)
2. **`pack`** - Build and publish packages to PyPI
3. **`wads-migrate`** - Migrate legacy projects (setup.cfg → pyproject.toml, old CI → new CI)
4. **CI Actions** - Reusable GitHub Actions in `actions/` directory
5. **AI Agents** - Diagnostic tools (`wads-ci-debug`, `wads-deps`, `wads-test-analyze`)

## Architecture: pyproject.toml as Single Source of Truth

The core design principle: **all project configuration lives in `pyproject.toml`**. The CI workflow template (`github_ci_publish_2025.yml`) reads configuration from `pyproject.toml` via the `read-ci-config` action, so projects don't hardcode settings in workflow files.

### Key Configuration Sections

| Section | Purpose |
|---------|---------|
| `[project]` | Standard Python project metadata |
| `[tool.wads.ci.install]` | `extras` — package extras CI installs (`.[extras]`); empty = core deps only |
| `[tool.wads.ci.testing]` | Python versions, pytest args, coverage, Windows testing |
| `[tool.wads.ci.commands]` | Pre-test, test, post-test, lint, format commands |
| `[tool.wads.ci.env]` | Environment variables (required, test, extra, defaults) |
| `[tool.wads.ci.quality]` | Ruff/Black/Mypy settings |
| `[tool.wads.ci.build]` | sdist/wheel build settings |
| `[tool.wads.ci.publish]` | PyPI publishing settings |
| `[tool.wads.ci.docs]` | Documentation generation (epythet) |
| `[tool.wads.ci.metrics]` | Code metrics tracking (umpyre) |
| `[tool.wads.ops.*]` | System/OS-level dependencies (ffmpeg, ODBC, etc.) |

## Project Structure

```
wads/
├── actions/              # Reusable GitHub Actions (composite actions)
│   ├── read-ci-config/   # Read [tool.wads.ci] from pyproject.toml
│   ├── install-system-deps/  # Install [tool.wads.ops.*] dependencies
│   ├── install-deps/     # Install Python dependencies
│   ├── run-tests/        # Run pytest with coverage
│   ├── ruff-format/      # Code formatting
│   ├── ruff-lint/        # Code linting
│   ├── build-dist/       # Build wheel/sdist
│   ├── pypi-upload/      # Upload to PyPI
│   ├── git-commit/       # Auto-commit (SSH)
│   └── git-tag/          # Create git tags
├── wads/                 # Main Python package
│   ├── populate.py       # Project creation (`populate` CLI; `--with-npm` overlay)
│   ├── pack.py           # Package publishing (`pack` CLI)
│   ├── migration.py      # Migration tools (`wads-migrate` CLI)
│   ├── templating.py     # ★ Declarative engine: TemplateSource (dict/fs/github)
│   │                     #   + Jinja2 (<< >> delimiters) + Artifact/generate()
│   ├── profiles.py       # Generation profiles/overlays (e.g. apply_npm_overlay)
│   ├── ci_config.py      # CIConfig class - reads pyproject.toml CI config
│   ├── npm_config.py     # NpmCIConfig - reads package.json wads.ci block
│   ├── install_system_deps.py  # System dependency installer
│   ├── toml_util.py      # TOML read/write helpers
│   ├── util.py           # Git, logging, path utilities
│   ├── data/             # Templates
│   │   ├── pyproject_toml_tpl.toml       # Default pyproject.toml template
│   │   ├── github_ci_uv_stub.yml         # ★ SSOT stub (default for new projects) —
│   │   │                                 #   5 lines, calls the reusable workflow
│   │   ├── github_ci_uv.yml              # Inline uv workflow (escape valve / source
│   │   │                                 #   of truth that the reusable workflow mirrors)
│   │   ├── github_ci_npm_stub.yml        # NPM CI stub (populate --with-npm)
│   │   ├── package_json_tpl.json         # package.json template w/ wads.ci block
│   │   ├── github_ci_publish_2025.yml    # Legacy 2025 CI workflow template
│   │   └── (other templates)
│   ├── agents/           # AI diagnostic agents
│   ├── scripts/          # CI helper scripts
│   └── tests/            # Test suite
├── pyproject.toml        # Wads's own config
└── README.md
```

## How Default Setup Works

### Template Flow

1. **`populate my-project`** reads the template at `wads/data/pyproject_toml_tpl.toml`
2. Loads it as TOML, merges user-provided values (name, description, author, license, etc.)
3. Writes the resulting `pyproject.toml` with Hatchling build system
4. Copies `wads/data/github_ci_uv_stub.yml` → `.github/workflows/ci.yml` (5-line stub
   that calls the reusable workflow in `i2mint/wads/.github/workflows/uv-ci.yml@master`).
   For repos that need to customize CI beyond `[tool.wads.ci.*]`, drop the stub and
   copy `wads/data/github_ci_uv.yml` inline instead.
5. Creates README.md, LICENSE, .gitignore, .gitattributes, .editorconfig, package dir

### Reusable workflow (SSOT)

Since wads 0.1.82, new projects ship a 5-line `ci.yml` stub that calls the
**reusable workflow** hosted at `i2mint/wads/.github/workflows/uv-ci.yml`. Bug
fixes and improvements to the workflow land in one place and propagate to every
consumer on their next CI run — no per-repo edit, no `wads-migrate` sweep.

| Tradeoff | Pin strategy |
|---|---|
| Float with wads (default) | `@master` — convenient; bad wads merge breaks CI everywhere on next run, but never reaches PyPI (publish is gated on workflow success) |
| Freeze | `@v0.1.81` (or any tag) — set via `wads-migrate ci-to-stub --pin @v0.1.81`; the repo only picks up wads updates when re-pinned |

The "CI failure ≠ broken release" property is what makes `@master` safe by
default: a botched wads update blocks publication of all downstream packages
until the wads fix lands, but never causes a broken artifact to ship. Repos that
require absolutely-no-CI-downtime can pin.

**Escape valve.** If a repo needs to customize the workflow itself (rare —
most customization belongs in `[tool.wads.ci.*]`), it can replace the stub with
a copy of `wads/data/github_ci_uv.yml` inline. The repo then owns CI updates
manually. Convert back to stub later with `wads-migrate ci-to-stub`.

### CI Workflow Flow (github_ci_publish_2025.yml)

The CI workflow has 4-5 jobs:

1. **setup** - Reads `[tool.wads.ci]` config, exports as outputs
2. **validation** - Matrix testing across python_versions:
   - Install system deps → Install Python deps → Ruff format → Ruff lint → Pytest → Metrics
3. **windows-validation** (optional) - Same tests on Windows, `continue-on-error: true`
4. **publish** (main/master only) - Format → Bump version → Build → PyPI upload → Commit → Tag
5. **github-pages** (optional) - Publish docs via epythet

### Migration Flow

To migrate a legacy project:

1. Run `wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml` (or use Python API)
2. Manually review and add `[tool.wads.ci]` section (use template as reference)
3. Replace `.github/workflows/ci.yml` with the 2025 template
4. Remove `setup.cfg` and `setup.py` (keep as backup if needed)
5. Verify with `pytest` and a push to a non-main branch

## Key Conventions

- **Build backend**: Hatchling (not setuptools)
- **Python version**: `>=3.10` default
- **Test matrix**: `["3.10", "3.12"]` default
- **Linting**: Ruff (replaces pylint, black, isort)
- **CI actions**: All from `i2mint/wads/actions/*@master`
- **Version bumping**: `i2mint/isee/actions/bump-version-number@master`
- **Docs**: epythet (GitHub Pages)
- **Metrics**: umpyre

### Declarative templating (since the #32 refactor)

- **Engine**: `wads/templating.py`. A *template source* is any `Mapping[str,str]`
  of relative-path → content (a `dict`, `FilesystemTemplateSource`, or
  `GithubTemplateSource`). Rendering is Jinja2 with **`<< >>` delimiters** (so
  templates don't collide with GitHub Actions `${{ }}` or shell `${}`).
  `Artifact` + `generate()` apply a declarative manifest with overwrite/skip
  semantics. `populate`'s static-file generation is driven by this engine.
- **Profiles/overlays**: `wads/profiles.py`. The default `populate` produces the
  python-lib profile (output unchanged — pinned by characterization tests in
  `wads/tests/test_populate_characterization.py`). `apply_npm_overlay` adds the
  opt-in NPM setup.
- **Dependency extras**: light core (`jinja2`, `pyyaml`, `packaging`, `argh`,
  `tomli`/`-w`) for config-reading + templating; `wads[create]` adds the heavy
  creation/publish toolchain (`requests`, `build`, `wheel`, `ruamel.yaml`).
  `wads[all]` = create + docs. The light/`create` boundary is locked by
  `wads/tests/test_light_install.py`.

### NPM CI (opt-in, `populate --with-npm`)

- Mirrors the Python model on the JS/TS side: config lives in
  `<subdir>/package.json` under a namespaced `"wads"` key (`wads.ci.*`); a stub
  (`wads/data/github_ci_npm_stub.yml`) calls the **reusable workflow**
  `i2mint/wads/.github/workflows/npm-ci.yml`.
- **Validate always; publish opt-in**: publishes only when
  `wads.ci.publish.enabled` is true AND the commit message contains
  `[publish-npm]` (distinct from the Python publish trigger). OIDC trusted
  publishing + provenance by default; version-exists guard; no auto-bump.
- **Package manager: npm (default) or pnpm.** The reusable workflow picks pnpm
  when `wads.ci.packageManager == "pnpm"` OR a `pnpm-lock.yaml` is present in
  the package dir (auto-detect in the `setup` job); else npm. The pnpm path adds
  a conditional `pnpm/action-setup` (version read from the package's
  `packageManager` field via `package_json_file`), switches the setup-node cache
  + lockfile, and installs with `pnpm install --frozen-lockfile`. lint/test/build
  and `npm publish` are unchanged. Additive: npm consumers (no field, no
  `pnpm-lock.yaml`) see byte-identical behavior on `@master`.
- `NpmCIConfig` (`wads/npm_config.py`) is the Python-side reader of that block
  (`package_manager` property; `SUPPORTED_PACKAGE_MANAGERS`).

## CLI Reference

```bash
# Create a new project
populate my-project --root-url https://github.com/user/my-project

# Create a project that also has a JS/TS component with opt-in NPM publishing
populate my-project --root-url https://github.com/user/my-project --with-npm

# Build and publish
pack go .

# Migrate setup.cfg → pyproject.toml
wads-migrate setup-to-pyproject setup.cfg

# Migrate old CI → new CI
wads-migrate ci-old-to-new .github/workflows/ci.yml

# Debug CI failures
wads-ci-debug myorg/myrepo --fix

# Analyze dependencies
wads-deps scan .

# Analyze test failures
wads-test-analyze results.xml
```

## Testing

```bash
pytest wads/tests/
```

Tests are in `wads/tests/` (not the top-level `tests/` directory).

## Common Pitfalls

- The `[tool.wads.ci]` section is **not** standard TOML metadata - it's wads-specific
- `testpaths` in the template defaults to `["tests"]` but wads itself uses `["wads/tests"]`
- The CI workflow uses `i2mint/wads/actions/*@master` - these must be on GitHub
- System deps in `[tool.wads.ops.*]` only run in CI, not locally
- Version bumping happens automatically in the publish job on main/master
