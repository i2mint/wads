"""
Populate a package directory with useful packaging files.

Provides the `populate_pkg_dir` function to add standard files like
README.md, pyproject.toml, and .gitignore.
"""

import os
import shutil
import json
from collections import ChainMap
from urllib.parse import urlparse
from warnings import warn

# from functools import partial
from typing import List, Optional
from wads import (
    pkg_join as wads_join,
    gitlab_ci_tpl_path,
    setup_tpl_path,
    pyproject_toml_tpl_path,
    gitignore_tpl_path,
    gitattributes_tpl_path,
    github_ci_tpl_deploy_path,
    # github_ci_tpl_publish_path,  # old publish path
    wads_configs,
    wads_configs_file,
    # New stuff:
    github_ci_publish_2025_path,
    editorconfig_tpl_path,
    bug_report_tpl_path,
    feature_request_tpl_path,
    pull_request_template_tpl_path,
    dependabot_tpl_path,
)
from wads.util import mk_conditional_logger, git, ensure_no_slash_suffix
from wads.pack import write_configs
from wads.toml_util import write_pyproject_toml, read_pyproject_toml
from wads.licensing import (
    license_body,
    resolve_author,
    substitute_license_placeholders,
)

# from wads.pack_util import write_configs

path_sep = os.path.sep


# --------------------------------------------------------------------------------------
# Tracking and summary helpers for populate
# --------------------------------------------------------------------------------------


class PopulateTracker:
    """Track actions during populate for summary reporting."""

    def __init__(self):
        self.skipped = []  # Files that existed and weren't overwritten
        self.needs_attention = []  # Files with issues or misalignments
        self.added = []  # Files that were created
        self.errors = []  # Files that raised errors

    def skip(self, filename: str):
        """Record a file that was skipped (already exists)."""
        self.skipped.append(filename)

    def attention(self, filename: str, reason: str = None):
        """Record a file that needs attention with optional reason."""
        if reason:
            self.needs_attention.append((filename, reason))
        else:
            self.needs_attention.append(filename)

    def add(self, filename: str):
        """Record a file that was added."""
        self.added.append(filename)

    def error(self, filename: str, error: str):
        """Record a file operation that failed."""
        self.errors.append((filename, error))

    def print_summary(self, verbose=True):
        """Print emoji-based summary of what happened."""
        print("\n" + "=" * 60)
        print("POPULATE SUMMARY")
        print("=" * 60)

        if self.skipped:
            print("\n✓ Skipped (already exists):")
            for item in self.skipped:
                print(f"  • {item}")

        if self.needs_attention:
            print("\n👀 Needs attention:")
            for item in self.needs_attention:
                if isinstance(item, tuple):
                    filename, reason = item
                    print(f"  • {filename}")
                    if verbose:
                        print(f"    └─ {reason}")
                else:
                    print(f"  • {item}")

        if self.added:
            print("\n✅ Added:")
            for item in self.added:
                print(f"  • {item}")

        if self.errors:
            print("\n❌ Errors:")
            for filename, error in self.errors:
                print(f"  • {filename}")
                if verbose:
                    print(f"    └─ {error}")

        print("\n" + "=" * 60)


populate_dflts = wads_configs.get(
    "populate_dflts",
    {
        "description": "There is a bit of an air of mystery around this project...",
        "root_url": None,
        "author": os.environ.get("WADS_DFLT_AUTHOR"),
        "license": "mit",
        "description_file": "README.md",
        "long_description": "file:README.md",
        "long_description_content_type": "text/markdown",
        "keywords": None,
        "install_requires": None,
        "verbose": True,
        "version": "0.0.1",
        "extras_require_testing": [],
        "project_type": "lib",
        "create_docsrc": False,
    },
)


def gen_readme_text(
    name, text="There is a bit of an air of mystery around this project..."
):
    return f"""
# {name}

{text}
"""


def write_pyproject_configs(pkg_dir: str, configs: dict):
    """
    Write pyproject.toml file from template and configs.

    Args:
        pkg_dir: Path to package directory
        configs: Dictionary of configuration values
    """
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomli as tomllib
        except ImportError:
            raise ImportError("tomli package required for Python < 3.11")

    try:
        import tomli_w
    except ImportError:
        raise ImportError("tomli_w package required for writing TOML")

    # Read and parse the template as TOML
    with open(pyproject_toml_tpl_path, "rb") as f:
        data = tomllib.load(f)

    # Prepare the data for substitution
    name = configs.get("name", "mypackage")
    version = configs.get("version", "0.0.1")
    description = configs.get("description", "Package description")
    url = configs.get("url", "")
    license_name = configs.get("license", "mit")

    # Warn if URL is missing or empty
    if not url:
        warn(
            f"No URL provided for package '{name}'. "
            f"PyPI requires a URL for package uploads. "
            f"Please add 'url' or 'root_url' to your configuration."
        )

    # Update the parsed data with actual values
    data["project"]["name"] = name
    data["project"]["version"] = version
    data["project"]["description"] = description

    # Handle URLs - update homepage and repository
    if url:
        if "urls" not in data["project"]:
            data["project"]["urls"] = {}
        data["project"]["urls"]["Homepage"] = url
        data["project"]["urls"]["Repository"] = url

    # Update license using inline table syntax
    data["project"]["license"] = {"text": license_name}

    # Add optional fields if present
    if configs.get("keywords"):
        keywords = configs["keywords"]
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",")]
        data["project"]["keywords"] = keywords

    if configs.get("author"):
        authors = configs["author"]
        if isinstance(authors, str):
            data["project"]["authors"] = [{"name": authors}]
        elif isinstance(authors, list):
            data["project"]["authors"] = [
                {"name": a} if isinstance(a, str) else a for a in authors
            ]

    if configs.get("install_requires"):
        deps = configs["install_requires"]
        if isinstance(deps, str):
            deps = [d.strip() for d in deps.split(",") if d.strip()]
        data["project"]["dependencies"] = deps

    # Write the pyproject.toml
    pyproject_path = os.path.join(pkg_dir, "pyproject.toml")
    with open(pyproject_path, "wb") as f:
        tomli_w.dump(data, f)


