#!/usr/bin/env python3
"""Export the pyproject-declared CI environment to ``$GITHUB_ENV``.

This is the run-time half of wads' two-layer secret model (see
:mod:`wads.ci_secrets`). The reusable workflow receives the caller's secrets
either as named pass-throughs (legacy stubs) or as one double-encoded JSON
blob under ``WADS_CI_SECRETS_JSON`` (modern stubs); this script decides which
values actually become job environment variables, driven entirely by
``[tool.wads.ci.env]`` in the consumer's ``pyproject.toml`` (read via the
``read-ci-config`` action):

* ``defaults``  — literal ``KEY=value`` pairs, always written.
* ``required_envvars`` — must resolve non-empty, else CI **fails** with a
  precise message.
* ``test_envvars`` — exported if set; a **warning** is emitted if missing.
* ``extra_envvars`` — exported if set; silent if missing.
* ``secret_aliases`` — map ``ENV_VAR -> SECRET_NAME`` for the (rare) case where
  the env var the code reads differs from the GitHub secret name.

Each declared name resolves against **secrets first** (named ones merged with
the transport blob) and the caller's **repository variables second** (the
``vars`` context resolves to the caller's repo in a reusable workflow) — so a
non-sensitive value like a test verbosity level can live in a repo variable
instead of being mis-classified as a secret.

Secret *values* are never printed. Values extracted from the transport blob
are not auto-masked by GitHub (only the blob as a whole is), so every
secret-sourced value is re-registered with ``::add-mask::`` (per line, the
documented form for multiline values) before being written to the job env.
"""

import json
import os
import sys
from typing import NamedTuple

# The blob key is a wads-wide constant; keep this script importable standalone
# (it is executed via `python -m` from a pip-installed wads) but don't crash if
# the import graph ever changes — the name is stable.
try:
    from wads.ci_secrets import JSON_TRANSPORT_SECRET
except ImportError:  # pragma: no cover - belt and braces for exotic installs
    JSON_TRANSPORT_SECRET = "WADS_CI_SECRETS_JSON"

# Secrets-context keys that must never be exported as repo env vars: GitHub's
# auto-token (the context spells it `github_token`) and the transport blob.
_NON_EXPORTABLE = frozenset({"github_token", JSON_TRANSPORT_SECRET.lower()})


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


def merge_transported_secrets(secrets):
    """Flatten the secrets mapping, expanding the ``WADS_CI_SECRETS_JSON`` blob.

    The blob is the caller's whole secrets context, serialized by the stub with
    ``toJSON(toJSON(secrets))`` (double-encoded => single-line). A
    single-encoded blob is also accepted. Named entries win over blob entries
    (they are the same caller values anyway), and non-exportable keys (the
    blob itself, ``github_token``) are dropped.

    >>> merged = merge_transported_secrets({
    ...     "WADS_CI_SECRETS_JSON": '"{\\\\n  \\\\"MY_KEY\\\\": \\\\"v1\\\\",\\\\n  \\\\"github_token\\\\": \\\\"t\\\\"\\\\n}"',
    ...     "OPENAI_API_KEY": "sk-named",
    ... })
    >>> sorted(merged)
    ['MY_KEY', 'OPENAI_API_KEY']
    >>> merged["MY_KEY"]
    'v1'

    Malformed blobs are ignored rather than fatal (the named layer still
    works, and required-validation reports any name that failed to resolve):

    >>> merge_transported_secrets({"WADS_CI_SECRETS_JSON": "not json", "A": "x"})
    {'A': 'x'}
    """
    secrets = dict(secrets or {})
    blob = secrets.get(JSON_TRANSPORT_SECRET, "")
    from_blob = {}
    if blob:
        try:
            decoded = json.loads(blob)
            if isinstance(decoded, str):  # double-encoded (the stub default)
                decoded = json.loads(decoded)
            if isinstance(decoded, dict):
                from_blob = {str(k): str(v) for k, v in decoded.items()}
        except (json.JSONDecodeError, TypeError):
            print(
                f"::warning::{JSON_TRANSPORT_SECRET} is not valid JSON; "
                "ignoring the transport blob.",
                file=sys.stderr,
            )
    merged = {**from_blob, **{k: v for k, v in secrets.items() if v}}
    return {
        name: value
        for name, value in merged.items()
        if value and name.lower() not in _NON_EXPORTABLE
    }


