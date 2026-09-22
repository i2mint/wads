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

| [`check_name_availability`](#wads.project_setup.check_name_availability)(name, \*[, org])         | Check a package name's validity and availability on PyPI and GitHub.            |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`check_names`](#wads.project_setup.check_names)(names, \*[, org])                    | Check multiple names for availability.                                          |
| [`create_github_repo`](#wads.project_setup.create_github_repo)(name, \*[, org, ...])         | Create a GitHub repository via the `gh` CLI.                                    |
| [`create_misc_docs`](#wads.project_setup.create_misc_docs)(pkg_dir, \*[, sections])        | Create misc/docs/ directory with template markdown files.                       |
| [`detect_github_username`](#wads.project_setup.detect_github_username)()                         | Detect the current GitHub username.                                             |
| [`github_repo_url`](#wads.project_setup.github_repo_url)(name, \*[, org])                 | Return the GitHub repository URL for org/name.                                  |
| [`is_available_on_github`](#wads.project_setup.is_available_on_github)(name, \*[, org])          | Check if a repository name is available on GitHub.                              |
| [`is_available_on_pypi`](#wads.project_setup.is_available_on_pypi)(name)                       | Check if a package name is unclaimed on PyPI.                                   |
| [`list_name_candidate_files`](#wads.project_setup.list_name_candidate_files)()                      | List all name candidate files in the name_candidates directory.                 |
| [`load_name_candidates`](#wads.project_setup.load_name_candidates)([filepath])                 | Load name candidates from a file or all files in the name_candidates directory. |
| [`pypi_project_url`](#wads.project_setup.pypi_project_url)(name)                           | Return the PyPI project page URL for a package name.                            |
| [`repo_exists`](#wads.project_setup.repo_exists)(name, \*[, org])                     | Check if a GitHub repository exists at org/name.                                |
| [`setup_opsward_for_project`](#wads.project_setup.setup_opsward_for_project)(pkg_dir)               | Set up AI agent configuration using opsward, if available.                      |
| [`setup_project`](#wads.project_setup.setup_project)(name, \*[, description, org, ...]) | Orchestrate full project creation.                                              |

### wads.project_setup.check_name_availability(name, , org=None)

Check a package name’s validity and availability on PyPI and GitHub.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

Returns a dict with keys:
: name, valid_pep508, pypi_available, pypi_url,
  github_available, github_url

```pycon
>>> result = check_name_availability("wads")
>>> result["valid_pep508"]
True
```

### wads.project_setup.check_names(names, , org=None)

Check multiple names for availability. Returns a list of result dicts.

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

### wads.project_setup.is_available_on_pypi(name)

Check if a package name is unclaimed on PyPI.

Returns True if the name is available (no package exists with that name).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> is_available_on_pypi("wads")
False
>>> is_available_on_pypi("zzz_nonexistent_pkg_12345")
True
```

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

### wads.project_setup.setup_project(name, , description='', org=None, author=None, license='mit', root_url=None, proj_rootdir=None, create_repo=True, populate=True, create_devdocs=False, setup_opsward=False, verbose=True)

Orchestrate full project creation.

Steps (each independently skippable via keyword args):

1. Validate name
2. Create GitHub repo (if create_repo)
3. Populate project files (if populate)
4. Create misc/docs/ (if create_devdocs)
5. Run opsward generate (if setup_opsward and opsward is available)

Returns a summary dict with keys: path, steps_completed, warnings.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
