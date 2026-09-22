# wads.scripts.install_deps

Install Dependencies

This script installs Python dependencies from various sources including
pyproject.toml, requirements.txt, and direct package names.

Usage:

```default
python -m wads.scripts.install_deps [options]
```

* **param –pypi-packages PKG1 PKG2…  Python packages to install:**
* **param –dependency-files FILE1:**
* **param FILE2:**
* **param …  Dependency files to install from:**
* **param –extras EXTRA1:**
* **param EXTRA2:**
* **param …  Extras to install from pyproject.toml:**

### Functions

| [`install_from_dependency_files`](#wads.scripts.install_deps.install_from_dependency_files)(files[, extras])   | Install from dependency files.   |
|---------------------------------------------------------------------------------------------------|----------------------------------|
| [`install_pypi_packages`](#wads.scripts.install_deps.install_pypi_packages)(packages)                  | Install packages from PyPI.      |
| [`main`](#wads.scripts.install_deps.main)()                                           | Main entry point.                |

### wads.scripts.install_deps.install_from_dependency_files(files, extras=None)

Install from dependency files.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### wads.scripts.install_deps.install_pypi_packages(packages)

Install packages from PyPI.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### wads.scripts.install_deps.main()

Main entry point.
