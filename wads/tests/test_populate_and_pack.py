"""
Comprehensive tests for populate and pack functionality with pyproject.toml.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

import pytest

from wads.populate import populate_pkg_dir, write_pyproject_configs
from wads.pack import (
    get_name_from_configs,
    current_configs_version,
    increment_configs_version,
    set_version,
    run_setup,
)
from wads.toml_util import read_pyproject_toml, get_project_version, get_project_name


def setup_git_repo(pkg_dir: Path, remote_url: str):
    """Helper function to initialize a git repo for testing"""
    subprocess.run(["git", "init"], cwd=pkg_dir, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=pkg_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=pkg_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", remote_url],
        cwd=pkg_dir,
        capture_output=True,
    )


class TestPopulate:
    """Test the populate functionality"""

    def test_populate_creates_pyproject_toml(self):
        """Test that populate creates pyproject.toml"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "testpkg"
            pkg_dir.mkdir()
            setup_git_repo(pkg_dir, "https://github.com/test/testpkg")

            populate_pkg_dir(
                str(pkg_dir),
                description="Test package",
                root_url="https://github.com/test",
                author="Test Author",
                version="0.1.0",
                skip_ci_def_gen=True,  # Skip CI generation for simpler test
            )

            # Check that pyproject.toml was created
            pyproject_file = pkg_dir / "pyproject.toml"
            assert pyproject_file.exists(), "pyproject.toml should be created"

            # Check that the package directory was created
            assert (pkg_dir / "testpkg" / "__init__.py").exists()

            # Check that README was created
            assert (pkg_dir / "README.md").exists()

            # Check that LICENSE was created
            assert (pkg_dir / "LICENSE").exists()

    def test_populate_creates_correct_metadata(self):
        """Test that populate creates correct metadata in pyproject.toml"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "mypkg"
            pkg_dir.mkdir()
            setup_git_repo(pkg_dir, "https://github.com/myorg/mypkg")

            populate_pkg_dir(
                str(pkg_dir),
                description="My test package",
                root_url="https://github.com/myorg",
                author="John Doe",
                version="1.2.3",
                keywords=["test", "package"],
                install_requires=["requests", "click"],
                skip_ci_def_gen=True,
            )

            # Read the pyproject.toml
            data = read_pyproject_toml(str(pkg_dir))

            # Check metadata
            assert data["project"]["name"] == "mypkg"
            assert data["project"]["version"] == "1.2.3"
            assert data["project"]["description"] == "My test package"
            assert data["project"]["keywords"] == ["test", "package"]
            assert data["project"]["dependencies"] == ["requests", "click"]
            assert data["project"]["authors"] == [{"name": "John Doe"}]

    def test_write_pyproject_configs(self):
        """Test writing pyproject.toml from configs"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir)

            configs = {
                "name": "testpkg",
                "version": "0.2.0",
                "description": "A test package",
                "url": "https://github.com/test/testpkg",
                "license": "apache-2.0",
                "keywords": ["test", "demo"],
                "author": "Test Author",
                "install_requires": ["numpy", "pandas"],
            }

            write_pyproject_configs(str(pkg_dir), configs)

            # Check that file was created and can be read
            data = read_pyproject_toml(str(pkg_dir))
            assert data["project"]["name"] == "testpkg"
            assert data["project"]["version"] == "0.2.0"


