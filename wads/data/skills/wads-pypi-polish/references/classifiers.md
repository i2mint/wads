# Trove classifiers: the menu and how to choose

Classifiers are a **controlled vocabulary** — only exact strings from the
canonical list are valid; an invalid one makes the upload fail. The canonical
SSOT is the `trove-classifiers` package (the same list PyPI uses). Validate with:

```bash
# Run the audit with trove-classifiers available — via uvx, so nothing is
# installed into the active environment (the audit uses it when importable):
uvx --python 3.12 --with trove-classifiers python scripts/audit_pyproject.py REPO
```

Browse the live list at <https://pypi.org/classifiers>.

Classifiers do **two** jobs: they render as facets on the project page, and they
power PyPI's filtered search. So they're both a quality signal and a discovery
lever. Pick the smallest set that's *true*. Padding with irrelevant classifiers
reads as noise.

## The pillars (almost every quality package sets these)

### Development Status — pick exactly one, honestly
```
Development Status :: 1 - Planning
Development Status :: 2 - Pre-Alpha
Development Status :: 3 - Alpha
Development Status :: 4 - Beta
Development Status :: 5 - Production/Stable
Development Status :: 6 - Mature
Development Status :: 7 - Inactive
```
Heuristic from version (only when no existing value and the user doesn't say):
`0.0.x`→Pre-Alpha/Alpha, `0.x`→Alpha/Beta, `1.x+`→Production/Stable. **Never auto-promote
to Production/Stable** — confirm with the user.

### Intended Audience — derive from the README
```
Intended Audience :: Developers
Intended Audience :: Science/Research
Intended Audience :: Information Technology
Intended Audience :: System Administrators
Intended Audience :: End Users/Desktop
Intended Audience :: Education
Intended Audience :: Financial and Insurance Industry
Intended Audience :: Healthcare Industry
```

### Programming Language :: Python — list every supported minor + the umbrellas
```
Programming Language :: Python :: 3
Programming Language :: Python :: 3 :: Only
Programming Language :: Python :: 3.9
Programming Language :: Python :: 3.10
Programming Language :: Python :: 3.11
Programming Language :: Python :: 3.12
Programming Language :: Python :: 3.13
Programming Language :: Python :: 3.14
```
Source the minor versions from the **CI test matrix** (truth) or, failing that,
from `requires-python`'s lower bound up to the latest version actually tested.
These are search/browse only — they do **not** gate installation (`requires-python`
does). Optionally add implementation tags if relevant:
```
Programming Language :: Python :: Implementation :: CPython
Programming Language :: Python :: Implementation :: PyPy
```

### Operating System — usually one of
```
Operating System :: OS Independent
Operating System :: POSIX :: Linux
Operating System :: MacOS
Operating System :: Microsoft :: Windows
```
Default to `OS Independent` for pure-Python packages.

### Topic — choose 1–3 that match what it is
Common ones for dev tooling / libraries:
```
Topic :: Software Development :: Libraries :: Python Modules
Topic :: Software Development :: Libraries
Topic :: Software Development :: Build Tools
Topic :: Software Development :: Code Generators
Topic :: Software Development :: Testing
Topic :: Utilities
Topic :: Internet :: WWW/HTTP
Topic :: Scientific/Engineering
Topic :: Scientific/Engineering :: Artificial Intelligence
Topic :: Scientific/Engineering :: Visualization
Topic :: Text Processing
Topic :: System :: Archiving
Topic :: Database
```

### Typing — only if it's true
```
Typing :: Typed
```
Add **only** if the package ships a `py.typed` marker file (PEP 561). Without
the marker, the claim is false and type-checkers won't honor it.

## License classifier (optional now)

Under PEP 639 the SPDX `license = "MIT"` expression is the source of truth and
`License ::` classifiers are deprecated for conveying license info. Many popular
packages still include one as a **search facet** — harmless, but optional:
```
License :: OSI Approved :: MIT License
License :: OSI Approved :: BSD License
License :: OSI Approved :: Apache Software License
License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)
```
Don't add both an SPDX `license` value *and* a `License ::` classifier if the
build backend errors on the combination (some newer setuptools/hatchling do);
prefer the SPDX expression.

## Framework / environment (when applicable)
```
Framework :: Pytest          # for a pytest plugin
Framework :: AsyncIO
Framework :: Jupyter
Environment :: Console       # CLI tools
Environment :: Web Environment
Natural Language :: English
```

## Worked example: a typed beta dev-tool library on Python 3.10–3.13

```toml
classifiers = [
  "Development Status :: 4 - Beta",
  "Intended Audience :: Developers",
  "Operating System :: OS Independent",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3 :: Only",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Topic :: Software Development :: Libraries :: Python Modules",
  "Typing :: Typed",
]
```
