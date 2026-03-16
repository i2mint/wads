"""Platform-appropriate user directories for wads configuration and data.

Provides a facade for user-specific paths that follow platform conventions:
- macOS: ~/Library/Application Support/wads/ (config+data), ~/Library/Caches/wads/ (cache)
- Linux: ~/.config/wads/ (config), ~/.local/share/wads/ (data), ~/.cache/wads/ (cache)
- Windows: %APPDATA%/wads/ (config), %LOCALAPPDATA%/wads/ (data+cache)

User preferences are stored in TOML format at config_dir() / "preferences.toml".
Name candidate files (plain text, one name per line) go in data_dir() / "name_candidates/".
"""

import sys
from pathlib import Path


APP_NAME = "wads"


def _get_platform_dir(kind: str) -> Path:
    """Return platform-appropriate directory for 'config', 'data', or 'cache'.

    Tries platformdirs first (if installed), then falls back to manual logic.
    """
    try:
        import platformdirs

        if kind == "config":
            return Path(platformdirs.user_config_dir(APP_NAME))
        elif kind == "data":
            return Path(platformdirs.user_data_dir(APP_NAME))
        elif kind == "cache":
            return Path(platformdirs.user_cache_dir(APP_NAME))
        raise ValueError(f"Unknown kind: {kind}")
    except ImportError:
        pass

    # Manual fallback
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library"
        if kind in ("config", "data"):
            return base / "Application Support" / APP_NAME
        return base / "Caches" / APP_NAME
    elif sys.platform == "win32":
        import os

        if kind == "config":
            return (
                Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / APP_NAME
            )
        elif kind in ("data", "cache"):
            return (
                Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
                / APP_NAME
            )
    else:
        # Linux / other Unix — follow XDG
        import os

        if kind == "config":
            return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / APP_NAME
        elif kind == "data":
            return (
                Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
                / APP_NAME
            )
        elif kind == "cache":
            return Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / APP_NAME

    raise ValueError(f"Unknown kind: {kind}")


def config_dir() -> Path:
    """User configuration directory for wads."""
    return _get_platform_dir("config")


def data_dir() -> Path:
    """User data directory for wads."""
    return _get_platform_dir("data")


def cache_dir() -> Path:
    """User cache directory for wads."""
    return _get_platform_dir("cache")


def name_candidates_dir() -> Path:
    """Directory for name candidate files (plain text, one name per line)."""
    return data_dir() / "name_candidates"


def user_preferences_path() -> Path:
    """Path to the user preferences TOML file."""
    return config_dir() / "preferences.toml"


def _ensure_parent(path: Path) -> Path:
    """Create parent directories if needed, return path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_user_preferences() -> dict:
    """Read user preferences from preferences.toml.

    Returns an empty dict if the file doesn't exist.

    >>> prefs = read_user_preferences()
    >>> isinstance(prefs, dict)
    True
    """
    path = user_preferences_path()
    if not path.exists():
        return {}

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomli as tomllib
        except ImportError:
            return {}

    with open(path, "rb") as f:
        return tomllib.load(f)


def write_user_preferences(prefs: dict) -> None:
    """Write user preferences to preferences.toml, creating directories as needed."""
    try:
        import tomli_w
    except ImportError:
        raise ImportError(
            "tomli_w is required to write preferences. Install with: pip install tomli-w"
        )

    path = _ensure_parent(user_preferences_path())
    with open(path, "wb") as f:
        tomli_w.dump(prefs, f)
