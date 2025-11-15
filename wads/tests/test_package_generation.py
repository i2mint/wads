"""Tests for package_module functionality (DEPRECATED).

These tests cover the deprecated embedded wheel packaging functionality that requires
setuptools. The tests are automatically skipped if setuptools is not installed.

To run these tests, install wads with setuptools support:
    pip install 'wads[setuptools]'

Note: This functionality is deprecated in favor of modern Python packaging with
pyproject.toml and standard dependency management.
"""

import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

from wads.package_module import generate_package

EXAMPLE_MODULE_FILE = Path(__file__).parent / "data" / "example_module.py"
EXAMPLE_MODULE_DIR = Path(__file__).parent / "data"

# Check if setuptools is available (needed for deprecated package_module functionality)
try:
    import setuptools

    HAS_SETUPTOOLS = True
except ImportError:
    HAS_SETUPTOOLS = False

skip_if_no_setuptools = pytest.mark.skipif(
    not HAS_SETUPTOOLS,
    reason="setuptools not installed - required for deprecated package_module functionality. Install with: pip install 'wads[setuptools]'",
)


@skip_if_no_setuptools
def test_generate_package_from_file():
    with tempfile.TemporaryDirectory() as tmp_folder:
        tmp_path = Path(tmp_folder)
        output_path = tmp_path / "output"
        generate_package(
            module_path=EXAMPLE_MODULE_FILE,
            install_requires=["dol", "i2 @ git+https://git@github.com/i2mint/i2.git"],
            output_path=output_path,
            version="8.8.8",
        )
        try:
            subprocess.check_output(
                [sys.executable, "setup.py", "sdist"],
                cwd=output_path,
            )
        except subprocess.CalledProcessError as e:
            error_message = e.output.decode("utf-8")  # Decode the output if needed
            print("Error message:", error_message)
            raise e

        i2_whl = next((output_path / "dist").glob("i2-*.whl"))
        assert i2_whl, "wheel not built from specified git repo"
        module_tar_gz = next((output_path / "dist").glob("*.tar.gz"))
        assert module_tar_gz.is_file()
        with tarfile.open(module_tar_gz, "r:gz") as tar:
            tar.extractall(tmp_path / "unpacked", filter="data")
        unpacked_dist = (
            tmp_path / "unpacked" / module_tar_gz.name[: -len(".tar.gz")] / "dist"
        )
        unpacked_i2_whl = next(unpacked_dist.glob("i2-*.whl"))
        assert (
            unpacked_i2_whl.read_bytes() == i2_whl.read_bytes()
        ), ".tar.gz does not include dependency wheel"


@skip_if_no_setuptools
def test_generate_package_from_dir():
    with tempfile.TemporaryDirectory() as tmp_folder:
        tmp_path = Path(tmp_folder)
        output_path = tmp_path / "output"
        generate_package(
            module_path=EXAMPLE_MODULE_DIR,
            install_requires=["dol", "i2 @ git+https://git@github.com/i2mint/i2.git"],
            output_path=output_path,
            version="8.8.8",
            glob_pattern=["*.pkl", "*.json"],
        )

        try:
            subprocess.check_output(
                [sys.executable, "setup.py", "sdist"],
                cwd=output_path,
            )
        except subprocess.CalledProcessError as e:
            error_message = e.output.decode("utf-8")  # Decode the output if needed
            print("Error message:", error_message)
            raise e
        i2_whl = next((output_path / "dist").glob("i2-*.whl"))
        assert i2_whl, "wheel not built from specified git repo"
        module_tar_gz = next((output_path / "dist").glob("*.tar.gz"))
        assert module_tar_gz.is_file()
        with tarfile.open(module_tar_gz, "r:gz") as tar:
            tar.extractall(tmp_path / "unpacked", filter="data")
        unpacked_dir = tmp_path / "unpacked" / module_tar_gz.name[: -len(".tar.gz")]
        unpacked_dist = unpacked_dir / "dist"
        unpacked_module = unpacked_dir / EXAMPLE_MODULE_DIR.stem
        unpacked_i2_whl = next(unpacked_dist.glob("i2-*.whl"))
        unpacked_json = next(unpacked_module.glob("*.json"))
        assert unpacked_json.is_file()
        unpacked_pkl = next(unpacked_module.glob("*.pkl"))
        assert unpacked_pkl.is_file()
        assert (
            unpacked_i2_whl.read_bytes() == i2_whl.read_bytes()
        ), ".tar.gz does not include dependency wheel"
