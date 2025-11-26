# PEP 725 External Dependencies - Quick Start

This is the quick reference guide for wads' PEP 725 implementation. For detailed documentation, see [PEP_725_COMPLETE_INDEX.md](PEP_725_COMPLETE_INDEX.md).

---

## What is This?

wads now supports **PEP 725** for declaring external (non-PyPI) system dependencies in `pyproject.toml`, just like you declare Python dependencies.

**Before:**
```yaml
# System dependencies scattered in .github/workflows/ci.yml
- name: Install deps
  run: sudo apt-get install -y unixodbc ffmpeg
```

**After:**
```toml
# System dependencies declared in pyproject.toml
[external]
host-requires = [
    "dep:generic/unixodbc",
    "dep:generic/ffmpeg"
]

[tool.wads.external.ops.unixodbc]
canonical_id = "dep:generic/unixodbc"
rationale = "ODBC driver interface"
install.linux = "sudo apt-get install -y unixodbc-dev"
install.macos = "brew install unixodbc"
```

---

## Quick Commands

### For Migrating Existing Projects

```bash
# Check if migration needed
python -m wads.external_deps_migration analyze .

# Get migration instructions
python -m wads.external_deps_migration instructions .

# Apply automatic migration (if possible)
python -m wads.external_deps_migration apply . --dry-run
python -m wads.external_deps_migration apply .
```

### For Local Development

```bash
# Check what's needed
python -m wads.setup_utils diagnose .

# Install system dependencies
python -m wads.setup_utils install-system .

# Install Python dependencies
python -m wads.setup_utils install-python .
```

### For CI Debugging

```bash
# Set up GitHub token
export GITHUB_TOKEN=ghp_your_token_here

# Diagnose latest failed CI run
python -m wads.ci_debug_agent owner/repo --fix
```

---

## 5-Minute Migration Guide

### Step 1: Check Current State

```bash
cd /path/to/your/project
python -m wads.external_deps_migration analyze .
```

### Step 2: Add External Dependencies

Edit `pyproject.toml` and add:

```toml
[external]
host-requires = [
    "dep:generic/your-package"
]

[tool.wads.external.ops.your-package]
canonical_id = "dep:generic/your-package"
rationale = "Why you need this package"
url = "https://package-homepage.org/"

install.linux = "sudo apt-get install -y your-package"
install.macos = "brew install your-package"
install.windows = "choco install your-package"
```

### Step 3: Verify

```bash
python -m wads.setup_utils diagnose .
```

### Step 4: Update CI (Temporary)

Add to `.github/workflows/ci.yml` after Python setup:

```yaml
      - name: Install System Dependencies
        run: |
          # Copy install commands from pyproject.toml
          sudo apt-get install -y your-package
```

### Step 5: Test and Push

```bash
# Test locally
python -m wads.setup_utils install-system . --dry-run

# Commit
git add pyproject.toml .github/workflows/ci.yml
git commit -m "Add PEP 725 external dependencies"
git push
```

---

## Common Use Cases

### ODBC Dependencies

```toml
[external]
host-requires = [
    "dep:generic/unixodbc",
    "dep:generic/msodbcsql18"
]

[tool.wads.external.ops.unixodbc]
canonical_id = "dep:generic/unixodbc"
rationale = "ODBC driver interface for database connectivity"
url = "https://www.unixodbc.org/"
install.linux = "sudo apt-get install -y unixodbc-dev"
install.macos = "brew install unixodbc"

[tool.wads.external.ops.msodbcsql18]
canonical_id = "dep:generic/msodbcsql18"
rationale = "Microsoft ODBC Driver 18 for SQL Server"
url = "https://docs.microsoft.com/sql/connect/odbc/"
install.linux = [
    "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
    "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
    "sudo apt-get update",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
]
```

### Audio/Video Processing

```toml
[external]
dependencies = [
    "dep:generic/ffmpeg",
    "dep:generic/libsndfile"
]

[tool.wads.external.ops.ffmpeg]
canonical_id = "dep:generic/ffmpeg"
rationale = "Multimedia framework for audio and video processing"
url = "https://ffmpeg.org/"
install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"

[tool.wads.external.ops.libsndfile]
canonical_id = "dep:generic/libsndfile"
rationale = "Library for reading and writing audio files"
url = "http://www.mega-nerd.com/libsndfile/"
install.linux = "sudo apt-get install -y libsndfile1"
install.macos = "brew install libsndfile"
```

### Build Tools

```toml
[external]
build-requires = [
    "dep:virtual/compiler/c",
    "dep:generic/git"
]

[tool.wads.external.ops.compiler-c]
canonical_id = "dep:virtual/compiler/c"
rationale = "C compiler for native extensions"
install.linux = "sudo apt-get install -y build-essential"
install.macos = "xcode-select --install"

[tool.wads.external.ops.git]
canonical_id = "dep:generic/git"
rationale = "Version control for source dependencies"
install.linux = "sudo apt-get install -y git"
install.macos = "brew install git"
```

---

## When CI Fails

### Quick Diagnosis

```bash
# 1. Set GitHub token
export GITHUB_TOKEN=ghp_your_token_here

# 2. Run CI debugger
python -m wads.ci_debug_agent owner/repo --fix --local-repo .

# 3. Review CI_FIX_INSTRUCTIONS.md

# 4. Apply fixes to pyproject.toml

# 5. Update CI workflow

# 6. Push and monitor
git add pyproject.toml .github/workflows/ci.yml
git commit -m "Fix CI: Add missing dependencies"
git push
```

