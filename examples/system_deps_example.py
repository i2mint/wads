"""
Example: Using System Dependencies in CI Configuration

This example demonstrates how to configure system dependencies (like ffmpeg,
libsndfile, etc.) in your pyproject.toml for automatic installation during CI.
"""

from pathlib import Path
import tempfile
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from wads.ci_config import CIConfig


def example_1_simple_ubuntu_deps():
    """Example 1: Simple list of Ubuntu packages."""

    print("=" * 70)
    print("Example 1: Simple Ubuntu Dependencies")
    print("=" * 70)

    # In your pyproject.toml, add this to [tool.wads.ci.testing]:
    example_toml = """
[tool.wads.ci.testing]
# Simple form: Just a list of Ubuntu package names
system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]
"""

    print("\nIn your pyproject.toml:")
    print(example_toml)

    # Load and process
    pyproject_data = {
        "project": {"name": "audio-project"},
        "tool": {
            "wads": {
                "ci": {
                    "testing": {
                        "system_dependencies": [
                            "ffmpeg",
                            "libsndfile1",
                            "portaudio19-dev",
                        ]
                    }
                }
            }
        },
    }

    config = CIConfig(pyproject_data)

    print("\nGenerated CI steps:")
    print("-" * 70)
    print(config.generate_pre_test_steps())
    print("\n")


def example_2_multi_platform_deps():
    """Example 2: Platform-specific dependencies."""

    print("=" * 70)
    print("Example 2: Multi-Platform Dependencies")
    print("=" * 70)

    # In your pyproject.toml:
    example_toml = """
[tool.wads.ci.testing]
# Platform-specific form: Different packages for each OS
system_dependencies = { 
    ubuntu = ["ffmpeg", "libsndfile1", "portaudio19-dev"],
    macos = ["ffmpeg", "libsndfile", "portaudio"],
    windows = ["ffmpeg"]  # Installed via chocolatey on Windows
}
"""

    print("\nIn your pyproject.toml:")
    print(example_toml)

    # Load and process
    pyproject_data = {
        "project": {"name": "cross-platform-audio"},
        "tool": {
            "wads": {
                "ci": {
                    "testing": {
                        "system_dependencies": {
                            "ubuntu": ["ffmpeg", "libsndfile1", "portaudio19-dev"],
                            "macos": ["ffmpeg", "libsndfile", "portaudio"],
                            "windows": ["ffmpeg"],
                        }
                    }
                }
            }
        },
    }

    config = CIConfig(pyproject_data)

    print("\nGenerated Ubuntu CI steps:")
    print("-" * 70)
    print(config.generate_pre_test_steps())

    print("\n\nWindows CI job (excerpt):")
    print("-" * 70)
    windows_job = config.generate_windows_validation_job()
    # Show just the system deps part
    if "choco install" in windows_job:
        for line in windows_job.split("\n"):
            if "Install System Dependencies" in line or "choco install" in line:
                print(line)
    print("\n")


def example_3_combined_with_custom_commands():
    """Example 3: System deps + custom pre-test commands."""

    print("=" * 70)
    print("Example 3: System Dependencies + Custom Pre-Test Commands")
    print("=" * 70)

    # In your pyproject.toml:
    example_toml = """
[tool.wads.ci.commands]
# Custom setup commands
pre_test = [
    "python scripts/download_test_data.py",
    "python scripts/setup_test_environment.py"
]

[tool.wads.ci.testing]
# System packages needed
system_dependencies = ["ffmpeg", "libsndfile1"]
"""

    print("\nIn your pyproject.toml:")
    print(example_toml)

    # Load and process
    pyproject_data = {
        "project": {"name": "ml-audio-project"},
        "tool": {
            "wads": {
                "ci": {
                    "commands": {
                        "pre_test": [
                            "python scripts/download_test_data.py",
                            "python scripts/setup_test_environment.py",
                        ]
                    },
                    "testing": {"system_dependencies": ["ffmpeg", "libsndfile1"]},
                }
            }
        },
    }

    config = CIConfig(pyproject_data)

    print("\nGenerated CI steps (both system deps and custom commands):")
    print("-" * 70)
    print(config.generate_pre_test_steps())
    print("\n")


def example_4_real_world_audio_project():
    """Example 4: Real-world audio processing project."""

    print("=" * 70)
    print("Example 4: Real-World Audio Processing Project")
    print("=" * 70)

    pyproject_data = {
        "project": {"name": "audio-ml-toolkit"},
        "tool": {
            "wads": {
                "ci": {
                    "commands": {
                        "pre_test": [
                            "python -m pip install --upgrade pip",
                            "python scripts/generate_test_audio.py",
                        ]
                    },
                    "testing": {
                        "python_versions": ["3.10", "3.11", "3.12"],
                        "system_dependencies": {
                            "ubuntu": [
                                "ffmpeg",
                                "libsndfile1",
                                "libsndfile1-dev",
                                "portaudio19-dev",
                                "libportaudio2",
                                "sox",
                            ],
                            "macos": ["ffmpeg", "libsndfile", "portaudio", "sox"],
                            "windows": ["ffmpeg"],
                        },
                        "pytest_args": ["-v", "--tb=short", "--durations=10"],
                        "coverage_enabled": True,
                        "test_on_windows": True,
                    },
                }
            }
        },
    }

    config = CIConfig(pyproject_data)

    print("\nProject: Audio ML Toolkit")
    print("Python versions:", config.python_versions)
    print("\nUbuntu dependencies:")
    deps = config._normalize_system_deps()
    for dep in deps["ubuntu"]:
        print(f"  • {dep}")

    print("\n\nGenerated Ubuntu CI steps:")
    print("-" * 70)
    print(config.generate_pre_test_steps())
    print("\n")


def main():
    """Run all examples."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "System Dependencies Examples" + " " * 25 + "║")
    print("╚" + "=" * 68 + "╝")
    print("\n")

    example_1_simple_ubuntu_deps()
    example_2_multi_platform_deps()
    example_3_combined_with_custom_commands()
    example_4_real_world_audio_project()

    print("=" * 70)
    print("✅ All examples completed!")
    print("=" * 70)
    print("\nTo use in your project:")
    print("1. Add system_dependencies to [tool.wads.ci.testing] in pyproject.toml")
    print("2. Run 'wads populate' to regenerate CI workflow")
    print("3. The CI will automatically install system dependencies before tests")
    print()


if __name__ == "__main__":
    main()
