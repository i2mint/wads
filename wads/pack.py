"""Utils to package and publish.



The typical sequence of the methodic and paranoid could be something like this:

::

    python pack.py current-configs  # see what you got
    python pack.py increment-configs-version  # update (increment the version and write that in setup.cfg
    python pack.py current-configs-version  # see that it worked
    python pack.py current-configs  # ... if you really want to see the whole configs again (you're really paranoid)
    python pack.py run-setup  # see that it worked
    python pack.py twine-upload-dist  # publish
    # and then go check things work...



If you're crazy (or know what you're doing) just do

::

    python pack.py go

"""

import importlib
import subprocess
import pathlib
from setuptools import find_packages
import json
import re
import sys
import pkgutil
import os
from types import ModuleType
from pprint import pprint
from warnings import warn
from typing import (
    Union,
    Mapping,
    Iterable,
    Generator,
    Sequence,
    Optional,
    Tuple,
    List,
    Literal,
)
from configparser import ConfigParser
from functools import partial

import argh

from wads.util import git

CONFIG_FILE_NAME = "setup.cfg"
METADATA_SECTION = "metadata"
OPTIONS_SECTION = "options"
DFLT_OPTIONS = {
    "packages": "find:",
    "include_package_data": True,
    "zip_safe": False,
}

pjoin = lambda *p: os.path.join(*p)
DOCSRC = "docsrc"
DFLT_PUBLISH_DOCS_TO = None  # 'github'


def get_name_from_configs(pkg_dir, *, assert_exists=True):
    """Get name from local setup.cfg (metadata section)"""
    configs = read_configs(pkg_dir=pkg_dir)
    name = configs.get("name", None)
    if assert_exists:
        assert name is not None, "No name was found in configs"
    return name


def clog(condition, *args, log_func=pprint, **kwargs):
    if condition:
        log_func(*args, **kwargs)


def check_in(
    commit_message: str,
    *,
    work_tree: str = ".",
    git_dir: Optional[str] = None,
    auto_choose_default_action: bool = False,
    bypass_docstring_validation: bool = False,
    bypass_tests: bool = False,
    bypass_code_formatting: bool = False,
    verbose: bool = False,
    pre_git_hooks: Sequence[str] = (),
):
    """Validate, normalize, stage, commit and push your local changes to a remote repository.

    :param commit_message: Your commit message
    :type commit_message: str
    :param work_tree: The relative or absolute path of the working directory. Defaults to '.'.
    :type work_tree: str, optional
    :param git_dir: The relative or absolute path of the git directory. If None, it will be taken to be "{work_tree}/.git/". Defaults to None.
    :type git_dir: str, optional
    :param auto_choose_default_action: Set to True if you don't want to be prompted and automatically select the default action. Defaults to False.
    :type auto_choose_default_action: bool, optional
    :param bypass_docstring_validation: Set to True if you don't want to check if a docstring exists for every module, class and function. Defaults to False.
    :type bypass_docstring_validation: bool, optional
    :param bypass_tests: Set to True if you don't want to run doctests and other tests. Defaults to False.
    :type bypass_tests: bool, optional
    :param bypass_code_formatting: Set to True if you don't want the code to be automatically formatted using axblack. Defaults to False.
    :type bypass_code_formatting: bool, optional
    :param verbose: Set to True if you want to log extra information during the process. Defaults to False.
    :type verbose: bool, optional
    :param pre_git_hooks: A sequence of git commands to run before the git commit. Defaults to ().
    """

    def ggit(command: str):
        r = git(command, work_tree=work_tree, git_dir=git_dir)
        clog(verbose, r, log_func=print)
        return r

    def print_step_title(step_title):
        if verbose:
            print()
            print(f"============= {step_title.upper()} =============")
        else:
            print(f"-- {step_title}")

    def abort():
        print("Aborting")
        sys.exit()

    def confirm(action, default):
        if auto_choose_default_action:
            return default
        return argh.interaction.confirm(action, default)

    def verify_current_changes():
        print_step_title("Verify current changes")
        if "nothing to commit, working tree clean" in ggit("status"):
            print("No changes to check in.")
            abort()

    def pull_remote_changes():
        print_step_title("Pull remote changes")
        ggit("stash")
        result = ggit("pull")
        ggit("stash apply")
        if result != "Already up to date." and not confirm(
            "Your local repository was not up to date, but it is now. Do you want to continue",
            default=True,
        ):
            abort()

    def validate_docstrings():
        def run_pylint(current_dir):
            import pylint.lint

            if os.path.exists(os.path.join(current_dir, "__init__.py")):
                result = pylint.lint.Run(
                    [
                        current_dir,
                        "--disable=all",
                        "--enable=C0114,C0115,C0116",
                    ],
                    do_exit=False,
                )
                if result.linter.stats["global_note"] < 10 and not confirm(
                    f"Docstrings are missing in directory {current_dir}. Do you want to continue",
                    default=True,
                ):
                    abort()
            else:
                for subdir in next(os.walk(current_dir))[1]:
                    run_pylint(os.path.join(current_dir, subdir))

        print_step_title("Validate docstrings")
        run_pylint(".")

    def run_tests():
        import pytest

        print_step_title("Run tests")
        args = ["--doctest-modules"]
        if verbose:
            args.append("-v")
        else:
            args.extend(["-q", "--no-summary"])
        result = pytest.main(args)
        if result == pytest.ExitCode.TESTS_FAILED and not confirm(
            "Tests have failed. Do you want to push anyway", default=False
        ):
            abort()
        elif result not in [
            pytest.ExitCode.OK,
            pytest.ExitCode.NO_TESTS_COLLECTED,
        ]:
            print("Something went wrong when running tests. Please check the output.")
            abort()

    def format_code():
        print_step_title("Format code")
        subprocess.run(
            "black --line-length=88 .",
            shell=True,
            check=True,
            capture_output=not verbose,
        )

    def commit_changes():
        print_step_title("Commit changes")
        ggit(f'commit --all --message="{commit_message}"')

    def push_changes():
        if not confirm(
            "Your changes have been commited. Do you want to push",
            default=True,
        ):
            abort()
        print_step_title("Push changes")
        ggit("push")

    try:
        for pre_git_hook in pre_git_hooks or []:
            ggit(pre_git_hook)
        verify_current_changes()
        pull_remote_changes()
        if not bypass_docstring_validation:
            validate_docstrings()
        if not bypass_tests:
            run_tests()
        if not bypass_code_formatting:
            format_code()
            verify_current_changes()  # check again after formatting
        commit_changes()
        push_changes()

    except subprocess.CalledProcessError:
        print("An error occured. Please check the output.")
        abort()

    print("Your changes have been checked in successfully!")


