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

| [`build_dist`](wads.scripts.build_dist.html.md#module-wads.scripts.build_dist)                     | Build Python Distribution Packages                                                           |
|----------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| [`install_deps`](wads.scripts.install_deps.html.md#module-wads.scripts.install_deps)                 | Install Dependencies                                                                         |
| [`read_ci_config`](wads.scripts.read_ci_config.html.md#module-wads.scripts.read_ci_config)             | Read CI Configuration and Export to GitHub Actions                                           |
| [`set_env_vars`](wads.scripts.set_env_vars.html.md#module-wads.scripts.set_env_vars)                 | Set Environment Variables from GitHub Secrets                                                |
| [`validate_ci_env`](wads.scripts.validate_ci_env.html.md#module-wads.scripts.validate_ci_env)           | CI Environment Validation Script                                                             |
| [`cargo_test_args`](wads.scripts.cargo_test_args.html.md#module-wads.scripts.cargo_test_args)           | Print the `cargo test` arguments for a maturin package (issue #166).                         |
| [`export_ci_env`](wads.scripts.export_ci_env.html.md#module-wads.scripts.export_ci_env)               | Export the pyproject-declared CI environment to `$GITHUB_ENV`.                               |
| [`npm_publish_guard`](wads.scripts.npm_publish_guard.html.md#module-wads.scripts.npm_publish_guard)       | Refuse an npm publish that would reuse the previous PyPI release's number (i2mint/wads#210). |
| [`pytest_doctest_flags`](wads.scripts.pytest_doctest_flags.html.md#module-wads.scripts.pytest_doctest_flags) | Print the `-o doctest_optionflags=...` pytest argument CI should add, if any.                |
| [`sync_version`](wads.scripts.sync_version.html.md#module-wads.scripts.sync_version)                 | Write the release version into the manifests `[tool.wads.ci.version].sync` lists.            |
