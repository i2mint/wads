import os
import shutil
import json
from collections import ChainMap
from urllib.parse import urlparse

# from functools import partial
from typing import List, Optional
from wads import (
    pkg_join as wads_join,
    gitlab_ci_tpl_path,
    setup_tpl_path,
    gitignore_tpl_path,
    github_ci_tpl_deploy_path,
    github_ci_tpl_publish_path,
    wads_configs,
    wads_configs_file,
)
from wads.util import mk_conditional_logger, git, ensure_no_slash_suffix
from wads.pack import write_configs
from wads.licensing import license_body

# from wads.pack_util import write_configs

path_sep = os.path.sep

populate_dflts = wads_configs.get(
    "populate_dflts",
    {
        "description": "There is a bit of an air of mystery around this project...",
        "root_url": None,
        "author": None,
        "license": "mit",
        "description_file": "README.md",
        "long_description": "file:README.md",
        "long_description_content_type": "text/markdown",
        "keywords": None,
        "install_requires": None,
        "verbose": True,
        "version": "0.0.1",
        "project_type": "lib",
    },
)


def gen_readme_text(
    name, text="There is a bit of an air of mystery around this project..."
):
    return f"""
# {name}
{text}
"""


# TODO: Function way to long -- break it up
# TODO: Add a `defaults_from` in **configs that allows one to have several named defaults in wads_configs_file
def populate_pkg_dir(
    pkg_dir,
    version: str = populate_dflts["version"],
    description: str = populate_dflts["description"],
    root_url: Optional[str] = populate_dflts["root_url"],
    author: Optional[str] = populate_dflts["author"],
    license: str = populate_dflts["license"],
    description_file: str = populate_dflts["description_file"],
    keywords: Optional[List] = populate_dflts["keywords"],
    install_requires: Optional[List] = populate_dflts["install_requires"],
    long_description=populate_dflts["long_description"],
    long_description_content_type=populate_dflts["long_description_content_type"],
    include_pip_install_instruction_in_readme=True,
    verbose: bool = populate_dflts["verbose"],
    overwrite: List = (),
    defaults_from: Optional[str] = None,
    skip_docsrc_gen=False,
    skip_ci_def_gen=False,
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
    :param skip_ci_def_gen: Skip the generation of the CI stuff
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

    if os.path.isfile(pjoin("setup.cfg")):
        with open(pjoin("setup.cfg"), "r"):
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
        with open(pjoin(resource_name), "wt") as fp:
            fp.write(content)

    if should_update(".gitignore"):
        shutil.copy(gitignore_tpl_path, pjoin(".gitignore"))

    if project_type == "app":
        if should_update("requirements.txt"):
            with open(pjoin("requirements.txt"), "w") as f:
                pass

    else:  # project_type == 'lib' or None
        if should_update("setup.py"):
            shutil.copy(setup_tpl_path, pjoin("setup.py"))
        if should_update("setup.cfg"):
            _clog("... making a 'setup.cfg'")
            if "pkg-dir" in configs:
                del configs["pkg-dir"]
            write_configs(pjoin(""), configs)

    if should_update("LICENSE"):
        _license_body = license_body(configs["license"])
        save_txt_to_pkg("LICENSE", _license_body)

    if should_update("README.md"):
        readme_text = gen_readme_text(name, configs.get("description"))
        if include_pip_install_instruction_in_readme:
            readme_text += f"\n\nTo install:\t```pip install {name}```\n"
        save_txt_to_pkg("README.md", readme_text)

    if project_type is None or project_type == "lib":
        if not skip_docsrc_gen:
            # TODO: Figure out epythet and wads relationship -- right now, there's a reflexive dependency
            from epythet.setup_docsrc import make_docsrc

            make_docsrc(pkg_dir, verbose=verbose)

    if not skip_ci_def_gen:
        root_url = root_url or _get_root_url_from_pkg_dir(pkg_dir)
        version_control_system = (
            version_control_system or _url_to_version_control_system(root_url)
        )
        ci_def_path, ci_tpl_path = _resolve_ci_def_and_tpl_path(
            ci_def_path, ci_tpl_path, pkg_dir, version_control_system, project_type
        )
        if should_update(ci_def_path):
            assert name in ci_def_path and name in _get_pkg_url_from_pkg_dir(
                pkg_dir
            ), f"The name wasn't found in both the ci_def_path AND the git url, so I'm going to be safe and do nothing"
            # TODO: Handle user_email better than this and make more visible
            user_email = kwargs.get("user_email", "thorwhalen1@gmail.com")
            _add_ci_def(ci_def_path, ci_tpl_path, root_url, name, _clog, user_email)

    return name


_unknown_version_control_system = object()


def _ensure_url_from_url_root_and_name(configs: dict):
    if "url" not in configs and "url_root" in configs and "name" in configs:
        if not configs["url_root"].endswith("/"):
            configs["urls_root"] += "/"
        configs["url"] = configs["urls_root"] + configs["name"]
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
                ci_tpl_path = github_ci_tpl_publish_path
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
    assert {"setup.py", name}.issubset(
        contents
    ), f"{target_pkg_dir} needs to have all three: {', '.join({'setup.py', name})}"

    pjoin = lambda *p: os.path.join(target_pkg_dir, *p)

    for resource_name in copy_files:
        print(f'... copying {resource_name} from {wads_join("")} to {target_pkg_dir}')
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

    with cd(proj_rootdir):
        _clog(f"cloning {url}...")
        subprocess.check_output(f"git clone {url}", shell=True).decode()
        _clog(f"populating package folder...")
        populate_pkg_dir(
            os.path.join(proj_rootdir, proj_name),
            defaults_from=url_name,
            description=description,
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