def goo(
    pkg_dir,
    commit_message,
    *,
    git_dir=None,
    auto_choose_default_action=False,
    bypass_docstring_validation=False,
    bypass_tests=False,
    bypass_code_formatting=False,
    verbose=False,
):
    """Validate, normalize, stage, commit and push your local changes to a remote repository.

    :param pkg_dir: The relative or absolute path of the working directory. Defaults to '.'.
    :type pkg_dir: str, optional
    :param commit_message: Your commit message
    :type commit_message: str
    :param git_dir: The relative or absolute path of the git directory. If None, it will be taken to be "{work_tree}/.git/". Defaults to None.
    :type git_dir: str, optional
    :param auto_choose_default_action: Set to True if you don't want to be prompted and automatically select the default action. Defaults to False.
    :type auto_choose_default_action: bool, optional
    :param bypass_docstring_validation: Set to True if you don't want to check if a docstring exists for every module, class and function. Defaults to False.
    :type bypass_docstring_validation: bool, optional
    :param bypass_tests: Set to True if you don't want to run doctests and other tests. Defaults to False.
    :type bypass_tests: bool, optional
    :param bypass_code_formatting: Set to True if you don't want the code to be automatically formatted using axblack. Defaults to False.
    :type bypass_code_formatting: bool, optional
    :param verbose: Set to True if you want to log extra information during the process. Defaults to False.
    :type verbose: bool, optional
    """

    return check_in(
        commit_message=commit_message,
        work_tree=pkg_dir,
        git_dir=git_dir,
        auto_choose_default_action=auto_choose_default_action,
        bypass_docstring_validation=bypass_docstring_validation,
        bypass_tests=bypass_tests,
        bypass_code_formatting=bypass_code_formatting,
        verbose=verbose,
    )


# TODO: Add a function that adds/commits/pushes the updated setup.cfg
# TODO: Include tests as first step
# TODO: blackify
# TODO: Git pull and make sure no conflicts before moving on...
def go(
    pkg_dir,
    *,
    version=None,
    publish_docs_to=DFLT_PUBLISH_DOCS_TO,
    verbose: bool = True,
    skip_git_commit: bool = False,
    answer_yes_to_all_prompts: bool = False,
    twine_upload_options_str: str = "",
    keep_dist_pkgs=False,
    commit_message="",
):
    """Update version, package and deploy:
    Runs in a sequence: increment_configs_version, update_setup_cfg, run_setup, twine_upload_dist

    :param version: The desired version (if not given, will increment the current version
    :param verbose: Whether to print stuff or not
    :param skip_git_commit: Whether to skip the git commit and push step
    :param answer_yes_to_all_prompts: If you do git commit and push, whether to ask confirmation after showing status

    """

    # TODO: Would like version to be decremented if the publication attempt fails!
    version = increment_configs_version(pkg_dir, version=version)
    update_setup_cfg(pkg_dir, verbose=verbose)
    run_setup(pkg_dir)
    twine_upload_dist(pkg_dir, options_str=twine_upload_options_str)

    if not keep_dist_pkgs:
        delete_pkg_directories(pkg_dir, verbose)

    if publish_docs_to:
        generate_and_publish_docs(pkg_dir, publish_docs_to)
    if not skip_git_commit:
        git_commit_and_push(
            pkg_dir,
            version=version,
            verbose=verbose,
            answer_yes_to_all_prompts=answer_yes_to_all_prompts,
            commit_message=commit_message,
        )


