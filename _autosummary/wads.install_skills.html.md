# wads.install_skills

Install wads Claude Code skills to ~/.claude/skills/ for global availability.

Skills shipped with wads:

- setup-py-project: AI-assisted Python project creation
- wads-migrate: Migration to modern wads/uv setup

Usage:

```default
wads-install-skills          # Install all skills (symlinks by default)
wads-install-skills --list   # List available skills
wads-install-skills --force  # Overwrite existing skills
wads-install-skills --copy   # Copy files instead of symlinking
```

### Functions

| [`install_skills`](#wads.install_skills.install_skills)(\*[, force, copy, verbose])   | Install wads Claude Code skills to ~/.claude/skills/.   |
|-----------------------------------------------------------------------------------------------|---------------------------------------------------------|
| [`list_available_skills`](#wads.install_skills.list_available_skills)()                      | List skill names bundled with wads.                     |
| [`main`](#wads.install_skills.main)()                                       | CLI entry point for wads-install-skills.                |

### wads.install_skills.install_skills(, force=False, copy=False, verbose=True)

Install wads Claude Code skills to ~/.claude/skills/.

By default, creates symlinks so skills stay in sync with the wads package.
Use `copy=True` to copy files instead (not recommended — updates won’t
propagate, and the skills depend on wads being installed anyway).

* **Parameters:**
  * **force** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, overwrite existing skill entries.
  * **copy** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, copy files instead of creating symlinks.
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, print progress.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  List of installed skill names.

### wads.install_skills.list_available_skills()

List skill names bundled with wads.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.install_skills.main()

CLI entry point for wads-install-skills.