class ExportPlan(NamedTuple):
    """What :func:`export_ci_env` decided, ready for :func:`main` to apply."""

    assignments: list  # ordered $GITHUB_ENV lines
    exported: list  # env-var names written, in order
    missing_required: list  # (var_name, source_name) pairs that failed to resolve
    missing_test: list  # test var names that failed to resolve
    mask_values: list  # secret-sourced values to ::add-mask:: before export


def export_ci_env(
    *,
    required=(),
    test=(),
    extra=(),
    defaults=None,
    aliases=None,
    secrets=None,
    vars_=None,
    warn=lambda msg: print(msg, file=sys.stderr),
):
    """Compute the env assignments to write, plus any missing-required errors.

    Pure function (no I/O) so it can be unit-tested without GitHub. Each
    declared name resolves secrets-first, then falls back to the caller's
    repository variables (``vars_``). Secret-sourced values are collected in
    ``mask_values`` for re-masking; variable- and default-sourced values are
    not masked (they are not sensitive by definition).

    >>> plan = export_ci_env(
    ...     required=["OPENAI_API_KEY"],
    ...     test=["TAVILY_API_KEY"],
    ...     extra=["UNSET_THING", "COSMO_TEST_LEVEL"],
    ...     defaults={"LOG_LEVEL": "DEBUG"},
    ...     secrets={"OPENAI_API_KEY": "sk-xxx", "TAVILY_API_KEY": ""},
    ...     vars_={"COSMO_TEST_LEVEL": "3"},
    ... )
    >>> plan.exported
    ['LOG_LEVEL', 'OPENAI_API_KEY', 'COSMO_TEST_LEVEL']
    >>> plan.missing_required
    []
    >>> plan.missing_test
    ['TAVILY_API_KEY']
    >>> plan.mask_values  # only the secret-sourced value
    ['sk-xxx']

    A required var with no backing secret *or* variable is reported (caller
    should fail CI):

    >>> export_ci_env(required=["PYPI_PASSWORD"], secrets={}).missing_required
    [('PYPI_PASSWORD', 'PYPI_PASSWORD')]

    Aliases let an env var read a differently-named secret:

    >>> plan = export_ci_env(
    ...     test=["HF_TOKEN"],
    ...     aliases={"HF_TOKEN": "HF_WRITE_TOKEN"},
    ...     secrets={"HF_WRITE_TOKEN": "hf_xxx"})
    >>> plan.exported
    ['HF_TOKEN']
    >>> plan.assignments
    ['HF_TOKEN=hf_xxx']
    """
    defaults = defaults or {}
    aliases = aliases or {}
    secrets = merge_transported_secrets(secrets)
    vars_ = vars_ or {}

    assignments = []
    exported = []
    missing_required = []
    missing_test = []
    mask_values = []

    # Literal defaults first; a later secret-backed var of the same name is
    # skipped as already-seen, so the committed default is authoritative.
    for key, value in defaults.items():
        assignments.append(_gh_env_assignment(str(key), str(value)))
        exported.append(str(key))

    def _resolve(var_name):
        """Return ``(source_name, value, is_secret)`` for ``var_name``."""
        source_name = aliases.get(var_name, var_name)
        value = secrets.get(source_name) or ""
        if value:
            return source_name, value, True
        return source_name, str(vars_.get(source_name) or ""), False

    seen = set(exported)

    def _export(var_name, value, is_secret):
        if var_name in seen:
            return
        if is_secret:
            mask_values.append(value)
        assignments.append(_gh_env_assignment(var_name, value))
        exported.append(var_name)
        seen.add(var_name)

    for var_name in required:
        source_name, value, is_secret = _resolve(var_name)
        if not value:
            missing_required.append((var_name, source_name))
            continue
        _export(var_name, value, is_secret)

    for var_name in test:
        _, value, is_secret = _resolve(var_name)
        if not value:
            missing_test.append(var_name)
            continue
        _export(var_name, value, is_secret)

    for var_name in extra:
        _, value, is_secret = _resolve(var_name)
        if value:
            _export(var_name, value, is_secret)

    for var_name in missing_test:
        warn(
            f"::warning::[tool.wads.ci.env].test_envvars lists {var_name!r} but "
            f"no backing secret or repo variable is set; tests needing it may "
            f"be skipped or fail."
        )

    return ExportPlan(assignments, exported, missing_required, missing_test, mask_values)


