# MANIFEST.in Migration Support

## Summary

Added comprehensive support for detecting and migrating `MANIFEST.in` files when using `populate . --migrate`.

## What Was Added

### 1. Core Functionality (`wads/migration.py`)

- **`_parse_manifest_in(filepath)`**: Parses MANIFEST.in directives (include, graft, prune, etc.)
- **`analyze_manifest_in(manifest_path)`**: Main analysis function that:
  - Detects if MANIFEST.in exists
  - Parses all directives
  - Converts to equivalent Hatchling configuration
  - Provides migration recommendations

### 2. Integration (`wads/config_comparison.py`)

- **`compare_manifest_in(actual_path)`**: Compares MANIFEST.in and recommends migration
- **Updated `summarize_config_status()`**: Now checks for MANIFEST.in
- Added to module documentation

### 3. Populate Integration (`wads/populate.py`)

- Automatically detects MANIFEST.in during `populate` execution
- Displays warnings when found
- Shows suggested `[tool.hatch.build.targets.wheel]` configuration
- Adds to "needs attention" summary with emoji indicators

### 4. Tests

Added 7 new tests (41 total, all passing):
- `test_parse_manifest_in`: Basic parsing
- `test_analyze_manifest_in_with_includes`: Include directive handling
- `test_analyze_manifest_in_with_excludes`: Exclude directive handling
- `test_analyze_manifest_in_empty`: Empty file handling
- `test_manifest_in_parsing`: Config comparison integration
- `test_manifest_in_nonexistent`: Missing file handling
- `test_compare_manifest_in`: Full comparison workflow

### 5. Documentation & Examples

- Updated `CONFIG_COMPARISON_README.md` with MANIFEST.in section
- Enhanced `config_comparison_demo.py` with MANIFEST.in demo
- Created `manifest_migration_example.py` showing full workflow

## How It Works

### During Migration (`populate . --migrate`)

```bash
$ populate . --migrate
```

**Output when MANIFEST.in detected:**
```
👀 Found MANIFEST.in (needs Hatchling migration)...
  MANIFEST.in is not directly supported by Hatchling
  • MANIFEST.in detected. With Hatchling, package data is handled differently.
  
  Suggested pyproject.toml configuration:
    [tool.hatch.build.targets.wheel]
    include = [
      "README.md LICENSE",
      "mypackage/data/**/*.json",
      "docs/**/*"
    ]
    exclude = [
      "tests/",
      "**/*.pyc"
    ]

POPULATE SUMMARY
👀 Needs attention:
  • MANIFEST.in
    └─ Needs migration to Hatchling [tool.hatch.build.targets.wheel]
```

### Directive Conversion

| MANIFEST.in | Hatchling Equivalent |
|-------------|---------------------|
| `include README.md` | `include = ["README.md"]` |
| `graft docs` | `include = ["docs/**/*"]` |
| `recursive-include pkg *.json` | `include = ["pkg/**/*.json"]` |
| `prune tests` | `exclude = ["tests/"]` |
| `global-exclude *.pyc` | `exclude = ["**/*.pyc"]` |

## API Usage

### Direct Analysis

```python
from wads.migration import analyze_manifest_in

result = analyze_manifest_in('MANIFEST.in')

if result['needs_migration']:
    print(result['hatchling_config'])
    # Copy to pyproject.toml
```

### During Config Comparison

```python
from wads.config_comparison import summarize_config_status

status = summarize_config_status('/path/to/project')

if status['has_manifest_in']:
    print("MANIFEST.in needs migration")
    print(status['manifest_status']['recommendations'])
```

## Key Benefits

1. **Automatic Detection**: No need to manually check for MANIFEST.in
2. **Smart Conversion**: Understands common MANIFEST.in patterns
3. **Clear Guidance**: Shows exactly what to add to pyproject.toml
4. **Integrated Workflow**: Part of the overall migration process
5. **Non-Breaking**: Only warns/recommends, doesn't force changes

## Migration Workflow

1. Run `populate . --migrate` in project root
2. See MANIFEST.in detection and suggestions
3. Copy suggested `[tool.hatch.build.targets.wheel]` config to pyproject.toml
4. Test build with `python -m build`
5. Remove MANIFEST.in once verified

## Important Notes

- **Hatchling includes package files by default** - only add explicit include/exclude if needed
- **MANIFEST.in is setuptools-specific** - not used by Hatchling
- **Pattern conversion is best-effort** - review suggested config before using
- **Some complex patterns may need manual adjustment**

## Files Modified

1. `wads/migration.py` - Added MANIFEST.in parsing (200+ lines)
2. `wads/config_comparison.py` - Added comparison function (40+ lines)
3. `wads/populate.py` - Added detection and warnings (30+ lines)
4. `wads/tests/test_migration.py` - Added 4 tests
5. `wads/tests/test_config_comparison.py` - Added 3 tests
6. `examples/CONFIG_COMPARISON_README.md` - Added section
7. `examples/config_comparison_demo.py` - Added demo function
8. `examples/manifest_migration_example.py` - New complete example

## Test Coverage

All 41 tests pass, including:
- Unit tests for parsing logic
- Integration tests with config comparison
- Edge cases (empty files, missing files, complex patterns)
- End-to-end workflow tests
