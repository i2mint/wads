"""
Tests for PEP 725/804 external dependencies support in wads CI configuration.

This module tests:
- DepURL parsing and validation
- External dependencies extraction from [external] table
- External operations metadata from [tool.wads.external.ops]
- Integration with CI workflow generation
- Backward compatibility with legacy system_dependencies
"""

import pytest
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from wads.ci_config import (
    CIConfig,
    _depurl_to_simple_name,
    _validate_depurl,
)


class TestDepURLParsing:
    """Test DepURL parsing and validation functions."""

    def test_depurl_to_simple_name_basic(self):
        """Test basic DepURL name extraction."""
        assert _depurl_to_simple_name("dep:generic/unixodbc") == "unixodbc"
        assert _depurl_to_simple_name("dep:generic/git") == "git"
        assert _depurl_to_simple_name("dep:generic/ffmpeg") == "ffmpeg"

    def test_depurl_to_simple_name_with_version(self):
        """Test DepURL name extraction with version specifier."""
        assert _depurl_to_simple_name("dep:generic/libffi@>=3.0") == "libffi"
        assert _depurl_to_simple_name("dep:generic/openssl@1.1.1") == "openssl"

    def test_depurl_to_simple_name_virtual(self):
        """Test DepURL name extraction for virtual dependencies."""
        assert _depurl_to_simple_name("dep:virtual/compiler/c") == "compiler-c"
        assert _depurl_to_simple_name("dep:virtual/interpreter/python") == "interpreter-python"

    def test_depurl_to_simple_name_with_query(self):
        """Test DepURL name extraction with query parameters."""
        assert _depurl_to_simple_name("dep:generic/git?version=2.0") == "git"

    def test_depurl_to_simple_name_with_fragment(self):
        """Test DepURL name extraction with fragment."""
        assert _depurl_to_simple_name("dep:generic/openssl#subpath") == "openssl"

    def test_validate_depurl_valid(self):
        """Test validation of valid DepURLs."""
        assert _validate_depurl("dep:generic/unixodbc") is True
        assert _validate_depurl("dep:virtual/compiler/c") is True
        assert _validate_depurl("dep:generic/git@2.0") is True
        assert _validate_depurl("dep:generic/openssl?foo=bar") is True

    def test_validate_depurl_invalid(self):
        """Test validation of invalid DepURLs."""
        assert _validate_depurl("generic/unixodbc") is False  # No scheme
        assert _validate_depurl("dep:") is False  # No parts
        assert _validate_depurl("dep:generic") is False  # Only one part
        assert _validate_depurl("dep:/") is False  # Empty parts
        assert _validate_depurl("") is False  # Empty string


