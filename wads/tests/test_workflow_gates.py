"""Regression guards for two CI wiring bugs (see issue #45 follow-up).

1. A GitHub *expression* (``${{ ... }}``) written literally inside an action
   manifest's input ``description``/``default`` is evaluated at manifest-load
   time. Referencing the ``secrets`` context there crashes the whole action
   ("Unrecognized named-value: 'secrets'"), which took down the validation job.

2. The reusable workflow's ``publish`` job must be gated on the Linux
   ``validation`` matrix — a failing test must block publication. This pins
   that the gate has no status-function escape hatch (``!cancelled()`` /
   ``always()``) and that ``validation`` is a dependency.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIONS_DIR = REPO_ROOT / "actions"
UV_CI = REPO_ROOT / ".github" / "workflows" / "uv-ci.yml"


def test_no_action_input_embeds_github_expression():
    """No action.yml input description/default may contain a `${{ }}` expression."""
    offenders = []
    for action_yml in ACTIONS_DIR.glob("*/action.yml"):
        data = yaml.safe_load(action_yml.read_text())
        for name, spec in (data.get("inputs") or {}).items():
            for field in ("description", "default"):
                val = spec.get(field)
                if isinstance(val, str) and "${{" in val:
                    offenders.append(f"{action_yml.parent.name}:{name}.{field}")
    assert not offenders, (
        "GitHub expressions in action input description/default are evaluated at "
        f"manifest load and can crash the action: {offenders}"
    )


def _jobs(path: Path):
    data = yaml.safe_load(path.read_text())
    return data["jobs"]


def test_publish_is_gated_on_validation():
    publish = _jobs(UV_CI)["publish"]
    needs = publish["needs"]
    assert "validation" in needs and "setup" in needs
    cond = publish["if"]
    # No status function -> implicit success() requires all `needs` to pass,
    # so a failing validation blocks publish. Reject the escape hatches.
    assert "cancelled(" not in cond, "publish must not bypass validation via !cancelled()"
    assert "always(" not in cond, "publish must not run via always()"


def test_windows_validation_is_optional_and_separate():
    jobs = _jobs(UV_CI)
    win = jobs["windows-validation"]
    # Windows is continue-on-error and is NOT a publish dependency, so it never
    # blocks publication.
    assert win.get("continue-on-error") is True
    assert "windows-validation" not in jobs["publish"]["needs"]
