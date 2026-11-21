# wads.scripts.plan_subpackages

Decide which subpackages release now (`[[tool.wads.ci.packages]]`, i2mint/wads#220).

Run by the `plan-subpackages` action in uv-ci’s `sub-plan` job, in a checkout with the
full history and tags. Prints nothing but GitHub Actions outputs:

- `releases`: JSON list of `{package, dir, tag_prefix, version}`, one per subpackage
  that releases (`wads.subpackages.plan_release`);
- `wheel-matrix`: the `sub-wheels` matrix rows (one per release x target, each carrying
  its `version`).

Usage:

```default
python3 -I plan_subpackages.py [REPO_DIR]
```

### Functions

| `main`([argv])                                              |                                                    |
|-------------------------------------------------------------|----------------------------------------------------|
| [`plan`](#wads.scripts.plan_subpackages.plan)(repo) | `(releases, wheel_matrix)` for the repo at `repo`. |

### wads.scripts.plan_subpackages.plan(repo)

`(releases, wheel_matrix)` for the repo at `repo`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)]
