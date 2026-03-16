"""Tests for wads.user_dirs module."""

from pathlib import Path
import pytest


class TestPlatformDirs:
    """Test platform directory resolution."""

    def test_config_dir_returns_path(self):
        from wads.user_dirs import config_dir

        result = config_dir()
        assert isinstance(result, Path)
        assert "wads" in str(result)

    def test_data_dir_returns_path(self):
        from wads.user_dirs import data_dir

        result = data_dir()
        assert isinstance(result, Path)
        assert "wads" in str(result)

    def test_cache_dir_returns_path(self):
        from wads.user_dirs import cache_dir

        result = cache_dir()
        assert isinstance(result, Path)
        assert "wads" in str(result)

    def test_name_candidates_dir_is_under_data_dir(self):
        from wads.user_dirs import name_candidates_dir, data_dir

        result = name_candidates_dir()
        assert result.parent == data_dir()
        assert result.name == "name_candidates"

    def test_user_preferences_path_is_under_config_dir(self):
        from wads.user_dirs import user_preferences_path, config_dir

        result = user_preferences_path()
        assert result.parent == config_dir()
        assert result.name == "preferences.toml"


class TestUserPreferences:
    """Test reading/writing user preferences."""

    def test_read_missing_file_returns_empty_dict(self, monkeypatch):
        from wads import user_dirs

        monkeypatch.setattr(
            user_dirs, "user_preferences_path", lambda: Path("/nonexistent/path.toml")
        )
        result = user_dirs.read_user_preferences()
        assert result == {}

    def test_write_and_read_roundtrip(self, tmp_path, monkeypatch):
        from wads import user_dirs

        prefs_path = tmp_path / "preferences.toml"
        monkeypatch.setattr(user_dirs, "user_preferences_path", lambda: prefs_path)

        prefs = {
            "default_author": "Test Author",
            "default_license": "mit",
            "github_username": "testuser",
        }
        user_dirs.write_user_preferences(prefs)
        assert prefs_path.exists()

        loaded = user_dirs.read_user_preferences()
        assert loaded == prefs

    def test_write_creates_parent_dirs(self, tmp_path, monkeypatch):
        from wads import user_dirs

        prefs_path = tmp_path / "nested" / "dir" / "preferences.toml"
        monkeypatch.setattr(user_dirs, "user_preferences_path", lambda: prefs_path)

        user_dirs.write_user_preferences({"key": "value"})
        assert prefs_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