def _load_json_env(name: str, default, *, redact: bool = False):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        if redact:
            # Never echo the raw value: the secrets/vars contexts arrive
            # JSON-re-escaped, a form no registered mask matches.
            print(
                f"[ERROR] {name} is not valid JSON ({e}; length {len(raw)}); "
                f"value withheld — it may contain secrets",
                file=sys.stderr,
            )
        else:
            print(f"[ERROR] {name} is not valid JSON: {raw!r}", file=sys.stderr)
        sys.exit(1)


def _emit_masks(mask_values):
    """Register each secret-sourced value with the runner's log masker.

    Values pulled out of the transport blob are NOT auto-masked (GitHub only
    masks the blob itself), so every line of every value is registered
    explicitly. Harmlessly re-masks named-transport values.

    The runner percent-decodes workflow-command data (``%25``→``%``,
    ``%0A``→newline, ``%0D``→CR), so ``%`` must be escaped or a value
    containing a literal ``%25``/``%0A`` would register the wrong mask string
    and leave the real value unmasked (CR/LF are already handled by the
    per-line split).
    """
    for value in mask_values:
        for line in value.splitlines():
            if line.strip():
                print(f"::add-mask::{line.replace('%', '%25')}")


def main() -> int:
    """Read inputs from env, write assignments to ``$GITHUB_ENV``, fail if required missing."""
    required = _load_json_env("WADS_ENV_REQUIRED", [])
    always_required = _load_json_env("WADS_ENV_ALWAYS_REQUIRED", [])
    test = _load_json_env("WADS_ENV_TEST", [])
    extra = _load_json_env("WADS_ENV_EXTRA", [])
    defaults = _load_json_env("WADS_ENV_DEFAULTS", {})
    aliases = _load_json_env("WADS_ENV_ALIASES", {})
    secrets = _load_json_env("WADS_SECRETS_JSON", {}, redact=True)
    vars_ = _load_json_env("WADS_VARS_JSON", {}, redact=True)

    plan = export_ci_env(
        required=list(required) + [n for n in always_required if n not in required],
        test=test,
        extra=extra,
        defaults=defaults,
        aliases=aliases,
        secrets=secrets,
        vars_=vars_,
    )

    # Masks must be registered before any later step could echo the values.
    _emit_masks(plan.mask_values)

    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            for line in plan.assignments:
                f.write(line + "\n")
    else:
        print("Warning: GITHUB_ENV not set; not writing assignments", file=sys.stderr)

    if plan.exported:
        print(f"[OK] Exported CI env vars: {', '.join(plan.exported)}")
    else:
        print("[OK] No CI env vars configured to export")

    if plan.missing_required:
        details = "\n".join(
            f"  - env var {var!r} (backed by {src!r}) is required but neither a "
            f"secret nor a repo variable of that name is set"
            for var, src in plan.missing_required
        )
        print(
            "[ERROR] Required CI values are missing:\n"
            f"{details}\n"
            "Set a secret (`wads-secrets add NAME` or `gh secret set NAME`), or "
            "for non-sensitive values a repo variable (`gh variable set NAME`), "
            "or move the name out of required_envvars.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
