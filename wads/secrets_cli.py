"""``wads-secrets`` — manage the CI secrets/env vars of a wads-managed repo.

A secret becomes usable in CI through two coordinated edits (see
:mod:`wads.ci_secrets` for the model):

1. **pyproject** ``[tool.wads.ci.env]`` — declares the env var (and whether it
   is required), so the reusable workflow exports it into the job environment.
2. **stub transport** — the repo's ``ci.yml`` must *pass* the backing secret to
   the reusable workflow (cross-owner ``secrets: inherit`` is unreliable).

``wads-secrets add`` performs both edits in one step, and can also set the
secret's value on GitHub via ``gh`` — so a single command takes a secret from
"not configured" to "available in CI".

Examples::

    wads-secrets add OPENAI_API_KEY                 # var == secret name
    wads-secrets add HF_TOKEN HF_WRITE_TOKEN         # env var <- aliased secret
    wads-secrets add DB_URL --kind required          # fail CI if unset
    wads-secrets add OPENAI_API_KEY --no-github      # edit files only
    wads-secrets list                                # show configured env vars

Names are forced to ``UPPER_SNAKE`` and value-looking inputs are rejected, so
you can't accidentally commit a secret *value* as a name.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from wads.ci_secrets import (
    DEFAULT_CI_SECRETS,
    InvalidSecretName,
    normalize_secret_name,
)

_KINDS = {
    "required": "required_envvars",
    "test": "test_envvars",
    "extra": "extra_envvars",
}


def _err(msg: str):
    print(f"error: {msg}", file=sys.stderr)


def _repo_from_git(path: str = ".") -> "str | None":
    """Return ``org/repo`` from the git ``origin`` remote of ``path``, or None.

    >>> _repo_from_git("/does/not/exist") is None
    True
    """
    try:
        url = subprocess.check_output(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    # git@github.com:org/repo.git  or  https://github.com/org/repo(.git)
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", url)
    return m.group(1) if m else None


def _load_toml_doc(pyproject_path: Path):
    try:
        import tomlkit
    except ImportError:
        raise SystemExit(
            "wads-secrets needs `tomlkit` to edit pyproject.toml. "
            "Install it with `pip install tomlkit` or `pip install wads[create]`."
        )
    return tomlkit, tomlkit.parse(pyproject_path.read_text())


def _ci_env_table(tomlkit, doc):
    """Get-or-create the ``[tool.wads.ci.env]`` table in ``doc``."""
    tool = doc.setdefault("tool", tomlkit.table())
    wads = tool.setdefault("wads", tomlkit.table())
    ci = wads.setdefault("ci", tomlkit.table())
    env = ci.setdefault("env", tomlkit.table())
    return env


def _existing_bucket(env, var_name: str) -> "str | None":
    """Return the bucket name ('required_envvars'/...) where ``var_name`` already lives."""
    for bucket in _KINDS.values():
        if var_name in list(env.get(bucket, []) or []):
            return bucket
    return None


def add_env_var_to_pyproject(pyproject_path, var_name, secret_name, *, kind="extra"):
    """Add ``var_name`` to ``[tool.wads.ci.env]``; record alias if names differ.

    Returns ``(changed, existing_bucket)``. If the var is already declared,
    makes no change and returns ``(False, <bucket>)``.
    """
    pyproject_path = Path(pyproject_path)
    bucket = _KINDS[kind]
    tomlkit, doc = _load_toml_doc(pyproject_path)
    env = _ci_env_table(tomlkit, doc)

    already = _existing_bucket(env, var_name)
    if already:
        return False, already

    arr = env.get(bucket)
    if arr is None:
        arr = tomlkit.array()
        env[bucket] = arr
    arr.append(var_name)

    if secret_name != var_name:
        aliases = env.get("secret_aliases")
        if aliases is None:
            aliases = tomlkit.table()
            env["secret_aliases"] = aliases
        aliases[var_name] = secret_name

    pyproject_path.write_text(tomlkit.dumps(doc))
    return True, None


def add_secret_to_stub(ci_file, secret_name):
    """Ensure the stub ``ci.yml`` passes ``secret_name`` to the reusable workflow.

    Returns ``(changed, reason)``. ``reason`` explains no-ops (already present,
    not a stub, file missing).
    """
    ci_file = Path(ci_file)
    if not ci_file.is_file():
        return False, "no ci.yml found (skipped transport edit)"
    text = ci_file.read_text()
    if "uv-ci.yml" not in text:
        return False, (
            "ci.yml is not the wads reusable-workflow stub (inline workflow?); "
            "transport not edited — env is driven by [tool.wads.ci.env]"
        )
    if re.search(rf"secrets\.{re.escape(secret_name)}\b", text):
        return False, "already passed in ci.yml"

    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)secrets:\s*$", line)
        if m:
            indent = m.group(1) + "  "
            newline = (
                "" if line.endswith("\n") else "\n"
            )  # ensure secrets: line terminated
            entry = f"{indent}{secret_name}: ${{{{ secrets.{secret_name} }}}}\n"
            lines[i] = line + newline
            lines.insert(i + 1, entry)
            ci_file.write_text("".join(lines))
            return True, "added to ci.yml transport"
    return False, "could not locate a `secrets:` block in ci.yml"


def _gh_available() -> bool:
    try:
        subprocess.check_output(["gh", "--version"], stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def set_github_secret(repo, secret_name, value) -> bool:
    """Set ``secret_name`` on ``repo`` via ``gh secret set``. Returns success."""
    try:
        subprocess.run(
            ["gh", "secret", "set", secret_name, "--repo", repo, "--body", value],
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        _err(f"gh secret set failed: {e}")
        return False


def add(
    var_name,
    secret_name=None,
    *,
    repo=None,
    kind="extra",
    value=None,
    github=True,
    pyproject="pyproject.toml",
    ci_file=".github/workflows/ci.yml",
):
    """Configure a CI secret: declare it in pyproject, pass it in ci.yml, set its value.

    :param var_name: env-var name your code reads (forced to UPPER_SNAKE).
    :param secret_name: GitHub secret backing it (default: same as var_name).
    :param repo: ``org/repo`` to set the secret on (default: git origin here).
    :param kind: ``extra`` (default), ``test``, or ``required``.
    :param value: secret value to push to GitHub (default: ``$VAR_NAME`` in env).
    :param github: also set the value on GitHub via ``gh`` (default True).
    """
    try:
        var_name = normalize_secret_name(var_name)
        secret_name = normalize_secret_name(secret_name) if secret_name else var_name
    except InvalidSecretName as e:
        _err(str(e))
        return 1
    if kind not in _KINDS:
        _err(f"--kind must be one of {sorted(_KINDS)}, got {kind!r}")
        return 1

    changed, existing = add_env_var_to_pyproject(
        pyproject, var_name, secret_name, kind=kind
    )
    if not changed and existing:
        print(
            f"'{var_name}' is already configured in [tool.wads.ci.env].{existing}; "
            "nothing to add."
        )
        return 0
    print(f"✓ pyproject: added {var_name!r} to [tool.wads.ci.env].{_KINDS[kind]}")
    if secret_name != var_name:
        print(f"  ↳ aliased to secret {secret_name!r}")

    stub_changed, reason = add_secret_to_stub(ci_file, secret_name)
    print(f"{'✓' if stub_changed else '·'} transport: {reason}")

    if secret_name not in DEFAULT_CI_SECRETS:
        print(
            f"⚠ {secret_name!r} is not in the wads secret superset "
            f"(wads/ci_secrets.py). The reusable workflow will reject an "
            f"undeclared secret. Add it to DEFAULT_CI_SECRETS via a wads PR, or "
            f"use the inline-workflow escape valve."
        )

    if github:
        _maybe_set_github_secret(repo, secret_name, var_name, value, ci_file)
    return 0


def _maybe_set_github_secret(repo, secret_name, var_name, value, ci_file):
    if not _gh_available():
        print(
            f"· github: `gh` not found; set it manually:\n"
            f"    gh secret set {secret_name} --repo <org/repo>"
        )
        return
    repo = repo or _repo_from_git(
        Path(ci_file).resolve().parents[2] if Path(ci_file).is_file() else "."
    )
    if not repo:
        print(
            f"· github: could not detect repo (no git origin); set it manually:\n"
            f"    gh secret set {secret_name} --repo <org/repo>"
        )
        return
    if value is None:
        value = os.environ.get(var_name) or os.environ.get(secret_name)
    if not value:
        print(
            f"· github: no value for {secret_name!r} (pass --value or export "
            f"${var_name}); set it later with:\n"
            f"    gh secret set {secret_name} --repo {repo}"
        )
        return
    if set_github_secret(repo, secret_name, value):
        print(f"✓ github: set secret {secret_name!r} on {repo}")


def list_(pyproject="pyproject.toml"):
    """List the env vars configured in ``[tool.wads.ci.env]``."""
    from wads.ci_config import CIConfig

    config = CIConfig.from_file(pyproject)
    aliases = config.env_secret_aliases
    buckets = {
        "required": config.env_vars_required,
        "test": config.env_vars_test,
        "extra": config.env_vars_extra,
    }
    any_var = False
    for kind, names in buckets.items():
        for name in names:
            any_var = True
            secret = aliases.get(name, name)
            suffix = f"  (secret: {secret})" if secret != name else ""
            print(f"  [{kind}] {name}{suffix}")
    if config.env_vars_defaults:
        for k, v in config.env_vars_defaults.items():
            print(f"  [default] {k} = {v}")
    if not any_var and not config.env_vars_defaults:
        print("No CI env vars configured in [tool.wads.ci.env].")
    return 0


def superset():
    """Print the wads secret superset (names a stub may pass)."""
    for name in DEFAULT_CI_SECRETS:
        print(name)
    return 0


def main(argv=None):
    """``wads-secrets`` CLI entry point (argparse-based)."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="wads-secrets",
        description="Manage the CI secrets / env vars of a wads-managed repo.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser(
        "add", help="declare a CI secret + pass it in ci.yml + set its value"
    )
    p_add.add_argument(
        "var_name", help="env-var name your code reads (forced UPPER_SNAKE)"
    )
    p_add.add_argument(
        "secret_name",
        nargs="?",
        default=None,
        help="GitHub secret backing it (default: same as VAR_NAME)",
    )
    p_add.add_argument(
        "--repo",
        default=None,
        help="org/repo to set the secret on (default: git origin)",
    )
    p_add.add_argument(
        "--kind",
        choices=sorted(_KINDS),
        default="extra",
        help="env-var bucket (default: extra)",
    )
    p_add.add_argument(
        "--value",
        default=None,
        help="secret value to push to GitHub (default: $VAR_NAME)",
    )
    p_add.add_argument(
        "--no-github",
        dest="github",
        action="store_false",
        help="edit files only; don't call gh",
    )
    p_add.add_argument("--pyproject", default="pyproject.toml")
    p_add.add_argument("--ci-file", dest="ci_file", default=".github/workflows/ci.yml")

    p_list = sub.add_parser("list", help="list configured CI env vars")
    p_list.add_argument("--pyproject", default="pyproject.toml")

    sub.add_parser("superset", help="print the wads secret superset")

    args = parser.parse_args(argv)
    if args.command == "add":
        return add(
            args.var_name,
            args.secret_name,
            repo=args.repo,
            kind=args.kind,
            value=args.value,
            github=args.github,
            pyproject=args.pyproject,
            ci_file=args.ci_file,
        )
    if args.command == "list":
        return list_(pyproject=args.pyproject)
    if args.command == "superset":
        return superset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
