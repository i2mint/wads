"""Stubs pass secrets by NAME by default; the JSON transport is opt-in.

i2mint/wads#74, #88 and #101: a stub whose ``secrets:`` block is
``WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}`` serialises the whole
secrets context into a workflow in another repository, which is what a
secret-exfiltration workflow looks like. GitHub's malicious-workflow scanner
holds such runs: ``action_required``, zero jobs, no log, not approvable
through the API. It was reproduced on several new repos and then on an existing
one (#101), and switching to the named transport made the next push start every
time. So the bundled template is named, and everything that writes a stub
(``populate``, and every re-render: ``wads-migrate ci-to-stub``,
``ci-on-demand``, ``fleet-stub``) writes named, converting a JSON stub, unless
``--transport json`` is asked for or a declared name is outside the superset.
"""

import subprocess

import pytest
import yaml

from wads import github_ci_uv_stub_path
from wads.ci_secrets import (
    NAMED_TRANSPORT_COMMENT,
    render_stub_json_transport,
    stub_with_named_transport,
    stub_with_transport,
)
from wads.ci_trigger import stub_shape
from wads.migration import migrate_ci_to_stub
from wads.populate import populate_pkg_dir

JSON_LINE = render_stub_json_transport().strip()
PYPI_LINE = "PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}"
STUB_TEMPLATE = open(github_ci_uv_stub_path).read()
JSON_STUB = stub_with_transport(STUB_TEMPLATE, transport="json")


def _secrets_of(stub_text: str) -> dict:
    return yaml.safe_load(stub_text)["jobs"]["ci"]["secrets"]


def test_migrate_ci_to_stub_defaults_to_the_named_transport():
    stub = migrate_ci_to_stub()
    assert "toJSON(secrets)" not in stub
    assert _secrets_of(stub) == {"PYPI_PASSWORD": "${{ secrets.PYPI_PASSWORD }}"}


def test_the_bundled_template_is_the_named_stub():
    """The shipped template itself must not carry what GitHub holds (#101)."""
    assert "toJSON" not in STUB_TEMPLATE
    assert NAMED_TRANSPORT_COMMENT + "      " + PYPI_LINE + "\n" in STUB_TEMPLATE
    assert migrate_ci_to_stub() == STUB_TEMPLATE


def test_the_json_transport_is_still_available_as_an_opt_in():
    stub = migrate_ci_to_stub(transport="json")
    assert stub == JSON_STUB
    assert JSON_LINE in stub
    assert _secrets_of(stub) == {
        "WADS_CI_SECRETS_JSON": "${{ toJSON(toJSON(secrets)) }}"
    }
    # The comment describes the transport the stub uses, not the other one.
    assert "Transport (JSON, opt-in)" in stub
    assert "Transport (named)" not in stub


def test_a_non_stub_workflow_converts_to_the_named_transport():
    assert stub_shape(None)["transport"] == "named"
    assert stub_shape("name: CI\non: [push]\njobs: {}\n")["transport"] == "named"


def test_stub_shape_reports_the_transport_a_stub_has():
    assert stub_shape(JSON_STUB)["transport"] == "json"
    assert stub_shape(STUB_TEMPLATE)["transport"] == "named"


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


def test_stub_with_named_transport_rejects_a_non_stub():
    with pytest.raises(ValueError, match="not a wads CI stub"):
        stub_with_named_transport("name: CI\n", ["PYPI_PASSWORD"])


def test_stub_with_transport_round_trips_and_is_idempotent():
    names = ["PYPI_PASSWORD", "HF_TOKEN"]
    named = stub_with_transport(JSON_STUB, names=names)
    assert stub_with_transport(named, names=names) == named
    assert stub_with_transport(named, transport="json") == JSON_STUB
    # Only the secrets region changes: everything after it is kept.
    tail = "    with:\n      project-name: x\n"
    assert stub_with_transport(JSON_STUB + tail, names=names) == named + tail


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


def test_rerendering_an_existing_json_stub_file_converts_it_to_named(tmp_path):
    """An existing repo's JSON stub gets held too (#101), so a re-render fixes it."""
    ci = _ci_file(tmp_path, JSON_STUB)
    assert migrate_ci_to_stub(str(ci)) == STUB_TEMPLATE


def test_rerendering_a_json_stub_keeps_json_when_asked(tmp_path):
    ci = _ci_file(tmp_path, JSON_STUB)
    assert migrate_ci_to_stub(str(ci), transport="json") == JSON_STUB


def test_rerendering_a_json_stub_with_out_of_superset_names_stays_json(
    tmp_path, capsys
):
    """Converting would write a stub that cannot start (#63): keep JSON, say so."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        '[tool.wads.ci.env]\nrequired_envvars = ["MY_CUSTOM_TOKEN"]\n'
    )
    ci = _ci_file(tmp_path, JSON_STUB)
    assert migrate_ci_to_stub(str(ci)) == JSON_STUB
    assert "MY_CUSTOM_TOKEN" in capsys.readouterr().err


def test_rerendering_a_json_stub_passes_the_declared_secrets_by_name(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        '[tool.wads.ci.env]\ntest_envvars = ["OPENAI_API_KEY"]\n'
    )
    ci = _ci_file(tmp_path, JSON_STUB)
    assert _secrets_of(migrate_ci_to_stub(str(ci))) == {
        "PYPI_PASSWORD": "${{ secrets.PYPI_PASSWORD }}",
        "OPENAI_API_KEY": "${{ secrets.OPENAI_API_KEY }}",
    }


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
        '[tool.wads.ci.env]\nextra_envvars = ["COSMO_TEST_LEVEL"]\n'
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


def test_rerendering_json_stub_content_converts_it_to_named():
    """``old_ci`` may be the workflow's content rather than a path."""
    assert migrate_ci_to_stub(JSON_STUB) == STUB_TEMPLATE


