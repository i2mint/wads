# PEP 725/804 External Dependencies Implementation Summary

This document summarizes the implementation of PEP 725/804 support in wads for standardized external dependency declarations.

## Implementation Date

**Completed:** January 2025
**Wads Version:** 0.1.56+

---

## Overview

Wads now supports PEP 725's standard format for declaring external (non-PyPI) dependencies using DepURLs, while maintaining backward compatibility with the legacy `system_dependencies` format.

### Key Components

1. **Standard Declarations** (`[external]` table): DepURLs following PEP 725
2. **Operational Metadata** (`[tool.wads.external.ops]`): Project-local install commands
3. **Legacy Support**: Backward compatibility with deprecation warnings
4. **Validation**: DepURL format validation
5. **Comprehensive Tests**: 25 test cases covering all scenarios

---

## Changes Made

### 1. Updated Template (`wads/data/pyproject_toml_tpl.toml`)

Added comprehensive sections:

```toml
[external]
build-requires = []
host-requires = []
dependencies = []

[external.optional-build-requires]
[external.optional-host-requires]
[external.optional-dependencies]
[external.dependency-groups]

[tool.wads.external.ops]
# Project-local operational metadata
```

**Lines Added:** ~70 lines of documentation and structure

### 2. Enhanced CI Configuration Parser (`wads/ci_config.py`)

#### New Functions

- **`_depurl_to_simple_name(depurl: str) -> str`**
  - Converts DepURLs to simplified names for ops lookup
  - Examples: `dep:generic/git` → `git`, `dep:virtual/compiler/c` → `compiler-c`

- **`_validate_depurl(depurl: str) -> bool`**
  - Validates DepURL format per PEP 725
  - Checks for `dep:` scheme and proper structure

#### New Methods in `CIConfig` Class

- **`_parse_external_dependencies() -> dict`**
  - Extracts DepURLs from `[external]` table
  - Returns structured dict with build/host/runtime categories

- **`_parse_external_ops() -> dict`**
  - Extracts operational metadata from `[tool.wads.external.ops]`
  - Returns dict keyed by simplified dependency names

#### New Properties

- **`external_dependencies`**: Access parsed external dependencies
- **`external_ops`**: Access operational metadata
- **`has_external_dependencies()`**: Check if any external deps are declared

#### Enhanced Methods

- **`generate_pre_test_steps(platform='linux')`**
  - Now supports both new and legacy formats
  - Processes DepURLs and matches with operational metadata
  - Generates platform-specific install commands
  - Emits deprecation warnings for legacy usage

- **`generate_windows_validation_job()`**
  - Updated to use new external ops for Windows
  - Supports both formats during transition
  - Generates proper PowerShell/chocolatey commands

**Lines Modified:** ~150 lines added/modified

### 3. Comprehensive Test Suite (`wads/tests/test_external_deps.py`)

Created 25 test cases covering:

- DepURL parsing and validation (7 tests)
- External dependencies parsing (5 tests)
- External ops metadata (2 tests)
- Pre-test steps generation (4 tests)
- Backward compatibility (3 tests)
- Windows validation (2 tests)
- Real-world scenarios (2 tests)

**Test Results:** ✅ 25/25 passing

**Lines Added:** ~530 lines

### 4. Migration Documentation

Created two comprehensive documents:

- **`PEP_725_MIGRATION_GUIDE.md`** (415 lines)
  - Step-by-step migration instructions
  - Before/after examples
  - Platform-specific guidance
  - FAQs and troubleshooting

- **`PEP_725_IMPLEMENTATION_SUMMARY.md`** (this document)
  - Technical implementation details
  - Changes inventory
  - Design decisions
  - Future enhancements

---

## Design Decisions

### 1. Dual Format Support

**Decision:** Support both old and new formats simultaneously during transition.

**Rationale:**
- Allows gradual migration for existing projects
- No breaking changes for users
- Clear deprecation warnings guide migration

**Implementation:**
- New format checked first
- Legacy format processed second with warnings
- Both sets of commands merged in generated CI

