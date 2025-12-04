# Wads Utilities Reference

This guide covers the command-line utilities provided by wads for debugging CI failures and migrating projects.

## Table of Contents

- [wads-ci-debug](#wads-ci-debug) - Diagnose and fix CI failures
- [wads-migrate](#wads-migrate) - Migrate projects to modern formats
- [populate](#populate) - Create new Python projects
- [pack](#pack) - Build and publish packages

---

## wads-ci-debug

Diagnose GitHub Actions CI failures and generate fix instructions.

### Installation

```bash
pip install wads
```

The `wads-ci-debug` command is automatically available after installation.

### Basic Usage

```bash
# Analyze latest CI failure
wads-ci-debug myorg/myrepo

# Analyze specific workflow run
wads-ci-debug myorg/myrepo --run-id 1234567890

# Generate fix instructions
wads-ci-debug myorg/myrepo --fix

# Save fix instructions to current directory
wads-ci-debug myorg/myrepo --fix --local-repo .
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `repo` | Yes | Repository in format `owner/name` (e.g., `i2mint/wads`) |
| `--run-id` | No | Specific workflow run ID to analyze (defaults to latest failed run) |
| `--fix` | No | Generate detailed fix instructions |
| `--local-repo` | No | Path to local repository clone (for saving fix instructions) |

### What It Does

1. **Fetches CI Logs:** Downloads logs from GitHub Actions for the specified run
2. **Parses Failures:** Extracts test failures, import errors, and other issues
3. **Identifies Root Causes:** Analyzes error patterns and tracebacks
4. **Generates Fixes:** Creates actionable fix instructions with file locations

### Example Output

```
================================================================================
CI DIAGNOSIS REPORT
================================================================================
Repository: i2mint/mypackage
Run ID: 7891011121
Status: FAILURE
Run URL: https://github.com/i2mint/mypackage/actions/runs/7891011121

================================================================================
TEST FAILURES (2 found)
================================================================================

1. test_audio_processing
   Error: ModuleNotFoundError: No module named 'pydub'
   File: tests/test_audio.py:5

   Root Cause: Missing dependency 'pydub'

2. test_file_conversion
   Error: FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'
   File: src/mypackage/converter.py:42

   Root Cause: Missing system dependency 'ffmpeg'

================================================================================
RECOMMENDATIONS
================================================================================

1. Add 'pydub' to project dependencies in pyproject.toml:

   [project]
   dependencies = [
       "pydub>=0.25.1",
   ]

2. Add ffmpeg as system dependency in pyproject.toml:

   [tool.wads.ops.ffmpeg]
   description = "Audio/video processing tool"
   install.linux = "sudo apt-get install -y ffmpeg"
   install.macos = "brew install ffmpeg"
```

### With `--fix` Flag

When using `--fix`, a detailed file `CI_FIX_INSTRUCTIONS.md` is created:

```markdown
# CI Fix Instructions

## Test Failures

### 1. test_audio_processing
**Error:** ModuleNotFoundError: No module named 'pydub'
**File:** tests/test_audio.py:5

**Fix:**
Add to pyproject.toml:
\`\`\`toml
[project]
dependencies = [
    "pydub>=0.25.1",
]
\`\`\`

### 2. test_file_conversion
**Error:** FileNotFoundError: ffmpeg not found
**File:** src/mypackage/converter.py:42

**Fix:**
Add to pyproject.toml:
\`\`\`toml
[tool.wads.ops.ffmpeg]
description = "Audio/video processing"
install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"
\`\`\`

Then ensure your CI workflow includes:
\`\`\`yaml
- name: Install System Dependencies
  uses: i2mint/wads/actions/install-system-deps@master
\`\`\`
```

### Environment Variables

**`GITHUB_TOKEN`** (optional): GitHub personal access token for accessing private repositories or increasing rate limits.

```bash
export GITHUB_TOKEN=ghp_your_token_here
wads-ci-debug myorg/private-repo
```

### Common Use Cases

**1. Quick diagnosis of latest failure:**
```bash
wads-ci-debug myorg/myrepo
```

**2. Investigate specific run:**
```bash
# Get run ID from GitHub Actions UI URL
wads-ci-debug myorg/myrepo --run-id 7891011121
```

**3. Generate fixes for team:**
```bash
cd /path/to/repo
wads-ci-debug myorg/myrepo --fix --local-repo .
# Creates CI_FIX_INSTRUCTIONS.md
git add CI_FIX_INSTRUCTIONS.md
git commit -m "Add CI fix instructions"
```

---

## wads-migrate

Migrate legacy projects to modern formats.

### Installation

```bash
pip install wads
```

### Commands

#### setup-to-pyproject

Convert `setup.cfg` to `pyproject.toml`:

```bash
wads-migrate setup-to-pyproject setup.cfg -o pyproject.toml
```

**Arguments:**
- `input`: Path to setup.cfg file or directory containing it
- `-o, --output`: Output file path (default: `pyproject.toml`)

**Example:**

```bash
# From specific file
wads-migrate setup-to-pyproject /path/to/setup.cfg -o pyproject.toml

# From directory (auto-finds setup.cfg)
wads-migrate setup-to-pyproject . -o pyproject.toml

# Use default output name
wads-migrate setup-to-pyproject setup.cfg
```

**What Gets Migrated:**
- Package metadata (name, version, description, author, etc.)
- Dependencies and optional dependencies
- Entry points (console_scripts, gui_scripts)
- Project URLs
- Classifiers and keywords
- Python version requirements

**Output Format:**
Modern `pyproject.toml` using Hatchling build backend.

#### ci-old-to-new

Convert old GitHub CI workflow to new format:

```bash
wads-migrate ci-old-to-new .github/workflows/old-ci.yml -o .github/workflows/ci.yml
```

**Arguments:**
- `input`: Path to old CI workflow file
- `-o, --output`: Output file path (optional, prints to stdout if not specified)
- `--project-name`: Project name if not found in old CI file

**Example:**

```bash
# Save to new file
wads-migrate ci-old-to-new .github/workflows/ci.yml -o .github/workflows/ci-new.yml

# Print to stdout (review before saving)
wads-migrate ci-old-to-new .github/workflows/ci.yml

# Specify project name
wads-migrate ci-old-to-new old-ci.yml --project-name myproject -o ci.yml
```

**What Gets Updated:**
- Action versions (checkout@v4, setup-python@v6)
- Linting/formatting (pylint → ruff)
- Modern composite actions
- Workflow structure and naming

### Python API

You can also use the migration tools programmatically:

```python
from wads.migration import migrate_setuptools_to_hatching, migrate_github_ci_old_to_new

# Migrate setup.cfg
pyproject_content = migrate_setuptools_to_hatching('setup.cfg')
with open('pyproject.toml', 'w') as f:
    f.write(pyproject_content)

# Migrate from dict
config = {
    'metadata': {
        'name': 'myproject',
        'version': '1.0.0',
        'description': 'My project'
    }
}
pyproject_content = migrate_setuptools_to_hatching(config)

# Migrate CI workflow
new_ci = migrate_github_ci_old_to_new('.github/workflows/ci.yml')
with open('.github/workflows/ci-new.yml', 'w') as f:
    f.write(new_ci)

# With defaults
new_ci = migrate_github_ci_old_to_new(
    'ci.yml',
    defaults={'project_name': 'myproject'}
)
```

---

## populate

Create new Python project with modern tooling.

### Basic Usage

```bash
# Create project in current directory
populate .

# Create new directory for project
populate my-project

# With GitHub URL
populate my-project --root-url https://github.com/myorg/my-project
```

### Common Options

```bash
populate my-project \
  --root-url https://github.com/myorg/my-project \
  --description "My awesome Python project" \
  --author "Your Name <email@example.com>" \
  --license mit \
  --keywords "python,package,tools"
```

### All Options

| Option | Description | Default |
|--------|-------------|---------|
| `--description` | Project description | - |
| `-r, --root-url` | GitHub repository URL | - |
| `-a, --author` | Author name and email | - |
| `-l, --license` | License type (mit, apache, bsd, etc.) | mit |
| `--description-file` | README file name | README.md |
| `-k, --keywords` | Comma-separated keywords | - |
| `--install-requires` | Dependencies | - |
| `-v, --verbose` | Verbose output | False |
| `-o, --overwrite` | Files to overwrite | () |
| `--defaults-from` | Config file for defaults | - |

### What Gets Created

```
my-project/
├── pyproject.toml          # Modern build configuration
├── README.md               # Project README
├── LICENSE                 # License file
├── .gitignore             # Python gitignore
├── .gitattributes         # Git attributes
└── my_project/
    └── __init__.py        # Package init
```

### Configuring Defaults

Create a custom config file:

```json
{
  "populate_dflts": {
    "root_url": "https://github.com/myorg",
    "author": "Your Name <email@example.com>",
    "license": "mit",
    "keywords": ["python", "tools"]
  }
}
```

Use it with:

```bash
populate my-project --defaults-from my-config.json
```

Or set environment variable:

```bash
export WADS_CONFIGS_FILE=/path/to/my-config.json
populate my-project
```

---

## pack

Build and publish Python packages to PyPI.

### Quick Usage

```bash
# All-in-one: increment version, build, and publish
pack go .

# First release (specify version)
pack go --version 0.1.0 .
```

### Step-by-Step

```bash
# 1. View current configuration
pack current-configs

# 2. Increment version
pack increment-configs-version

# 3. Verify version was updated
pack current-configs-version

# 4. Build package
pack run-setup

# 5. Upload to PyPI
pack twine-upload-dist
```

### Commands

| Command | Description |
|---------|-------------|
| `current-configs` | Display current package configuration |
| `current-configs-version` | Display current version |
| `increment-configs-version` | Bump patch version (0.1.0 → 0.1.1) |
| `run-setup` | Build source distribution and wheel |
| `twine-upload-dist` | Upload to PyPI using twine |
| `go` | Do all steps above in sequence |

### PyPI Credentials

Set up your PyPI credentials in `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-your-token-here
```

Or set environment variables:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-your-token-here
```

---

## Troubleshooting

### wads-ci-debug: "No failed runs found"

**Issue:** Repository has no recent CI failures.

**Solution:** Specify a run ID explicitly:
```bash
wads-ci-debug myorg/myrepo --run-id 1234567890
```

### wads-ci-debug: API rate limit

**Issue:** GitHub API rate limit exceeded (60 requests/hour for unauthenticated).

**Solution:** Use GitHub token:
```bash
export GITHUB_TOKEN=ghp_your_token_here
wads-ci-debug myorg/myrepo
```

### wads-migrate: "setup.cfg not found"

**Issue:** File doesn't exist or wrong path.

**Solution:** Check file exists:
```bash
ls -la setup.cfg
wads-migrate setup-to-pyproject /full/path/to/setup.cfg
```

### populate: Files already exist

**Issue:** Won't overwrite existing files by default.

**Solution:** Use `--overwrite`:
```bash
populate . --overwrite pyproject.toml,README.md
```

### pack: "Version tag already exists"

**Issue:** Git tag conflicts with version.

**Solution:** See [README Troubleshooting](../README.md#version-tag-misalignment)

---

## See Also

- [System Dependencies Guide](SYSTEM_DEPENDENCIES.md) - Manage system packages
- [Migration Guide](MIGRATION.md) - Detailed migration walkthrough
- [README](../README.md) - Main documentation
