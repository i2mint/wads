# wads.toml_util

Utilities for reading and writing pyproject.toml files.

### Functions

| [`get_project_metadata`](#wads.toml_util.get_project_metadata)(pkg_dir)                | Get the [project] section from pyproject.toml.                       |
|-----------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`get_project_name`](#wads.toml_util.get_project_name)(pkg_dir)                    | Get the project name from pyproject.toml.                            |
| [`get_project_version`](#wads.toml_util.get_project_version)(pkg_dir)                 | Get the version from pyproject.toml.                                 |
| [`read_pyproject_toml`](#wads.toml_util.read_pyproject_toml)(pkg_dir)                 | Read pyproject.toml from the specified package directory.            |
| [`set_project_version`](#wads.toml_util.set_project_version)(pkg_dir, version)        | Set the version in pyproject.toml.                                   |
| [`update_project_metadata`](#wads.toml_util.update_project_metadata)(pkg_dir, \*\*kwargs) | Update project metadata in pyproject.toml.                           |
| [`update_project_url`](#wads.toml_util.update_project_url)(pkg_dir, url[, url_key])  | Update or add a URL in the [project.urls] section of pyproject.toml. |
| [`write_pyproject_toml`](#wads.toml_util.write_pyproject_toml)(pkg_dir, data)          | Write data to pyproject.toml in the specified package directory.     |

### wads.toml_util.get_project_metadata(pkg_dir)

Get the [project] section from pyproject.toml.

* **Parameters:**
  **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to the package directory
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
* **Returns:**
  Dictionary containing project metadata

### wads.toml_util.get_project_name(pkg_dir)

Get the project name from pyproject.toml.

* **Parameters:**
  **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to the package directory
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Project name or None if not found

### wads.toml_util.get_project_version(pkg_dir)

Get the version from pyproject.toml.

* **Parameters:**
  **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to the package directory
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Version string or None if not found

### wads.toml_util.read_pyproject_toml(pkg_dir)

Read pyproject.toml from the specified package directory.

* **Parameters:**
  **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to the package directory
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
* **Returns:**
  Dictionary containing the parsed TOML data
* **Raises:**
  * [**ImportError**](https://docs.python.org/3/builtins/exceptions.html#ImportError) – If tomli/tomllib is not available
  * [**FileNotFoundError**](https://docs.python.org/3/builtins/exceptions.html#FileNotFoundError) – If pyproject.toml doesn’t exist

### wads.toml_util.set_project_version(pkg_dir, version)

Set the version in pyproject.toml.

* **Parameters:**
  * **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to the package directory
  * **version** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – New version string
* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.toml_util.update_project_metadata(pkg_dir, \*\*kwargs)

Update project metadata in pyproject.toml.

* **Parameters:**
  * **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to the package directory
  * **\*\*kwargs** – Metadata fields to update
* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.toml_util.update_project_url(pkg_dir, url, url_key='Homepage')

Update or add a URL in the [project.urls] section of pyproject.toml.

* **Parameters:**
  * **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to the package directory
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The URL to set
  * **url_key** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The key to use in the urls dict (default: “Homepage”)
* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.toml_util.write_pyproject_toml(pkg_dir, data)

Write data to pyproject.toml in the specified package directory.

* **Parameters:**
  * **pkg_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to the package directory
  * **data** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]) – Dictionary to write as TOML
* **Raises:**
  [**ImportError**](https://docs.python.org/3/builtins/exceptions.html#ImportError) – If tomli_w is not available
* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