# TODO: Function way to long -- break it up
# TODO: Add a `defaults_from` in **configs that allows one to have several named defaults in wads_configs_file
def populate_pkg_dir(
    pkg_dir,
    version: str = populate_dflts["version"],
    description: str = populate_dflts["description"],
    *,
    root_url: str | None = populate_dflts["root_url"],
    author: str | None = populate_dflts["author"],
    license: str = populate_dflts["license"],
    description_file: str = populate_dflts["description_file"],
    keywords: list | None = populate_dflts["keywords"],
    install_requires: list | None = populate_dflts["install_requires"],
    long_description=populate_dflts["long_description"],
    long_description_content_type=populate_dflts["long_description_content_type"],
    include_pip_install_instruction_in_readme=True,
    verbose: bool = populate_dflts["verbose"],
    overwrite: list = (),
    defaults_from: str | None = None,
    create_docsrc: bool = populate_dflts.get("create_docsrc", False),
    skip_docsrc_gen=False,
    skip_ci_def_gen=False,
    migrate: bool = False,
    create_gitattributes: bool = True,
    create_setup_py: bool = False,
    create_community_files: bool = False,
    version_control_system=None,
    ci_def_path=None,
    ci_tpl_path=None,
    project_type=populate_dflts["project_type"],
    **configs,
):
    """Populate project directory root with useful packaging files, if they're missing.

    >>> from wads.populate import populate_pkg_dir
    >>> import os  # doctest: +SKIP
    >>> name = 'wads'  # doctest: +SKIP
    >>> pkg_dir = f'/D/Dropbox/dev/p3/proj/i/{name}'  # doctest: +SKIP
    >>> populate_pkg_dir(pkg_dir,  # doctest: +SKIP
    ...                  description='Tools for packaging',
    ...                  root_url=f'https://github.com/i2mint',
    ...                  author='OtoSense')

    :param pkg_dir: The relative or absolute path of the working directory. Defaults to '.'.
    :type pkg_dir: str, optional
    :param version: The desired version
    :param description: Short description of project
    :param root_url: Root url of the code repository (not the url of the project, but one level up that!)
    :param author: Author of the package
    :param license: License name for the package (should be recognized by pypi). Default is 'mit'
    :param description_file: File name containing a description of the project. Default is 'README.md'
    :param keywords: Keywords to include in pypi publication
    :param install_requires: The (pip install) names of of the packages required to install the package we're generating
    :param long_description: Text of the long description. Default is "file:README.md" (takes contents of README.md)
    :param long_description_content_type: How to parse the long_description. Default is "text/markdown"
    :param verbose: Set to True if you want to log extra information during the process. Defaults to False.
    :type verbose: bool, optional: Whether to print a lot of stuff as project is being populated.
    :param default_from: Name of field to look up in wads_configs to get defaults from,
        or 'user_input' to get it from user input.
    :param skip_docsrc_gen: Skip the generation of documentation stuff
    :param create_docsrc: If True, create and populate a `docsrc/` directory (overrides skip_docsrc_gen).
    :param skip_ci_def_gen: Skip the generation of the CI stuff
    :param create_setup_py: If True, create setup.py for backward compatibility (default: False, not needed with Hatchling).
    :param create_community_files: If True, create community files (.editorconfig, issue/PR templates, dependabot.yml). Default: False.
    :param migrate: If True, migrate existing setup.cfg to pyproject.toml and old CI to new CI format.
        Will fail if old CI has unmappable content.
    :param create_gitattributes: If True (default), create a .gitattributes file with '*.ipynb linguist-documentation'.
    :param version_control_system: 'github' or 'gitlab' (will TRY to be resolved from root url if not given)
    :param ci_def_path: Path of the CI definition
    :param ci_tpl_path: Pater of the template definition
    :param configs: Extra configurations
    :return:

    """

    # If the pkg_dir is a github url, then we'll clone it and populate the
    # resulting folder
    if pkg_dir.startswith("https://github.com") or pkg_dir.startswith("git@github.com"):
        url = pkg_dir
        return populate_proj_from_url(url)

    args_defaults = dict()
    if defaults_from is not None:
        if defaults_from == "user_input":  # TODO: Implement!
            args_defaults = dict()  # ... and then fill with user input
            raise NotImplementedError("Not immplemented yet")  # TODO: Implement
        else:
            try:
                wads_configs = json.load(open(wads_configs_file))
                args_defaults = wads_configs[defaults_from]
            except KeyError:
                raise KeyError(
                    f"{wads_configs_file} json didn't have a {defaults_from} field"
                )

    if isinstance(overwrite, str):
        overwrite = {overwrite}
    else:
        overwrite = set(overwrite)

    _clog = mk_conditional_logger(condition=verbose, func=print)
    tracker = PopulateTracker()
    pkg_dir = os.path.abspath(os.path.expanduser(pkg_dir))
    assert os.path.isdir(pkg_dir), f"{pkg_dir} is not a directory"
    pkg_dir = ensure_no_slash_suffix(pkg_dir)
    name = os.path.basename(pkg_dir)
    pjoin = lambda *p: os.path.join(pkg_dir, *p)

    if name not in os.listdir(pkg_dir):
        f = pjoin(name)
        _clog(f"... making directory {pkg_dir}")
        os.mkdir(f)
    if "__init__.py" not in os.listdir(pjoin(name)):
        f = pjoin(name, "__init__.py")
        _clog(f"... making an empty {f}")
        with open(f, "w") as fp:
            fp.write("")

    # Note: Overkill since we just made those things...
    if name not in os.listdir(pkg_dir) or "__init__.py" not in os.listdir(pjoin(name)):
        raise RuntimeError(
            "You should have a {name}/{name}/__init__.py structure. You don't."
        )

    # Check for existing config files (prioritize pyproject.toml over setup.cfg)
    if os.path.isfile(pjoin("pyproject.toml")):
        pass  # Will be handled later
    elif os.path.isfile(pjoin("setup.cfg")):
        _clog("... found existing setup.cfg (consider migrating to pyproject.toml)")
        pass

    kwargs = dict(
        version=version,
        description=description,
        root_url=root_url,
        author=author,
        license=license,
        description_file=description_file,
        long_description=long_description,
        long_description_content_type=long_description_content_type,
        keywords=keywords,
        install_requires=install_requires,
    )
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    # configs = dict(name=name, **configs, **kwargs, **args_defaults)
    # configs = dict(name=name, **args_defaults, **configs, **kwargs)
    configs = dict(ChainMap(dict(name=name), kwargs, configs, args_defaults))

    kwargs["description-file"] = kwargs.pop("description_file", "")

    assert configs.get("name", name) == name, (
        f"There's a name conflict. pkg_dir tells me the name is {name}, "
        f"but configs tell me its {configs.get('name')}"
    )
    _ensure_url_from_url_root_and_name(configs)
    configs["display_name"] = configs.get("display_name", configs["name"])

    def should_update(resource_name):
        return (resource_name in overwrite) or (
            not os.path.isfile(pjoin(resource_name))
        )

    def save_txt_to_pkg(resource_name, content):
        target_path = pjoin(resource_name)
        assert not os.path.isfile(target_path), f"{target_path} exists already"
        _clog(f"... making a {resource_name}")
        with open(pjoin(resource_name), "w") as fp:
            fp.write(content)

    if should_update(".gitignore"):
        shutil.copy(gitignore_tpl_path, pjoin(".gitignore"))
        tracker.add(".gitignore")
    else:
        tracker.skip(".gitignore")

    if create_gitattributes and should_update(".gitattributes"):
        _clog("... making a .gitattributes")
        shutil.copy(gitattributes_tpl_path, pjoin(".gitattributes"))
        tracker.add(".gitattributes")
    elif create_gitattributes:
        tracker.skip(".gitattributes")

    # Create community files only if requested
    if create_community_files:
        # Create .editorconfig for consistent formatting
        if should_update(".editorconfig"):
            shutil.copy(editorconfig_tpl_path, pjoin(".editorconfig"))
            tracker.add(".editorconfig")
        else:
            tracker.skip(".editorconfig")

        # Create GitHub issue templates
        github_issue_template_dir = pjoin(".github", "ISSUE_TEMPLATE")
        os.makedirs(github_issue_template_dir, exist_ok=True)

        if should_update(pjoin(github_issue_template_dir, "bug_report.md")):
            shutil.copy(
                bug_report_tpl_path, pjoin(github_issue_template_dir, "bug_report.md")
            )
            tracker.add(".github/ISSUE_TEMPLATE/bug_report.md")
        else:
            tracker.skip(".github/ISSUE_TEMPLATE/bug_report.md")

        if should_update(pjoin(github_issue_template_dir, "feature_request.md")):
            shutil.copy(
                feature_request_tpl_path,
                pjoin(github_issue_template_dir, "feature_request.md"),
            )
            tracker.add(".github/ISSUE_TEMPLATE/feature_request.md")
        else:
            tracker.skip(".github/ISSUE_TEMPLATE/feature_request.md")

        # Create PR template
        if should_update(pjoin(".github", "PULL_REQUEST_TEMPLATE.md")):
            shutil.copy(
                pull_request_template_tpl_path,
                pjoin(".github", "PULL_REQUEST_TEMPLATE.md"),
            )
            tracker.add(".github/PULL_REQUEST_TEMPLATE.md")
        else:
            tracker.skip(".github/PULL_REQUEST_TEMPLATE.md")

        # Create Dependabot config
        if should_update(pjoin(".github", "dependabot.yml")):
            shutil.copy(dependabot_tpl_path, pjoin(".github", "dependabot.yml"))
            tracker.add(".github/dependabot.yml")
        else:
            tracker.skip(".github/dependabot.yml")

    if project_type == "app":
        if should_update("requirements.txt"):
            with open(pjoin("requirements.txt"), "w") as f:
                pass
            tracker.add("requirements.txt")
        else:
            tracker.skip("requirements.txt")

    else:  # project_type == 'lib' or None
        if should_update("pyproject.toml"):
            setup_cfg_path = pjoin("setup.cfg")

            # Check if setup.cfg exists (with or without migrate flag)
            if os.path.isfile(setup_cfg_path):
                _clog("... found setup.cfg, migrating to pyproject.toml")
                from wads.migration import migrate_setuptools_to_hatching

                try:
                    # Migrate setup.cfg to pyproject.toml
                    pyproject_content = migrate_setuptools_to_hatching(
                        setup_cfg_path, defaults=configs
                    )

                    # Write the migrated content
                    with open(pjoin("pyproject.toml"), "w") as f:
                        f.write(pyproject_content)
                    tracker.add("pyproject.toml")
                    _clog("✅ Migrated setup.cfg → pyproject.toml")
                except Exception as e:
                    _clog(
                        f"... migration failed ({e}), falling back to template-based creation"
                    )
                    tracker.error("pyproject.toml", f"Migration failed: {e}")
                    if "pkg-dir" in configs:
                        del configs["pkg-dir"]
                    write_pyproject_configs(pjoin(""), configs)
                    tracker.add("pyproject.toml")
            else:
                _clog("... making a 'pyproject.toml'")
                if "pkg-dir" in configs:
                    del configs["pkg-dir"]
                write_pyproject_configs(pjoin(""), configs)
                tracker.add("pyproject.toml")
        else:
            tracker.skip("pyproject.toml")
            # If pyproject.toml exists but URL is missing/empty, update it
            if configs.get("url"):
                from wads.toml_util import update_project_url, read_pyproject_toml

                existing_data = read_pyproject_toml(pjoin(""))
                existing_url = (
                    existing_data.get("project", {}).get("urls", {}).get("Homepage", "")
                )
                if not existing_url:
                    _clog(
                        f"... updating URL in existing pyproject.toml to {configs['url']}"
                    )
                    update_project_url(pjoin(""), configs["url"])
        # setup.py is no longer needed with Hatchling, but can be created for backward compatibility
        if create_setup_py and should_update("setup.py"):
            shutil.copy(setup_tpl_path, pjoin("setup.py"))
            tracker.add("setup.py")
        elif not create_setup_py and os.path.isfile(pjoin("setup.py")):
            # If setup.py exists but we're not creating it, just skip it
            tracker.skip("setup.py")

    if should_update("LICENSE"):
        _license_body = license_body(configs["license"])

        # Resolve author for license placeholder substitution
        # Try to get authors from existing pyproject.toml if it exists
        pyproject_authors = None
        if os.path.isfile(pjoin("pyproject.toml")):
            try:
                pyproject_data = read_pyproject_toml(pjoin(""))
                pyproject_authors = pyproject_data.get("project", {}).get("authors")
            except Exception:
                pass  # If reading fails, continue without pyproject authors

        resolved_author = resolve_author(
            author=configs.get("author"),
            pyproject_authors=pyproject_authors,
            url=configs.get("url"),
        )

        # Substitute placeholders in license
        _license_body = substitute_license_placeholders(
            _license_body,
            author=resolved_author,
        )

        save_txt_to_pkg("LICENSE", _license_body)
        tracker.add("LICENSE")
    else:
        tracker.skip("LICENSE")

    if should_update("README.md"):
        readme_text = gen_readme_text(name, configs.get("description"))
        if include_pip_install_instruction_in_readme:
            readme_text += f"\n\nTo install:\t```pip install {name}```\n"
        save_txt_to_pkg("README.md", readme_text)
        tracker.add("README.md")
    else:
        tracker.skip("README.md")

    if project_type is None or project_type == "lib":
        # Respect both the new `create_docsrc` flag and the existing
        # `skip_docsrc_gen` for backward compatibility. `skip_docsrc_gen`
        # takes precedence when True. By default `create_docsrc` is False
        # so docsrc won't be created unless explicitly requested.
        if skip_docsrc_gen:
            _clog("... skipping docsrc generation because skip_docsrc_gen=True")
        elif create_docsrc:
            # TODO: Figure out epythet and wads relationship -- right now, there's a reflexive dependency
            try:
                from epythet.setup_docsrc import make_docsrc
            except ImportError:
                raise ImportError(
                    "Documentation operations require epythet. "
                    "Install wads with documentation support: pip install wads[docs]"
                )

            warn(
                "Documentation generation with epythet is deprecated. "
                "Install wads with documentation support: pip install wads[docs]",
                DeprecationWarning,
                stacklevel=2,
            )

            make_docsrc(pkg_dir, verbose=verbose)
        else:
            _clog("... not creating docsrc by default (create_docsrc=False)")

    if not skip_ci_def_gen:
        root_url = root_url or _get_root_url_from_pkg_dir(pkg_dir)
        version_control_system = (
            version_control_system or _url_to_version_control_system(root_url)
        )
        ci_def_path, ci_tpl_path = _resolve_ci_def_and_tpl_path(
            ci_def_path, ci_tpl_path, pkg_dir, version_control_system, project_type
        )
        if should_update(ci_def_path):
            assert name in ci_def_path and name in _get_pkg_url_from_pkg_dir(pkg_dir), (
                f"The name wasn't found in both the ci_def_path AND the git url, so I'm going to be safe and do nothing"
            )

            # Check if we should migrate old CI to new format
            if migrate and version_control_system == "github":
                old_ci_path = pjoin(".github/workflows/ci.yml")
                if os.path.isfile(old_ci_path):
                    _clog(f"... migrating old CI from {old_ci_path} to {ci_def_path}")
                    from wads.migration import migrate_github_ci_old_to_new

                    try:
                        new_ci_content = migrate_github_ci_old_to_new(
                            old_ci_path, defaults={"project_name": name}
                        )
                        os.makedirs(os.path.dirname(ci_def_path), exist_ok=True)
                        with open(ci_def_path, "w") as f:
                            f.write(new_ci_content)
                        _clog(f"... successfully migrated CI to {ci_def_path}")
                        tracker.add(ci_def_path.replace(pkg_dir + os.sep, ""))
                    except Exception as e:
                        tracker.error(
                            ci_def_path.replace(pkg_dir + os.sep, ""),
                            f"Migration failed: {e}",
                        )
                        raise RuntimeError(
                            f"Failed to migrate CI file {old_ci_path}: {e}\n"
                            f"The old CI may contain configurations that cannot be automatically migrated."
                        ) from e
                else:
                    # No old CI to migrate, create new one from template
                    user_email = kwargs.get("user_email", "thorwhalen1@gmail.com")
                    _add_ci_def(
                        ci_def_path, ci_tpl_path, root_url, name, _clog, user_email
                    )
                    tracker.add(ci_def_path.replace(pkg_dir + os.sep, ""))
            else:
                # Not migrating or not github, use template
                user_email = kwargs.get("user_email", "thorwhalen1@gmail.com")
                _add_ci_def(ci_def_path, ci_tpl_path, root_url, name, _clog, user_email)
                tracker.add(ci_def_path.replace(pkg_dir + os.sep, ""))
        else:
            tracker.skip(ci_def_path.replace(pkg_dir + os.sep, ""))

    # -------------------------------------------------------------------------
    # Compare existing files against templates and add attention items
    # -------------------------------------------------------------------------
    from wads.config_comparison import (
        compare_pyproject_toml,
        compare_setup_cfg,
        compare_ci_workflow,
    )

    # Check pyproject.toml alignment
    pyproject_path = pjoin("pyproject.toml")
    if os.path.isfile(pyproject_path) and "pyproject.toml" not in tracker.added:
        _clog("\n👀 Checking pyproject.toml alignment with template...")
        comparison = compare_pyproject_toml(pyproject_path, project_name=name)
        if comparison.get("needs_attention"):
            reasons = []
            if comparison.get("missing_sections"):
                reasons.append(
                    f"Missing sections: {', '.join(comparison['missing_sections'][:3])}"
                    + ("..." if len(comparison["missing_sections"]) > 3 else "")
                )
            for rec in comparison.get("recommendations", []):
                reasons.append(rec)

            tracker.attention("pyproject.toml", " | ".join(reasons))
            if verbose:
                _clog("  Issues found:")
                for rec in comparison.get("recommendations", []):
                    _clog(f"    • {rec}")

    # Check setup.cfg (warn about deprecation)
    setup_cfg_path = pjoin("setup.cfg")
    if os.path.isfile(setup_cfg_path):
        _clog("\n👀 Found setup.cfg (deprecated)...")
        comparison = compare_setup_cfg(setup_cfg_path)
        if comparison.get("should_migrate"):
            tracker.attention(
                "setup.cfg", "Deprecated format. Run: populate . --migrate"
            )
            if verbose:
                _clog("  Consider migrating to pyproject.toml")
                _clog("  Run: populate . --migrate")

    # Check MANIFEST.in (warn about migration needed)
    manifest_path = pjoin("MANIFEST.in")
    if os.path.isfile(manifest_path):
        from wads.config_comparison import compare_manifest_in

        _clog("\n👀 Found MANIFEST.in (needs Hatchling migration)...")
        manifest_comparison = compare_manifest_in(manifest_path)
        if manifest_comparison.get("needs_migration"):
            # If migrate flag is set, automatically add to pyproject.toml
            if migrate and manifest_comparison.get("hatchling_config"):
                pyproject_path = pjoin("pyproject.toml")
                if os.path.isfile(pyproject_path):
                    try:
                        # Read existing pyproject.toml
                        from wads.toml_util import read_pyproject_toml
                        import tomli_w

                        existing_data = read_pyproject_toml(pjoin(""))

                        # Parse the hatchling config suggestion
                        hatchling_lines = manifest_comparison["hatchling_config"].split(
                            "\n"
                        )

                        # Extract include/exclude lists from the suggestion
                        include_items = []
                        exclude_items = []
                        current_section = None

                        for line in hatchling_lines:
                            line = line.strip()
                            if "include = [" in line:
                                current_section = "include"
                            elif "exclude = [" in line:
                                current_section = "exclude"
                            elif line.startswith('"') and current_section:
                                # Extract the item (remove quotes, backslashes, and trailing comma)
                                item = (
                                    line.strip('"')
                                    .strip("\\")
                                    .rstrip(",")
                                    .strip()
                                    .strip('"')
                                )
                                if current_section == "include":
                                    include_items.append(item)
                                else:
                                    exclude_items.append(item)
                            elif line == "]":
                                current_section = None

                        # Check if migration already done - only update if items missing
                        if "tool" not in existing_data:
                            existing_data["tool"] = {}
                        if "hatch" not in existing_data["tool"]:
                            existing_data["tool"]["hatch"] = {}
                        if "build" not in existing_data["tool"]["hatch"]:
                            existing_data["tool"]["hatch"]["build"] = {}
                        if "targets" not in existing_data["tool"]["hatch"]["build"]:
                            existing_data["tool"]["hatch"]["build"]["targets"] = {}
                        if (
                            "wheel"
                            not in existing_data["tool"]["hatch"]["build"]["targets"]
                        ):
                            existing_data["tool"]["hatch"]["build"]["targets"][
                                "wheel"
                            ] = {}

                        wheel_config = existing_data["tool"]["hatch"]["build"][
                            "targets"
                        ]["wheel"]

                        # Check if items already present - skip if migration already done
                        existing_include = set(wheel_config.get("include", []))
                        existing_exclude = set(wheel_config.get("exclude", []))
                        new_include = set(include_items)
                        new_exclude = set(exclude_items)

                        needs_update = False
                        if include_items and not new_include.issubset(existing_include):
                            wheel_config["include"] = include_items
                            needs_update = True
                        if exclude_items and not new_exclude.issubset(existing_exclude):
                            wheel_config["exclude"] = exclude_items
                            needs_update = True

                        # Only write if changes needed
                        if needs_update:
                            with open(pyproject_path, "wb") as f:
                                tomli_w.dump(existing_data, f)

                            _clog(
                                "✅ Migrated MANIFEST.in → pyproject.toml [tool.hatch.build.targets.wheel]"
                            )
                            tracker.add("pyproject.toml (updated with MANIFEST.in)")
                        else:
                            _clog("✓ MANIFEST.in already migrated to pyproject.toml")
                            tracker.skip(
                                "pyproject.toml (MANIFEST.in already migrated)"
                            )
                    except Exception as e:
                        _clog(f"⚠️  Could not auto-migrate MANIFEST.in: {e}")
                        tracker.attention(
                            "MANIFEST.in",
                            "Auto-migration failed - see suggestions below",
                        )
                else:
                    tracker.attention(
                        "MANIFEST.in",
                        "Needs migration but pyproject.toml not found",
                    )
            else:
                tracker.attention(
                    "MANIFEST.in",
                    "Needs migration to Hatchling [tool.hatch.build.targets.wheel]",
                )

            if verbose and not (
                migrate and manifest_comparison.get("hatchling_config")
            ):
                _clog("  MANIFEST.in is not directly supported by Hatchling")
                for rec in manifest_comparison.get("recommendations", [])[:2]:
                    _clog(f"  • {rec}")
                if manifest_comparison.get("hatchling_config"):
                    _clog("\n  Suggested pyproject.toml configuration:")
                    for line in manifest_comparison["hatchling_config"].split("\n"):
                        _clog(f"    {line}")

    # Check CI workflow alignment
    ci_path = pjoin(".github/workflows/ci.yml")
    if (
        os.path.isfile(ci_path)
        and ci_path.replace(pkg_dir + os.sep, "") not in tracker.added
    ):
        _clog("\n👀 Checking CI workflow alignment with template...")
        ci_comparison = compare_ci_workflow(ci_path, project_name=name)
        if ci_comparison.get("needs_attention"):
            reasons = [rec for rec in ci_comparison.get("recommendations", [])]
            tracker.attention(
                ".github/workflows/ci.yml",
                " | ".join(reasons[:2]) + ("..." if len(reasons) > 2 else ""),
            )
            if verbose:
                _clog("  Issues found:")
                for rec in ci_comparison.get("recommendations", []):
                    _clog(f"    • {rec}")

    # Print summary
    if verbose:
        tracker.print_summary(verbose=True)
    else:
        tracker.print_summary(verbose=False)

    return name