### 2. Project-Local Operational Metadata

**Decision:** Store install commands in `[tool.wads.external.ops]` rather than waiting for PEP 804 central registry.

**Rationale:**
- PEP 804 central registry not yet implemented
- Projects need operational metadata now
- Allows project-specific customization
- Easy to migrate to central registry later

**Structure:**
```toml
[tool.wads.external.ops.{simplified_name}]
canonical_id = "{depurl}"  # Links to [external] declaration
install.{platform} = "command"
check.{platform} = "command"
rationale = "why needed"
url = "upstream url"
```

### 3. DepURL Name Simplification

**Decision:** Convert DepURLs to simplified names for ops keys.

**Rationale:**
- DepURLs contain special characters (`/`, `@`, `?`) not valid in TOML keys
- Simplified names more readable
- `canonical_id` field preserves full DepURL reference

**Algorithm:**
- `dep:generic/name` → `name`
- `dep:virtual/cat/name` → `cat-name`
- Remove version, query, fragment specifiers

### 4. Platform-Specific Commands

**Decision:** Use nested `install.{platform}` structure.

**Rationale:**
- Clear platform targeting
- Supports platform-specific differences
- Missing platforms acceptable (not all projects support all platforms)
- TOML dot notation creates nested dicts automatically

### 5. Validation Approach

**Decision:** Validate DepURLs but warn rather than fail on missing ops.

**Rationale:**
- Invalid DepURLs indicate configuration errors
- Missing ops metadata may be intentional (future registry lookup)
- Warnings logged during CI generation for visibility
- Allows forward compatibility with future central registry

---

## Integration Points

### 1. CI Workflow Generation

**File:** `.github/workflows/ci.yml` (generated)

**Integration:**
- Pre-test steps call `config.generate_pre_test_steps(platform='linux')`
- Windows job calls `config.generate_windows_validation_job()`
- Install commands inserted into YAML `run:` blocks

### 2. GitHub Actions

**Existing actions remain unchanged:**
- `install-deps/action.yml` - Still handles Python dependencies
- `run-tests/action.yml` - Still runs pytest
- System dependencies installed in separate step before Python deps

### 3. Template Substitution

**Process:**
1. User defines deps in `pyproject.toml`
2. `python -m wads.populate .` reads config
3. `CIConfig.to_ci_template_substitutions()` generates placeholders
4. Template engine substitutes `#PRE_TEST_STEPS#` and `#WINDOWS_VALIDATION_JOB#`
5. Generated CI workflow written to `.github/workflows/ci.yml`

---

## Backward Compatibility

### Legacy Format Still Supported

```toml
[tool.wads.ci.testing]
system_dependencies = ["ffmpeg"]
```

### Deprecation Strategy

1. **Warnings:** DeprecationWarning emitted when legacy format detected
2. **Documentation:** Migration guide provided
3. **Timeline:** Legacy support maintained for at least 6 months
4. **Future:** Eventually remove in wads 0.2.0

### Breaking Changes

**None in current release.** Fully backward compatible.

---

## Testing Strategy

### Test Coverage

- **Unit Tests:** DepURL parsing, validation, name simplification
- **Integration Tests:** End-to-end CI generation with dependencies
- **Backward Compat Tests:** Legacy format still works
- **Real-World Tests:** odbcdol-style configuration
- **Platform Tests:** Linux, macOS, Windows commands

### Test Scenarios

1. Empty configuration (no deps)
2. Single dependency
3. Multiple dependencies
4. Multi-step install commands
5. Platform-specific variations
6. Legacy list format
7. Legacy dict format
8. Mixed old and new formats
9. Windows-specific testing
10. Optional dependencies

---

## Usage Examples

### Basic Example

```toml
[external]
dependencies = ["dep:generic/git"]

[tool.wads.external.ops.git]
canonical_id = "dep:generic/git"
rationale = "Version control"
install.linux = "sudo apt-get install -y git"
install.macos = "brew install git"
```

### Complex Example (Database Connectivity)

