#!/usr/bin/env python3
"""Export the pyproject-declared CI environment to ``$GITHUB_ENV``.

This is the run-time half of wads' two-layer secret model (see
:mod:`wads.ci_secrets`). The reusable workflow declares a static *superset* of
secrets (transport); this script decides which of them actually become job
environment variables, driven entirely by ``[tool.wads.ci.env]`` in the
consumer's ``pyproject.toml`` (read via the ``read-ci-config`` action):

* ``defaults``  — literal ``KEY=value`` pairs, always written.
* ``required_envvars`` — must resolve to a non-empty secret, else CI **fails**
  with a precise message.
* ``test_envvars`` — exported if set; a **warning** is emitted if missing.
* ``extra_envvars`` — exported if set; silent if missing.
* ``secret_aliases`` — map ``ENV_VAR -> SECRET_NAME`` for the (rare) case where
  the env var the code reads differs from the GitHub secret name.

The full ``secrets`` context is handed in as JSON via ``toJSON(secrets)`` so this
logic needs **no per-secret enumeration** — only the workflow's static
``on.workflow_call.secrets`` block enumerates (and that is generated from
:data:`wads.ci_secrets.DEFAULT_CI_SECRETS`).

Secret *values* are never printed; only names appear in the summary. Values are
GitHub-registered secrets and are masked in logs regardless.
"""

import json
import os
import sys
from pathlib import Path


def _gh_env_assignment(name: str, value: str) -> str:
    """Return a ``$GITHUB_ENV`` assignment line(s) for ``name=value``.

    Single-line values use ``NAME=value``; multi-line values (e.g. an
    ``SSH_PRIVATE_KEY``) use the documented heredoc form with a delimiter that
    is guaranteed not to occur inside the value.

    >>> _gh_env_assignment("FOO", "bar")
    'FOO=bar'
    >>> print(_gh_env_assignment("KEY", "line1\\nline2"))
    KEY<<__WADS_EOF__
    line1
    line2
    __WADS_EOF__
    """
    if "\n" not in value and "\r" not in value:
        return f"{name}={value}"
    # Pick a delimiter not present in the value.
    delimiter = "__WADS_EOF__"
    while delimiter in value:
        delimiter += "_"
    return f"{name}<<{delimiter}\n{value}\n{delimiter}"


def export_ci_env(
    *,
    required=(),
    test=(),
    extra=(),
    defaults=None,
    aliases=None,
    secrets=None,
    warn=lambda msg: print(msg, file=sys.stderr),
):
    """Compute the env assignments to write, plus any missing-required errors.

    Pure function (no I/O) so it can be unit-tested without GitHub. Returns
    ``(assignments, exported, missing_required, missing_test)`` where
    ``assignments`` is an ordered list of ``$GITHUB_ENV`` lines.

    >>> a, exported, missing_req, missing_test = export_ci_env(
    ...     required=["OPENAI_API_KEY"],
    ...     test=["TAVILY_API_KEY"],
    ...     extra=["UNSET_THING"],
    ...     defaults={"LOG_LEVEL": "DEBUG"},
    ...     secrets={"OPENAI_API_KEY": "sk-xxx", "TAVILY_API_KEY": ""},
    ... )
    >>> exported
    ['LOG_LEVEL', 'OPENAI_API_KEY']
    >>> missing_req
    []
    >>> missing_test
    ['TAVILY_API_KEY']

    A required var with no backing secret is reported (caller should fail CI):

    >>> _, _, missing_req, _ = export_ci_env(
    ...     required=["PYPI_PASSWORD"], secrets={})
    >>> missing_req
    [('PYPI_PASSWORD', 'PYPI_PASSWORD')]

    Aliases let an env var read a differently-named secret:

    >>> a, exported, _, _ = export_ci_env(
    ...     test=["HF_TOKEN"],
    ...     aliases={"HF_TOKEN": "HF_WRITE_TOKEN"},
    ...     secrets={"HF_WRITE_TOKEN": "hf_xxx"})
    >>> exported
    ['HF_TOKEN']
    >>> a
    ['HF_TOKEN=hf_xxx']
    """
    defaults = defaults or {}
    aliases = aliases or {}
    secrets = secrets or {}

    assignments = []
    exported = []
    missing_required = []
    missing_test = []

    # Literal defaults first, so a secret-backed var of the same name wins.
    for key, value in defaults.items():
        assignments.append(_gh_env_assignment(str(key), str(value)))
        exported.append(str(key))

    def _resolve(var_name):
        secret_name = aliases.get(var_name, var_name)
        return secret_name, secrets.get(secret_name) or ""

    seen = set(exported)
    for var_name in required:
        secret_name, value = _resolve(var_name)
        if not value:
            missing_required.append((var_name, secret_name))
            continue
        if var_name not in seen:
            assignments.append(_gh_env_assignment(var_name, value))
            exported.append(var_name)
            seen.add(var_name)

    for var_name in test:
        secret_name, value = _resolve(var_name)
        if not value:
            missing_test.append(var_name)
            continue
        if var_name not in seen:
            assignments.append(_gh_env_assignment(var_name, value))
            exported.append(var_name)
            seen.add(var_name)

    for var_name in extra:
        _, value = _resolve(var_name)
        if value and var_name not in seen:
            assignments.append(_gh_env_assignment(var_name, value))
            exported.append(var_name)
            seen.add(var_name)

    for var_name in missing_test:
        warn(
            f"::warning::[tool.wads.ci.env].test_envvars lists {var_name!r} but "
            f"its backing secret is not set on this repo; tests needing it may be "
            f"skipped or fail."
        )

    return assignments, exported, missing_required, missing_test


def _load_json_env(name: str, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"[ERROR] {name} is not valid JSON: {raw!r}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    """Read inputs from env, write assignments to ``$GITHUB_ENV``, fail if required missing."""
    required = _load_json_env("WADS_ENV_REQUIRED", [])
    test = _load_json_env("WADS_ENV_TEST", [])
    extra = _load_json_env("WADS_ENV_EXTRA", [])
    defaults = _load_json_env("WADS_ENV_DEFAULTS", {})
    aliases = _load_json_env("WADS_ENV_ALIASES", {})
    secrets = _load_json_env("WADS_SECRETS_JSON", {})

    assignments, exported, missing_required, _ = export_ci_env(
        required=required,
        test=test,
        extra=extra,
        defaults=defaults,
        aliases=aliases,
        secrets=secrets,
    )

    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            for line in assignments:
                f.write(line + "\n")
    else:
        print("Warning: GITHUB_ENV not set; not writing assignments", file=sys.stderr)

    if exported:
        print(f"[OK] Exported CI env vars: {', '.join(exported)}")
    else:
        print("[OK] No CI env vars configured to export")

    if missing_required:
        details = "\n".join(
            f"  - env var {var!r} (backed by secret {sec!r}) is required by "
            f"[tool.wads.ci.env].required_envvars but the secret is not set"
            for var, sec in missing_required
        )
        print(
            "[ERROR] Required CI secrets are missing:\n"
            f"{details}\n"
            "Set them on the repo (e.g. `wads-secrets add NAME` or "
            "`gh secret set NAME`), or move them out of required_envvars.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