_unknown_version_control_system = object()


def _ensure_url_from_url_root_and_name(configs: dict):
    """Ensure configs has a 'url' field, constructing it from root_url/url_root if needed."""
    # Handle both 'root_url' and 'url_root' for backward compatibility
    root_url = configs.get("root_url") or configs.get("url_root")

    if "url" not in configs and root_url and "name" in configs:
        if not root_url.endswith("/"):
            root_url += "/"
        configs["url"] = root_url + configs["name"]
    return configs


def _url_to_version_control_system(url):
    if "github.com" in url:
        return "github"
    elif "gitlab" in url:
        return "gitlab"
    else:
        return _unknown_version_control_system


def _resolve_ci_def_and_tpl_path(
    ci_def_path, ci_tpl_path, pkg_dir, version_control_system, project_type
):
    if ci_def_path is None:
        if version_control_system == "github":
            ci_def_path = os.path.join(pkg_dir, ".github/workflows/ci.yml")
        elif version_control_system == "gitlab":
            ci_def_path = os.path.join(pkg_dir, ".gitlab-ci.yml")
        else:
            raise ValueError(f"Unknown root url type: Neither github.com nor gitlab!")
    if ci_tpl_path is None:
        if version_control_system == "github":
            if project_type == "app":
                ci_tpl_path = github_ci_tpl_deploy_path
            else:  # project_type == 'lib', etc.
                print(f"project_type is {project_type}")
                ci_tpl_path = github_ci_publish_2025_path
        elif version_control_system == "gitlab":
            ci_tpl_path = gitlab_ci_tpl_path
        else:
            raise ValueError(f"Unknown root url type: Neither github.com nor gitlab!")
    print(f"{ci_tpl_path=}")
    return ci_def_path, ci_tpl_path


