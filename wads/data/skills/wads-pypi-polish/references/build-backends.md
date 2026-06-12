# Build-backend & schema notes

Most modern packages use the standard `[project]` table, understood by
setuptools, hatchling, flit, pdm, and uv-build. Edit `[project]` for those.

## Detect the backend

Read `[build-system].build-backend`:

| build-backend | metadata location |
|---|---|
| `setuptools.build_meta` | `[project]` (standard) |
| `hatchling.build` | `[project]` (standard) |
| `flit_core.buildapi` | `[project]` (standard) |
| `pdm.backend` | `[project]` (standard) |
| `uv_build` | `[project]` (standard) |
| `poetry.core.masonry.api` | `[project]` **and/or** legacy `[tool.poetry]` |

## Poetry's two modes

Poetry **≥ 2.0** (Jan 2025) supports the standard `[project]` table. Poetry
**< 2.0** uses only `[tool.poetry]`, where the field names differ:

| Standard `[project]` | Legacy `[tool.poetry]` |
|---|---|
| `description` | `description` |
| `keywords` | `keywords` |
| `classifiers` | `classifiers` |
| `[project.urls]` | `[tool.poetry.urls]` (also `homepage`/`repository`/`documentation` keys) |
| `authors = [{name=…, email=…}]` | `authors = ["Name <email>"]` |
| `license = "MIT"` | `license = "MIT"` |

If a file already uses `[tool.poetry]`, **stay in that schema** unless the user
wants to migrate to `[project]` (a bigger change). Detect by presence of a
`[tool.poetry]` table with a `name`/`version` key.

## SPDX license (PEP 639)

Prefer the string form:

```toml
license = "MIT"
license-files = ["LICENSE"]      # or ["LICEN[CS]E*"]
```

Avoid the deprecated table form `license = { text = "MIT" }` /
`license = { file = "LICENSE" }`. If the backend version predates PEP 639
support and errors on the string form, fall back to the table form and note it.
Backend versions that added PEP 639 support: hatchling 1.27, setuptools 77.0.3,
flit-core 3.12, pdm-backend 2.4.0, poetry-core 2.2.0, uv-build 0.7.19.

## Dynamic fields

Common to compute `version` (and sometimes `readme`) at build time:

```toml
[project]
dynamic = ["version"]
```

Don't convert a static version to dynamic (or vice-versa) as part of polishing —
that's a build-config change, out of scope. Just respect whichever is in use.

## Formatting discipline when editing

- Preserve the file's existing quote style (`'` vs `"`), indentation, and
  comments. Match neighbors.
- Add new tables adjacent to related ones; don't reorder existing tables.
- Keep lists one-item-per-line if the file already does.
- After editing, parse to confirm validity (the audit script does this), and if
  build tooling is present, do a metadata build to confirm.
