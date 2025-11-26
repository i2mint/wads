# Migration Guide: PEP 725/804 External Dependencies in Wads

This guide helps you migrate from the deprecated `[tool.wads.ci.testing.system_dependencies]` format to the new standards-based `[external]` format with operational metadata in `[tool.wads.external.ops]`.

## Table of Contents

- [Why Migrate?](#why-migrate)
- [Overview of Changes](#overview-of-changes)
- [Migration Steps](#migration-steps)
- [Examples](#examples)
- [Backward Compatibility](#backward-compatibility)
- [FAQs](#faqs)

---

## Why Migrate?

The new format aligns with emerging Python packaging standards:

- **PEP 725**: Specifies how to declare external (non-PyPI) dependencies using DepURLs
- **PEP 804**: Defines a future central registry for external dependencies
- **Wads Extensions**: Adds project-local operational metadata (check/install commands) to complement the central registry

### Benefits

1. **Standard Format**: DepURLs are becoming the standard way to declare non-PyPI dependencies
2. **Better Documentation**: Explicit rationale, URLs, and alternatives for each dependency
3. **Platform Flexibility**: Platform-specific install commands without hardcoding in CI
4. **Future-Proof**: Prepared for PEP 804 central registry integration
5. **Richer Metadata**: Support for check commands, alternatives, and contextual notes

---

## Overview of Changes

### Old Format (Deprecated)

```toml
[tool.wads.ci.testing]
system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]

# OR platform-specific:
system_dependencies = {
    ubuntu = ["ffmpeg", "libsndfile1"],
    macos = ["ffmpeg", "libsndfile"],
    windows = []
}
```

**Problems:**
- Non-standard format (wads-specific)
- No metadata about why dependencies are needed
- No version constraints
- Limited to simple package names

### New Format (Recommended)

```toml
# Standard PEP 725 declarations
[external]
dependencies = [
    "dep:generic/ffmpeg",
    "dep:generic/libsndfile"
]

# Wads operational metadata (project-local)
[tool.wads.external.ops.ffmpeg]
canonical_id = "dep:generic/ffmpeg"
rationale = "Required for audio/video processing"
url = "https://ffmpeg.org/"

install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"
install.windows = "choco install ffmpeg"

[tool.wads.external.ops.libsndfile]
canonical_id = "dep:generic/libsndfile"
rationale = "Provides audio file I/O"
url = "http://www.mega-nerd.com/libsndfile/"

install.linux = "sudo apt-get install -y libsndfile1"
install.macos = "brew install libsndfile"
```

**Benefits:**
- Standard DepURL format
- Rich metadata (rationale, URL, alternatives)
- Supports version constraints
- Prepared for future central registry

---

## Migration Steps

### Step 1: Identify Your Current Dependencies

Look for these patterns in your `pyproject.toml`:

```toml
[tool.wads.ci.testing]
system_dependencies = [...]
```

or

```toml
[tool.wads.ci.env]
install.linux = [...]
install.macos = [...]
```

### Step 2: Convert Package Names to DepURLs

Use this conversion table:

| Package Type | DepURL Format | Example |
|--------------|---------------|---------|
| Generic package | `dep:generic/{name}` | `dep:generic/git` |
| System library | `dep:generic/{name}` | `dep:generic/unixodbc` |
| Virtual dependency | `dep:virtual/{category}/{name}` | `dep:virtual/compiler/c` |
| With version | `dep:generic/{name}@{version}` | `dep:generic/openssl@>=1.1` |

**Common conversions:**

- `ffmpeg` → `dep:generic/ffmpeg`
- `git` → `dep:generic/git`
- `unixodbc` → `dep:generic/unixodbc`
- `libsndfile1` → `dep:generic/libsndfile`
- `portaudio19-dev` → `dep:generic/portaudio`

### Step 3: Create DepURL Declarations

Add to the **top** of your `pyproject.toml` (after `[project]`):

```toml
[external]
# Dependencies needed at runtime
dependencies = [
    "dep:generic/ffmpeg",
    "dep:generic/git"
]

# Dependencies needed during build (headers, compilers)
host-requires = [
    "dep:generic/unixodbc"
]

# Optional dependencies for specific features
[external.optional-dependencies]
audio = ["dep:generic/portaudio"]
```

### Step 4: Add Operational Metadata

For each DepURL, create a `[tool.wads.external.ops.{name}]` section:

```toml
[tool.wads.external.ops.{simplified_name}]
canonical_id = "{the_depurl}"
rationale = "Why this dependency is needed"
url = "https://project-homepage.org/"

# Install commands (string or list of strings)
install.linux = "command"
install.macos = "command"
install.windows = "command"

# Optional
note = "Additional context"
alternatives = ["alternative-package"]
```

**Simplified name rules:**

- `dep:generic/unixodbc` → `unixodbc`
- `dep:generic/git` → `git`
- `dep:virtual/compiler/c` → `compiler-c`

### Step 5: Remove Deprecated Sections

**Remove or comment out:**

```toml
# DEPRECATED - Remove this:
# [tool.wads.ci.testing]
# system_dependencies = [...]
```

### Step 6: Test Your Changes

1. Run wads to regenerate CI workflows:
   ```bash
   python -m wads.populate .
   ```

2. Check the generated `.github/workflows/ci.yml` for correct install commands

3. Commit and test in CI

---

## Examples

### Example 1: Simple Audio Processing Project

**Before:**

```toml
[tool.wads.ci.testing]
system_dependencies = ["ffmpeg", "libsndfile1"]
```

**After:**

```toml
[external]
dependencies = [
    "dep:generic/ffmpeg",
    "dep:generic/libsndfile"
]

[tool.wads.external.ops.ffmpeg]
canonical_id = "dep:generic/ffmpeg"
rationale = "Audio/video format conversion and processing"
url = "https://ffmpeg.org/"
install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"
install.windows = "choco install ffmpeg"

[tool.wads.external.ops.libsndfile]
canonical_id = "dep:generic/libsndfile"
rationale = "Read and write audio files in various formats"
url = "http://www.mega-nerd.com/libsndfile/"
install.linux = "sudo apt-get install -y libsndfile1"
install.macos = "brew install libsndfile"
note = "On Ubuntu, the package name is libsndfile1"
```

### Example 2: Database Connectivity (odbcdol-style)

**Before:**

```toml
[tool.wads.ci.testing]
system_dependencies = {
    ubuntu = ["unixodbc", "unixodbc-dev"],
    macos = ["unixodbc"],
    windows = []
}
```

**After:**

```toml
[external]
host-requires = [
    "dep:generic/unixodbc",
    "dep:generic/msodbcsql18"
]

[tool.wads.external.ops.unixodbc]
canonical_id = "dep:generic/unixodbc"
rationale = "Provides ODBC driver interface for SQL database connectivity"
url = "https://www.unixodbc.org/"

check.linux = [["dpkg", "-s", "unixodbc"], ["rpm", "-q", "unixODBC"]]
check.macos = ["brew", "list", "unixodbc"]

install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y unixodbc unixodbc-dev"
]
install.macos = "brew install unixodbc"

note = "On Alpine, use: apk add unixodbc unixodbc-dev"
alternatives = ["iodbc"]

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

note = "Requires accepting Microsoft EULA"
```

### Example 3: Multi-Step Installation

**Before:**

```toml
[tool.wads.ci.env]
install.linux = [
    "curl -sSL https://install.python-poetry.org | python3 -",
    "export PATH=$HOME/.local/bin:$PATH"
]
```

**After:**

```toml
[external]
dependencies = ["dep:generic/poetry"]

[tool.wads.external.ops.poetry]
canonical_id = "dep:generic/poetry"
rationale = "Python dependency management tool"
url = "https://python-poetry.org/"

install.linux = [
    "curl -sSL https://install.python-poetry.org | python3 -",
    "export PATH=$HOME/.local/bin:$PATH"
]
install.macos = [
    "curl -sSL https://install.python-poetry.org | python3 -",
    "export PATH=$HOME/.local/bin:$PATH"
]
install.windows = "powershell -Command \"(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -\""

alternatives = ["pipenv", "pdm"]
```

### Example 4: Platform-Specific Packages

**Before:**

```toml
[tool.wads.ci.testing]
system_dependencies = {
    ubuntu = ["libportaudio2", "portaudio19-dev"],
    macos = ["portaudio"],
    windows = ["portaudio"]
}
```

**After:**

```toml
[external]
host-requires = ["dep:generic/portaudio"]

[tool.wads.external.ops.portaudio]
canonical_id = "dep:generic/portaudio"
rationale = "Cross-platform audio I/O library"
url = "http://www.portaudio.com/"

install.linux = "sudo apt-get install -y libportaudio2 portaudio19-dev"
install.macos = "brew install portaudio"
install.windows = "choco install portaudio"

note = "Ubuntu needs both runtime (libportaudio2) and dev (portaudio19-dev) packages"
```

---

## Backward Compatibility

### Transition Period

During migration, wads supports **both** formats:

```toml
# NEW format (preferred)
[external]
dependencies = ["dep:generic/git"]

[tool.wads.external.ops.git]
canonical_id = "dep:generic/git"
install.linux = "sudo apt-get install -y git"

# OLD format (deprecated, but still works)
[tool.wads.ci.testing]
system_dependencies = ["ffmpeg"]
```

**Important:**
- Both will be processed
- You'll see deprecation warnings
- Plan to remove old format within a few releases

### Deprecation Warnings

When you run wads with the old format, you'll see:

```
DeprecationWarning: Using deprecated [tool.wads.ci.testing.system_dependencies].
Please migrate to [external] with DepURLs and [tool.wads.external.ops]
```

These warnings are intentional and help track migration progress.

---

## FAQs

### Q: Can I use both formats during migration?

**A:** Yes! The old format continues to work, allowing gradual migration. However, you should plan to migrate fully to avoid future compatibility issues.

### Q: What if I don't have install commands for all platforms?

**A:** That's fine! Only specify platforms you support:

```toml
[tool.wads.external.ops.mypackage]
canonical_id = "dep:generic/mypackage"
install.linux = "sudo apt-get install -y mypackage"
# No macos or windows entries - that's OK
```

### Q: Can I specify version constraints?

**A:** Yes, in the DepURL itself:

```toml
[external]
dependencies = [
    "dep:generic/openssl@>=1.1.1",
    "dep:generic/python@^3.10"
]
```

### Q: What about check commands?

**A:** Add them in the ops section:

```toml
[tool.wads.external.ops.git]
canonical_id = "dep:generic/git"
check.linux = ["which", "git"]
check.macos = ["which", "git"]
check.windows = ["where", "git"]
install.linux = "sudo apt-get install -y git"
```

### Q: How do I handle dependencies with different package names per platform?

**A:** Use a single DepURL and specify platform-specific commands:

```toml
[external]
dependencies = ["dep:generic/libsndfile"]

[tool.wads.external.ops.libsndfile]
canonical_id = "dep:generic/libsndfile"
install.linux = "sudo apt-get install -y libsndfile1"  # Note: libsndfile1 on Ubuntu
install.macos = "brew install libsndfile"              # Note: libsndfile on macOS
```

### Q: Can I use this with private packages?

**A:** For private packages, you might need custom DepURLs and detailed install instructions:

```toml
[external]
dependencies = ["dep:generic/mycompany-internal-tool"]

[tool.wads.external.ops.mycompany-internal-tool]
canonical_id = "dep:generic/mycompany-internal-tool"
rationale = "Internal company tool for XYZ"
url = "https://internal.mycompany.com/tools/xyz"

install.linux = [
    "curl -H 'Authorization: Bearer ${INTERNAL_TOKEN}' https://internal.mycompany.com/xyz.sh | bash"
]
```

### Q: What happens if I don't migrate?

**A:** The old format will continue to work for now, but:
- You'll see deprecation warnings
- You'll miss out on the benefits of the new format
- Future wads versions may eventually remove support

### Q: Where can I learn more about DepURLs?

**A:** See:
- [PEP 725](https://peps.python.org/pep-0725/) - External Dependencies specification
- [PEP 804](https://peps.python.org/pep-0804/) - Central registry (in development)
- This document's DepURL conversion table

---

## Migration Checklist

Use this checklist to track your migration:

- [ ] Identify all current `system_dependencies` in `pyproject.toml`
- [ ] Convert package names to DepURLs
- [ ] Create `[external]` section with all DepURLs
- [ ] For each DepURL, create `[tool.wads.external.ops.{name}]` section
- [ ] Add `canonical_id`, `rationale`, and `url` for each dependency
- [ ] Add `install.{platform}` commands for supported platforms
- [ ] (Optional) Add `check.{platform}` commands
- [ ] (Optional) Add `note` and `alternatives` fields
- [ ] Remove or comment out old `[tool.wads.ci.testing.system_dependencies]`
- [ ] Run `python -m wads.populate .` to regenerate CI
- [ ] Review generated `.github/workflows/ci.yml`
- [ ] Commit changes and test in CI
- [ ] Verify no deprecation warnings

---

## Getting Help

If you encounter issues during migration:

1. Check this guide's examples for similar use cases
2. Review the [CI_CONFIG_GUIDE.md](CI_CONFIG_GUIDE.md) for comprehensive docs
3. Look at the test files in `wads/tests/test_external_deps.py` for examples
4. Report issues at: https://github.com/i2mint/wads/issues

---

**Last Updated:** 2025-01-25
**Wads Version:** 0.1.56+