def _add_ci_def(ci_def_path, ci_tpl_path, root_url, name, clog, user_email):
    clog(f"... making a {ci_def_path}")
    with open(ci_tpl_path) as f_in:
        ci_def = f_in.read()
        ci_def = ci_def.replace("#PROJECT_NAME#", name)
        hostname = urlparse(root_url).netloc
        ci_def = ci_def.replace("#GITLAB_HOSTNAME#", hostname)
        ci_def = ci_def.replace("#USER_EMAIL#", user_email)
        os.makedirs(os.path.dirname(ci_def_path), exist_ok=True)
        with open(ci_def_path, "w") as f_out:
            f_out.write(ci_def)


def _get_pkg_url_from_pkg_dir(pkg_dir):
    """Look in the .git of pkg_dir and get the project url for it.

    Note: If the url found is an ssh url, it will be converted to an https one.
    """
    import re

    pkg_dir = ensure_no_slash_suffix(pkg_dir)
    pkg_git_url = git(command="remote get-url origin", work_tree=pkg_dir)

    # Check if the URL is an SSH URL and convert it to HTTPS if needed
    ssh_match = re.match(r"git@(.*?):(.*?)(?:\.git)?$", pkg_git_url)
    if ssh_match:
        domain, repo = ssh_match.groups()
        pkg_git_url = f"https://{domain}/{repo}"

    return pkg_git_url


