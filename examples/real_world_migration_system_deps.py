"""
Real-World Example: Adding System Dependencies to an Existing Project

This demonstrates how to migrate an existing project to use the new
system dependencies feature.
"""


def show_before():
    """Show how things were done before (manual CI editing)."""

    print("=" * 70)
    print("BEFORE: Manual CI Editing (The Old Way)")
    print("=" * 70)

    ci_yaml = """
# .github/workflows/ci.yml (manually edited)
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      # ❌ Problem: System deps hardcoded in CI YAML
      - name: Install System Dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y ffmpeg libsndfile1 portaudio19-dev
      
      - name: Install Python Dependencies
        run: pip install -e .[test]
      
      - name: Run Tests
        run: pytest
"""

    print("\n", ci_yaml)
    print("\n❌ Problems:")
    print("  • System dependencies scattered across CI files")
    print("  • Hard to discover what packages are needed")
    print("  • Manual synchronization between projects")
    print("  • No platform-specific configuration")
    print()


def show_after():
    """Show the new configuration-driven approach."""

    print("=" * 70)
    print("AFTER: Configuration-Driven (The New Way)")
    print("=" * 70)

    pyproject_toml = """
# pyproject.toml (single source of truth)
[project]
name = "audio-ml-toolkit"
version = "0.1.0"

[tool.wads.ci.testing]
# ✅ System dependencies declared here
system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]
python_versions = ["3.10", "3.12"]
pytest_args = ["-v", "--cov=audio_ml"]
"""

    print("\n", pyproject_toml)

    print("\n✅ Benefits:")
    print("  • All configuration in pyproject.toml")
    print("  • Easy to discover and update")
    print("  • Automatically generated CI workflows")
    print("  • Platform-specific support built-in")
    print()


def show_migration_steps():
    """Show step-by-step migration guide."""

    print("=" * 70)
    print("MIGRATION STEPS: From Old to New")
    print("=" * 70)

    steps = """
Step 1: Identify your system dependencies
------------------------------------------
Look at your current CI workflow:

  .github/workflows/ci.yml
  └── Find lines like: sudo apt-get install -y [packages...]

Example found: ffmpeg libsndfile1 portaudio19-dev


Step 2: Add to pyproject.toml
------------------------------
Edit your pyproject.toml and add:

  [tool.wads.ci.testing]
  system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]


Step 3: Regenerate CI workflow
-------------------------------
Run wads populate:

  $ cd /path/to/your/project
  $ python -m wads.populate .

This will regenerate your CI workflow with system dependencies included.


Step 4: Verify the changes
---------------------------
Check the generated .github/workflows/ci.yml:

  • Should contain "Install System Dependencies" step
  • Should have sudo apt-get install with your packages
  • Positioned before "Run Tests" step


Step 5: Commit and push
------------------------
  $ git add pyproject.toml .github/workflows/ci.yml
  $ git commit -m "Configure system dependencies in pyproject.toml"
  $ git push
"""

    print(steps)


def show_common_packages():
    """Show commonly used system packages by category."""

    print("=" * 70)
    print("COMMON SYSTEM PACKAGES BY CATEGORY")
    print("=" * 70)

    categories = {
        "Audio Processing": [
            "ffmpeg",
            "libsndfile1",
            "libsndfile1-dev",
            "portaudio19-dev",
            "libportaudio2",
            "sox",
            "libavcodec-dev",
            "libavformat-dev",
        ],
        "Computer Vision": [
            "libopencv-dev",
            "python3-opencv",
            "libglib2.0-0",
            "libsm6",
            "libxext6",
            "libxrender-dev",
            "libjpeg-dev",
            "libpng-dev",
        ],
        "Database Testing": [
            "postgresql-client",
            "postgresql-server-dev-all",
            "redis-tools",
            "mongodb-clients",
            "mysql-client",
            "sqlite3",
        ],
        "Scientific Computing": [
            "libhdf5-dev",
            "libnetcdf-dev",
            "libopenblas-dev",
            "gfortran",
            "libgsl-dev",
            "libfftw3-dev",
        ],
        "Graphics & Plotting": [
            "libcairo2-dev",
            "libgirepository1.0-dev",
            "graphviz",
            "libgraphviz-dev",
        ],
        "Web Automation": [
            "chromium-browser",
            "chromium-chromedriver",
            "firefox",
            "xvfb",
        ],
    }

    for category, packages in categories.items():
        print(f"\n{category}")
        print("-" * len(category))
        for pkg in packages:
            print(f"  • {pkg}")

    print()


def show_troubleshooting():
    """Show common issues and solutions."""

    print("=" * 70)
    print("TROUBLESHOOTING COMMON ISSUES")
    print("=" * 70)

    issues = """
Issue 1: Package not found in Ubuntu
-------------------------------------
Problem: CI fails with "E: Unable to locate package xyz"

Solution: Check the exact package name for Ubuntu 22.04:
  1. Go to https://packages.ubuntu.com/
  2. Search for your package
  3. Use the exact name listed

Example: 
  ❌ libsnd  (wrong)
  ✅ libsndfile1  (correct)


Issue 2: Need different packages on different platforms
--------------------------------------------------------
Problem: Package has different names on Ubuntu vs Windows

Solution: Use platform-specific configuration:
  [tool.wads.ci.testing]
  system_dependencies = {
      ubuntu = ["libsndfile1", "libsndfile1-dev"],
      windows = ["libsndfile"]
  }


Issue 3: Package needs specific version
----------------------------------------
Problem: Need ffmpeg 4.x but Ubuntu has 3.x

Solution: Use custom pre_test command:
  [tool.wads.ci.commands]
  pre_test = [
      "sudo add-apt-repository ppa:savoury1/ffmpeg4 -y",
      "sudo apt-get update"
  ]
  
  [tool.wads.ci.testing]
  system_dependencies = ["ffmpeg"]


Issue 4: Development headers missing
-------------------------------------
Problem: Compiling C extensions fails

Solution: Include both runtime and -dev packages:
  system_dependencies = [
      "libfoo",      # Runtime library
      "libfoo-dev"   # Development headers
  ]

Example:
  system_dependencies = [
      "libsndfile1",      # For runtime
      "libsndfile1-dev"   # For building packages with C extensions
  ]
"""

    print(issues)


def main():
    """Run all demonstrations."""

    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 10 + "Real-World Migration: System Dependencies" + " " * 17 + "║")
    print("╚" + "=" * 68 + "╝")
    print("\n")

    show_before()
    show_after()
    show_migration_steps()
    show_common_packages()
    show_troubleshooting()

    print("=" * 70)
    print("✅ Ready to migrate your project!")
    print("=" * 70)
    print("\nQuick start:")
    print("  1. Add [tool.wads.ci.testing] section to pyproject.toml")
    print("  2. Add system_dependencies = [...] with your packages")
    print("  3. Run: python -m wads.populate .")
    print("  4. Commit and push changes")
    print("\nFor more help, see:")
    print("  • examples/SYSTEM_DEPS_README.md")
    print("  • CI_CONFIG_GUIDE.md")
    print()


if __name__ == "__main__":
    main()
