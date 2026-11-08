# wads.project_setup

Project setup utilities: name checking, GitHub operations, and orchestration.

This module provides the building blocks for AI-assisted project creation.
Each function is independently useful — they can be called from Python, CLI, or
a Claude skill.

Key capabilities:

- Check package name availability on PyPI and GitHub
- Manage name candidate files (pools of potential names)
- Create GitHub repositories via the gh CLI
- Orchestrate full project creation (repo → populate → commit/push)

### Functions

| [`check_name_availability`](#wads.project_setup.check_name_availability)(name, \*[, org, npm, ...])   | Check a package name's validity and availability on PyPI (and optionally npm, GitHub).          |
|-------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| [`check_names`](#wads.project_setup.check_names)(names, \*[, org])                        | Check multiple names for availability (kwargs: `npm`, `github`, see `check_name_availability`). |
| [`create_github_repo`](#wads.project_setup.create_github_repo)(name, \*[, org, ...])             | Create a GitHub repository via the `gh` CLI.                                                    |
| [`create_misc_docs`](#wads.project_setup.create_misc_docs)(pkg_dir, \*[, sections])            | Create misc/docs/ directory with template markdown files.                                       |
| [`detect_github_username`](#wads.project_setup.detect_github_username)()                             | Detect the current GitHub username.                                                             |
| [`ensure_pypi_secret`](#wads.project_setup.ensure_pypi_secret)(repo, \*, pyproject[, ...])       | Give `repo` a `PYPI_PASSWORD` Actions secret when its CI will need one.                         |
| [`github_repo_url`](#wads.project_setup.github_repo_url)(name, \*[, org])                     | Return the GitHub repository URL for org/name.                                                  |
| [`is_available_on_github`](#wads.project_setup.is_available_on_github)(name, \*[, org])              | Check if a repository name is available on GitHub.                                              |
| [`is_available_on_npm`](#wads.project_setup.is_available_on_npm)(name, \*[, timeout])             | Check if a package name is unclaimed on the npm registry (HTTP 404 = free).                     |
| [`is_available_on_pypi`](#wads.project_setup.is_available_on_pypi)(name)                           | Check if a package name is unclaimed on PyPI.                                                   |
| [`list_name_candidate_files`](#wads.project_setup.list_name_candidate_files)()                          | List all name candidate files in the name_candidates directory.                                 |
| [`load_name_candidates`](#wads.project_setup.load_name_candidates)([filepath])                     | Load name candidates from a file or all files in the name_candidates directory.                 |
| [`pypi_project_url`](#wads.project_setup.pypi_project_url)(name)                               | Return the PyPI project page URL for a package name.                                            |
| [`repo_exists`](#wads.project_setup.repo_exists)(name, \*[, org])                         | Check if a GitHub repository exists at org/name.                                                |
| [`setup_opsward_for_project`](#wads.project_setup.setup_opsward_for_project)(pkg_dir)                   | Set up AI agent configuration using opsward, if available.                                      |
| [`setup_project`](#wads.project_setup.setup_project)(name, \*[, description, org, ...])     | Orchestrate full project creation.                                                              |

### wads.project_setup.check_name_availability(name, , org=None, npm=False, github=False)

Check a package name’s validity and availability on PyPI (and optionally npm, GitHub).

PyPI is always checked. Pass `npm=True` when the project also publishes to npm.
GitHub is checked only with `github=True` (explicit user request): GitHub
calls are rate limited, and PyPI/npm are what decide a package name.

Returns a dict with keys:
: name, valid_pep508, pypi_available, pypi_url,
  npm_available, npm_url, github_available, github_url

(keys of checks that were not run are None)

```pycon
>>> result = check_name_availability("wads")
>>> result["valid_pep508"]
True
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.project_setup.check_names(names, , org=None, \*\*kwargs)

Check multiple names for availability (kwargs: `npm`, `github`, see
`check_name_availability`). Returns a list of result dicts.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### wads.project_setup.create_github_repo(name, , org=None, description='', public=True, clone=True, clone_dir=None)

Create a GitHub repository via the `gh` CLI.

* **Parameters:**
  * **name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Repository name.
  * **org** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – GitHub org or username. Detected if not provided.
  * **description** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Repository description.
  * **public** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, create a public repo. If False, private.
  * **clone** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, clone the repo after creation.
  * **clone_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Directory to clone into. Defaults to current dir.
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  The local path to the cloned/created repository.
* **Raises:**
  * [**EnvironmentError**](https://docs.python.org/3/builtins/exceptions.html#EnvironmentError) – If `gh` CLI is not available.
  * [**CalledProcessError**](https://docs.python.org/3/library/subprocess.html#subprocess.CalledProcessError) – If repo creation fails.

### wads.project_setup.create_misc_docs(pkg_dir, , sections=None)

Create misc/docs/ directory with template markdown files.

* **Parameters:**
  * **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Project root directory.
  * **sections** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – List of section names to create. Defaults to
    [“research”, “design”, “roadmap”].
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  List of created file paths.

### wads.project_setup.detect_github_username()

Detect the current GitHub username.

Tries `gh auth status` first, then falls back to `git config user.name`.
Returns None if detection fails.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.project_setup.ensure_pypi_secret(repo, , pyproject, environ=None, pypirc=None, secret_name='PYPI_PASSWORD')

Give `repo` a `PYPI_PASSWORD` Actions secret when its CI will need one.

Org repos usually inherit an org secret; personal ones do not, and the first
merge’s publish job then fails with “Required CI values are missing” (#205).
The secret is set only if `[tool.wads.ci.publish].enabled` is true in
`pyproject` and the repo cannot already see one (its own, or an org secret
shared with it). If that cannot be established, nothing is set: a repo-level
copy would shadow an org secret. The token comes from
[`wads.ci_local.resolve_pypi_token()`](wads.ci_local.html.md#wads.ci_local.resolve_pypi_token) (`$PYPI_PASSWORD`,
`$UV_PUBLISH_TOKEN`, then `~/.pypirc` `[pypi]`) and reaches `gh` on
stdin via [`wads.secrets_cli.set_github_secret()`](wads.secrets_cli.html.md#wads.secrets_cli.set_github_secret). It is never returned,
printed or put in a message.

Returns `{"status": ..., "message": ...}`; `status` is one of `set`,
`already_present`, `publish_disabled`, `no_token`, `no_pyproject`,
`unknown`, `failed`. `message` is a one-line account (the remedy, when
not `set`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.project_setup.github_repo_url(name, , org=None)

Return the GitHub repository URL for org/name.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.project_setup.is_available_on_github(name, , org=None)

Check if a repository name is available on GitHub.

Requires the `gh` CLI to be installed and authenticated.
Returns True if no repo exists at org/name.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### wads.project_setup.is_available_on_npm(name, , timeout=10)

Check if a package name is unclaimed on the npm registry (HTTP 404 = free).

Returns None when the registry could not give a definite answer.

```pycon
>>> is_available_on_npm("zzz-nonexistent-pkg-12345")
True
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.project_setup.is_available_on_pypi(name)

Check if a package name is unclaimed on PyPI.

Returns True if the name is available (no package exists with that name).

```pycon
>>> is_available_on_pypi("wads")
False
>>> is_available_on_pypi("zzz_nonexistent_pkg_12345")
True
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### wads.project_setup.list_name_candidate_files()

List all name candidate files in the name_candidates directory.

Name candidate files are plain text files (one name per line).
Lines starting with # are comments; blank lines are ignored.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### wads.project_setup.load_name_candidates(filepath=None)

Load name candidates from a file or all files in the name_candidates directory.

* **Parameters:**
  **filepath** ([`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Specific file to load from. If None, loads from all files
  in the name_candidates directory.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  List of candidate names (deduplicated, preserving order).

### wads.project_setup.pypi_project_url(name)

Return the PyPI project page URL for a package name.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.project_setup.repo_exists(name, , org=None)

Check if a GitHub repository exists at org/name.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### wads.project_setup.setup_opsward_for_project(pkg_dir)

Set up AI agent configuration using opsward, if available.

Returns True if opsward ran successfully, False if not available.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### wads.project_setup.setup_project(name, , description='', org=None, author=None, license='mit', root_url=None, proj_rootdir=None, create_repo=True, populate=True, create_devdocs=False, setup_opsward=False, set_pypi_secret=True, verbose=True)

Orchestrate full project creation.

Steps (each independently skippable via keyword args):

1. Validate name
2. Create GitHub repo (if create_repo)
3. Populate project files (if populate)
4. Create misc/docs/ (if create_devdocs)
5. Run opsward generate (if setup_opsward and opsward is available)
6. Set the `PYPI_PASSWORD` Actions secret (if this call created the repo, and
   populate and set_pypi_secret, and publishing is enabled, and the repo cannot
   already see one; a pre-existing repo is left alone); see
   [`ensure_pypi_secret()`](#wads.project_setup.ensure_pypi_secret). If no token is found, a warning with the
   > one-line remedy is returned and printed; project creation still succeeds.

Returns a summary dict with keys: path, steps_completed, warnings.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