def _get_root_url_from_pkg_dir(pkg_dir):
    """Look in the .git of pkg_dir, get the url, and make a root_url from it"""
    pkg_git_url = _get_pkg_url_from_pkg_dir(pkg_dir)
    name = os.path.basename(pkg_dir)
    assert pkg_git_url.endswith(name) or pkg_git_url[:-1].endswith(name), (
        f"The pkg_git_url doesn't end with the pkg name ({name}), "
        f"so I won't try to guess. pkg_git_url is {pkg_git_url}. "
        f"For what ever you're doing, maybe there's a way to explicitly specify "
        f"the root url you're looking for?"
    )
    return pkg_git_url[: -len(name)]


def update_pack_and_setup_py(
    target_pkg_dir, copy_files=("setup.py", "wads/data/MANIFEST.in")
):
    """Just copy over setup.py and pack.py (moving the original to be prefixed by '_'"""
    copy_files = set(copy_files)
    target_pkg_dir = ensure_no_slash_suffix(target_pkg_dir)
    name = os.path.basename(target_pkg_dir)
    contents = os.listdir(target_pkg_dir)
    assert {"setup.py", name}.issubset(contents), (
        f"{target_pkg_dir} needs to have all three: {', '.join({'setup.py', name})}"
    )

    pjoin = lambda *p: os.path.join(target_pkg_dir, *p)

    for resource_name in copy_files:
        print(f"... copying {resource_name} from {wads_join('')} to {target_pkg_dir}")
        shutil.move(src=pjoin(resource_name), dst=pjoin("_" + resource_name))
        shutil.copy(src=wads_join(resource_name), dst=pjoin(resource_name))


