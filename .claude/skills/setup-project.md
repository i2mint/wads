# Skill: Create a New Python Project with Wads

Use this skill when asked to create a new Python project from scratch using the wads system.

## Overview

Creates a complete Python project with:
- `pyproject.toml` (Hatchling build, wads CI config)
- GitHub Actions CI/CD workflow
- README.md, LICENSE, .gitignore, .gitattributes, .editorconfig
- Package directory with `__init__.py`
- Optional: issue templates, PR template, dependabot config

## Quick Method (CLI)

```bash
populate PROJECT_NAME \
  --root-url https://github.com/ORG/PROJECT_NAME \
  --description "Project description" \
  --author "Author Name" \
  --license mit
```

## Manual Method

### 1. Create Directory Structure

```
project-name/
├── .github/workflows/ci.yml
├── .gitignore
├── .gitattributes
├── .editorconfig
├── LICENSE
├── README.md
├── pyproject.toml
└── project_name/
    ├── __init__.py
    └── tests/
        └── __init__.py
```

### 2. Copy Templates

Templates are in the wads package at `wads/data/`:

| Template | Destination |
|----------|-------------|
| `pyproject_toml_tpl.toml` | `pyproject.toml` |
| `github_ci_publish_2025.yml` | `.github/workflows/ci.yml` |
| `.gitignore_tpl` | `.gitignore` |
| `.gitattributes_tpl` | `.gitattributes` |
| `.editorconfig_tpl` | `.editorconfig` |

### 3. Fill in pyproject.toml

Replace all empty strings with actual values:
- `name`, `version`, `description`
- `authors`, `license`, `keywords`
- `dependencies`
- `Homepage` URL

### 4. Initialize Git

```bash
cd project-name
git init
git add .
git commit -m "Initial project setup with wads"
```

### 5. Configure GitHub

- Create GitHub repository
- Add secrets: `PYPI_USERNAME`, `PYPI_PASSWORD`, `SSH_PRIVATE_KEY`
- Push to trigger CI

## Expected Results

- First push to a non-main branch runs validation only (tests, lint, format)
- First push to main/master runs validation + publish to PyPI
- GitHub Pages docs published automatically (if epythet configured)

## Verification Checklist

- [ ] `pip install -e ".[dev]"` succeeds
- [ ] `pytest` passes
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] CI workflow runs successfully on push