def git_commit_and_push(
    pkg_dir,
    *,
    version=None,
    verbose: bool = True,
    answer_yes_to_all_prompts: bool = False,
    commit_message="",
    what_to_add="*",
):
    def ggit(command):
        r = git(command, work_tree=pkg_dir)
        clog(verbose, r, log_func=print)

    ggit("status")

    if not answer_yes_to_all_prompts:
        answer = input("Should I do a 'git add *'? ([Y]/n): ")
        if answer and answer != "Y":
            print("Okay, I'll stop here.")
            return
    ggit(f"add {what_to_add}")

    ggit("status")  # show status again

    commit_command = f'commit -m "{version}: {commit_message}"'
    if not answer_yes_to_all_prompts:
        answer = input(f"Should I {commit_command} and push? ([Y]/n)")
        if answer and answer != "Y":
            print("Okay, I'll stop here.")
            return
    ggit(commit_command)
    ggit(f"push")


def generate_and_publish_docs(pkg_dir, *, publish_docs_to="github"):
    # TODO: Figure out epythet and wads relationship -- right now, there's a reflexive dependency
    from epythet import make_autodocs, make

    make_autodocs(pkg_dir)
    if publish_docs_to:
        make(pkg_dir, publish_docs_to)


PathStr = str
PkgName = str
PkgSpec = Union[PathStr, ModuleType, pathlib.Path, PkgName]


def delete_pkg_directories(pkg_dir: PathStr, verbose=True):
    from shutil import rmtree

    pkg_dir, pkg_dirname = extract_pkg_dir_and_name(pkg_dir)
    names_to_delete = ["dist", "build", f"{pkg_dirname}.egg-info"]
    for name_to_delete in names_to_delete:
        delete_dirpath = os.path.join(pkg_dir, name_to_delete)
        if os.path.isdir(delete_dirpath):
            if verbose:
                print(f"Deleting folder: {delete_dirpath}")
            rmtree(delete_dirpath)


def get_module_path(module: ModuleType) -> str:
    """
    Get the path to the directory containing the module's code file.

    >>> import os
    >>> get_module_path(os)  # doctest: +SKIP
    '/usr/lib/python3.8'
    >>> import sklearn  # doctest: +SKIP
    >>> get_module_path(sklearn)  # doctest: +SKIP
    '/usr/local/lib/python3.8/dist-packages/sklearn'
    >>> import local_package  # doctest: +SKIP
    >>> get_module_path(local_package)  # doctest: +SKIP
    '/home/user/projects/local_package/local_package'

    Read more: https://github.com/i2mint/wads/discussions/7#discussioncomment-9761632

    """
    if isinstance(module, ModuleType):
        loader = pkgutil.get_loader(module)
        if loader is None or loader.get_filename() is None:
            raise ValueError(f"Cannot find the filename for module {module.__name__}")
        return os.path.dirname(loader.get_filename())
    return module


def _get_pkg_dir_and_name(pkg_dir, validate=True):
    pkg_dir = os.path.realpath(pkg_dir)
    if pkg_dir.endswith(os.sep):
        pkg_dir = pkg_dir[:-1]
    pkg_name = os.path.basename(pkg_dir)
    if validate:
        if not os.path.isdir(pkg_dir):
            raise AssertionError(f"Directory {pkg_dir} wasn't found")
        if pkg_name not in os.listdir(pkg_dir):
            name_candidates = folders_that_have_init_py_files(pkg_dir)
            if not name_candidates:
                raise AssertionError(
                    f"pkg_dir={pkg_dir} doesn't itself contain a dir named {pkg_name}"
                )
            elif len(name_candidates) > 1:
                raise AssertionError(
                    f"pkg_dir={pkg_dir} contains multiple dirs with __init__.py files: "
                    f"{name_candidates}, so I don't know which to chose as the package name"
                )
            else:
                pkg_name = name_candidates[0]
    return pkg_dir, pkg_name


def extract_pkg_dir_and_name(
    pkg_spec: PkgSpec, *, validate: bool = True
) -> Tuple[str, str]:
    """
    Extracts the pkg_dir and pkg_dirname from the input `pkg_spec`.
    Optionally validates the pkg_dir is actually one (has a pkg_name/__init__.py file)

    Also processes input to get a path from a pathlib.Path object, or a module object,
    or a module/package name string.

    `pkg_spec` can be an imported package (must be a locally developped package)
    whose name and containing directory is the same):

    >>> import wads
    >>> extract_pkg_dir_and_name(wads)  # doctest: +ELLIPSIS
    (.../wads', 'wads')

    You can also just specify the name of the package (it will be imported):

    >>> extract_pkg_dir_and_name('wads')  # doctest: +SKIP
    ('.../wads', 'wads')

    Or you can specify the path to the package directory explicitly:

    >>> extract_pkg_dir_and_name('/home/user/projects/wads')  # doctest: +SKIP
    ('/home/user/projects/wads', 'wads')

    """
    if isinstance(pkg_spec, pathlib.Path):
        pkg_spec = str(pkg_spec)
    # if pkg_spec has only alphanumeric characters, assume it's a package name and import it
    if isinstance(pkg_spec, str) and not os.path.isdir(pkg_spec) and pkg_spec.isalnum():
        pkg_spec = importlib.import_module(pkg_spec)
    # if pkg_spec is a module object, get the path to the module
    if isinstance(pkg_spec, ModuleType):
        module_dir = get_module_path(pkg_spec)
        # package dir is the parent of module dir
        # Note that this is only true for packages developped locally
        pkg_spec = os.path.dirname(module_dir)

    pkg_dir, pkg_name = _get_pkg_dir_and_name(pkg_spec)

    if validate:
        assert os.path.isdir(pkg_dir), f"Directory {pkg_dir} wasn't found"
        if not pkg_name in os.listdir(pkg_dir):
            raise AssertionError(
                f"pkg_dir={pkg_dir} doesn't itself contain a dir named {pkg_name}"
            )
        assert "__init__.py" in os.listdir(os.path.join(pkg_dir, pkg_name)), (
            f"pkg_dir={pkg_dir} contains a dir named {pkg_name}, "
            f"but that dir isn't a package (does not have a __init__.py"
        )

    return pkg_dir, pkg_name


