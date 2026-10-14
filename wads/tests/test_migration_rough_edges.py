"""i2mint/wads#52: rough edges in ``setup-to-pyproject`` output and pin hints."""

import re
from pathlib import Path

import pytest

from wads.ci_config import CIConfig
from wads.migration import migrate_setuptools_to_hatching
from wads.toml_util import pep639_license

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

MIGRATION_SOURCE = (Path(__file__).parents[1] / "migration.py").read_text()


def _migrated_license(license_value):
    cfg = {
        "metadata": {
            "name": "myproj",
            "version": "0.1.0",
            "description": "My project",
            "url": "https://github.com/user/myproj",
            "license": license_value,
        }
    }
    return tomllib.loads(migrate_setuptools_to_hatching(cfg))["project"]["license"]


@pytest.mark.parametrize(
    "given, expected",
    [
        ("MIT", "MIT"),
        ("mit", "MIT"),
        ("Apache Software License", "Apache-2.0"),
        ("apache-2.0", "Apache-2.0"),
    ],
)
def test_setup_to_pyproject_emits_an_spdx_license_string(given, expected):
    """Item 1: PEP 639 ``license = "<SPDX>"``, not the deprecated table."""
    assert _migrated_license(given) == expected


def test_a_license_that_is_not_spdx_keeps_the_table_form():
    """Hatchling rejects a non-SPDX ``license`` string, so never emit one."""
    assert _migrated_license("Proprietary, all rights reserved") == {
        "text": "Proprietary, all rights reserved"
    }


def test_pep639_license_falls_back_without_a_new_enough_packaging(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_licenses(name, *args, **kwargs):
        if name == "packaging.licenses":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_licenses)
    assert pep639_license("MIT") == {"text": "MIT"}


def test_an_empty_ci_project_name_falls_back_to_the_package_name():
    """Item 2: ``project_name = ""`` never reaches ``--cov=`` as an empty target."""
    config = CIConfig(
        {"project": {"name": "myproj"}, "tool": {"wads": {"ci": {"project_name": ""}}}}
    )
    assert config.project_name == "myproj"


def test_pin_hints_use_bare_version_tags():
    """Items 4/5: wads tags have no ``v`` prefix, and wads publishes tags, not releases."""
    assert not re.findall(r"@v\d", MIGRATION_SOURCE)
    assert "@vX" not in MIGRATION_SOURCE
    assert "gh release list" not in MIGRATION_SOURCE


def test_org_slash_proj_strips_a_url_slash_even_on_windows(monkeypatch):
    """A URL's trailing ``/`` is not an OS path separator (``\\`` on Windows)."""
    import wads.util
    from wads.populate import _get_org_slash_proj

    monkeypatch.setattr(wads.util, "path_sep", "\\")
    assert _get_org_slash_proj("https://github.com/thorwhalen/ut/") == "thorwhalen/ut"


@pytest.mark.parametrize("value", [None, 3])
def test_pep639_license_passes_non_strings_through_as_a_table(value):
    assert pep639_license(value) == {"text": value}


def test_pep639_license_leaves_a_table_alone():
    assert pep639_license({"text": "MIT"}) == {"text": "MIT"}


# Item 3: no tests/ dir -> testpaths point at the package, not at a missing "tests".

_SETUP_CFG = """[metadata]
name = my-proj
version = 0.1.0
description = My project
url = https://github.com/user/my-proj
license = MIT
"""


def _testpaths(tmp_path, *dirs, **kwargs):
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)
        if not d.endswith("tests"):
            (tmp_path / d / "__init__.py").write_text("")
    cfg = tmp_path / "setup.cfg"
    cfg.write_text(_SETUP_CFG)
    out = migrate_setuptools_to_hatching(str(cfg), **kwargs)
    return tomllib.loads(out)["tool"]["pytest"]["ini_options"]["testpaths"]


def test_no_tests_dir_points_testpaths_at_the_package(tmp_path):
    assert _testpaths(tmp_path, "my_proj") == ["my_proj"]


def test_src_layout_package_is_found(tmp_path):
    assert _testpaths(tmp_path, "src/my_proj") == ["src/my_proj"]


def test_an_existing_tests_dir_keeps_the_template(tmp_path):
    assert _testpaths(tmp_path, "my_proj", "tests") == ["tests"]


def test_no_package_dir_found_keeps_the_template(tmp_path):
    assert _testpaths(tmp_path) == ["tests"]


def test_content_without_a_directory_keeps_the_template():
    out = tomllib.loads(migrate_setuptools_to_hatching(_SETUP_CFG))
    assert out["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


def test_project_dir_can_be_given_explicitly(tmp_path):
    (tmp_path / "my_proj").mkdir()
    (tmp_path / "my_proj" / "__init__.py").write_text("")
    out = tomllib.loads(
        migrate_setuptools_to_hatching(_SETUP_CFG, project_dir=tmp_path)
    )
    assert out["tool"]["pytest"]["ini_options"]["testpaths"] == ["my_proj"]


def test_a_path_object_gets_the_same_default_project_dir(tmp_path):
    (tmp_path / "my_proj").mkdir()
    (tmp_path / "my_proj" / "__init__.py").write_text("")
    (tmp_path / "setup.cfg").write_text(_SETUP_CFG)
    out = tomllib.loads(migrate_setuptools_to_hatching(tmp_path / "setup.cfg"))
    assert out["tool"]["pytest"]["ini_options"]["testpaths"] == ["my_proj"]