---

## Documentation Index

**Start Here:**
- [README_PEP_725.md](README_PEP_725.md) ← You are here (quick start)
- [PEP_725_COMPLETE_INDEX.md](PEP_725_COMPLETE_INDEX.md) - Complete index of all files

**User Guides:**
- [PEP_725_MIGRATION_GUIDE.md](PEP_725_MIGRATION_GUIDE.md) - Detailed migration guide
- [SETUP_UTILS_GUIDE.md](SETUP_UTILS_GUIDE.md) - Local setup utilities guide
- [CI_DEBUG_AGENT_GUIDE.md](CI_DEBUG_AGENT_GUIDE.md) - CI debugging guide

**Examples:**
- [CI_DEBUG_EXAMPLE_ODBCDOL.md](CI_DEBUG_EXAMPLE_ODBCDOL.md) - Real-world odbcdol example
- [i/dols/odbcdol/pyproject_NEW_FORMAT.toml](../dols/odbcdol/pyproject_NEW_FORMAT.toml) - Example configuration

**Technical:**
- [PEP_725_IMPLEMENTATION_SUMMARY.md](PEP_725_IMPLEMENTATION_SUMMARY.md) - Implementation details
- [IMPROVED_MIGRATION_OUTPUT.md](IMPROVED_MIGRATION_OUTPUT.md) - Error message improvements

---

## Command Reference

### Migration Commands

```bash
# Analyze migration status
python -m wads.external_deps_migration analyze /path/to/project

# Get detailed instructions
python -m wads.external_deps_migration instructions /path/to/project

# Preview what migration would do
python -m wads.external_deps_migration preview /path/to/project

# Apply migration (with dry-run)
python -m wads.external_deps_migration apply /path/to/project --dry-run
python -m wads.external_deps_migration apply /path/to/project
```

### Setup Commands

```bash
# Diagnose all dependencies
python -m wads.setup_utils diagnose /path/to/project

# Install system dependencies
python -m wads.setup_utils install-system /path/to/project [--dry-run]

# Install Python dependencies
python -m wads.setup_utils install-python /path/to/project [--dry-run]

# Check environment variables
python -m wads.setup_utils check-env /path/to/project
```

### CI Debug Commands

```bash
# Analyze latest failed run
python -m wads.ci_debug_agent owner/repo

# Analyze specific run
python -m wads.ci_debug_agent owner/repo --run-id 12345678

# Generate fix instructions
python -m wads.ci_debug_agent owner/repo --fix --local-repo /path/to/project
```

---

## FAQ

### Q: Do I need to migrate immediately?

**A:** No. The old format still works. Migrate when convenient.

### Q: Will this break my existing CI?

**A:** No. Backward compatibility is fully maintained.

### Q: Why am I getting VS Code errors about `[external]`?

**A:** VS Code's TOML schema doesn't include PEP 725 yet. The TOML is valid - ignore the warnings.

### Q: Can I have both old and new formats?

**A:** Yes. wads will merge dependencies from both formats.

### Q: How do I get a GitHub token for the CI debugger?

**A:** Go to https://github.com/settings/tokens and create a token with `repo` scope.

### Q: Where do install commands run?

**A:** On your local machine when you run `install-system`, and in CI when the workflow executes the install step.

### Q: What if my dependency isn't in the common mappings?

**A:** Create your own DepURL (e.g., `dep:generic/mypackage`) and add the operational metadata manually.

---

## Troubleshooting

### "Cannot auto-migrate this project"

**Solution:** Use `instructions` command for manual steps:
```bash
python -m wads.external_deps_migration instructions .
```

### "GITHUB_TOKEN environment variable required"

**Solution:** Set your GitHub token:
```bash
export GITHUB_TOKEN=ghp_your_token_here
```

### CI still failing after migration

**Solution:** Update `.github/workflows/ci.yml` to install system dependencies (manual step until wads CI generation is updated).

### Permission denied during install

**Solution:** Ensure install commands include `sudo` for Linux, or run with appropriate permissions.

---

## What's Next?

1. **Try it out:** Migrate one project using the quick guide above
2. **Read the guides:** Check out the detailed documentation
3. **Debug CI failures:** Use the CI debug agent when things break
4. **Contribute:** Add more package mappings or detection patterns

---

## Key Benefits

✅ **Declarative** - Dependencies in `pyproject.toml` alongside Python deps
✅ **Portable** - Cross-platform install instructions
✅ **Self-Documenting** - Rationale and URLs explain WHY
✅ **Verifiable** - Install and test locally before CI
✅ **Debuggable** - Automatic CI failure diagnosis
✅ **Future-Proof** - Ready for PEP 804 central registry

---

## Need Help?

- **Quick Reference:** This file
- **Complete Index:** [PEP_725_COMPLETE_INDEX.md](PEP_725_COMPLETE_INDEX.md)
- **Migration Guide:** [PEP_725_MIGRATION_GUIDE.md](PEP_725_MIGRATION_GUIDE.md)
- **Setup Guide:** [SETUP_UTILS_GUIDE.md](SETUP_UTILS_GUIDE.md)
- **CI Debug Guide:** [CI_DEBUG_AGENT_GUIDE.md](CI_DEBUG_AGENT_GUIDE.md)
- **Real Example:** [CI_DEBUG_EXAMPLE_ODBCDOL.md](CI_DEBUG_EXAMPLE_ODBCDOL.md)

---

**Version:** 1.0
**Date:** 2025-01-25
**Wads:** 0.1.56+