def folders_that_have_init_py_files(pkg_dir: PathStr) -> List[str]:
    """
    Get a list of folders in the package directory that have an __init__.py file.

    >>> folders_that_have_init_py_files('/home/user/projects/wads')  # doctest: +SKIP
    ['wads', 'wads/util', 'wads/pack', 'wads/docs_gen']

    """
    return [
        d
        for d in os.listdir(pkg_dir)
        if os.path.isdir(os.path.join(pkg_dir, d))
        and "__init__.py" in os.listdir(os.path.join(pkg_dir, d))
    ]


def get_pkg_name(pkg_spec: PkgSpec, validate=True) -> PkgName:
    """
    Get the name of the package from a package name, module object or path.
    Optionally validates some naming rules.
    """
    pkg_dir, pkg_dirname = extract_pkg_dir_and_name(pkg_spec, validate=validate)
    configs_pkg_name = get_name_from_configs(pkg_dir)
    if validate:
        assert (
            pkg_dirname == configs_pkg_name
        ), f"({pkg_dirname=} and {configs_pkg_name=} were not the same"
    return configs_pkg_name


def _get_pkg_dir(pkg_spec: PkgSpec, validate=True) -> PathStr:
    """
    Get the path to the package directory from a package name, module object or path.
    """
    pkg_dir, _ = extract_pkg_dir_and_name(pkg_spec, validate=validate)
    return pkg_dir


def current_configs(pkg_dir):
    configs = read_configs(pkg_dir=_get_pkg_dir(pkg_dir))
    pprint(configs)


def current_configs_version(pkg_dir):
    pkg_dir = _get_pkg_dir(pkg_dir)
    return read_configs(pkg_dir=pkg_dir).get("version")


# TODO: Both setup and twine are python. Change to use python objects directly.
def update_setup_cfg(pkg_dir, *, new_deploy=False, version=None, verbose=True):
    """Update setup.cfg.
    If version is not given, will ask pypi (via http request) what the current version
    is, and increment that.
    """
    pkg_dir = _get_pkg_dir(pkg_dir)
    configs = read_and_resolve_setup_configs(
        pkg_dir=_get_pkg_dir(pkg_dir),
        new_deploy=new_deploy,
        version=version,
    )
    pprint("\n{configs}\n")
    clog(verbose, pprint(configs))
    write_configs(pkg_dir=pkg_dir, configs=configs)


def set_version(pkg_dir, version):
    """Update version setup.cfg"""
    pkg_dir = _get_pkg_dir(pkg_dir)
    configs = read_configs(pkg_dir)
    assert isinstance(version, str), "version should be a string"
    configs["version"] = version
    write_configs(pkg_dir=pkg_dir, configs=configs)


def increment_configs_version(
    pkg_dir,
    *,
    version=None,
):
    """Increment version setup.cfg."""
    pkg_dir = _get_pkg_dir(pkg_dir)
    configs = read_configs(pkg_dir=pkg_dir)
    version = _get_version(pkg_dir, version=version, configs=configs, new_deploy=False)
    version = increment_version(version)
    configs["version"] = version
    write_configs(pkg_dir=pkg_dir, configs=configs)
    return version


def run_setup(pkg_dir):
    """Run ``python setup.py sdist bdist_wheel``"""
    print("--------------------------- setup_output ---------------------------")
    pkg_dir = _get_pkg_dir(pkg_dir)
    original_dir = os.getcwd()
    os.chdir(pkg_dir)
    setup_output = subprocess.run(
        f"{sys.executable} setup.py sdist bdist_wheel".split(" ")
    )
    os.chdir(original_dir)
    # print(f"{setup_output}\n")


def twine_upload_dist(pkg_dir, *, options_str=None):
    """Publish to pypi. Runs ``python -m twine upload dist/*``"""
    print("--------------------------- upload_output ---------------------------")
    pkg_dir = _get_pkg_dir(pkg_dir)
    original_dir = os.getcwd()
    os.chdir(pkg_dir)
    # TODO: dist/*? How to publish just last one?
    if options_str:
        command = f"{sys.executable} -m twine upload {options_str} dist/*"
    else:
        command = f"{sys.executable} -m twine upload dist/*"
    # print(command)
    subprocess.run(command.split(" "))
    os.chdir(original_dir)
    # print(f"{upload_output.decode()}\n")


