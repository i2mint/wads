"""Tests for wads.project_setup module."""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestNameAvailability:
    """Test name availability checking functions."""

    def test_pypi_project_url(self):
        from wads.project_setup import pypi_project_url

        url = pypi_project_url("wads")
        assert url == "https://pypi.org/project/wads/"

    def test_github_repo_url(self):
        from wads.project_setup import github_repo_url

        url = github_repo_url("myrepo", org="myorg")
        assert url == "https://github.com/myorg/myrepo"

    def test_is_available_on_pypi_existing_package(self):
        """Mock: package exists on PyPI → not available."""
        from wads.project_setup import is_available_on_pypi

        with patch("wads.project_setup.http_get_json", return_value={"info": {}}):
            assert is_available_on_pypi("some-package") is False

    def test_is_available_on_pypi_nonexistent_package(self):
        """Mock: package not on PyPI → available."""
        from wads.project_setup import is_available_on_pypi

        with patch("wads.project_setup.http_get_json", return_value=None):
            assert is_available_on_pypi("nonexistent-package") is True

    def test_check_name_availability_valid_name(self):
        """Mock both PyPI and GitHub checks."""
        from wads.project_setup import check_name_availability

        with (
            patch("wads.project_setup.is_available_on_pypi", return_value=True),
            patch("wads.project_setup.is_available_on_github", return_value=True),
            patch("wads.project_setup._resolve_org", return_value="testorg"),
        ):
            result = check_name_availability("goodname", github=True)

        assert result["name"] == "goodname"
        assert result["valid_pep508"] is True
        assert result["pypi_available"] is True
        assert result["github_available"] is True
        assert result["pypi_url"] is None  # available, so no URL
        assert result["github_url"] is None

    def test_check_name_availability_taken_on_pypi(self):
        from wads.project_setup import check_name_availability

        with (
            patch("wads.project_setup.is_available_on_pypi", return_value=False),
            patch("wads.project_setup.is_available_on_github", return_value=True),
            patch("wads.project_setup._resolve_org", return_value="testorg"),
        ):
            result = check_name_availability("taken", github=True)

        assert result["pypi_available"] is False
        assert result["pypi_url"] == "https://pypi.org/project/taken/"
        assert result["github_available"] is True

    def test_check_name_availability_invalid_name(self):
        from wads.project_setup import check_name_availability

        result = check_name_availability("_invalid_name_")
        assert result["valid_pep508"] is False
        assert result["pypi_available"] is None
        assert result["github_available"] is None

    def test_check_names_multiple(self):
        from wads.project_setup import check_names

        with (
            patch("wads.project_setup.is_available_on_pypi", return_value=True),
            patch("wads.project_setup.is_available_on_github", return_value=True),
            patch("wads.project_setup._resolve_org", return_value="testorg"),
        ):
            results = check_names(["name1", "name2"])

        assert len(results) == 2
        assert results[0]["name"] == "name1"
        assert results[1]["name"] == "name2"


class TestNameCandidates:
    """Test name candidate file operations."""

    def test_parse_name_file(self, tmp_path):
        from wads.project_setup import _parse_name_file

        f = tmp_path / "names.txt"
        f.write_text("# comment\nalpha\n\nbeta\n# another comment\ngamma\n")

        names = _parse_name_file(f)
        assert names == ["alpha", "beta", "gamma"]

    def test_load_name_candidates_from_file(self, tmp_path):
        from wads.project_setup import load_name_candidates

        f = tmp_path / "pool.txt"
        f.write_text("aaa\nbbb\nccc\n")

        names = load_name_candidates(f)
        assert names == ["aaa", "bbb", "ccc"]

    def test_load_name_candidates_deduplicates(self, tmp_path, monkeypatch):
        from wads import project_setup

        pool_dir = tmp_path / "name_candidates"
        pool_dir.mkdir()
        (pool_dir / "a.txt").write_text("alpha\nbeta\n")
        (pool_dir / "b.txt").write_text("beta\ngamma\n")

        monkeypatch.setattr(project_setup, "name_candidates_dir", lambda: pool_dir)

        # Need to also patch the import in list_name_candidate_files
        from wads import user_dirs
        monkeypatch.setattr(user_dirs, "name_candidates_dir", lambda: pool_dir)

        names = project_setup.load_name_candidates()
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" in names
        assert len(names) == 3  # beta not duplicated

    def test_list_name_candidate_files_empty(self, tmp_path, monkeypatch):
        from wads import project_setup, user_dirs

        monkeypatch.setattr(user_dirs, "name_candidates_dir", lambda: tmp_path / "nonexistent")

        # Reimport to pick up the monkeypatch
        files = project_setup.list_name_candidate_files()
        assert files == []


