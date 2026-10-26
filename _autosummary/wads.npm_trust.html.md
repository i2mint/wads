# wads.npm_trust

`wads npm-trust`: find a repo’s npm publishers and attach Trusted Publishers.

npm trusted publishing (OIDC, see the `npm-publishing` skill) needs, per package,
one `npm trust github <pkg> --file <caller workflow> --repo <owner>/<repo> [--env E]
--allow-publish -y` (npm >= 11.15, an owner login with 2FA) and the package must already
exist on npm. Doing that by hand across a fleet means finding, for every package, the
workflow that publishes it. This module does the finding, reports it, and optionally
runs the commands:

1. **Discover** ([`discover()`](#wads.npm_trust.discover)): the workflows under `.github/workflows` that publish
   (`npm publish`, `pnpm publish`, `pnpm -r publish`, `changeset publish`,
   `changesets/action` with a `publish:` command, a script such as `pnpm release`
   that runs one of those, or a caller of a wads `npm-ci*.yml` reusable workflow), and
   the non-private packages each publishes (the package in the working directory, every
   workspace member for `-r` / `--workspaces` / changesets, or the `--filter``ed
   ones), with the job's ``environment`. A `--dry-run`, a commented or `echo``ed
   line, or ``npm run publish:docs` is not a publish. For a reusable workflow npm checks
   the *caller’s* filename, which is the file found here.
2. **Report** ([`npm_trust()`](#wads.npm_trust.npm_trust), the default): one row per (package, workflow,
   environment), saying whether the package is on npm or needs a first manual publish;
   a row whose name or environment cannot be resolved (`${{ ... }}`) or is unsafe to
   pass to npm says so and is never run.
3. **Apply** (`apply=True`): run `npm trust github` for each package that is on npm,
   continue past per-package failures, and verify with `npm trust list`.

Everything that touches the world (`npm`, `git`) goes through one injectable
`run` callable, so the discovery and the plan are testable without a network.

```pycon
>>> trust_command(Publisher("@x/a", "o/r", "release.yml", "npm"))
['npm', 'trust', 'github', '@x/a', '--file', 'release.yml', '--repo', 'o/r', '--env', 'npm', '--allow-publish', '-y']
```

### Module Attributes

| [`CALL_TIMEOUT`](#wads.npm_trust.CALL_TIMEOUT)              | Seconds one npm/git call may take (npm may wait on an OTP or a web login).         |
|----------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`WADS_REUSABLE_DEFAULT_DIR`](#wads.npm_trust.WADS_REUSABLE_DEFAULT_DIR) | What wads' reusable npm workflows publish when the caller passes no `package-dir`. |

### Functions

| [`apply_trust`](#wads.npm_trust.apply_trust)(rows, \*[, run])                       | Attach each row's publisher; a failure on one package never stops the others.                                             |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| [`check_publisher`](#wads.npm_trust.check_publisher)(publisher)                         | `publisher` with `problem` set if it must not be passed to `npm trust`.                                                   |
| [`discover`](#wads.npm_trust.discover)([repo_dir, repo, run])                    | Every (package, workflow, environment) the repo's workflows publish to npm.                                               |
| [`github_slug`](#wads.npm_trust.github_slug)([repo_dir, run])                       | `owner/name` of the `origin` remote of `repo_dir`, if it is a GitHub one.                                                 |
| [`has_trust`](#wads.npm_trust.has_trust)(listing, publisher)                      | Whether an `npm trust list` text has an entry naming exactly this repo and workflow.                                      |
| [`is_on_npm`](#wads.npm_trust.is_on_npm)(package, \*[, run])                      | Whether `package` is published (`None`: could not tell, e.g. offline).                                                    |
| [`job_calls`](#wads.npm_trust.job_calls)(job, scripts)                            | The publish calls of a workflow job: its `run` steps, changesets, a wads caller.                                          |
| [`npm_trust`](#wads.npm_trust.npm_trust)([repo, apply, dry_run, ...])             | Find the npm packages `repo` publishes and attach Trusted Publishers (dry run by default).                                |
| [`packages_of`](#wads.npm_trust.packages_of)(root, call)                            | Names of the non-private packages `call` publishes from `root`.                                                           |
| [`preflight`](#wads.npm_trust.preflight)(\*[, run])                               | Problems that would make every attach fail: no npm, not logged in.                                                        |
| [`publish_calls`](#wads.npm_trust.publish_calls)(text[, scripts, directory, \_depth]) | The publish commands in a shell script text, following `cd` and package scripts.                                          |
| [`render_rows`](#wads.npm_trust.render_rows)(rows[, fmt])                           | Rows as an aligned `table`, `tsv` (the fleet rollout's format) or `json`.                                                 |
| `row_fields`(row)                                                                                   |                                                                                                                           |
| [`run_npm_trust`](#wads.npm_trust.run_npm_trust)([repo, apply, dry_run, ...])         | [`npm_trust()`](#wads.npm_trust.npm_trust) with injectable `run` (npm/git) and `out` (printing).        |
| [`subprocess_run`](#wads.npm_trust.subprocess_run)(argv)                               | The default `run`: captured, no stdin, time-limited; a missing tool is rc 127.                                            |
| [`survey`](#wads.npm_trust.survey)(publishers, \*[, run, check_npm])           | [`Row`](#wads.npm_trust.Row) per publisher, asking npm once per package unless `check_npm=False`. |
| [`trust_command`](#wads.npm_trust.trust_command)(publisher)                           | The `npm trust github` call that attaches this publisher.                                                                 |
| [`trust_listing`](#wads.npm_trust.trust_listing)(package, \*[, run])                  | The text of `npm trust list <package>`, or `None` when it cannot be read.                                                 |
| [`workspace_globs`](#wads.npm_trust.workspace_globs)(root)                              | The workspace patterns of the package at `root` (npm/yarn `workspaces` or pnpm).                                          |
| [`workspace_manifests`](#wads.npm_trust.workspace_manifests)(root)                          | `package.json` contents of `root` itself and its workspace members.                                                       |

### Classes

| [`Outcome`](#wads.npm_trust.Outcome)(row, action[, detail, verified])      | What [`apply_trust()`](#wads.npm_trust.apply_trust) did for one row.                                |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| [`PublishCall`](#wads.npm_trust.PublishCall)([directory, everything, filters]) | One publish command: where it runs and which workspace members it covers.                                           |
| [`Publisher`](#wads.npm_trust.Publisher)(package, repo, workflow[, ...])     | One package that one workflow job publishes: what `npm trust github` needs.                                         |
| [`Row`](#wads.npm_trust.Row)(publisher[, on_npm, trusted])             | A [`Publisher`](#wads.npm_trust.Publisher) plus what npm says about it (`on_npm` None = unknown). |

### wads.npm_trust.CALL_TIMEOUT *= 60*

Seconds one npm/git call may take (npm may wait on an OTP or a web login).

### *class* wads.npm_trust.Outcome(row, action, detail='', verified=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What [`apply_trust()`](#wads.npm_trust.apply_trust) did for one row.

### *class* wads.npm_trust.PublishCall(directory='.', everything=False, filters=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One publish command: where it runs and which workspace members it covers.

### *class* wads.npm_trust.Publisher(package, repo, workflow, environment='', problem='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One package that one workflow job publishes: what `npm trust github` needs.

`problem` is set when the row cannot be acted on (unresolved expression, name
npm would read as an option); such rows are reported, never run.

### *class* wads.npm_trust.Row(publisher, on_npm=None, trusted=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A [`Publisher`](#wads.npm_trust.Publisher) plus what npm says about it (`on_npm` None = unknown).

#### *property* actionable *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether `--apply` would run `npm trust github` for this row.

### wads.npm_trust.WADS_REUSABLE_DEFAULT_DIR *= {'npm-ci-monorepo.yml': '.', 'npm-ci.yml': 'js'}*

What wads’ reusable npm workflows publish when the caller passes no `package-dir`.

### wads.npm_trust.apply_trust(rows, \*, run=<function subprocess_run>)

Attach each row’s publisher; a failure on one package never stops the others.

Rows with a problem, not on npm, or of unknown state are skipped with the reason,
rows that already carry the trust are left alone, and a successful attach is
verified with `npm trust list`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Outcome`](#wads.npm_trust.Outcome)]

### wads.npm_trust.check_publisher(publisher)

`publisher` with `problem` set if it must not be passed to `npm trust`.

* **Return type:**
  [`Publisher`](#wads.npm_trust.Publisher)

### wads.npm_trust.discover(repo_dir='.', \*, repo=None, run=<function subprocess_run>)

Every (package, workflow, environment) the repo’s workflows publish to npm.

`repo` is the `owner/name` slug; `None` reads it from the `origin` remote
(see [`github_slug()`](#wads.npm_trust.github_slug)), falling back to `'?/?'`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Publisher`](#wads.npm_trust.Publisher)]

### wads.npm_trust.github_slug(repo_dir='.', \*, run=<function subprocess_run>)

`owner/name` of the `origin` remote of `repo_dir`, if it is a GitHub one.

```pycon
>>> fake = lambda argv: subprocess.CompletedProcess(argv, 0, "git@github.com:i2mint/wads.git\n", "")
>>> github_slug(".", run=fake)
'i2mint/wads'
```

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.npm_trust.has_trust(listing, publisher)

Whether an `npm trust list` text has an entry naming exactly this repo and workflow.

Whole tokens only, so `o/rr` or `release.yml.bak` never stand in for `o/r` or
`release.yml`.

```pycon
>>> p = Publisher("pkg", "o/r", "release.yml")
>>> has_trust("github  o/r  release.yml", p)
True
>>> has_trust("github  o/rr  release.yml.bak", p)
False
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### wads.npm_trust.is_on_npm(package, \*, run=<function subprocess_run>)

Whether `package` is published (`None`: could not tell, e.g. offline).

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`bool`](https://docs.python.org/3/builtins/functions.html#bool)]

### wads.npm_trust.job_calls(job, scripts)

The publish calls of a workflow job: its `run` steps, changesets, a wads caller.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`PublishCall`](#wads.npm_trust.PublishCall)]

### wads.npm_trust.npm_trust(repo='.', , apply=False, dry_run=False, github_repo=None, offline=False, fmt='table')

Find the npm packages `repo` publishes and attach Trusted Publishers (dry run by default).

Prints one row per (package, workflow, environment) with whether the package is on npm
or needs a first manual publish, and the `npm trust github` call for each package
`--apply` would act on. Nothing changes unless `--apply` (`--dry-run` is the
explicit spelling of the default): then each package that is on npm gets its Trusted
Publisher (needs npm >= 11.15 and an owner login with 2FA), failures are reported per
package, and every attach is verified with `npm trust list`. `--offline` skips the
npm lookups; `--github-repo owner/name` overrides the origin remote.

### wads.npm_trust.packages_of(root, call)

Names of the non-private packages `call` publishes from `root`.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     _ = Path(d, "package.json").write_text('{"name": "solo"}')
...     packages_of(Path(d), PublishCall())
['solo']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.npm_trust.preflight(\*, run=<function subprocess_run>)

Problems that would make every attach fail: no npm, not logged in.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.npm_trust.publish_calls(text, scripts=None, , directory='.', \_depth=0)

The publish commands in a shell script text, following `cd` and package scripts.

```pycon
>>> publish_calls("pnpm -r publish --access public")
[PublishCall(directory='.', everything=True, filters=())]
>>> publish_calls("cd packages/a && npm publish")[0].directory
'packages/a'
>>> publish_calls("npm publish --dry-run\n# npm publish\necho npm publish")
[]
>>> publish_calls("pnpm release", {"release": "changeset publish"})[0].everything
True
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`PublishCall`](#wads.npm_trust.PublishCall)]

### wads.npm_trust.render_rows(rows, fmt='table')

Rows as an aligned `table`, `tsv` (the fleet rollout’s format) or `json`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.npm_trust.run_npm_trust(repo='.', \*, apply=False, dry_run=False, github_repo=None, offline=False, fmt='table', run=<function subprocess_run>, out=<built-in function print>)

[`npm_trust()`](#wads.npm_trust.npm_trust) with injectable `run` (npm/git) and `out` (printing).

### wads.npm_trust.subprocess_run(argv)

The default `run`: captured, no stdin, time-limited; a missing tool is rc 127.

* **Return type:**
  [`CompletedProcess`](https://docs.python.org/3/library/subprocess.html#subprocess.CompletedProcess)

### wads.npm_trust.survey(publishers, \*, run=<function subprocess_run>, check_npm=True)

[`Row`](#wads.npm_trust.Row) per publisher, asking npm once per package unless `check_npm=False`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Row`](#wads.npm_trust.Row)]

### wads.npm_trust.trust_command(publisher)

The `npm trust github` call that attaches this publisher.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.npm_trust.trust_listing(package, \*, run=<function subprocess_run>)

The text of `npm trust list <package>`, or `None` when it cannot be read.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.npm_trust.workspace_globs(root)

The workspace patterns of the package at `root` (npm/yarn `workspaces` or pnpm).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.npm_trust.workspace_manifests(root)

`package.json` contents of `root` itself and its workspace members.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]