# -----------------------------------------------------------------------------
# setup.cfg reading and writing

# TODO: A lot of work done here to read setup.cfg. setup function apparently does it for you. How to use that?


# TODO: postprocess_ini_section_items and preprocess_ini_section_items: Add comma separated possibility?
# TODO: Find out if configparse has an option to do this processing alreadys
def postprocess_ini_section_items(items: Union[Mapping, Iterable]) -> Generator:
    r"""Transform newline-separated string values into actual list of strings (assuming that intent)

    >>> section_from_ini = {
    ...     'name': 'wads',
    ...     'keywords': '\n\tpackaging\n\tpublishing'
    ... }
    >>> section_for_python = dict(postprocess_ini_section_items(section_from_ini))
    >>> section_for_python
    {'name': 'wads', 'keywords': ['packaging', 'publishing']}

    """
    splitter_re = re.compile("[\n\r\t]+")
    if isinstance(items, Mapping):
        items = items.items()
    for k, v in items:
        if v.startswith("\n"):
            v = splitter_re.split(v[1:])
            v = [vv.strip() for vv in v if vv.strip()]
            v = [vv for vv in v if not vv.startswith("#")]  # remove commented lines
        yield k, v


# TODO: Find out if configparse has an option to do this processing already
def preprocess_ini_section_items(items: Union[Mapping, Iterable]) -> Generator:
    """Transform list values into newline-separated strings, in view of writing the value to a ini formatted section

    >>> section = {
    ...     'name': 'wads',
    ...     'keywords': ['documentation', 'packaging', 'publishing']
    ... }
    >>> for_ini = dict(preprocess_ini_section_items(section))
    >>> print('keywords =' + for_ini['keywords'])  # doctest: +NORMALIZE_WHITESPACE
    keywords =
        documentation
        packaging
        publishing

    """
    if isinstance(items, Mapping):
        items = items.items()
    for k, v in items:
        if isinstance(v, str) and not v.startswith('"') and "," in v:
            v = list(map(str.strip, v.split(",")))
        if isinstance(v, list):
            v = "\n\t" + "\n\t".join(v)

        yield k, v


def read_configs(
    pkg_dir: PathStr,
    postproc=postprocess_ini_section_items,
    section=METADATA_SECTION,
    *,
    verbose=False,
):
    assert isinstance(
        pkg_dir, PathStr
    ), "It doesn't look like pkg_dir is a path. Did you perhaps invert pkg_dir and postproc order"
    pkg_dir = _get_pkg_dir(pkg_dir)
    config_filepath = pjoin(pkg_dir, CONFIG_FILE_NAME)
    c = ConfigParser()
    if os.path.isfile(config_filepath):
        c.read_file(open(config_filepath, "r"))
        if verbose:
            print(f"{section=}, {type(section)=}")
        try:
            d = c[section]
        except KeyError:
            d = {}
        if postproc:
            d = dict(postproc(d))
    else:
        d = {}
    return d


def write_configs(
    pkg_dir: PathStr,
    configs,
    preproc=preprocess_ini_section_items,
    dflt_options=DFLT_OPTIONS,
):
    assert isinstance(
        pkg_dir, PathStr
    ), "It doesn't look like pkg_dir is a path. Did you perhaps invert pkg_dir and configs order"
    pkg_dir = _get_pkg_dir(pkg_dir)
    config_filepath = pjoin(pkg_dir, CONFIG_FILE_NAME)
    c = ConfigParser()
    if os.path.isfile(config_filepath):
        c.read_file(open(config_filepath, "r"))

    metadata_dict = dict(preproc(configs))
    options = dict(dflt_options, **read_configs(pkg_dir, preproc, OPTIONS_SECTION))

    # TODO: Legacy. Reorg key to [section][key] mapping to avoid such ugly complexities.
    for k in [
        "install_requires",
        "install-requires",
        "packages",
        "zip_safe",
        "include_package_data",
    ]:
        if k in metadata_dict:
            if k not in options:
                options[k] = metadata_dict.pop(
                    k
                )  # get it out of metadata_dict and into options
            else:
                metadata_dict.pop(
                    k
                )  # if it's both in metadata and in options, just get it out of metadata

    c[METADATA_SECTION] = metadata_dict
    c[OPTIONS_SECTION] = options
    with open(config_filepath, "w") as fp:
        c.write(fp)


# -----------------------------------------------------------------------------
# Versioning

from packaging.version import parse


def sorted_versions(strings: Iterable[str], version_patch_prefix=""):
    """
    Filter out and return version strings in (versioning) descending order.
    """
    version_pattern = re.compile(rf"^(\d+.){{2}}{version_patch_prefix}\d+$")

    # Filter and sort the versions in descending order
    sorted_versions = sorted(
        (
            x.replace(f"{version_patch_prefix}", "")
            for x in strings
            if version_pattern.match(x)
        ),
        key=parse,
        reverse=True,
    )
    return sorted_versions


def increment_version(version_str):
    version_nums = list(map(int, version_str.split(".")))
    version_nums[-1] += 1
    return ".".join(map(str, version_nums))


