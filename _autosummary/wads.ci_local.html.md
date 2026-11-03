# wads.ci_local

Do locally what the wads CI would have done: the same `[tool.wads.ci]`, no Actions minutes.

`wads ci-local` reads the repo’s `pyproject.toml` through [`wads.ci_config.CIConfig`](wads.ci_config.html.md#wads.ci_config.CIConfig),
the object the reusable workflow’s setup job reads, and runs in order:

1. **lint**: `ruff format --check` (reported, never fatal: CI reformats in place and moves
   on), then `ruff check <project>`, both through `uvx` so the repo’s own `[tool.ruff]`
   applies exactly as in CI. Black and mypy too, when enabled.
2. **tests**: for each `python_versions` entry, a fresh `uv` venv in a temporary
   directory, `uv pip install -e .[extras]`, then pytest with the arguments
   `actions/run-tests-uv` builds (coverage, `--doctest-modules` and its option flags,
   one `--ignore` per excluded path, then `pytest_args`).
3. **build**: `uv build` into the temporary directory, never the repo’s `dist/`, so a
   stale artifact can never be uploaded.

With `publish=True` it does what the publish job does in place of the plain build:
format in place, bump the version with `isee` (as CI does), build, `uv publish`,
commit, tag and push. Before any of that it refuses on a dirty tree, a branch other than
the default, a branch behind its remote, or missing PyPI credentials.

Known differences from CI: the developer’s environment passes through to the commands
(minus PyPI credentials, which only the upload step sees, and minus the machine’s install
pins such as `UV_CONSTRAINT`, which hosted CI does not have), where CI exports only the
variables `[tool.wads.ci.env]` declares; `[tool.wads.ops.*]` system packages are not
installed; and lint runs on the tree as it is, where CI formats first.

Each run works in a fresh `wads-ci-local-*` temporary directory that records its owner’s
PID ([`wads.workdirs`](wads.workdirs.html.md#module-wads.workdirs)), and gives pytest a private `--basetemp` inside it, so
concurrent runs never delete each other’s basetemp and the workdir’s removal takes the
basetemp with it. Before starting, a run removes the workdirs killed runs left behind
(older than a few hours, owner no longer running) and refuses, with a plain message, when
the temp filesystem lacks the space or the inodes for one venv per tested Python, rather
than failing partway with `No space left on device` (issue #159).

Every command goes through one `runner` seam. The default runs subprocesses; tests pass
a fake. The default also refuses upload and push steps while pytest is running, so no test
can ever spend or publish.

```pycon
>>> steps = plan_ci_local(".", config=CIConfig({"project": {"name": "pkg"}}))
>>> [s.name for s in steps][:3]
['format check (ruff)', 'lint (ruff)', 'python 3.10: venv']
```

### Module Attributes

| [`WORKDIR_PREFIX`](#wads.ci_local.WORKDIR_PREFIX)            | Prefix of the temporary work directory each run makes (and sweeps when left behind).                                 |
|----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| [`WORKDIR_BYTES_PER_PYTHON`](#wads.ci_local.WORKDIR_BYTES_PER_PYTHON)  | one venv with the project's deps installed (0.5-0.7 GB for a mid-size package), plus headroom.                       |
| [`WORKDIR_INODES_PER_PYTHON`](#wads.ci_local.WORKDIR_INODES_PER_PYTHON) | a workdir held ~22k and a pytest basetemp up to ~82k on a real tmpfs that ran out of inodes, not bytes (issue #159). |

### Functions

| [`ci_local`](#wads.ci_local.ci_local)([repo, publish, dry_run, level])        | Do locally what wads CI would have done, from the repo's [tool.wads.ci] config.                                               |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| [`plan_ci_local`](#wads.ci_local.plan_ci_local)([repo, publish, config, platform]) | Everything `wads ci-local` would run for `repo`, in order, without running it.                                                |
| [`pytest_argv`](#wads.ci_local.pytest_argv)(config, \*[, repo])                  | The pytest arguments `actions/run-tests-uv` builds, in its order.                                                             |
| [`render_plan`](#wads.ci_local.render_plan)(steps)                               | The plan as numbered lines, flagging non-blocking and side-effecting steps.                                                   |
| [`resolve_pypi_token`](#wads.ci_local.resolve_pypi_token)(\*[, environ, pypirc])        | Find a PyPI API token, most specific source first.                                                                            |
| [`run_ci_local`](#wads.ci_local.run_ci_local)([repo, publish, config, ...])       | Run [`plan_ci_local()`](#wads.ci_local.plan_ci_local)'s steps, stop at the first blocking failure, and report. |
| [`steps_env`](#wads.ci_local.steps_env)(source_env, \*[, defaults, withheld])  | The environment the steps run in, and the names of `source_env` it left out.                                                  |
| [`subprocess_runner`](#wads.ci_local.subprocess_runner)(argv, \*, cwd, env[, ...])     | The default runner: really run `argv`, streaming its output.                                                                  |
| [`uv_build_args`](#wads.ci_local.uv_build_args)(\*[, sdist, wheel])                | `uv build` selection flags for `[tool.wads.ci.build]`.                                                                        |
| [`venv_python`](#wads.ci_local.venv_python)(venv, \*[, platform])                | Path of the interpreter inside a venv directory.                                                                              |

### Classes

| [`CILocalReport`](#wads.ci_local.CILocalReport)(project, publish, ...[, ...])   | The outcome of a `wads ci-local` run, rendered the way CI would summarise it.   |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`RunResult`](#wads.ci_local.RunResult)(returncode[, stdout])               | What a runner reports back: the exit code, and stdout when it was captured.     |
| [`Step`](#wads.ci_local.Step)(name[, argv, check, description, ...])   | One thing CI would do: a command (`argv`) or an in-process `check`.             |

### *class* wads.ci_local.CILocalReport(project, publish, trigger_mode, python_versions, outcomes=list(), notes=list(), values=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The outcome of a `wads ci-local` run, rendered the way CI would summarise it.

#### *property* failure *: [Optional](https://docs.python.org/3/library/typing.html#typing.Optional)[[Step](#wads.ci_local.Step)]*

The blocking step that failed, if any.

### *class* wads.ci_local.RunResult(returncode, stdout='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a runner reports back: the exit code, and stdout when it was captured.

### *class* wads.ci_local.Step(name, argv=(), check=None, description='', blocking=True, side_effect='', capture='', env=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One thing CI would do: a command (`argv`) or an in-process `check`.

`argv` and `env` values may hold `<<workdir>>`, `<<version>>`,
`<<default_branch>>` or `<<pypi_token>>`, filled in at run time. A non-`blocking`
failure is reported without stopping the run. `capture` names the context value that
receives the command’s last stdout line. A `check` takes the run context and returns
an error message, or `None` when it passes.

### wads.ci_local.WORKDIR_BYTES_PER_PYTHON *= 1000000000*

one venv
with the project’s deps installed (0.5-0.7 GB for a mid-size package), plus headroom.

* **Type:**
  Free space the temp filesystem needs per tested Python before a run starts

### wads.ci_local.WORKDIR_INODES_PER_PYTHON *= 100000*

a workdir held ~22k and a pytest basetemp up
to ~82k on a real tmpfs that ran out of inodes, not bytes (issue #159).

* **Type:**
  Free inodes it needs per tested Python

### wads.ci_local.WORKDIR_PREFIX *= 'wads-ci-local-'*

Prefix of the temporary work directory each run makes (and sweeps when left behind).

### wads.ci_local.ci_local(repo='.', , publish=False, dry_run=False, level=None)

Do locally what wads CI would have done, from the repo’s [tool.wads.ci] config.

Lint, tests (a fresh uv venv per configured Python) and build. With –publish, the
publish job instead: format, bump version, build, upload to PyPI, commit, tag and push,
refusing on a dirty tree, off the default branch, or without PyPI credentials. With
–dry-run, print the plan and run nothing. `--level validate|deploy` names the same
choice as CI’s on-demand ladder (`deploy` is `--publish`).

### wads.ci_local.plan_ci_local(repo='.', , publish=False, config=None, platform='posix')

Everything `wads ci-local` would run for `repo`, in order, without running it.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Step`](#wads.ci_local.Step)]

### wads.ci_local.pytest_argv(config, , repo=None)

The pytest arguments `actions/run-tests-uv` builds, in its order.

The default `doctest_optionflags` are passed unless `repo`’s own pytest config
sets them (`repo=None`: not checked, defaults passed).

```pycon
>>> pytest_argv(CIConfig({"project": {"name": "pkg"}}))
['--cov=pkg', '--cov-report=term-missing', '--doctest-modules',
 '-o', 'doctest_optionflags=ELLIPSIS IGNORE_EXCEPTION_DETAIL',
 '--ignore=examples', '--ignore=scrap', '-v', '--tb=short']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.ci_local.render_plan(steps)

The plan as numbered lines, flagging non-blocking and side-effecting steps.

The header also says what [`run_ci_local()`](#wads.ci_local.run_ci_local) does before the plan: sweep stale
workdirs and check the temp filesystem has room.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.ci_local.resolve_pypi_token(, environ=None, pypirc=None)

Find a PyPI API token, most specific source first. Returns `(token, source)`.

1. `$PYPI_PASSWORD`, the secret name CI reads;
2. `$UV_PUBLISH_TOKEN`, what `uv publish` itself reads;
3. `~/.pypirc`, section `[pypi]`: `password`, when `username` is `__token__`
   (or absent) or the password is a `pypi-` token.

Token-only, like CI. The token itself is never printed.

```pycon
>>> resolve_pypi_token(environ={"PYPI_PASSWORD": "pypi-x", "UV_PUBLISH_TOKEN": "pypi-y"})
('pypi-x', '$PYPI_PASSWORD')
>>> resolve_pypi_token(environ={}, pypirc="/nonexistent/.pypirc")
(None, '')
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.ci_local.run_ci_local(repo='.', \*, publish=False, config=None, runner=<function subprocess_runner>, environ=None, out=None, keep_workdir=False, workdir_root=None, host_pin_vars=('UV_CONSTRAINT', 'UV_BUILD_CONSTRAINT', 'UV_OVERRIDE', 'PIP_CONSTRAINT'))

Run [`plan_ci_local()`](#wads.ci_local.plan_ci_local)’s steps, stop at the first blocking failure, and report.

The steps run in a fresh work directory under `workdir_root` (default: the system
temp directory), after removing the stale ones killed runs left there and checking
that the filesystem has room for this run (issue #159).

`environ` (default `os.environ`) reaches every step minus the PyPI credentials
(only the upload sees them) and minus `host_pin_vars`, the dev machine’s install
constraints that hosted CI does not have (issue #191).

* **Return type:**
  [`CILocalReport`](#wads.ci_local.CILocalReport)

### wads.ci_local.steps_env(source_env, , defaults=(), withheld=('PYPI_PASSWORD', 'UV_PUBLISH_TOKEN', 'UV_PUBLISH_USERNAME', 'UV_PUBLISH_PASSWORD', 'UV_CONSTRAINT', 'UV_BUILD_CONSTRAINT', 'UV_OVERRIDE', 'PIP_CONSTRAINT'))

The environment the steps run in, and the names of `source_env` it left out.

`source_env` minus `withheld`, then the committed `defaults`, which are
authoritative as in CI’s export-ci-env (so a withheld name a default sets is back,
and is not reported as left out).

```pycon
>>> steps_env({"HOME": "/h", "UV_CONSTRAINT": "/c.txt", "PYPI_PASSWORD": "t"})
({'HOME': '/h'}, ['PYPI_PASSWORD', 'UV_CONSTRAINT'])
>>> steps_env({"UV_CONSTRAINT": "/c.txt"}, defaults={"UV_CONSTRAINT": "/repo.txt"})
({'UV_CONSTRAINT': '/repo.txt'}, [])
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### wads.ci_local.subprocess_runner(argv, , cwd, env, capture=False, side_effect='')

The default runner: really run `argv`, streaming its output.

Refuses outward side effects (upload, push) while pytest is running.

* **Return type:**
  [`RunResult`](#wads.ci_local.RunResult)

### wads.ci_local.uv_build_args(, sdist=True, wheel=True)

`uv build` selection flags for `[tool.wads.ci.build]`.

```pycon
>>> uv_build_args()
[]
>>> uv_build_args(sdist=False)
['--wheel']
>>> uv_build_args(wheel=False)
['--sdist']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.ci_local.venv_python(venv, , platform='posix')

Path of the interpreter inside a venv directory.

```pycon
>>> venv_python("v", platform="posix")
'v/bin/python'
>>> venv_python("v", platform="nt")
'v/Scripts/python.exe'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
