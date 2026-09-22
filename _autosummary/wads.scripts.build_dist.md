# wads.scripts.build_dist

Build Python Distribution Packages

This script builds Python distribution packages (sdist and/or wheel) using
modern PEP 517 build tools.

Usage:

```default
python -m wads.scripts.build_dist [options]
```

* **param –output-dir PATH    Output directory for built distributions (default:**
  dist)
* **param –sdist             Build source distribution (default:**
  true)
* **param –wheel             Build wheel distribution (default:**
  true)
* **param –no-sdist          Skip building source distribution:**
* **param –no-wheel          Skip building wheel distribution:**

### Functions

| [`build_distributions`](#wads.scripts.build_dist.build_distributions)([output_dir, ...])   | Build distribution packages.   |
|-------------------------------------------------------------------------------------------|--------------------------------|
| [`main`](#wads.scripts.build_dist.main)()                                   | Main entry point.              |

### wads.scripts.build_dist.build_distributions(output_dir='dist', build_sdist=True, build_wheel=True)

Build distribution packages.

* **Parameters:**
  * **output_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Output directory for distributions
  * **build_sdist** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether to build source distribution
  * **build_wheel** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether to build wheel distribution
* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
* **Returns:**
  Exit code (0 for success, 1 for failure)

### wads.scripts.build_dist.main()

Main entry point.