try:
    import requests

    requests_is_installed = True
except ModuleNotFoundError:
    requests_is_installed = False


def http_get_json(url, use_requests=requests_is_installed) -> Union[dict, None]:
    """Make ah http request to url and get json, and return as python dict"""

    if use_requests:
        import requests

        r = requests.get(url)
        if r.status_code == 200:
            return r.json()
        else:
            raise ValueError(f"response code was {r.status_code}")
    else:
        import urllib.request
        from urllib.error import HTTPError

        req = urllib.request.Request(url)
        try:
            r = urllib.request.urlopen(req)
            if r.code == 200:
                return json.loads(r.read())
            else:
                raise ValueError(f"response code was {r.code}")
        except HTTPError:
            return None  # to indicate (hopefully) that name doesn't exist
        except Exception:
            raise


PYPI_PACKAGE_JSON_URL = "https://pypi.python.org/pypi/{package}/json"


# TODO: Perhaps there's a safer way to analyze errors (and determine if the package exists or other HTTPError)
def versions_from_pypi(
    pkg_dir: PathStr,
    *,
    name: Union[None, str] = None,
    use_requests=requests_is_installed,
) -> Union[str, None]:
    """
    Return version of package on pypi.python.org using json.

    :param package: Name of the package
    :return: A version (string) or None if there was an exception (usually means there
    """
    name = get_pkg_name(pkg_dir)
    url = PYPI_PACKAGE_JSON_URL.format(package=name)

    pkg_info = http_get_json(url, use_requests=use_requests)
    releases = pkg_info.get("releases", [])

    # keep only the versions that don't have yanked=True
    def yanked_release(release_info_list):
        return any(x.get("yanked", False) for x in release_info_list)

    releases = [k for k, v in releases.items() if not yanked_release(v)]
    return sorted_versions(releases)


def highest_pypi_version(
    pkg_dir: PathStr,
    *,
    name: Union[None, str] = None,
    use_requests=requests_is_installed,
) -> List[str]:
    """
    Return version of package on pypi.python.org using json.

    >>> highest_pypi_version('wads')  # doctest: +SKIP
    '0.1.19'

    :param package: Name of the package
    :return: A version (string) or None if there was an exception (usually means there
    """
    versions = versions_from_pypi(pkg_dir, name=name, use_requests=use_requests)
    if versions:
        return versions[0]
    # else: return None


def current_pypi_version(
    pkg_dir: PathStr,
) -> Union[str, None]:
    """
    Return version of package on pypi.python.org using json.

    >>> current_pypi_version('wads')  # doctest: +SKIP
    '0.1.19'

    """
    name = get_pkg_name(pkg_dir)
    url = PYPI_PACKAGE_JSON_URL.format(package=name)
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data["info"]["version"]
    else:
        raise Exception(f"Failed to get information for {package_name}")


def next_version_for_package(
    pkg_dir: PathStr,
    name: Union[None, str] = None,
    version_if_current_version_none="0.0.1",
    use_requests=requests_is_installed,
) -> str:
    name = name or get_name_from_configs(pkg_dir=pkg_dir)
    current_version = current_pypi_version(name, use_requests=use_requests)
    if current_version is not None:
        return increment_version(current_version)
    else:
        return version_if_current_version_none


def _get_version(
    pkg_dir: PathStr,
    version,
    configs,
    name: Union[None, str] = None,
    new_deploy=False,
):
    version = version or configs.get("version", None)
    if version is None:
        try:
            if new_deploy:
                version = next_version_for_package(
                    pkg_dir, name
                )  # when you want to make a new package
            else:
                version = current_pypi_version(
                    pkg_dir, name
                )  # when you want to make a new package
        except Exception as e:
            print(
                f"Got an error trying to get the new version of {name} so will try to get the version from setup.cfg..."
            )
            print(f"{e}")
            version = configs.get("version", None)
            if version is None:
                raise ValueError(
                    f"Couldn't fetch the next version from PyPi (no API token?), "
                    f"nor did I find a version in setup.cfg (metadata section)."
                )
    return version


def versions_from_tags(pkg_spec: PkgSpec, version_patch_prefix: str = ""):
    pkg_dir, pkg_name = extract_pkg_dir_and_name(pkg_spec)
    tags = [x.strip() for x in git("tag", work_tree=pkg_dir).split("\n")]
    # Pattern to match versions with the patch prefix
    pattern = rf"^(\d+.){{2}}{version_patch_prefix}\d+$"
    # Filter and sort the versions in descending order
    sorted_versions = sorted(
        [
            x.replace(f"{version_patch_prefix}", "")
            for x in tags
            if re.match(pattern, x)
        ],
        key=parse,
        reverse=True,
    )
    return sorted_versions


def highest_tag_version(pkg_spec: PkgSpec, version_patch_prefix: str = ""):
    sorted_tag_versions = versions_from_tags(pkg_spec, version_patch_prefix)
    if len(sorted_tag_versions) > 0:
        return sorted_tag_versions[0]
    return None


