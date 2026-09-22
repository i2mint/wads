# wads.scripts

CI and automation scripts for wads.

These scripts extract complex logic from GitHub Actions workflow files,
making them easier to test, maintain, and reuse.

Available scripts:

> - build_dist: Build Python distribution packages
> - install_deps: Install Python dependencies
> - read_ci_config: Read CI configuration from pyproject.toml
> - set_env_vars: Set environment variables from GitHub Secrets
> - validate_ci_env: Validate CI environment variables

### Modules

| [`build_dist`](wads.scripts.build_dist.md#module-wads.scripts.build_dist)           | Build Python Distribution Packages                             |
|------------------------------------------------------------------------------------------------------|----------------------------------------------------------------|
| [`install_deps`](wads.scripts.install_deps.md#module-wads.scripts.install_deps)       | Install Dependencies                                           |
| [`read_ci_config`](wads.scripts.read_ci_config.md#module-wads.scripts.read_ci_config)   | Read CI Configuration and Export to GitHub Actions             |
| [`set_env_vars`](wads.scripts.set_env_vars.md#module-wads.scripts.set_env_vars)       | Set Environment Variables from GitHub Secrets                  |
| [`validate_ci_env`](wads.scripts.validate_ci_env.md#module-wads.scripts.validate_ci_env) | CI Environment Validation Script                               |
| [`export_ci_env`](wads.scripts.export_ci_env.md#module-wads.scripts.export_ci_env)     | Export the pyproject-declared CI environment to `$GITHUB_ENV`. |
