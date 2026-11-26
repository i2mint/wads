"""repo_audit: setup-uv bump advice and the private-package PyPI skip (#257)."""

import urllib.request

from wads import repo_audit as ra

_INLINE_STALE = """name: CI
on: push
jobs:
  t:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: astral-sh/setup-uv@v3
      - uses: i2mint/wads/actions/run-tests-uv@master
"""


def test_private_package_skips_pypi_check(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not hit the network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    rep = ra.Report("r")
    ra.audit_pypi(
        rep,
        {"name": "p", "version": "0.1.0", "classifiers": ["Private :: Do Not Upload"]},
    )
    assert rep.findings == [] and rep.facts["pypi_skipped"] == "private"


def test_any_private_classifier_variant_skips(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: 1 / 0,  # would raise ZeroDivisionError
    )
    rep = ra.Report("r")
    ra.audit_pypi(
        rep, {"name": "p", "version": "1", "classifiers": ["Private :: Internal"]}
    )
    assert rep.findings == []


def test_public_package_still_checks_pypi(monkeypatch):
    calls = []

    def fake(*a, **k):
        calls.append(a)
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    ra.audit_pypi(ra.Report("r"), {"name": "p", "version": "0.1.0"})
    assert calls


def test_stale_pin_finding_mentions_activate_environment(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(_INLINE_STALE)
    rep = ra.Report(str(tmp_path))
    ra.audit_ci(tmp_path, rep)
    stale = [f for f in rep.findings if "stale action pins" in f["summary"]]
    assert stale and "activate-environment: true" in stale[0]["summary"]