def setup_cfg_version(pkg_spec: PkgSpec):
    """Get version from setup.cfg file."""
    pkg_dir, _ = extract_pkg_dir_and_name(pkg_spec)
    configs = read_configs(pkg_dir=pkg_dir)
    return configs.get("version", None)


def versions_from_different_sources(pkg_spec: PkgSpec):
    return {
        "tag": highest_tag_version(pkg_spec),
        "current_pypi": current_pypi_version(pkg_spec),
        "highest_not_yanked_pypi": highest_pypi_version(pkg_spec),
        "setup_cfg": setup_cfg_version(pkg_spec),
    }


ValidVersionSources = Literal[
    "tag", "current_pypi", "highest_not_yanked_pypi", "setup_cfg"
]


def raise_error(msg, error_type=ValueError):
    raise error_type(msg)


def validate_versions(versions: dict, action_when_not_valid=raise_error) -> dict:
    """
    Validate versions from different sources.

    You get the versions input from the `versions_from_different_sources` function.

    :param versions: A dictionary with the versions from different sources
    :param action_when_not_valid: A function that will be called when the versions are not valid
        Default is to raise a ValueError with the error message.
        Another option is to print the error message, log it, or issue a warning.
    :return: The versions if they are valid
    """

    # TODO: Raise specific exceptions with what-to-do-about-it messages
    #   Tip: Write the instructions in a github wiki/discussion/issue and provide link

    error_msg = ""
    if versions["tag"] != versions["setup_cfg"]:
        error_msg += (
            f"Tag version ({versions['tag']}) is different "
            f"from setup.cfg's version: {versions['setup_cfg']}\n"
        )
    if versions["current_pypi"] != versions["highest_not_yanked_pypi"]:
        error_msg += (
            f"Current pypi version ({versions['current_pypi']}) is different "
            f"from the highest not yanked pypi version: {versions['highest_not_yanked_pypi']}\n"
        )
    if versions["current_pypi"] > versions["setup_cfg"]:
        error_msg += (
            f"Current pypi version ({versions['current_pypi']}) is higher "
            f"than setup.cfg's version: {versions['setup_cfg']}\n"
        )
    if error_msg:
        error_msg += (
            f"Please make sure the versions are consistent and then try again: \n"
            f"  {versions=}"
        )
        action_when_not_valid(error_msg)

    # but if all is well, return the versions:
    return versions


# -----------------------------------------------------------------------------


def read_and_resolve_setup_configs(
    pkg_dir: PathStr, *, new_deploy=False, version=None, assert_names=True
):
    """make setup params and call setup

    :param pkg_dir: Directory where the pkg is (which is also where the setup.cfg is)
    :param new_deploy: whether this setup for a new deployment (publishing to pypi) or not
    :param version: The version number to set this up as.
                    If not given will look at setup.cfg[metadata] for one,
                    and if not found there will use the current version (requesting pypi.org)
                    and bump it if the new_deploy flag is on
    """
    # read the config file (get a dict with it's contents)
    pkg_dir, pkg_dirname = _get_pkg_dir_and_name(pkg_dir)
    if assert_names:
        extract_pkg_dir_and_name(pkg_dir)

    configs = read_configs(pkg_dir)

    # parse out name and root_url
    assert (
        "root_url" in configs or "url" in configs
    ), "configs didn't have a root_url or url"

    name = configs["name"] or pkg_dirname
    if assert_names:
        assert (
            name == pkg_dirname
        ), f"config name ({name}) and pkg_dirname ({pkg_dirname}) are not equal!"

    if "root_url" in configs:
        root_url = configs["root_url"]
        if root_url.endswith(
            "/"
        ):  # yes, it's a url so it's always forward slash, not the systems' slash os.sep
            root_url = root_url[:-1]
        url = f"{root_url}/{name}"
    elif "url" in configs:
        url = configs["url"]
    else:
        raise ValueError(
            f"configs didn't have a root_url or url. It should have at least one of these!"
        )

    # Note: if version is not in config, version will be None,
    #  resulting in bumping the version or making it be 0.0.1 if the package is not found (i.e. first deploy)

    meta_data_dict = {k: v for k, v in configs.items()}

    # make the setup_kwargs
    setup_kwargs = dict(
        meta_data_dict,
        # You can add more key=val pairs here if they're missing in config file
    )

    version = _get_version(pkg_dir, version, configs, name, new_deploy)

    def text_of_readme_md_file():
        try:
            with open("README.md") as f:
                return f.read()
        except:
            return ""

    dflt_kwargs = dict(
        name=f"{name}",
        version=f"{version}",
        url=url,
        packages=find_packages(),
        include_package_data=True,
        platforms="any",
        # long_description=text_of_readme_md_file(),
        # long_description_content_type="text/markdown",
        description_file="README.md",
    )

    configs = dict(dflt_kwargs, **setup_kwargs)

    return configs


def _print_some_lines_of_code(file, file_contents, slice_):
    print(
        f"------------ lines {slice_.start} through {slice_.stop} of {file} ------------"
    )
    print("\n".join(file_contents.split("\n")[slice_]))
    print("---------------------------------------------------------")


def _slice_from_string(string):
    try:
        try:
            return slice(0, int(string))
        except ValueError:
            return slice(*map(int, string.split(":")))
    except ValueError:
        return None


