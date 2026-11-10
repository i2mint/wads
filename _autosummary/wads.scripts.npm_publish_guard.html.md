# wads.scripts.npm_publish_guard

Refuse an npm publish that would reuse the previous PyPI release’s number (i2mint/wads#210).

Run by the `npm-publish-guard` action in npm-ci’s pack job, before anything is
installed or uploaded. A no-op when the repo has no `pyproject.toml` or its
`[tool.wads.ci.version].sync` lists no manifest in the npm package; otherwise the
decision is `wads.version_sync.npm_publish_refusal`.

Usage:

```default
SUBJECT='<commit subject>' [WORKFLOW_REF=<github.workflow_ref>] \
    python3 -I npm_publish_guard.py PACKAGE_DIR CHANGED_FILES [REPO_DIR]
```

`CHANGED_FILES` holds the push’s changed paths, repo relative, NUL separated
(`git diff --name-only -z`). `WORKFLOW_REF` names the calling npm stub, whose
own file counts as part of the npm package.

### Functions

| [`main`](#wads.scripts.npm_publish_guard.main)([argv])   | 0 when npm may publish, 1 with an error annotation when it must not.   |
|-----------------------------------------------------------------|------------------------------------------------------------------------|

### wads.scripts.npm_publish_guard.main(argv=None)

0 when npm may publish, 1 with an error annotation when it must not.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
