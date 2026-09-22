# wads

## Console Scripts

To see available commands

```default
wads --help
```

### Functions

| `pkg_join`(\*paths)   |    |
|-----------------------|----|
| `rjoin`(\*paths)      |    |

### Modules

| [`agents`](wads.agents.md#module-wads.agents)                           | Wads AI Agents                                                                                                                   |
|------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| [`ci_config`](wads.ci_config.md#module-wads.ci_config)                     | Utilities for reading and applying CI configuration from pyproject.toml.                                                         |
| [`ci_local`](wads.ci_local.md#module-wads.ci_local)                       | Do locally what the wads CI would have done: the same `[tool.wads.ci]`, no Actions minutes.                                      |
| [`ci_secrets`](wads.ci_secrets.md#module-wads.ci_secrets)                   | Canonical registry of CI secret names for wads-managed projects.                                                                 |
| [`ci_trigger`](wads.ci_trigger.md#module-wads.ci_trigger)                   | On-demand CI: render a repo's caller stub from `[tool.wads.ci.trigger]`, and flip a repo to on-demand in one idempotent command. |
| [`config_comparison`](wads.config_comparison.md#module-wads.config_comparison)     | Compare project configuration files (pyproject.toml, setup.cfg, MANIFEST.in) against templates.                                  |
| [`fleet_migrate`](wads.fleet_migrate.md#module-wads.fleet_migrate)             | Batch migration helpers across the user's local Python ecosystem.                                                                |
| [`install_skills`](wads.install_skills.md#module-wads.install_skills)           | Install wads Claude Code skills to ~/.claude/skills/ for global availability.                                                    |
| [`install_system_deps`](wads.install_system_deps.md#module-wads.install_system_deps) | Install system dependencies from [tool.wads.ops.\*] sections in pyproject.toml.                                                  |
| [`licence_check`](wads.licence_check.md#module-wads.licence_check)             | Audit the licence perimeter of a package's installed dependency closure.                                                         |
| [`licensing`](wads.licensing.md#module-wads.licensing)                     | Licensing                                                                                                                        |
| [`migration`](wads.migration.md#module-wads.migration)                     | Migration tools for converting old setuptools/CI configurations to modern formats.                                               |
| [`npm_config`](wads.npm_config.md#module-wads.npm_config)                   | Read NPM CI configuration from a `package.json` `wads.ci` block.                                                                 |
| [`pack`](wads.pack.md#module-wads.pack)                               | Utils to package and publish.                                                                                                    |
| [`populate`](wads.populate.md#module-wads.populate)                       | Populate a package directory with useful packaging files.                                                                        |
| [`profiles`](wads.profiles.md#module-wads.profiles)                       | Declarative generation *profiles* and *overlays* built on the engine.                                                            |
| [`project_setup`](wads.project_setup.md#module-wads.project_setup)             | Project setup utilities: name checking, GitHub operations, and orchestration.                                                    |
| [`repo_audit`](wads.repo_audit.md#module-wads.repo_audit)                   | Read-only health audit of a (wads-managed) Python repo.                                                                          |
| [`scripts`](wads.scripts.md#module-wads.scripts)                         | CI and automation scripts for wads.                                                                                              |
| [`secrets_cli`](wads.secrets_cli.md#module-wads.secrets_cli)                 | `wads-secrets` — manage the CI secrets/env vars of a wads-managed repo.                                                          |
| [`setup_utils`](wads.setup_utils.md#module-wads.setup_utils)                 | Utilities for setting up packages based on pyproject.toml configuration.                                                         |
| [`templating`](wads.templating.md#module-wads.templating)                   | Declarative, template-source-driven generation engine.                                                                           |
| [`toml_util`](wads.toml_util.md#module-wads.toml_util)                     | Utilities for reading and writing pyproject.toml files.                                                                          |
| [`user_dirs`](wads.user_dirs.md#module-wads.user_dirs)                     | Platform-appropriate user directories for wads configuration and data.                                                           |
| [`util`](wads.util.md#module-wads.util)                               | wads util                                                                                                                        |