# --------------------------------------------------------------------------------------
# Extra: Populating a project from a github url
import contextlib
import subprocess
from functools import partial

DFLT_PROJ_ROOT_ENVVAR = "DFLT_PROJ_ROOT_ENVVAR"


def clog(*args, condition=True, log_func=print, **kwargs):
    if condition:
        return log_func(*args, **kwargs)


@contextlib.contextmanager
def cd(newdir, verbose=True):
    """Change your working directory, do stuff, and change back to the original"""
    _clog = partial(clog, condition=verbose, log_func=print)
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        _clog(f"cd {newdir}")
        yield
    finally:
        _clog(f"cd {prevdir}")
        os.chdir(prevdir)


# TODO: Use config2py to specify these, so user can configure them
name_for_url_root = {
    "https://github.com/i2mint": "i2mint",
    "https://github.com/thorwhalen": "thor",
}

# TODO: Use config2py to specify these, so user can configure them
proj_root_dir_for_name = {
    "i2mint": "i",
    "thor": "t",
}


def _mk_default_project_description(org_slash_proj: str) -> str:
    org, proj_name = org_slash_proj.split("/")
    return f"{proj_name} should say it all, no?"


def _get_org_slash_proj(repo: str) -> str:
    """Gets an org/proj_name string from a url (assuming it's at the end)

    >>> _get_org_slash_proj('https://github.com/thorwhalen/ut/')
    'thorwhalen/ut'
    """
    *_, org, proj_name = ensure_no_slash_suffix(repo).split("/")
    return f"{org}/{proj_name}"