class TestGitHubOperations:
    """Test GitHub-related functions."""

    def test_detect_github_username_from_gh(self):
        from wads.project_setup import detect_github_username

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Logged in to github.com account testuser (oauth_token)"

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", return_value="/usr/bin/gh"):
                username = detect_github_username()
                assert username == "testuser"

    def test_detect_github_username_from_git_config(self):
        from wads.project_setup import detect_github_username

        # gh not installed
        def mock_which(cmd):
            return None if cmd == "gh" else "/usr/bin/git"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "gituser\n"

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("subprocess.run", return_value=mock_result),
        ):
            username = detect_github_username()
            assert username == "gituser"

    def test_require_gh_raises_when_missing(self):
        from wads.project_setup import _require_gh

        with patch("shutil.which", return_value=None):
            with pytest.raises(EnvironmentError, match="GitHub CLI"):
                _require_gh()


class TestCreateMiscDocs:
    """Test dev docs creation."""

    def test_creates_default_sections(self, tmp_path):
        from wads.project_setup import create_misc_docs

        created = create_misc_docs(str(tmp_path))
        assert len(created) == 3

        docs_dir = tmp_path / "misc" / "docs"
        assert docs_dir.exists()
        assert (docs_dir / "research.md").exists()
        assert (docs_dir / "design.md").exists()
        assert (docs_dir / "roadmap.md").exists()

    def test_creates_custom_sections(self, tmp_path):
        from wads.project_setup import create_misc_docs

        created = create_misc_docs(str(tmp_path), sections=["api", "architecture"])
        assert len(created) == 2
        assert (tmp_path / "misc" / "docs" / "api.md").exists()
        assert (tmp_path / "misc" / "docs" / "architecture.md").exists()

    def test_skips_existing_files(self, tmp_path):
        from wads.project_setup import create_misc_docs

        # Create one file first
        docs_dir = tmp_path / "misc" / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "research.md").write_text("existing content")

        created = create_misc_docs(str(tmp_path))
        # Should only create design.md and roadmap.md
        assert len(created) == 2
        # Existing file should be untouched
        assert (docs_dir / "research.md").read_text() == "existing content"


