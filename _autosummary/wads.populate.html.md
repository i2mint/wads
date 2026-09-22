# wads.populate

Populate a package directory with useful packaging files.

Provides the `populate_pkg_dir` function to add standard files like
README.md, pyproject.toml, and .gitignore.

### Functions

| [`cd`](#wads.populate.cd)(newdir[, verbose])                            | Change your working directory, do stuff, and change back to the original         |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| `clog`(\*args[, condition, log_func])                                                             |                                                                                  |
| `gen_readme_text`(name[, text])                                                                   |                                                                                  |
| [`get_github_project_description`](#wads.populate.get_github_project_description)(repo[, ...])      | Get a project's description from GitHub, falling back to a default.              |
| [`main`](#wads.populate.main)()                                           | Entry point of the `populate` console script.                                    |
| [`populate_pkg_dir`](#wads.populate.populate_pkg_dir)(pkg_dir[, version, ...])        | Populate project directory root with useful packaging files, if they're missing. |
| [`populate_proj_from_url`](#wads.populate.populate_proj_from_url)(url[, proj_rootdir, ...]) | git clone a repository and set the resulting folder up for packaging.            |
| [`update_pack_and_setup_py`](#wads.populate.update_pack_and_setup_py)(target_pkg_dir[, ...])  | Just copy over setup.py and pack.py (moving the original to be prefixed by '_'   |
| [`write_pyproject_configs`](#wads.populate.write_pyproject_configs)(pkg_dir, configs)        | Write pyproject.toml file from template and configs.                             |

### Classes

| [`PopulateTracker`](#wads.populate.PopulateTracker)()   | Track actions during populate for summary reporting.   |
|----------------------------------------------------------------------|--------------------------------------------------------|

### *class* wads.populate.PopulateTracker

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Track actions during populate for summary reporting.

#### add(filename)

Record a file that was added.

#### attention(filename, reason=None)

Record a file that needs attention with optional reason.

#### error(filename, error)

Record a file operation that failed.

#### print_summary(verbose=True)

Print emoji-based summary of what happened.

#### skip(filename)

Record a file that was skipped (already exists).

### wads.populate.cd(newdir, verbose=True)

Change your working directory, do stuff, and change back to the original

### wads.populate.get_github_project_description(repo, default_factory=<function \_mk_default_project_description>, \*, token=None, use_gh_cli=True)

Get a project’s description from GitHub, falling back to a default.

Resolution order (each step is skipped when it yields nothing):

1. **GitHub REST API.** A token (the `token` argument, else the
   `GITHUB_TOKEN` / `GH_TOKEN` env var) is sent as a bearer token so
   private repositories you can access are reachable. Without a token the
   API only sees public repos – private repos return 404.
2. \*\*The `gh` CLI\*\* (`gh repo view`), if installed and authenticated –
   the easiest way to reach private repos without managing a token.
3. `default_factory(org/proj)` – a placeholder description.

Never raises on a fetch failure: a missing or unreachable description should
not block project creation (a genuinely missing repo surfaces clearly at the
subsequent `git clone`).

### wads.populate.main()

Entry point of the `populate` console script.

### wads.populate.populate_pkg_dir(pkg_dir, version='0.0.1', description='There is a bit of an air of mystery around this project...', , root_url=None, author=None, license='mit', description_file='README.md', keywords=[], install_requires=[], long_description='file:README.md', long_description_content_type='text/markdown', include_pip_install_instruction_in_readme=True, verbose=True, overwrite=(), defaults_from=None, create_docsrc=False, skip_docsrc_gen=False, skip_ci_def_gen=False, migrate=False, create_gitattributes=True, create_setup_py=False, create_community_files=False, version_control_system=None, ci_def_path=None, ci_tpl_path=None, project_type='lib', frontend='', with_npm=False, npm_subdir='js', npm_package_name=None, npm_version='0.0.1', npm_package_manager='npm', create_tests=False, \*\*configs)

Populate project directory root with useful packaging files, if they’re missing.

```pycon
>>> from wads.populate import populate_pkg_dir
>>> import os
>>> name = 'wads'
>>> pkg_dir = f'/path/to/projects/{name}'
>>> populate_pkg_dir(pkg_dir,
...                  description='Tools for packaging',
...                  root_url=f'https://github.com/i2mint',
...                  author='OtoSense')
```

* **Parameters:**
  * **pkg_dir** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *optional*) – The relative or absolute path of the working directory. Defaults to ‘.’.
  * **version** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The desired version
  * **description** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Short description of project
  * **root_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Root url of the code repository (not the url of the project, but one level up that!)
  * **author** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Author of the package
  * **license** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – License name for the package (should be recognized by pypi). Default is ‘mit’
  * **description_file** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – File name containing a description of the project. Default is ‘README.md’
  * **keywords** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Keywords to include in pypi publication
  * **install_requires** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – The (pip install) names of of the packages required to install the package we’re generating
  * **long_description** – Text of the long description. Default is “[file:README.md](file:README.md)” (takes contents of README.md)
  * **long_description_content_type** – How to parse the long_description. Default is “text/markdown”
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Set to True if you want to log extra information during the process. Defaults to False.
  * **default_from** – Name of field to look up in wads_configs to get defaults from,
    or ‘user_input’ to get it from user input.
  * **skip_docsrc_gen** – Skip the generation of documentation stuff
  * **create_docsrc** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, create and populate a `docsrc/` directory (overrides skip_docsrc_gen).
  * **skip_ci_def_gen** – Skip the generation of the CI stuff
  * **create_setup_py** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, create setup.py for backward compatibility (default: False, not needed with Hatchling).
  * **create_community_files** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, create community files (.editorconfig, issue/PR templates, dependabot.yml). Default: False.
  * **migrate** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, migrate existing setup.cfg to pyproject.toml and old CI to new CI format.
    Will fail if old CI has unmappable content.
  * **create_gitattributes** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True (default), create a .gitattributes file with ‘

    ```
    *
    ```

    .ipynb linguist-documentation’.
  * **version_control_system** – ‘github’ or ‘gitlab’ (will TRY to be resolved from root url if not given)
  * **ci_def_path** – Path of the CI definition
  * **ci_tpl_path** – Pater of the template definition
  * **frontend** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Comma-separated list of frontend profiles to add (issue
    #39), e.g. `"ts"` or `"js,ts"`. Available profiles: `js` (the
    original npm overlay), `ts` (single-package TypeScript), and
    `ts-monorepo` (pnpm workspaces + turbo). Each component lands in its
    own subdir with its own path-filtered workflow, so multiple profiles
    never collide. Empty by default. The single-component overrides below
    (`npm_subdir` / `npm_package_name` / `npm_package_manager`) apply
    only when exactly one profile is selected; with several, each profile
    uses its own defaults.
  * **with_npm** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Back-compat alias for `frontend="js"` (issue #32). If
    True, adds the `js` profile: a `<npm_subdir>/package.json` (with a
    `wads.ci` config block) and a `.github/workflows/npm-ci.yml` stub
    calling wads’s reusable NPM workflow. Off by default.
  * **npm_subdir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Subdirectory holding the JS/TS package (default `js`).
  * **npm_package_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – npm package name (defaults to the project name).
  * **npm_version** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – initial npm package version (default `0.0.1`).
  * **npm_package_manager** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – package manager for the JS/TS package —
    `"npm"` (default) or `"pnpm"`. pnpm consumers should also declare a
    `"packageManager": "pnpm@x.y.z"` field in package.json.
  * **create_tests** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, scaffold a `tests/` folder (`__init__.py`,
    a `test_<name>.py` smoke test, and a `tests/util.py` data accessor).
    Off by default so default output is unchanged.
  * **configs** – Extra configurations
* **Returns:**

### wads.populate.populate_proj_from_url(url, proj_rootdir=None, description=None, license='mit', \*\*kwargs)

git clone a repository and set the resulting folder up for packaging.

### wads.populate.update_pack_and_setup_py(target_pkg_dir, copy_files=('setup.py', 'wads/data/MANIFEST.in'))

Just copy over setup.py and pack.py (moving the original to be prefixed by ‘_’

### wads.populate.write_pyproject_configs(pkg_dir, configs)

Write pyproject.toml file from template and configs.

* **Parameters:**
  * **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to package directory
  * **configs** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – Dictionary of configuration values
