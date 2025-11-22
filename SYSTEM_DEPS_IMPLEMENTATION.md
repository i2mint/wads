# System Dependencies Feature Implementation Summary

## What Was Implemented

Added support for declaring system-level dependencies (OS packages like `ffmpeg`, `libsndfile`, etc.) in `pyproject.toml`, which are automatically installed during CI runs.

## Changes Made

### 1. Core Implementation (`wads/ci_config.py`)

**Added:**
- `system_dependencies` property to read configuration from `[tool.wads.ci.testing]`
- `_normalize_system_deps()` method to handle both list and dict formats
- Updated `generate_pre_test_steps()` to include system dependencies installation
- Updated `generate_windows_validation_job()` to install Windows-specific dependencies

**Behavior:**
```python
# Simple list (Ubuntu only)
system_dependencies = ["ffmpeg", "libsndfile1"]

# Platform-specific dict
system_dependencies = {
    "ubuntu": ["ffmpeg", "libsndfile1"],
    "macos": ["ffmpeg", "libsndfile"],
    "windows": ["ffmpeg"]
}
```

### 2. Template Configuration (`wads/data/pyproject_toml_tpl.toml`)

**Added:**
```toml
[tool.wads.ci.testing]
# System dependencies (OS packages needed for tests)
# Simple form (Ubuntu only):
# system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]

# Platform-specific form:
# system_dependencies = { 
#     ubuntu = ["ffmpeg", "libsndfile1"], 
#     macos = ["ffmpeg", "libsndfile"], 
#     windows = [] 
# }
```

### 3. Documentation

**Created/Updated:**
- `CI_CONFIG_GUIDE.md` - Added system dependencies section with examples
- `examples/SYSTEM_DEPS_README.md` - Comprehensive guide with use cases and troubleshooting
- `examples/system_deps_example.py` - Interactive examples demonstrating all features

### 4. Testing

**Created:**
- `test_system_deps.py` - Unit tests for all system dependencies functionality
- `test_integration_system_deps.py` - End-to-end integration test

**Test Coverage:**
- ✅ Simple list format (Ubuntu only)
- ✅ Platform-specific dict format
- ✅ Empty/no dependencies
- ✅ Combined with custom pre-test commands
- ✅ CI template substitution
- ✅ End-to-end workflow generation

## How It Works

### Execution Flow

1. User adds `system_dependencies` to `[tool.wads.ci.testing]` in `pyproject.toml`
2. Run `wads populate` to regenerate CI workflow
3. `CIConfig.from_file()` reads the configuration
4. `generate_pre_test_steps()` creates YAML steps for system package installation
5. `to_ci_template_substitutions()` includes these steps in the `#PRE_TEST_STEPS#` placeholder
6. Generated CI workflow includes system dependency installation before tests

### Generated CI Output

**Input (pyproject.toml):**
```toml
[tool.wads.ci.testing]
system_dependencies = ["ffmpeg", "libsndfile1"]
```

**Output (generated CI):**
```yaml
- name: Install System Dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y ffmpeg libsndfile1
```

### Installation Order

1. **System dependencies** installed first
2. **Python dependencies** via pip
3. **Custom pre-test commands** (if any)
4. **Tests** run

## Use Cases

### Audio/Video Processing
```toml
system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev", "sox"]
```

### Computer Vision
```toml
system_dependencies = ["libopencv-dev", "python3-opencv", "libglib2.0-0"]
```

### Database Testing
```toml
system_dependencies = ["postgresql-client", "redis-tools", "mongodb-clients"]
```

### Scientific Computing
```toml
system_dependencies = ["libhdf5-dev", "libnetcdf-dev", "gfortran"]
```

## Configuration Examples

### Simple Ubuntu Dependencies
```toml
[tool.wads.ci.testing]
system_dependencies = ["ffmpeg", "libsndfile1"]
```

### Multi-Platform
```toml
[tool.wads.ci.testing]
system_dependencies = {
    ubuntu = ["ffmpeg", "libsndfile1", "libsndfile1-dev"],
    macos = ["ffmpeg", "libsndfile"],
    windows = ["ffmpeg"]
}
```

### With Custom Commands
```toml
[tool.wads.ci.commands]
pre_test = ["python scripts/setup_data.py"]

[tool.wads.ci.testing]
system_dependencies = ["ffmpeg"]
```

## Benefits

### ✅ Configuration-Driven
- Single source of truth in `pyproject.toml`
- No hardcoded values in CI YAML

### ✅ Cross-Platform Support
- Ubuntu (apt-get)
- Windows (chocolatey)
- macOS (brew - future)

### ✅ Type-Safe
- Python-level validation before YAML generation
- Clear error messages

### ✅ Composable
- Works with custom pre-test commands
- Respects existing CI configuration

### ✅ Maintainable
- Easy to update dependencies
- Clear documentation in code

## Testing Results

### Unit Tests
```
✅ test_system_deps_list passed
✅ test_system_deps_dict passed
✅ test_no_system_deps passed
✅ test_system_deps_with_pre_test_commands passed
✅ test_ci_template_substitutions passed
```

### Integration Test
```
✅ Install System Dependencies step
✅ apt-get update command
✅ ffmpeg package
✅ libsndfile1 package
✅ portaudio19-dev package
✅ Python versions array
✅ PROJECT_NAME env var
```

### Existing Tests
```
39 passed in 4.48s
```
All existing wads tests continue to pass.

## Files Modified/Created

### Modified
- `wads/ci_config.py` - Added system dependencies support
- `wads/data/pyproject_toml_tpl.toml` - Added configuration template
- `CI_CONFIG_GUIDE.md` - Added documentation section

### Created
- `test_system_deps.py` - Unit tests
- `test_integration_system_deps.py` - Integration test
- `examples/system_deps_example.py` - Interactive examples
- `examples/SYSTEM_DEPS_README.md` - Comprehensive guide

## Next Steps (Optional Enhancements)

### High Priority
- [ ] Update migration tools to preserve system dependencies from old CI
- [ ] Add `wads ci validate` command to check dependency availability

### Medium Priority
- [ ] Support for macOS (brew) in main validation job
- [ ] Caching of installed system packages for faster CI
- [ ] Validate package names against known package repositories

### Low Priority
- [ ] Support for custom package managers (snap, nix)
- [ ] Interactive `wads ci configure` wizard
- [ ] CI config presets (e.g., `--audio`, `--ml`, `--web`)

## Conclusion

The system dependencies feature is **fully implemented and tested**. It provides a clean, configuration-driven way to declare OS-level dependencies needed for CI testing, eliminating the need to manually edit CI YAML files.

Users can now simply add dependencies to `pyproject.toml` and run `wads populate` to automatically generate CI workflows with proper system package installation.