def test_auto_transport_falls_back_to_json_for_out_of_superset_secrets(
    tmp_path, capsys
):
    """Converting an EXISTING inline repo must never yield a stub that cannot start.

    A named stub passing a name outside the superset fails at parse time
    (issue #63). Without an explicit ``transport``, fall back to JSON, which
    passes any name, and say so.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        '[tool.wads.ci.env]\nrequired_envvars = ["MY_CUSTOM_TOKEN"]\n'
    )
    ci = _ci_file(tmp_path, "name: CI\non: [push]\njobs:\n  t:\n    runs-on: x\n")
    stub = migrate_ci_to_stub(str(ci))
    assert JSON_LINE in stub
    assert "MY_CUSTOM_TOKEN" in capsys.readouterr().err
    # An explicit choice is still honoured (with the loud #63 warning).
    named = migrate_ci_to_stub(str(ci), transport="named")
    assert "MY_CUSTOM_TOKEN: ${{ secrets.MY_CUSTOM_TOKEN }}" in named


def test_populate_leaves_a_custom_template_alone(tmp_path):
    """Only the bundled stub is rewritten; a custom template is the user's."""
    custom = tmp_path / "my_ci.yml"
    custom.write_text(
        "name: CI\njobs:\n  ci:\n    secrets:\n" + render_stub_json_transport() + "\n"
    )
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
        ci_tpl_path=str(custom),
    )
    ci = (pkg_dir / ".github" / "workflows" / "ci.yml").read_text()
    assert ci == custom.read_text()


def test_the_cli_falls_back_to_json_for_out_of_superset_secrets(tmp_path):
    """`wads-migrate ci-to-stub` on an inline workflow must not write an unstartable stub."""
    import sys

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        '[tool.wads.ci.env]\nrequired_envvars = ["MY_CUSTOM_TOKEN"]\n'
    )
    from wads import github_ci_uv_path

    ci = _ci_file(tmp_path, open(github_ci_uv_path).read())
    out = tmp_path / "out.yml"
    subprocess.run(
        [sys.executable, "-m", "wads.migration", "ci-to-stub", str(ci), "-o", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert JSON_LINE in out.read_text()


def test_on_demand_flip_of_an_inline_repo_never_writes_an_unstartable_stub(tmp_path):
    from wads import github_ci_uv_path
    from wads.ci_trigger import flip_to_on_demand

    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        '[tool.wads.ci.env]\nrequired_envvars = ["MY_CUSTOM_TOKEN"]\n'
    )
    ci = _ci_file(tmp_path, open(github_ci_uv_path).read())
    flip_to_on_demand(tmp_path)
    assert JSON_LINE in ci.read_text()


def test_on_demand_flip_of_a_json_stub_converts_it_to_named(tmp_path):
    from wads.ci_trigger import flip_to_on_demand

    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
    )
    ci = _ci_file(tmp_path, JSON_STUB)
    flip_to_on_demand(tmp_path)
    text = ci.read_text()
    assert "toJSON" not in text
    assert PYPI_LINE in text


_HEAD = "jobs:\n  ci:\n    uses: i2mint/wads/.github/workflows/uv-ci.yml@master\n"


@pytest.mark.parametrize(
    "stub",
    [
        # A comment above `with:` (not above `secrets:`) keeps the inputs.
        _HEAD
        + "    # a note\n    with:\n      project-name: foo\n    secrets:\n"
        + render_stub_json_transport()
        + "\n",
        # Blank and comment lines between entries are part of the block.
        _HEAD
        + "    secrets:\n      PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}\n\n"
        + "    # hand note\n      HF_TOKEN: ${{ secrets.HF_TOKEN }}\n",
        # No trailing newline.
        _HEAD + "    secrets:\n" + render_stub_json_transport(),
    ],
)
def test_stub_with_transport_handles_hand_edited_stubs(stub):
    out = stub_with_transport(stub, names=["PYPI_PASSWORD"])
    job = yaml.safe_load(out)["jobs"]["ci"]
    assert job["secrets"] == {"PYPI_PASSWORD": "${{ secrets.PYPI_PASSWORD }}"}
    if "project-name" in stub:
        assert job["with"] == {"project-name": "foo"}


def test_an_unreadable_pyproject_keeps_a_json_stub(tmp_path, capsys):
    """Converting would silently drop the secrets the repo declares."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
        "[tool.wads.ci.env]\ntest_envvars = 5\n"  # not a list
    )
    ci = _ci_file(tmp_path, JSON_STUB)
    assert migrate_ci_to_stub(str(ci)) == JSON_STUB
    assert "could not be read" in capsys.readouterr().err


def test_stub_with_transport_rejects_an_unknown_transport():
    with pytest.raises(ValueError, match="transport must be"):
        stub_with_transport(STUB_TEMPLATE, transport="inherit")


def test_migrate_ci_to_stub_rejects_an_unknown_transport():
    with pytest.raises(ValueError, match="transport must be"):
        migrate_ci_to_stub(transport="inherit")


def test_is_json_stub_reads_a_path_or_content(tmp_path):
    from wads.migration import _is_json_stub

    ci = _ci_file(tmp_path, JSON_STUB)
    assert _is_json_stub(str(ci))
    assert _is_json_stub(JSON_STUB)
    assert not _is_json_stub(STUB_TEMPLATE)
    assert not _is_json_stub(None)

