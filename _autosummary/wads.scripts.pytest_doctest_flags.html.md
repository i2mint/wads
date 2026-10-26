# wads.scripts.pytest_doctest_flags

Print the `-o doctest_optionflags=...` pytest argument CI should add, if any.

CI used to pass `-o doctest_optionflags='ELLIPSIS IGNORE_EXCEPTION_DETAIL'`
unconditionally, which overrides the repo’s own pytest configuration (the wads
template ships `["NORMALIZE_WHITESPACE", "ELLIPSIS"]`), so doctests could pass
locally and fail in CI or the reverse. This script is the single source of the
default flags and of the rule: pass the default only when the repo’s pytest config
(`pytest.ini`, `pyproject.toml`, `tox.ini` or `setup.cfg`) does not set
`doctest_optionflags`. Prints the argument (`doctest_optionflags=...`) or
nothing; stdlib only. Used by
`actions/run-tests-uv` and, via `DOCTEST_OPTIONFLAGS`, by `wads ci-local` (which imports the functions).

### Functions

| [`doctest_optionflags_arg`](#wads.scripts.pytest_doctest_flags.doctest_optionflags_arg)([repo, pytest_args])   | The `-o` value to pass, or `''` when the repo's own pytest config wins.               |
|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| `main`([argv])                                                                                  |                                                                                       |
| [`pytest_args_say`](#wads.scripts.pytest_doctest_flags.pytest_args_say)(pytest_args)                   | What a pytest argument string says about the flags: `-o` / `--override-ini` and `-c`. |
| [`repo_sets_doctest_optionflags`](#wads.scripts.pytest_doctest_flags.repo_sets_doctest_optionflags)([repo, ...])     | Whether the pytest config file pytest itself would pick sets `doctest_optionflags`.   |

### wads.scripts.pytest_doctest_flags.doctest_optionflags_arg(repo=None, , pytest_args='')

The `-o` value to pass, or `''` when the repo’s own pytest config wins.

`repo=None` means “do not look”: the default flags are returned. `pytest_args`
(the extra arguments CI also passes) is honoured: an explicit `-o` /
`--override-ini doctest_optionflags=...` there wins and `-c FILE` names the
config file. `--rootdir` does not matter: pytest picks its config file from
`-c` and the test paths, never from the rootdir option.

```pycon
>>> doctest_optionflags_arg()
'doctest_optionflags=ELLIPSIS IGNORE_EXCEPTION_DETAIL'
>>> doctest_optionflags_arg(pytest_args="-o doctest_optionflags=ELLIPSIS")
''
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.scripts.pytest_doctest_flags.pytest_args_say(pytest_args)

What a pytest argument string says about the flags: `-o` / `--override-ini` and `-c`.

```pycon
>>> pytest_args_say("-x -c other.ini")
{'override': False, 'config_file': 'other.ini'}
>>> pytest_args_say("--override-ini=doctest_optionflags=ELLIPSIS")["override"]
True
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.scripts.pytest_doctest_flags.repo_sets_doctest_optionflags(repo='.', , config_file=None)

Whether the pytest config file pytest itself would pick sets `doctest_optionflags`.

Mirrors pytest’s precedence (`pytest.ini`, `pyproject.toml`, `tox.ini`,
`setup.cfg`; the last three only with their pytest section), stdlib only so it
runs under any CI interpreter. `config_file` (`-c FILE`) replaces the search.

```pycon
>>> import tempfile
>>> def check(**files):
...     with tempfile.TemporaryDirectory() as d:
...         for name, text in files.items():
...             Path(d, name.replace("_", ".", 1) if name.startswith("pytest_") else name).write_text(text)
...         return repo_sets_doctest_optionflags(d)
>>> check()
False
>>> py = '[tool.pytest.ini_options]\ndoctest_optionflags = ["ELLIPSIS"]\n'
>>> check(**{"pyproject.toml": py})
True
>>> check(**{"pyproject.toml": "[tool.pytest.ini_options]\nx = 1\n", "setup.cfg": "[tool:pytest]\ndoctest_optionflags = ELLIPSIS\n"})
False
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