class TestExternalDependenciesParsing:
    """Test parsing of [external] table."""

    def test_parse_empty_external_section(self):
        """Test parsing when no [external] section exists."""
        pyproject_data = {"project": {"name": "test-project"}}
        config = CIConfig(pyproject_data)
        deps = config.external_dependencies

        assert deps['build'] == []
        assert deps['host'] == []
        assert deps['runtime'] == []
        assert deps['optional_build'] == {}
        assert deps['optional_host'] == {}
        assert deps['optional_runtime'] == {}
        assert deps['groups'] == {}

    def test_parse_basic_external_deps(self):
        """Test parsing basic external dependencies."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "external": {
                "build-requires": ["dep:virtual/compiler/c"],
                "host-requires": ["dep:generic/unixodbc"],
                "dependencies": ["dep:generic/git"],
            }
        }
        config = CIConfig(pyproject_data)
        deps = config.external_dependencies

        assert deps['build'] == ["dep:virtual/compiler/c"]
        assert deps['host'] == ["dep:generic/unixodbc"]
        assert deps['runtime'] == ["dep:generic/git"]

    def test_parse_optional_external_deps(self):
        """Test parsing optional external dependencies."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "external": {
                "optional-dependencies": {
                    "git-support": ["dep:generic/git"],
                    "advanced": ["dep:generic/libffi"]
                }
            }
        }
        config = CIConfig(pyproject_data)
        deps = config.external_dependencies

        assert deps['optional_runtime'] == {
            "git-support": ["dep:generic/git"],
            "advanced": ["dep:generic/libffi"]
        }

    def test_parse_dependency_groups(self):
        """Test parsing dependency groups."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "external": {
                "dependency-groups": {
                    "dev": ["dep:generic/git", "dep:generic/make"]
                }
            }
        }
        config = CIConfig(pyproject_data)
        deps = config.external_dependencies

        assert deps['groups'] == {
            "dev": ["dep:generic/git", "dep:generic/make"]
        }

    def test_has_external_dependencies(self):
        """Test checking if external dependencies exist."""
        # No dependencies
        config1 = CIConfig({"project": {"name": "test"}})
        assert config1.has_external_dependencies() is False

        # With dependencies
        pyproject_data = {
            "project": {"name": "test-project"},
            "external": {
                "dependencies": ["dep:generic/git"]
            }
        }
        config2 = CIConfig(pyproject_data)
        assert config2.has_external_dependencies() is True


class TestExternalOpsMetadata:
    """Test parsing of [tool.wads.external.ops]."""

    def test_parse_empty_ops_section(self):
        """Test parsing when no ops metadata exists."""
        pyproject_data = {"project": {"name": "test-project"}}
        config = CIConfig(pyproject_data)
        ops = config.external_ops

        assert ops == {}

    def test_parse_basic_ops_metadata(self):
        """Test parsing basic operational metadata."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "tool": {
                "wads": {
                    "external": {
                        "ops": {
                            "unixodbc": {
                                "canonical_id": "dep:generic/unixodbc",
                                "rationale": "ODBC driver interface",
                                "url": "https://www.unixodbc.org/",
                                "install": {
                                    "linux": [
                                        "sudo apt-get update",
                                        "sudo apt-get install -y unixodbc unixodbc-dev"
                                    ],
                                    "macos": "brew install unixodbc",
                                    "windows": "choco install unixodbc-full"
                                }
                            }
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        ops = config.external_ops

        assert "unixodbc" in ops
        assert ops["unixodbc"]["canonical_id"] == "dep:generic/unixodbc"
        assert ops["unixodbc"]["rationale"] == "ODBC driver interface"
        assert isinstance(ops["unixodbc"]["install"]["linux"], list)
        assert ops["unixodbc"]["install"]["macos"] == "brew install unixodbc"


class TestPreTestStepsGeneration:
    """Test generation of pre-test steps with external dependencies."""

    def test_generate_pre_test_steps_empty(self):
        """Test generation with no dependencies."""
        pyproject_data = {"project": {"name": "test-project"}}
        config = CIConfig(pyproject_data)
        steps = config.generate_pre_test_steps()

        assert steps == ""

    def test_generate_pre_test_steps_with_external_deps(self):
        """Test generation with external dependencies and ops."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "external": {
                "dependencies": ["dep:generic/git"]
            },
            "tool": {
                "wads": {
                    "external": {
                        "ops": {
                            "git": {
                                "canonical_id": "dep:generic/git",
                                "install": {
                                    "linux": "sudo apt-get install -y git"
                                }
                            }
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        steps = config.generate_pre_test_steps(platform='linux')

        assert "Install System Dependencies" in steps
        assert "sudo apt-get install -y git" in steps

    def test_generate_pre_test_steps_with_multi_line_install(self):
        """Test generation with multi-line install commands."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "external": {
                "dependencies": ["dep:generic/unixodbc"]
            },
            "tool": {
                "wads": {
                    "external": {
                        "ops": {
                            "unixodbc": {
                                "canonical_id": "dep:generic/unixodbc",
                                "install": {
                                    "linux": [
                                        "sudo apt-get update",
                                        "sudo apt-get install -y unixodbc unixodbc-dev"
                                    ]
                                }
                            }
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        steps = config.generate_pre_test_steps(platform='linux')

        assert "sudo apt-get update" in steps
        assert "sudo apt-get install -y unixodbc unixodbc-dev" in steps

    def test_generate_pre_test_steps_with_custom_commands(self):
        """Test generation with custom pre-test commands."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "tool": {
                "wads": {
                    "ci": {
                        "commands": {
                            "pre_test": ["python setup_test_data.py"]
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        steps = config.generate_pre_test_steps()

        assert "Pre-test Setup" in steps
        assert "python setup_test_data.py" in steps

    def test_generate_pre_test_steps_multiple_deps(self):
        """Test generation with multiple external dependencies."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "external": {
                "host-requires": ["dep:generic/unixodbc"],
                "dependencies": ["dep:generic/git"]
            },
            "tool": {
                "wads": {
                    "external": {
                        "ops": {
                            "unixodbc": {
                                "canonical_id": "dep:generic/unixodbc",
                                "install": {
                                    "linux": "sudo apt-get install -y unixodbc"
                                }
                            },
                            "git": {
                                "canonical_id": "dep:generic/git",
                                "install": {
                                    "linux": "sudo apt-get install -y git"
                                }
                            }
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        steps = config.generate_pre_test_steps(platform='linux')

        assert "sudo apt-get install -y unixodbc" in steps
        assert "sudo apt-get install -y git" in steps


class TestBackwardCompatibility:
    """Test backward compatibility with legacy system_dependencies."""

    def test_legacy_system_dependencies_list(self):
        """Test legacy system_dependencies as list (Ubuntu only)."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "tool": {
                "wads": {
                    "ci": {
                        "testing": {
                            "system_dependencies": ["ffmpeg", "libsndfile1"]
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        steps = config.generate_pre_test_steps(platform='linux')

        assert "sudo apt-get update" in steps
        assert "sudo apt-get install -y ffmpeg libsndfile1" in steps

    def test_legacy_system_dependencies_dict(self):
        """Test legacy system_dependencies as dict."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "tool": {
                "wads": {
                    "ci": {
                        "testing": {
                            "system_dependencies": {
                                "ubuntu": ["ffmpeg", "libsndfile1"],
                                "macos": ["ffmpeg", "libsndfile"],
                                "windows": []
                            }
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        steps_linux = config.generate_pre_test_steps(platform='linux')

        assert "sudo apt-get install -y ffmpeg libsndfile1" in steps_linux

    def test_mixed_new_and_legacy_deps(self):
        """Test that both new and legacy formats can coexist during migration."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "external": {
                "dependencies": ["dep:generic/git"]
            },
            "tool": {
                "wads": {
                    "external": {
                        "ops": {
                            "git": {
                                "canonical_id": "dep:generic/git",
                                "install": {
                                    "linux": "sudo apt-get install -y git"
                                }
                            }
                        }
                    },
                    "ci": {
                        "testing": {
                            "system_dependencies": ["ffmpeg"]
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        steps = config.generate_pre_test_steps(platform='linux')

        # Both should be present
        assert "sudo apt-get install -y git" in steps
        assert "ffmpeg" in steps


class TestWindowsValidationJob:
    """Test Windows validation job generation with external dependencies."""

    def test_windows_job_with_external_deps(self):
        """Test Windows job generation with external dependencies."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "external": {
                "dependencies": ["dep:generic/git"]
            },
            "tool": {
                "wads": {
                    "external": {
                        "ops": {
                            "git": {
                                "canonical_id": "dep:generic/git",
                                "install": {
                                    "windows": "choco install -y git"
                                }
                            }
                        }
                    },
                    "ci": {
                        "testing": {
                            "test_on_windows": True
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        job = config.generate_windows_validation_job()

        assert "windows-validation:" in job
        assert "choco install -y git" in job

    def test_windows_job_disabled(self):
        """Test that Windows job is not generated when disabled."""
        pyproject_data = {
            "project": {"name": "test-project"},
            "tool": {
                "wads": {
                    "ci": {
                        "testing": {
                            "test_on_windows": False
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        job = config.generate_windows_validation_job()

        assert job == ""


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_odbcdol_style_config(self):
        """Test configuration similar to odbcdol project."""
        pyproject_data = {
            "project": {"name": "odbcdol"},
            "external": {
                "host-requires": [
                    "dep:generic/unixodbc",
                    "dep:generic/msodbcsql18"
                ]
            },
            "tool": {
                "wads": {
                    "external": {
                        "ops": {
                            "unixodbc": {
                                "canonical_id": "dep:generic/unixodbc",
                                "rationale": "Provides ODBC driver interface for database connectivity",
                                "url": "https://www.unixodbc.org/",
                                "install": {
                                    "linux": [
                                        "sudo apt-get update",
                                        "sudo apt-get install -y unixodbc unixodbc-dev"
                                    ],
                                    "macos": "brew install unixodbc"
                                }
                            },
                            "msodbcsql18": {
                                "canonical_id": "dep:generic/msodbcsql18",
                                "rationale": "Microsoft ODBC Driver 18 for SQL Server",
                                "url": "https://docs.microsoft.com/sql/connect/odbc/",
                                "install": {
                                    "linux": [
                                        "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
                                        "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
                                        "sudo apt-get update",
                                        "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
                                    ]
                                }
                            }
                        }
                    },
                    "ci": {
                        "testing": {
                            "python_versions": ["3.10", "3.11", "3.12"]
                        }
                    }
                }
            }
        }
        config = CIConfig(pyproject_data)
        steps = config.generate_pre_test_steps(platform='linux')

        # Check that both dependencies are installed
        assert "unixodbc" in steps
        assert "msodbcsql18" in steps
        # Check multi-line commands are present
        assert "sudo apt-get update" in steps
        assert "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18" in steps


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
