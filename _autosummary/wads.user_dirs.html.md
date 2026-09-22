# wads.user_dirs

Platform-appropriate user directories for wads configuration and data.

Provides a facade for user-specific paths that follow platform conventions:

- macOS: ~/Library/Application Support/wads/ (config+data), ~/Library/Caches/wads/ (cache)
- Linux: ~/.config/wads/ (config), ~/.local/share/wads/ (data), ~/.cache/wads/ (cache)
- Windows: %APPDATA%/wads/ (config), %LOCALAPPDATA%/wads/ (data+cache)

User preferences are stored in TOML format at config_dir() / “preferences.toml”.
Name candidate files (plain text, one name per line) go in data_dir() / “name_candidates/”.

### Functions

| [`cache_dir`](#wads.user_dirs.cache_dir)()                   | User cache directory for wads.                                              |
|--------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`config_dir`](#wads.user_dirs.config_dir)()                  | User configuration directory for wads.                                      |
| [`data_dir`](#wads.user_dirs.data_dir)()                    | User data directory for wads.                                               |
| [`name_candidates_dir`](#wads.user_dirs.name_candidates_dir)()         | Directory for name candidate files (plain text, one name per line).         |
| [`read_user_preferences`](#wads.user_dirs.read_user_preferences)()       | Read user preferences from preferences.toml.                                |
| [`user_preferences_path`](#wads.user_dirs.user_preferences_path)()       | Path to the user preferences TOML file.                                     |
| [`write_user_preferences`](#wads.user_dirs.write_user_preferences)(prefs) | Write user preferences to preferences.toml, creating directories as needed. |

### wads.user_dirs.cache_dir()

User cache directory for wads.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### wads.user_dirs.config_dir()

User configuration directory for wads.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### wads.user_dirs.data_dir()

User data directory for wads.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### wads.user_dirs.name_candidates_dir()

Directory for name candidate files (plain text, one name per line).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### wads.user_dirs.read_user_preferences()

Read user preferences from preferences.toml.

Returns an empty dict if the file doesn’t exist.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

```pycon
>>> prefs = read_user_preferences()
>>> isinstance(prefs, dict)
True
```

### wads.user_dirs.user_preferences_path()

Path to the user preferences TOML file.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### wads.user_dirs.write_user_preferences(prefs)

Write user preferences to preferences.toml, creating directories as needed.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