```toml
[external]
host-requires = [
    "dep:generic/unixodbc",
    "dep:generic/msodbcsql18"
]

[tool.wads.external.ops.unixodbc]
canonical_id = "dep:generic/unixodbc"
rationale = "ODBC interface"
url = "https://www.unixodbc.org/"
install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y unixodbc unixodbc-dev"
]
install.macos = "brew install unixodbc"

[tool.wads.external.ops.msodbcsql18]
canonical_id = "dep:generic/msodbcsql18"
rationale = "Microsoft SQL Server ODBC driver"
url = "https://docs.microsoft.com/sql/connect/odbc/"
install.linux = [
    "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
    "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
    "sudo apt-get update",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
]
```

---

## Future Enhancements

### 1. PEP 804 Central Registry Integration

When PEP 804 is implemented:

```python
def _get_install_commands(depurl, platform):
    # Try project-local ops first
    if depurl in local_ops:
        return local_ops[depurl]

    # Fall back to central registry
    return query_pep804_registry(depurl, platform)
```

### 2. Check Command Execution

Currently `check.{platform}` is parsed but not executed. Future enhancement:

```python
def check_dependency_installed(dep_ops, platform):
    check_cmds = dep_ops.get('check', {}).get(platform, [])
    for cmd in check_cmds:
        if subprocess.run(cmd).returncode == 0:
            return True
    return False
```

### 3. Dry-Run Mode

Allow testing without actual installation:

```bash
python -m wads.ci_config --dry-run pyproject.toml
# Shows what would be installed, doesn't execute
```

### 4. Dependency Version Constraints

Better handling of version specifiers in DepURLs:

```toml
[external]
dependencies = ["dep:generic/openssl@>=1.1.1,<3.0"]
```

### 5. Alternative Selection

Automatic fallback to alternatives:

```toml
[tool.wads.external.ops.unixodbc]
alternatives = ["iodbc"]
# Try unixodbc first, fall back to iodbc if not available
```

---

## Files Modified/Created

### Modified Files

| File | Lines Changed | Description |
|------|---------------|-------------|
| `wads/ci_config.py` | ~150 added | Core parsing and generation logic |
| `wads/data/pyproject_toml_tpl.toml` | ~70 added | Template with new sections |

### Created Files

| File | Lines | Description |
|------|-------|-------------|
| `wads/tests/test_external_deps.py` | 530 | Comprehensive test suite |
| `PEP_725_MIGRATION_GUIDE.md` | 415 | User migration guide |
| `PEP_725_IMPLEMENTATION_SUMMARY.md` | 310 | Technical summary (this file) |

### Total Impact

- **Lines Added:** ~1,475
- **Files Modified:** 2
- **Files Created:** 3
- **Test Coverage:** 25 tests, 100% passing

---

## Migration Path for Existing Projects

1. **Phase 1:** Add new `[external]` section alongside legacy format
2. **Phase 2:** Test generated CI with both formats
3. **Phase 3:** Remove legacy `system_dependencies` section
4. **Phase 4:** Add rich metadata (rationale, URL, alternatives)
5. **Complete:** No deprecation warnings, full PEP 725 compliance

---

## References

- [PEP 725: External Dependencies](https://peps.python.org/pep-0725/)
- [PEP 804: Package Metadata Extensions](https://peps.python.org/pep-0804/)
- [Wads CI Configuration Guide](CI_CONFIG_GUIDE.md)
- [Migration Guide](PEP_725_MIGRATION_GUIDE.md)
- [Wads Repository](https://github.com/i2mint/wads)

---

## Acknowledgments

This implementation follows the design principles outlined in the PEP 725/804 instructions document, ensuring:

- Single source of truth for dependency declarations (`[external]`)
- Single source of truth for operations (`[tool.wads.external.ops]`)
- Graceful degradation when ops metadata missing
- Backward compatibility with legacy formats
- Clear separation between standards (PEP 725) and tooling (wads ops)

**Implementation Status:** ✅ Complete and Tested
