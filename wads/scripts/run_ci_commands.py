#!/usr/bin/env python3
"""Run the ``[tool.wads.ci.commands]`` ``pre_test`` / ``post_test`` lists in CI.

``read_ci_config`` hands each list over as a JSON array (a GitHub Actions output); the
``run-tests-uv`` action puts it in an environment variable and calls this script with
the variable's name. Each command runs under ``bash -c`` (as ``wads ci-local`` runs it; Git Bash on Windows runners), in order, in the current
directory and environment (the venv is already activated), and the first failure stops
the run with its exit status. An empty or unset list does nothing. Stdlib only.

>>> run_commands(["echo hi"], run=lambda cmd, **kw: 0)
+ echo hi
0
>>> run_commands('["false", "echo unreachable"]', run=lambda cmd, **kw: 1 if cmd == "false" else 0)
+ false
1
"""

import json
import os
import subprocess
import sys
from typing import Callable, Sequence, Union


#: The environment variable naming the bash to use. The action sets it from ``$BASH``:
#: on Windows runners a bare ``bash`` resolves to System32's WSL launcher, not Git Bash.
BASH_ENV_VAR = "WADS_BASH"


def _default_run(command: str, **kwargs) -> int:
    bash = os.environ.get(BASH_ENV_VAR) or "bash"
    return subprocess.run([bash, "-c", command], **kwargs).returncode


def run_commands(
    commands: Union[str, Sequence[str], None],
    *,
    run: Callable[..., int] = _default_run,
) -> int:
    """Run ``commands`` (a list, or its JSON text) in order; return the first non-zero
    exit status, else 0."""
    if isinstance(commands, str):
        commands = json.loads(commands) if commands.strip() else []
    for command in commands or ():
        print(f"+ {command}", flush=True)
        status = run(command)
        if status != 0:
            print(f"command failed (exit {status}): {command}", file=sys.stderr)
            return status
    return 0


def main(argv=None) -> int:
    """``run_ci_commands.py ENV_VAR``: run the JSON list held in that variable."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: run_ci_commands.py ENV_VAR_NAME", file=sys.stderr)
        return 2
    return run_commands(os.environ.get(argv[0], ""))


if __name__ == "__main__":
    sys.exit(main())
