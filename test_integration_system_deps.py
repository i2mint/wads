"""
Integration test: Generate CI workflow with system dependencies.

This test creates a minimal pyproject.toml with system dependencies configured,
generates a CI workflow, and verifies the output contains the expected installation steps.
"""

import tempfile
import os
from pathlib import Path
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from wads.ci_config import CIConfig
from wads.populate import _add_ci_def


def test_integration_system_deps_in_generated_ci():
    """Test that system dependencies appear in generated CI workflow."""

    print("\n" + "=" * 70)
    print("Integration Test: System Dependencies in Generated CI Workflow")
    print("=" * 70)

    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a pyproject.toml with system dependencies
        pyproject_content = """
[project]
name = "test-audio-project"
version = "0.1.0"

[tool.wads.ci]
project_name = "test-audio-project"

[tool.wads.ci.testing]
python_versions = ["3.10", "3.12"]
system_dependencies = ["ffmpeg", "libsndfile1", "portaudio19-dev"]
pytest_args = ["-v"]
"""

        pyproject_path = tmpdir_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        print(f"\n✓ Created test pyproject.toml at {pyproject_path}")
        print(f"  Content:\n{pyproject_content}")

        # Load the CI config
        config = CIConfig.from_file(pyproject_path)

        print(f"\n✓ Loaded CI config:")
        print(f"  - Project: {config.project_name}")
        print(f"  - Python versions: {config.python_versions}")
        print(f"  - System deps: {config.system_dependencies}")

        # Generate CI workflow
        ci_dir = tmpdir_path / ".github" / "workflows"
        ci_dir.mkdir(parents=True)
        ci_file = ci_dir / "ci.yml"

        # Get the CI template path
        from wads import github_ci_publish_2025_path

        print(f"\n✓ Using CI template: {Path(github_ci_publish_2025_path).name}")

        # Generate CI file
        _add_ci_def(
            ci_def_path=str(ci_file),
            ci_tpl_path=github_ci_publish_2025_path,
            root_url="https://github.com/test/test-audio-project",
            name="test-audio-project",
            clog=print,
            user_email="test@example.com",
            pkg_dir=str(tmpdir_path),
        )

        # Read generated CI
        generated_ci = ci_file.read_text()

        print(f"\n✓ Generated CI workflow at {ci_file}")

        # Verify system dependencies are in the CI
        checks = {
            "Install System Dependencies step": "- name: Install System Dependencies"
            in generated_ci,
            "apt-get update command": "sudo apt-get update" in generated_ci,
            "ffmpeg package": "ffmpeg" in generated_ci,
            "libsndfile1 package": "libsndfile1" in generated_ci,
            "portaudio19-dev package": "portaudio19-dev" in generated_ci,
            "Python versions array": '["3.10", "3.12"]' in generated_ci,
            "PROJECT_NAME env var": "PROJECT_NAME: test-audio-project" in generated_ci,
        }

        print("\n✓ Verification:")
        all_passed = True
        for check_name, result in checks.items():
            status = "✅" if result else "❌"
            print(f"  {status} {check_name}")
            if not result:
                all_passed = False

        if not all_passed:
            print("\n❌ Some checks failed!")
            print("\nGenerated CI content (first 2000 chars):")
            print("-" * 70)
            print(generated_ci[:2000])
            return False

        # Show the relevant part of the generated CI
        print("\n✓ Generated System Dependencies Step:")
        print("-" * 70)
        lines = generated_ci.split("\n")
        in_deps_section = False
        for i, line in enumerate(lines):
            if "Install System Dependencies" in line:
                in_deps_section = True
            if in_deps_section:
                print(line)
                if line.strip() and not line.startswith(" ") and i > 0:
                    break

        print("\n" + "=" * 70)
        print("✅ Integration test PASSED!")
        print("=" * 70)
        return True


if __name__ == "__main__":
    success = test_integration_system_deps_in_generated_ci()
    sys.exit(0 if success else 1)