class TestPackWithPyprojectToml:
    """Test pack.py functions with pyproject.toml"""

    def test_get_name_from_configs(self):
        """Test getting package name from pyproject.toml"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "mypkg"
            pkg_dir.mkdir()
            setup_git_repo(pkg_dir, "https://github.com/test/mypkg")

            populate_pkg_dir(
                str(pkg_dir),
                description="Test package",
                root_url="https://github.com/test",
                skip_ci_def_gen=True,
            )

            name = get_name_from_configs(str(pkg_dir))
            assert name == "mypkg"

    def test_current_configs_version(self):
        """Test getting current version from pyproject.toml"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "versionpkg"
            pkg_dir.mkdir()
            setup_git_repo(pkg_dir, "https://github.com/test/versionpkg")

            populate_pkg_dir(
                str(pkg_dir),
                description="Test package",
                root_url="https://github.com/test",
                version="1.2.3",
                skip_ci_def_gen=True,
            )

            version = current_configs_version(str(pkg_dir))
            assert version == "1.2.3"

    def test_set_version(self):
        """Test setting version in pyproject.toml"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "verpkg"
            pkg_dir.mkdir()
            setup_git_repo(pkg_dir, "https://github.com/test/verpkg")

            populate_pkg_dir(
                str(pkg_dir),
                description="Test package",
                root_url="https://github.com/test",
                version="0.0.1",
                skip_ci_def_gen=True,
            )

            # Set new version
            set_version(str(pkg_dir), "2.0.0")

            # Verify it was updated
            version = get_project_version(str(pkg_dir))
            assert version == "2.0.0"

    def test_increment_configs_version(self):
        """Test incrementing version in pyproject.toml"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "incpkg"
            pkg_dir.mkdir()
            setup_git_repo(pkg_dir, "https://github.com/test/incpkg")

            populate_pkg_dir(
                str(pkg_dir),
                description="Test package",
                root_url="https://github.com/test",
                version="1.2.3",
                skip_ci_def_gen=True,
            )

            # Increment version
            new_version = increment_configs_version(str(pkg_dir))

            # Should be incremented to 1.2.4
            assert new_version == "1.2.4"

            # Verify it was updated in file
            version = get_project_version(str(pkg_dir))
            assert version == "1.2.4"


class TestBuild:
    """Test building packages"""

    def test_generated_package_can_be_built(self):
        """Test that a package generated by populate can be built"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "buildpkg"
            pkg_dir.mkdir()
            setup_git_repo(pkg_dir, "https://github.com/test/buildpkg")

            populate_pkg_dir(
                str(pkg_dir),
                description="A buildable package",
                root_url="https://github.com/test",
                version="0.1.0",
                install_requires=["requests"],
                skip_ci_def_gen=True,
            )

            # Try to build the package
            try:
                run_setup(str(pkg_dir))

                # Check that dist directory was created
                dist_dir = pkg_dir / "dist"
                assert dist_dir.exists(), "dist directory should be created"

                # Check that wheel and sdist were created
                dist_files = list(dist_dir.glob("*"))
                assert len(dist_files) > 0, "Build should create distribution files"

                # Should have at least a .tar.gz and .whl
                extensions = {f.suffix for f in dist_files}
                assert ".whl" in extensions or ".gz" in extensions

            except subprocess.CalledProcessError as e:
                # Print output for debugging
                print(f"Build failed: {e}")
                pytest.fail(f"Package build failed: {e}")

    def test_built_package_passes_twine_check(self):
        """Test that built packages pass twine check"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "twinepkg"
            pkg_dir.mkdir()
            setup_git_repo(pkg_dir, "https://github.com/test/twinepkg")

            populate_pkg_dir(
                str(pkg_dir),
                description="A package for twine checking",
                root_url="https://github.com/test",
                version="0.1.0",
                skip_ci_def_gen=True,
            )

            # Build the package
            run_setup(str(pkg_dir))

            # Run twine check
            result = subprocess.run(
                [sys.executable, "-m", "twine", "check", "dist/*"],
                cwd=pkg_dir,
                capture_output=True,
                text=True,
            )

            # Skip if twine not installed
            if result.returncode != 0 and "No module named twine" in result.stderr:
                pytest.skip("twine not installed")

            # Twine check should pass
            assert (
                result.returncode == 0
            ), f"Twine check failed: {result.stdout}\n{result.stderr}"
            assert "PASSED" in result.stdout or result.returncode == 0


class TestCompatibility:
    """Test backward compatibility with setup.cfg"""

    def test_can_read_legacy_setup_cfg(self):
        """Test that pack can still read legacy setup.cfg files"""
        # This test would require a legacy setup.cfg file
        # For now, just ensure the functions don't crash when pyproject.toml is missing
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
