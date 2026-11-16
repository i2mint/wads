# wads.licensing

Licensing

### Functions

| `get_licenses`([refresh])                                                                         |                                                                                                                             |
|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| [`get_licenses_from_github`](#wads.licensing.get_licenses_from_github)()                       | get_licenses_json_from_github You need to have a github token placed in the right place for this! See pygithub for details. |
| `license_body`([license, ...])                                                                    |                                                                                                                             |
| `license_info`([license, ...])                                                                    |                                                                                                                             |
| `licenses_dict`([refresh])                                                                        |                                                                                                                             |
| [`require_license`](#wads.licensing.require_license)(license)                         | The `license_info` of `license`, or a `ValueError` naming the closest keys.                                                 |
| [`resolve_author`](#wads.licensing.resolve_author)([author, pyproject_authors, url]) | Resolve the author name following a priority chain.                                                                         |
| [`substitute_license_placeholders`](#wads.licensing.substitute_license_placeholders)(license_text)    | Replace placeholders in license text with actual values.                                                                    |

### wads.licensing.get_licenses_from_github()

get_licenses_json_from_github
You need to have a github token placed in the right place for this!
See pygithub for details.

```text
license_jsons = get_licenses_json_from_github()
```

### wads.licensing.require_license(license)

The `license_info` of `license`, or a `ValueError` naming the closest keys.

`license` is a key, name or SPDX id, in any case, or a name
[`wads.toml_util.pep639_license()`](wads.toml_util.html.md#wads.toml_util.pep639_license) knows (`Apache Software License`). An
unknown one used to print the key list and carry on to write an empty LICENSE
(issue #237).

```pycon
>>> require_license("mit")["spdx_id"], require_license("APACHE-2.0")["key"]
('MIT', 'apache-2.0')
>>> require_license("Apache Software License")["key"]
'apache-2.0'
>>> require_license("apach")
Traceback (most recent call last):
  ...
ValueError: 'apach' is not a valid licence key; closest: apache-2.0 (...
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.licensing.resolve_author(author=None, pyproject_authors=None, url=None)

Resolve the author name following a priority chain.

Priority order:

1. If author is explicitly provided, use it
2. If pyproject_authors is provided, use the first author’s name
3. If url is a GitHub URL, extract the org/user from it
4. If WADS_DFLT_AUTHOR env variable is set, use it
5. Return placeholder if nothing else works

* **Parameters:**
  * **author** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Explicitly provided author name
  * **pyproject_authors** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)]) – List of author dicts from pyproject.toml
  * **url** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Project URL (e.g., GitHub URL)
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  Resolved author name or placeholder

```pycon
>>> resolve_author(author='John Doe')
'John Doe'
>>> resolve_author(pyproject_authors=[{'name': 'Jane Smith'}])
'Jane Smith'
>>> resolve_author(url='https://github.com/myorg/myrepo')
'myorg'
```

### wads.licensing.substitute_license_placeholders(license_text, author=None, year=None)

Replace placeholders in license text with actual values.

Common placeholders:

- [yyyy], [year] -> current year
- [fullname], [name of copyright owner] -> author name
- 1. -> © (optional enhancement)

* **Parameters:**
  * **license_text** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – License text with placeholders
  * **author** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Author/copyright owner name (if None, placeholder remains)
  * **year** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Year for copyright (if None, uses current year)
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Returns:**
  License text with substituted values

```pycon
>>> text = "Copyright [yyyy] [fullname]"
>>> result = substitute_license_placeholders(text, author='John', year=2025)
>>> result
'Copyright 2025 John'
```