class TestEnsurePypiSecret:
    """``ensure_pypi_secret`` (issue #205). Fake pypirc files only; ``gh`` is faked."""

    FAKE = "pypi-fake-token-for-tests"

    @pytest.fixture
    def gh(self, monkeypatch):
        """Fake ``subprocess.run``: records calls; ``present`` = names ``gh secret list`` returns."""
        import json
        import subprocess

        class Gh:
            calls: list = []
            present: dict = {"repo": [], "org": None}  # org None -> listing fails

        def fake_run(cmd, **kw):
            Gh.calls.append((list(cmd), kw.get("input")))
            if cmd[:3] == ["gh", "secret", "list"]:
                key = "org" if "--org" in cmd else "repo"
                names = Gh.present[key]
                if names is None:
                    raise subprocess.CalledProcessError(1, cmd)
                out = json.dumps([{"name": n} for n in names])
                return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

        Gh.calls = []
        Gh.present = {"repo": [], "org": None}
        monkeypatch.setattr(subprocess, "run", fake_run)
        return Gh

    @pytest.fixture
    def project(self, tmp_path):
        def make(enabled=True):
            pp = tmp_path / "pyproject.toml"
            pp.write_text(
                '[project]\nname = "x"\nversion = "0.0.1"\n'
                f"[tool.wads.ci.publish]\nenabled = {str(enabled).lower()}\n"
            )
            return pp

        return make

    @pytest.fixture
    def pypirc(self, tmp_path):
        rc = tmp_path / ".pypirc"
        rc.write_text(f"[pypi]\nusername = __token__\npassword = {self.FAKE}\n")
        return rc

    def _sets(self, gh):
        return [c for c in gh.calls if c[0][:3] == ["gh", "secret", "set"]]

    def test_sets_secret_from_pypirc_via_stdin(self, gh, project, pypirc):
        from wads.project_setup import ensure_pypi_secret

        out = ensure_pypi_secret("me/pkg", pyproject=project(), environ={}, pypirc=pypirc)
        assert out["status"] == "set"
        (cmd, stdin), = self._sets(gh)
        assert cmd == ["gh", "secret", "set", "PYPI_PASSWORD", "--repo", "me/pkg"]
        assert stdin == self.FAKE.encode()
        assert all(self.FAKE not in " ".join(c) for c, _ in gh.calls)
        assert self.FAKE not in repr(out)

    def test_env_beats_pypirc(self, gh, project, pypirc):
        from wads.project_setup import ensure_pypi_secret

        ensure_pypi_secret(
            "me/pkg", pyproject=project(), environ={"PYPI_PASSWORD": "pypi-env"}, pypirc=pypirc
        )
        assert self._sets(gh)[0][1] == b"pypi-env"

    @pytest.mark.parametrize("where", ["repo", "org"])
    def test_existing_secret_is_left_alone(self, gh, project, pypirc, where):
        from wads.project_setup import ensure_pypi_secret

        gh.present[where] = ["pypi_password"]  # GitHub names are case-insensitive
        out = ensure_pypi_secret("me/pkg", pyproject=project(), environ={}, pypirc=pypirc)
        assert out["status"] == "already_present"
        assert not self._sets(gh)

    def test_publish_disabled_does_nothing(self, gh, project, pypirc):
        from wads.project_setup import ensure_pypi_secret

        out = ensure_pypi_secret(
            "me/pkg", pyproject=project(enabled=False), environ={}, pypirc=pypirc
        )
        assert out["status"] == "publish_disabled"
        assert not gh.calls

    def test_no_token_gives_remedy_and_sets_nothing(self, gh, project, tmp_path):
        from wads.project_setup import ensure_pypi_secret

        out = ensure_pypi_secret(
            "me/pkg", pyproject=project(), environ={}, pypirc=tmp_path / "missing"
        )
        assert out["status"] == "no_token"
        assert "wads-secrets add PYPI_PASSWORD" in out["message"]
        assert not self._sets(gh)

    def test_missing_pyproject(self, gh, tmp_path):
        from wads.project_setup import ensure_pypi_secret

        out = ensure_pypi_secret("me/pkg", pyproject=tmp_path / "nope.toml")
        assert out["status"] == "no_pyproject"

    def test_gh_set_failure_is_reported_without_the_value(self, gh, project, pypirc):
        from wads.project_setup import ensure_pypi_secret

        with patch("wads.secrets_cli.set_github_secret", return_value=False):
            out = ensure_pypi_secret("me/pkg", pyproject=project(), environ={}, pypirc=pypirc)
        assert out["status"] == "failed"
        assert self.FAKE not in repr(out)


class TestSetupProjectPypiSecret:
    def _run(self, tmp_path, outcome, **kw):
        from wads import project_setup as ps

        with (
            patch.object(ps, "repo_exists", return_value=False),
            patch.object(ps, "create_github_repo"),
            patch("wads.populate.populate_pkg_dir"),
            patch.object(ps, "ensure_pypi_secret", return_value=outcome) as ens,
        ):
            res = ps.setup_project(
                "pkg", org="me", proj_rootdir=str(tmp_path / "pkg"), verbose=False, **kw
            )
        return res, ens

    def test_step_recorded_when_set(self, tmp_path):
        res, ens = self._run(tmp_path, {"status": "set", "message": "ok"})
        assert "pypi_secret_set" in res["steps_completed"]
        assert ens.call_args.args[0] == "me/pkg"

    def test_warning_when_no_token(self, tmp_path):
        res, _ = self._run(tmp_path, {"status": "no_token", "message": "remedy"})
        assert "pypi_secret_no_token" in res["warnings"]

    def test_opt_out_and_no_repo(self, tmp_path):
        _, ens = self._run(tmp_path, {"status": "set", "message": ""}, set_pypi_secret=False)
        ens.assert_not_called()
        _, ens = self._run(tmp_path, {"status": "set", "message": ""}, create_repo=False)
        ens.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_check_name_availability_skips_github_by_default():
    from wads.project_setup import check_name_availability

    with (
        patch("wads.project_setup.is_available_on_pypi", return_value=True),
        patch("wads.project_setup.is_available_on_github") as gh,
    ):
        result = check_name_availability("goodname")
    gh.assert_not_called()
    assert result["github_available"] is None
    assert result["npm_available"] is None