def _ask_user_what_to_do_about_this_file(
    file, file_contents, dflt_n_lines_slice=20, start_here=0
):
    ask_again = lambda: _ask_user_what_to_do_about_this_file(
        file, file_contents, dflt_n_lines_slice, start_here
    )
    r = input(f"\nEnter a one liner doc for {file} then press enter:\n")
    r = r.strip()
    if r == "":
        start = start_here
        stop = start_here + dflt_n_lines_slice
        print_these_lines = slice(start, stop)
        start_here += (
            dflt_n_lines_slice  # so that next time r == '', we print new lines
        )
    else:
        print_these_lines = _slice_from_string(r)
    if print_these_lines is not None:
        _print_some_lines_of_code(file, file_contents, print_these_lines)
        # ... and then call the function again, recursively, until exit or some doc string is given
        return ask_again()
    else:
        if _equals_or_first_letter_of(r, "exit"):
            print("Exiting...")
            return "exit"
        if _equals_or_first_letter_of(r, "skip"):
            print("Skipping that one...")
            return "skip"
        if _equals_or_first_letter_of(r, "funcs"):
            _print_functions_and_classes(file, file_contents)
            return ask_again()
        if len(r) <= 5:
            print("---> Your docstring needs to be at least 5 characters")
            return ask_again()

        return r


def _print_functions_and_classes(file, file_contents):
    def gen():
        for line in file_contents.split("\n"):
            stripped_line = line.strip()
            if stripped_line.startswith("def ") or stripped_line.startswith("class "):
                yield line

    print(f"----------- funcs, classes, and methods of {file} -----------")
    print("\n".join(gen()))
    print("---------------------------------------------------------")


def _equals_or_first_letter_of(input_string, target_string):
    return input_string == target_string or (
        len(input_string) == 1 and input_string[0] == target_string[0]
    )


def process_missing_module_docstrings(
    *,
    pkg_dir: PathStr,
    action="input",
    exceptions=(),
    docstr_template='"""\n{user_input}\n"""\n',
):
    r"""
    Goes through modules of package, sees which ones don't have docstrings,
    and gives you the option to write one.

    The function will go through all .py files (except those mentioned in exceptions),
    check if there's a module docstring (that is, that the first non-white characters are
    triple-quotes (double or single)).

    What happens with that depends on the ``action`` argument,

    If ``action='list'``, those modules missing docstrings will be listed.
    If ``action='count'``, the count of those modules missing docstrings will be returned.

    If ``action='input'``, for every module you'll be given the option to enter a
    SINGLE LINE module docstring (though you could include multi-lines with \n).
    Just type the docstring you want and hit enter to go to the next module with missing docstring.
    Or, you can also:
        - type exit, or e: To exit this process
        - type skip, or s: To skip the module and go to the next
        - type funcs, or f: To see a print out of functions, classes, and methods
        - just hit enter, to get some lines of code (the first, then the next, etc.)
        - enter a number, or a number:number, to specify what lines you want to see printed
    Printing lines helps you write an informed module docstring

    :keyword module, docstr, docstrings, module doc strings
    """
    from dol import TextFiles, filt_iter

    pkg_dir, _ = _get_pkg_dir_and_name(pkg_dir)

    exceptions = set(exceptions)
    files = filt_iter(
        TextFiles(pkg_dir + "{}.py", max_levels=None),
        filt=exceptions.isdisjoint,
    )

    def files_and_contents_that_dont_have_docs():
        for file, file_contents in files.items():
            contents = file_contents.strip()
            if not contents.startswith('"""') and not contents.startswith("'''"):
                yield file, file_contents

    if action == "list":
        return [
            file for file, file_contents in files_and_contents_that_dont_have_docs()
        ]
    elif action == "count":
        return len(list(files_and_contents_that_dont_have_docs()))
    elif action == "input":
        were_no_files = True
        for file, file_contents in files_and_contents_that_dont_have_docs():
            were_no_files = False
            r = _ask_user_what_to_do_about_this_file(file, file_contents)
            if r == "exit":
                return
            elif r == "skip":
                continue

            files[file] = docstr_template.format(user_input=r) + file_contents

        if were_no_files:
            print("---> Seems like all your modules have docstrings! Congrads!")
            return True
    else:
        raise ValueError(f"Unknown action: {action}")


# -----------------------------------------------------------------------------


argh_kwargs = {
    "namespace": "pack",
    "functions": [
        generate_and_publish_docs,
        current_configs,
        increment_configs_version,
        current_configs_version,
        twine_upload_dist,
        read_and_resolve_setup_configs,
        update_setup_cfg,
        go,
        goo,
        check_in,
        get_name_from_configs,
        run_setup,
        current_pypi_version,
        extract_pkg_dir_and_name,
        git_commit_and_push,
        process_missing_module_docstrings,
    ],
    "namespace_kwargs": {
        "title": "Package Configurations",
        "description": "Utils to package and publish.",
    },
}


def main():
    import argh  # pip install argh

    argh.dispatch_commands(argh_kwargs.get("functions", None))


if __name__ == "__main__":
    main()
