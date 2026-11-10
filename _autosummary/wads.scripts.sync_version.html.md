# wads.scripts.sync_version

Write the release version into the manifests `[tool.wads.ci.version].sync` lists.

Run by the `sync-version` action in uv-ci’s publish jobs, right after the version
bump, so the bump commit carries every manifest (i2mint/wads#210). The `--file`
form writes one `package.json` or `package-lock.json`; the `git-commit`
action’s push-back conflict resolver uses it to put this run’s version on top of
upstream’s file.

Usage:

```default
python3 -I sync_version.py VERSION FILES_JSON [REPO_DIR]
python3 -I sync_version.py --file PATH VERSION
```

### Functions

| [`main`](#wads.scripts.sync_version.main)([argv])   | Sync `VERSION` into each file of `FILES_JSON`; 1 with an error annotation on failure.   |
|-----------------------------------------------------------------|-----------------------------------------------------------------------------------------|

### wads.scripts.sync_version.main(argv=None)

Sync `VERSION` into each file of `FILES_JSON`; 1 with an error annotation on failure.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