def _to_git_https_url(git_url):
    """
    Converts gitURLs (namely SSH ones) to their HTTPS equivalent.

    :param git_url: A string containing the Git SSH URL.
    :return: A string containing the equivalent HTTPS URL.
    """
    if git_url.startswith("https://github.com"):
        return git_url
    elif git_url.startswith("http://github.com"):
        # return https equivalent
        return git_url.replace("http", "https")
    elif git_url.startswith("git@github.com"):
        stripped_url = git_url.replace("git@", "").replace(".git", "")
        formatted_url = stripped_url.replace(":", "/")
        https_url = f"https://{formatted_url}"
        return https_url
    elif git_url.startswith("github.com"):
        return f"https://{git_url}"
    else:
        owner, repo, *remainder = git_url.split("/")
        if not remainder:
            return f"https://github.com/{owner}/{repo}"
        else:
            raise ValueError(f"Cannot convert {git_url} to HTTPS URL")


def populate_proj_from_url(
    url,
    proj_rootdir=os.environ.get(DFLT_PROJ_ROOT_ENVVAR, None),
    description=None,
    license=populate_dflts["license"],
    **kwargs,
):
    """git clone a repository and set the resulting folder up for packaging."""
    verbose = kwargs.get("verbose", True)
    _clog = partial(clog, condition=verbose)

    _clog(f"Populating project for {url=}...")

    https_url = _to_git_https_url(url)
    https_url = ensure_no_slash_suffix(https_url)

    assert proj_rootdir, (
        "Your proj_rootdir was empty -- "
        "specify it or set the DFLT_PROJ_ROOT_ENVVAR envvar"
    )
    _clog(f"{proj_rootdir=}")

    root_url, proj_name = os.path.dirname(https_url), os.path.basename(https_url)
    if description is None:
        description = get_github_project_description(https_url)
    url_name = name_for_url_root.get(root_url, None)
    if url_name:
        _clog(f"url_name={url_name}")

    if url_name is not None and url_name in proj_root_dir_for_name:
        proj_rootdir = os.path.join(proj_rootdir, proj_root_dir_for_name[url_name])
    _clog(f"proj_rootdir={proj_rootdir}")

    proj_path = os.path.join(proj_rootdir, proj_name)

    with cd(proj_rootdir):
        # Only clone if the directory doesn't exist
        if not os.path.isdir(proj_path):
            _clog(f"cloning {url}...")
            subprocess.check_output(f"git clone {url}", shell=True).decode()
        else:
            _clog(f"Directory {proj_path} already exists, skipping clone...")

        _clog(f"populating package folder...")
        populate_pkg_dir(
            proj_path,
            defaults_from=url_name,
            description=description,
            root_url=root_url,  # Pass root_url explicitly
            license=license,
            **kwargs,
        )


def get_github_project_description(
    repo: str, default_factory=_mk_default_project_description
):
    """Get project description from github repository, or default if not found"""
    import requests

    org_slash_proj = _get_org_slash_proj(repo)
    api_url = f"https://api.github.com/repos/{org_slash_proj}"
    r = requests.get(api_url)
    if r.status_code == 200:
        description = r.json().get("description", None)
        if description:
            return description
        else:
            return default_factory(org_slash_proj)
    else:
        raise RuntimeError(
            f"Request response status for {api_url} wasn't 200. Was {r.status_code}"
        )


def main():
    import argh  # TODO: replace by argparse, or require argh in wads?

    argh.dispatch_command(populate_pkg_dir)


if __name__ == "__main__":
    main()
