# System Dependencies in CI

## Overview

The **wads** CI system now supports declaring system-level dependencies (like `ffmpeg`, `libsndfile`, etc.) directly in your `pyproject.toml`. These dependencies are automatically installed during CI runs before your tests execute.

## Quick Start

### Simple Ubuntu-Only Dependencies

Add to your `pyproject.toml`:

```toml
[tool.wads.ci.testing]
system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]
```

Run `wads populate` to regenerate your CI workflow. The generated CI will include:

```yaml
- name: Install System Dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y ffmpeg libsndfile1 portaudio19-dev
```

### Multi-Platform Dependencies

For projects that test on multiple operating systems:

```toml
[tool.wads.ci.testing]
system_dependencies = {
    ubuntu = ["ffmpeg", "libsndfile1", "portaudio19-dev"],
    macos = ["ffmpeg", "libsndfile", "portaudio"],
    windows = ["ffmpeg"]
}
```

This automatically:
- Uses `apt-get` on Ubuntu CI runners
- Uses `choco` on Windows CI runners
- Uses `brew` on macOS CI runners (when enabled)

## Use Cases

### Audio Processing Projects

```toml
[tool.wads.ci.testing]
system_dependencies = {
    ubuntu = [
        "ffmpeg",
        "libsndfile1",
        "libsndfile1-dev",
        "portaudio19-dev",
        "libportaudio2",
        "sox"
    ],
    macos = [
        "ffmpeg",
        "libsndfile",
        "portaudio",
        "sox"
    ],
    windows = ["ffmpeg"]
}
```

### Computer Vision / Image Processing

```toml
[tool.wads.ci.testing]
system_dependencies = [
    "libopencv-dev",
    "python3-opencv",
    "libglib2.0-0",
    "libsm6",
    "libxext6",
    "libxrender-dev"
]
```

### Database Testing

```toml
[tool.wads.ci.testing]
system_dependencies = [
    "postgresql-client",
    "redis-tools",
    "mongodb-clients"
]
```

### Scientific Computing

```toml
[tool.wads.ci.testing]
system_dependencies = [
    "libhdf5-dev",
    "libnetcdf-dev",
    "libopenblas-dev",
    "gfortran"
]
```

## Combined with Custom Commands

You can combine system dependencies with custom pre-test setup:

```toml
[tool.wads.ci.commands]
pre_test = [
    "python scripts/download_test_data.py",
    "python scripts/setup_test_db.py"
]

[tool.wads.ci.testing]
system_dependencies = ["ffmpeg", "postgresql-client"]
```

**Execution order:**
1. Install system dependencies
2. Run custom pre-test commands
3. Run tests

## Finding Package Names

### Ubuntu/Debian (apt-get)
```bash
# Search for packages
apt-cache search ffmpeg

# Get package info
apt show ffmpeg
```

Common packages:
- Audio: `ffmpeg`, `libsndfile1`, `portaudio19-dev`, `sox`
- Video: `ffmpeg`, `libavcodec-dev`, `libavformat-dev`
- Images: `libopencv-dev`, `libjpeg-dev`, `libpng-dev`
- Databases: `postgresql-client`, `redis-tools`, `mongodb-clients`

### Windows (Chocolatey)
```bash
# Search for packages
choco search ffmpeg

# Get package info
choco info ffmpeg
```

Common packages:
- `ffmpeg`, `imagemagick`, `nodejs`, `python`, `git`

### macOS (Homebrew)
```bash
# Search for packages
brew search ffmpeg

# Get package info
brew info ffmpeg
```

Common packages:
- `ffmpeg`, `libsndfile`, `portaudio`, `sox`, `opencv`

## Best Practices

### 1. Use Platform-Specific Config for Cross-Platform Projects

```toml
system_dependencies = {
    ubuntu = ["lib-xyz", "lib-xyz-dev"],  # Ubuntu needs -dev packages
    macos = ["xyz"],                       # macOS uses simpler names
    windows = ["xyz"]                      # Windows via chocolatey
}
```

### 2. Include Development Headers

For C extensions, include development packages:

```toml
system_dependencies = [
    "libfoo",      # Runtime library
    "libfoo-dev"   # Development headers
]
```

### 3. Pin Versions When Needed

```toml
# In pre_test commands if you need specific versions
[tool.wads.ci.commands]
pre_test = [
    "sudo apt-get install -y ffmpeg=7:4.4.2-0ubuntu0.22.04.1"
]
```

### 4. Document Why Dependencies Are Needed

```toml
[tool.wads.ci.testing]
# Audio processing dependencies:
# - ffmpeg: Video/audio conversion in tests
# - libsndfile1: Reading/writing audio files
# - portaudio19-dev: Real-time audio I/O testing
system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]
```

## Troubleshooting

### Dependency Not Found

**Problem:** CI fails with "Package not found"

**Solution:** Check the exact package name for your Ubuntu version:
```bash
# In CI, add a debug step:
- name: Debug Available Packages
  run: |
    apt-cache search libsndfile
    apt list --installed | grep snd
```

### Wrong Ubuntu Version

**Problem:** Package names differ between Ubuntu versions

**Solution:** Use version-specific config or install from PPA:
```toml
[tool.wads.ci.commands]
pre_test = [
    "sudo add-apt-repository ppa:something/something -y",
    "sudo apt-get update"
]

[tool.wads.ci.testing]
system_dependencies = ["package-from-ppa"]
```

### Windows Installation Fails

**Problem:** Chocolatey package not available

**Solution:** Disable Windows testing or use alternative installation:
```toml
[tool.wads.ci.testing]
test_on_windows = false

# Or install manually in pre_test:
[tool.wads.ci.commands]
pre_test = [
    "if [ \"$RUNNER_OS\" == \"Windows\" ]; then curl -O https://...; fi"
]
```

## Examples

Run the examples to see system dependencies in action:

```bash
python examples/system_deps_example.py
```

This demonstrates:
- Simple Ubuntu dependencies
- Multi-platform configuration
- Combined with custom commands
- Real-world audio processing project

## See Also

- [CI_CONFIG_GUIDE.md](../CI_CONFIG_GUIDE.md) - Complete CI configuration reference
- [wads/ci_config.py](../wads/ci_config.py) - Implementation details
- [test_system_deps.py](../test_system_deps.py) - Unit tests
