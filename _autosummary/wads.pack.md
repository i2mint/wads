# wads.pack

Utils to package and publish.

The typical sequence of the methodic and paranoid could be something like this:

```default
python pack.py current-configs  # see what you got
python pack.py increment-configs-version  # update (increment the version and write that in setup.cfg
python pack.py current-configs-version  # see that it worked
python pack.py current-configs  # ... if you really want to see the whole configs again (you're really paranoid)
python pack.py run-setup  # see that it worked
python pack.py twine-upload-dist  # publish
# and then go check things work...
```

If you’re crazy (or know what you’re doing) just do

```default
python pack.py go
```

### Module Attributes

| [`COMMANDS`](#wads.pack.COMMANDS)   | The commands `pack` exposes, in the order they appear in `pack --help`.   |
|-------------------------------------------------------------|---------------------------------------------------------------------------|

### Functions

| [`check_in`](#wads.pack.check_in)(commit_message, \*[, work_tree, ...])     | Validate, normalize, stage, commit and push your local changes to a remote repository.                                            |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| `clog`(condition, \*args[, log_func])                                                               |                                                                                                                                   |
| `current_configs`(pkg_dir)                                                                          |                                                                                                                                   |
| `current_configs_version`(pkg_dir)                                                                  |                                                                                                                                   |
| [`current_pypi_version`](#wads.pack.current_pypi_version)(pkg_dir, \*[, name, ...])     | Return version of package on pypi.python.org using json.                                                                          |
| `delete_pkg_directories`(pkg_dir[, verbose])                                                        |                                                                                                                                   |
| [`extract_pkg_dir_and_name`](#wads.pack.extract_pkg_dir_and_name)(pkg_spec, \*[, validate]) | Extracts the pkg_dir and pkg_dirname from the input `pkg_spec`.                                                                   |
| [`folders_that_have_init_py_files`](#wads.pack.folders_that_have_init_py_files)(pkg_dir)           | Get a list of folders in the package directory that have an \_\_init_\_.py file.                                                  |
| `generate_and_publish_docs`(pkg_dir, \*[, ...])                                                     |                                                                                                                                   |
| [`get_module_path`](#wads.pack.get_module_path)(module)                            | Get the path to the directory containing the module's code file.                                                                  |
| [`get_name_from_configs`](#wads.pack.get_name_from_configs)(pkg_dir, \*[, ...])          | Get name from local config file (pyproject.toml or setup.cfg)                                                                     |
| [`get_pkg_name`](#wads.pack.get_pkg_name)(pkg_spec[, validate])                 | Get the name of the package from a package name, module object or path.                                                           |
| `git_commit_and_push`(pkg_dir, \*[, version, ...])                                                  |                                                                                                                                   |
| [`go`](#wads.pack.go)(pkg_dir, \*[, version, publish_docs_to, ...])   | Update version, package and deploy: Runs in a sequence: increment_configs_version, update_setup_cfg, run_setup, twine_upload_dist |
| [`goo`](#wads.pack.goo)(pkg_dir, commit_message, \*[, git_dir, ...])   | Validate, normalize, stage, commit and push your local changes to a remote repository.                                            |
| [`highest_pypi_version`](#wads.pack.highest_pypi_version)(pkg_dir, \*[, name, ...])     | Return version of package on pypi.python.org using json.                                                                          |
| `highest_tag_version`(pkg_spec[, ...])                                                              |                                                                                                                                   |
| [`http_get_json`](#wads.pack.http_get_json)(url[, use_requests])                 | Make ah http request to url and get json, and return as python dict                                                               |
| [`increment_configs_version`](#wads.pack.increment_configs_version)(pkg_dir, \*[, version])  | Increment version in config file (pyproject.toml and/or setup.cfg).                                                               |
| `increment_version`(version_str)                                                                    |                                                                                                                                   |
| [`main`](#wads.pack.main)()                                             | Entry point of the `pack` console script.                                                                                         |
| `next_version_for_package`(pkg_dir[, name, ...])                                                    |                                                                                                                                   |
| `pjoin`(\*p)                                                                                        |                                                                                                                                   |
| [`postprocess_ini_section_items`](#wads.pack.postprocess_ini_section_items)(items)               | Transform newline-separated string values into actual list of strings (assuming that intent)                                      |
| [`preprocess_ini_section_items`](#wads.pack.preprocess_ini_section_items)(items)                | Transform list values into newline-separated strings, in view of writing the value to a ini formatted section                     |
| [`process_missing_module_docstrings`](#wads.pack.process_missing_module_docstrings)(\*, pkg_dir)     | Goes through modules of package, sees which ones don't have docstrings, and gives you the option to write one.                    |
| [`pyproject_toml_version`](#wads.pack.pyproject_toml_version)(pkg_spec)                   | Get version from pyproject.toml file.                                                                                             |
| `raise_error`(msg[, error_type])                                                                    |                                                                                                                                   |
| [`read_and_resolve_setup_configs`](#wads.pack.read_and_resolve_setup_configs)(pkg_dir, \*[, ...]) | make setup params and call setup                                                                                                  |
| `read_configs`(pkg_dir[, postproc, section, ...])                                                   |                                                                                                                                   |
| [`run_setup`](#wads.pack.run_setup)(pkg_dir)                                 | Run `python -m build` (modern PEP 517 compliant build)                                                                            |
| [`set_version`](#wads.pack.set_version)(pkg_dir, version)                      | Update version in config file (pyproject.toml and/or setup.cfg)                                                                   |
| [`setup_cfg_version`](#wads.pack.setup_cfg_version)(pkg_spec)                        | Get version from setup.cfg file.                                                                                                  |
| [`sorted_versions`](#wads.pack.sorted_versions)(strings[, version_patch_prefix])   | Filter out and return version strings in (versioning) descending order.                                                           |
| [`twine_upload_dist`](#wads.pack.twine_upload_dist)(pkg_dir, \*[, options_str])      | Publish to pypi.                                                                                                                  |
| [`update_setup_cfg`](#wads.pack.update_setup_cfg)(pkg_dir, \*[, new_deploy, ...])   | Update setup.cfg or pyproject.toml.                                                                                               |
| [`validate_package_name`](#wads.pack.validate_package_name)(name[, raise_error])         | Validate that a package name follows PEP 508 naming conventions.                                                                  |
| [`validate_versions`](#wads.pack.validate_versions)(versions[, ...])                 | Validate versions from different sources.                                                                                         |
| `versions_from_different_sources`(pkg_spec)                                                         |                                                                                                                                   |
| [`versions_from_pypi`](#wads.pack.versions_from_pypi)(pkg_dir, \*[, name, ...])       | Return version of package on pypi.python.org using json.                                                                          |
| `versions_from_tags`(pkg_spec[, ...])                                                               |                                                                                                                                   |
| `write_configs`(pkg_dir, configs[, preproc, ...])                                                   |                                                                                                                                   |

### wads.pack.COMMANDS *= [<function generate_and_publish_docs>, <function current_configs>, <function increment_configs_version>, <function current_configs_version>, <function twine_upload_dist>, <function read_and_resolve_setup_configs>, <function update_setup_cfg>, <function go>, <function goo>, <function check_in>, <function get_name_from_configs>, <function run_setup>, <function current_pypi_version>, <function extract_pkg_dir_and_name>, <function git_commit_and_push>, <function process_missing_module_docstrings>]*

The commands `pack` exposes, in the order they appear in `pack --help`.

### wads.pack.check_in(commit_message, , work_tree='.', git_dir=None, auto_choose_default_action=False, bypass_docstring_validation=False, bypass_tests=False, bypass_code_formatting=False, verbose=False, pre_git_hooks=())

Validate, normalize, stage, commit and push your local changes to a remote repository.

* **Parameters:**
  * **commit_message** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Your commit message
  * **work_tree** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The relative or absolute path of the working directory. Defaults to ‘.’.
  * **git_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – The relative or absolute path of the git directory. If None, it will be taken to be “{work_tree}/.git/”. Defaults to None.
  * **auto_choose_default_action** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Set to True if you don’t want to be prompted and automatically select the default action. Defaults to False.
  * **bypass_docstring_validation** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Set to True if you don’t want to check if a docstring exists for every module, class and function. Defaults to False.
  * **bypass_tests** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Set to True if you don’t want to run doctests and other tests. Defaults to False.
  * **bypass_code_formatting** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Set to True if you don’t want the code to be automatically formatted using axblack. Defaults to False.
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Set to True if you want to log extra information during the process. Defaults to False.
  * **pre_git_hooks** ([`Sequence`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – A sequence of git commands to run before the git commit. Defaults to ().

### wads.pack.current_pypi_version(pkg_dir, , name=None, use_requests=True)

Return version of package on pypi.python.org using json.

Routes through [`http_get_json()`](#wads.pack.http_get_json), so it works whether or not the optional
`requests` dependency is installed (urllib fallback), and returns `None`
when the package isn’t on PyPI instead of raising.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> current_pypi_version('wads')
'0.1.19'
```

### wads.pack.extract_pkg_dir_and_name(pkg_spec, , validate=True)

Extracts the pkg_dir and pkg_dirname from the input `pkg_spec`.
Optionally validates the pkg_dir is actually one (has a pkg_name/_\_init_\_.py file)

Also processes input to get a path from a pathlib.Path object, or a module object,
or a module/package name string.

`pkg_spec` can be an imported package (must be a locally developped package)
whose name and containing directory is the same):

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> import wads
>>> extract_pkg_dir_and_name(wads)
(.../wads', 'wads')
```

You can also just specify the name of the package (it will be imported):

```pycon
>>> extract_pkg_dir_and_name('wads')
('.../wads', 'wads')
```

Or you can specify the path to the package directory explicitly:

```pycon
>>> extract_pkg_dir_and_name('/home/user/projects/wads')
('/home/user/projects/wads', 'wads')
```

### wads.pack.folders_that_have_init_py_files(pkg_dir)

Get a list of folders in the package directory that have an \_\_init_\_.py file.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> folders_that_have_init_py_files('/home/user/projects/wads')
['wads', 'wads/util', 'wads/pack', 'wads/docs_gen']
```

### wads.pack.get_module_path(module)

Get the path to the directory containing the module’s code file.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> import os
>>> get_module_path(os)
'/usr/lib/python3.8'
>>> import sklearn
>>> get_module_path(sklearn)
'/usr/local/lib/python3.8/dist-packages/sklearn'
>>> import local_package
>>> get_module_path(local_package)
'/home/user/projects/local_package/local_package'
```

Read more: [https://github.com/i2mint/wads/discussions/7#discussioncomment-9761632](https://github.com/i2mint/wads/discussions/7#discussioncomment-9761632)

### wads.pack.get_name_from_configs(pkg_dir, , assert_exists=True, validate_name=True)

Get name from local config file (pyproject.toml or setup.cfg)

### wads.pack.get_pkg_name(pkg_spec, validate=True)

Get the name of the package from a package name, module object or path.
Optionally validates some naming rules.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.pack.go(pkg_dir, , version=None, publish_docs_to=None, verbose=True, skip_git_commit=False, answer_yes_to_all_prompts=False, twine_upload_options_str='', keep_dist_pkgs=False, commit_message='')

Update version, package and deploy:
Runs in a sequence: increment_configs_version, update_setup_cfg, run_setup, twine_upload_dist

* **Parameters:**
  * **version** – The desired version (if not given, will increment the current version
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether to print stuff or not
  * **skip_git_commit** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether to skip the git commit and push step
  * **answer_yes_to_all_prompts** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If you do git commit and push, whether to ask confirmation after showing status

### wads.pack.goo(pkg_dir, commit_message, , git_dir=None, auto_choose_default_action=False, bypass_docstring_validation=False, bypass_tests=False, bypass_code_formatting=False, verbose=False)

Validate, normalize, stage, commit and push your local changes to a remote repository.

* **Parameters:**
  * **pkg_dir** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *optional*) – The relative or absolute path of the working directory. Defaults to ‘.’.
  * **commit_message** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Your commit message
  * **git_dir** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *optional*) – The relative or absolute path of the git directory. If None, it will be taken to be “{work_tree}/.git/”. Defaults to None.
  * **auto_choose_default_action** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool) *,* *optional*) – Set to True if you don’t want to be prompted and automatically select the default action. Defaults to False.
  * **bypass_docstring_validation** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool) *,* *optional*) – Set to True if you don’t want to check if a docstring exists for every module, class and function. Defaults to False.
  * **bypass_tests** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool) *,* *optional*) – Set to True if you don’t want to run doctests and other tests. Defaults to False.
  * **bypass_code_formatting** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool) *,* *optional*) – Set to True if you don’t want the code to be automatically formatted using axblack. Defaults to False.
  * **verbose** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool) *,* *optional*) – Set to True if you want to log extra information during the process. Defaults to False.

### wads.pack.highest_pypi_version(pkg_dir, , name=None, use_requests=True)

Return version of package on pypi.python.org using json.

```pycon
>>> highest_pypi_version('wads')
'0.1.19'
```

* **Parameters:**
  **package** – Name of the package
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  A version (string) or None if there was an exception (usually means there

### wads.pack.http_get_json(url, use_requests=True)

Make ah http request to url and get json, and return as python dict

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.pack.increment_configs_version(pkg_dir, , version=None)

Increment version in config file (pyproject.toml and/or setup.cfg).

### wads.pack.main()

Entry point of the `pack` console script.

### wads.pack.postprocess_ini_section_items(items)

Transform newline-separated string values into actual list of strings (assuming that intent)

* **Return type:**
  [`Generator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Generator)

```pycon
>>> section_from_ini = {
...     'name': 'wads',
...     'keywords': '\n\tpackaging\n\tpublishing'
... }
>>> section_for_python = dict(postprocess_ini_section_items(section_from_ini))
>>> section_for_python
{'name': 'wads', 'keywords': ['packaging', 'publishing']}
```

### wads.pack.preprocess_ini_section_items(items)

Transform list values into newline-separated strings, in view of writing the value to a ini formatted section

* **Return type:**
  [`Generator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Generator)

```pycon
>>> section = {
...     'name': 'wads',
...     'keywords': ['documentation', 'packaging', 'publishing']
... }
>>> for_ini = dict(preprocess_ini_section_items(section))
>>> print('keywords =' + for_ini['keywords'])
keywords =
    documentation
    packaging
    publishing
```

### wads.pack.process_missing_module_docstrings(, pkg_dir, action='input', exceptions=(), docstr_template='"""\\\\n{user_input}\\\\n"""\\\\n')

Goes through modules of package, sees which ones don’t have docstrings,
and gives you the option to write one.

The function will go through all .py files (except those mentioned in exceptions),
check if there’s a module docstring (that is, that the first non-white characters are
triple-quotes (double or single)).

What happens with that depends on the `action` argument,

If `action='list'`, those modules missing docstrings will be listed.
If `action='count'`, the count of those modules missing docstrings will be returned.

If `action='input'`, for every module you’ll be given the option to enter a
SINGLE LINE module docstring (though you could include multi-lines with n).
Just type the docstring you want and hit enter to go to the next module with missing docstring.
Or, you can also:

> - type exit, or e: To exit this process
> - type skip, or s: To skip the module and go to the next
> - type funcs, or f: To see a print out of functions, classes, and methods
> - just hit enter, to get some lines of code (the first, then the next, etc.)
> - enter a number, or a number:number, to specify what lines you want to see printed

Printing lines helps you write an informed module docstring

:keyword module, docstr, docstrings, module doc strings

### wads.pack.pyproject_toml_version(pkg_spec)

Get version from pyproject.toml file.

### wads.pack.read_and_resolve_setup_configs(pkg_dir, , new_deploy=False, version=None, assert_names=True)

make setup params and call setup

* **Parameters:**
  * **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Directory where the pkg is (which is also where the setup.cfg is)
  * **new_deploy** – whether this setup for a new deployment (publishing to pypi) or not
  * **version** – The version number to set this up as.
    If not given will look at setup.cfg[metadata] for one,
    and if not found there will use the current version (requesting pypi.org)
    and bump it if the new_deploy flag is on

### wads.pack.run_setup(pkg_dir)

Run `python -m build` (modern PEP 517 compliant build)

### wads.pack.set_version(pkg_dir, version)

Update version in config file (pyproject.toml and/or setup.cfg)

### wads.pack.setup_cfg_version(pkg_spec)

Get version from setup.cfg file.

### wads.pack.sorted_versions(strings, version_patch_prefix='')

Filter out and return version strings in (versioning) descending order.

### wads.pack.twine_upload_dist(pkg_dir, , options_str=None)

Publish to pypi. Runs `python -m twine upload dist/*`

### wads.pack.update_setup_cfg(pkg_dir, , new_deploy=False, version=None, verbose=True)

Update setup.cfg or pyproject.toml.
If version is not given, will ask pypi (via http request) what the current version
is, and increment that.

### wads.pack.validate_package_name(name, raise_error=True)

Validate that a package name follows PEP 508 naming conventions.

Package names must:

- Begin and end with ASCII letters or digits
- Contain only ASCII letters, digits, underscores, hyphens, and periods

* **Parameters:**
  * **name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The package name to validate
  * **raise_error** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, raises ValueError on invalid name. If False, returns bool.
* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
* **Returns:**
  True if valid, False if invalid (when raise_error=False)
* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If name is invalid and raise_error=True

### Examples

```pycon
>>> validate_package_name('wads')
True
>>> validate_package_name('wads-test')
True
>>> validate_package_name('wads_test')
True
>>> validate_package_name('_wads_test', raise_error=False)
False
>>> validate_package_name('wads-test-', raise_error=False)
False
```

### wads.pack.validate_versions(versions, action_when_not_valid=<function raise_error>)

Validate versions from different sources.

You get the versions input from the `versions_from_different_sources` function.

* **Parameters:**
  * **versions** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – A dictionary with the versions from different sources
  * **action_when_not_valid** – A function that will be called when the versions are not valid
    Default is to raise a ValueError with the error message.
    Another option is to print the error message, log it, or issue a warning.
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
* **Returns:**
  The versions if they are valid

### wads.pack.versions_from_pypi(pkg_dir, , name=None, use_requests=True)

Return version of package on pypi.python.org using json.

* **Parameters:**
  **package** – Name of the package
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
* **Returns:**
  A version (string) or None if there was an exception (usually means there
