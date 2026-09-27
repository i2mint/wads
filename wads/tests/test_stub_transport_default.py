"""New stubs pass secrets by NAME by default; the JSON transport is opt-in.

i2mint/wads#74 and #88: a stub whose ``secrets:`` block is
``WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}`` serialises the whole
secrets context into a workflow in another repository, which is what a
secret-exfiltration workflow looks like. GitHub's malicious-workflow scanner
holds such runs on NEW repositories: ``action_required``, zero jobs, no log,
not approvable through the API. It was reproduced on four new repos
(tituli, looks, mergeset, acquaint), and switching to the named transport made
the next push start every time. So everything that writes a NEW stub
(``populate``, ``wads-migrate ci-to-stub`` on an inline workflow) now defaults
to named, while an existing stub keeps the transport it already has.
"""

import subprocess

import pytest
import yaml

from wads import github_ci_uv_stub_path
from wads.ci_secrets import render_stub_json_transport, stub_with_named_transport
from wads.ci_trigger import stub_shape
from wads.migration import migrate_ci_to_stub
from wads.populate import populate_pkg_dir

JSON_LINE = render_stub_json_transport().strip()
PYPI_LINE = "PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}"
STUB_TEMPLATE = open(github_ci_uv_stub_path).read()


def _secrets_of(stub_text: str) -> dict:
    return yaml.safe_load(stub_text)["jobs"]["ci"]["secrets"]


def test_migrate_ci_to_stub_defaults_to_the_named_transport():
    stub = migrate_ci_to_stub()
    assert "toJSON(secrets)" not in stub
    assert _secrets_of(stub) == {"PYPI_PASSWORD": "${{ secrets.PYPI_PASSWORD }}"}


def test_the_json_transport_is_still_available_as_an_opt_in():
    stub = migrate_ci_to_stub(transport="json")
    assert stub == STUB_TEMPLATE
    assert JSON_LINE in stub


def test_a_non_stub_workflow_converts_to_the_named_transport():
    assert stub_shape(None)["transport"] == "named"
    assert stub_shape("name: CI\non: [push]\njobs: {}\n")["transport"] == "named"


def test_an_existing_json_stub_keeps_its_transport_on_rerender():
    """Re-rendering never silently changes the transport a repo already runs."""
    assert stub_shape(STUB_TEMPLATE)["transport"] == "json"


def test_the_named_stub_says_why_json_is_not_the_default():
    """A reader who opts into JSON must be told about the held-run failure."""
    stub = migrate_ci_to_stub()
    assert "action_required" in stub
    assert "--transport json" in stub
    assert "legacy" not in stub.lower()


def test_stub_with_named_transport_lists_the_given_names():
    stub = stub_with_named_transport(STUB_TEMPLATE, ["PYPI_PASSWORD", "HF_TOKEN"])
    assert _secrets_of(stub) == {
        "PYPI_PASSWORD": "${{ secrets.PYPI_PASSWORD }}",
        "HF_TOKEN": "${{ secrets.HF_TOKEN }}",
    }


def test_stub_with_named_transport_rejects_a_stub_without_the_json_region():
    with pytest.raises(ValueError, match="JSON transport region"):
        stub_with_named_transport("name: CI\n", ["PYPI_PASSWORD"])


@pytest.fixture
def populated_ci(tmp_path):
    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=pkg_dir, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/myorg/mypkg"],
        cwd=pkg_dir,
        check=True,
    )
    populate_pkg_dir(
        str(pkg_dir),
        description="Test package",
        root_url="https://github.com/myorg",
        author="John Doe",
        version="1.2.3",
        verbose=False,
    )
    return (pkg_dir / ".github" / "workflows" / "ci.yml").read_text()


def test_populate_writes_a_named_transport_stub(populated_ci):
    assert "toJSON(secrets)" not in populated_ci
    assert PYPI_LINE in populated_ci
    assert _secrets_of(populated_ci) == {
        "PYPI_PASSWORD": "${{ secrets.PYPI_PASSWORD }}"
    }
    assert "uses: i2mint/wads/.github/workflows/uv-ci.yml@master" in populated_ci


def _ci_file(tmp_path, text):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    ci = wf / "ci.yml"
    ci.write_text(text)
    return ci


def test_rerendering_an_existing_json_stub_file_keeps_json(tmp_path):
    """The Python API (used by fleet_migrate) must not flip an existing repo."""
    ci = _ci_file(tmp_path, STUB_TEMPLATE)
    assert migrate_ci_to_stub(str(ci)) == STUB_TEMPLATE


def test_converting_an_inline_workflow_file_gives_named(tmp_path):
    ci = _ci_file(tmp_path, "name: CI\non: [push]\njobs:\n  t:\n    runs-on: x\n")
    assert "toJSON(secrets)" not in migrate_ci_to_stub(str(ci))


def test_populate_warns_about_names_a_named_stub_cannot_pass(tmp_path, capsys):
    """An existing pyproject declaring an out-of-superset secret gets the #63 warning."""
    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=pkg_dir, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/myorg/mypkg"],
        cwd=pkg_dir,
        check=True,
    )
    (pkg_dir / "pyproject.toml").write_text(
        '[project]\nname = "mypkg"\nversion = "0.1.0"\n'
        "[tool.wads.ci.env]\nextra_envvars = [\"COSMO_TEST_LEVEL\"]\n"
    )
    populate_pkg_dir(
        str(pkg_dir),
        description="Test package",
        root_url="https://github.com/myorg",
        author="John Doe",
        version="1.2.3",
        verbose=False,
    )
    ci = (pkg_dir / ".github" / "workflows" / "ci.yml").read_text()
    assert "COSMO_TEST_LEVEL: ${{ secrets.COSMO_TEST_LEVEL }}" in ci
    assert "CANNOT START" in capsys.readouterr().err
