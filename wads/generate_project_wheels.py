import glob
import os
import re
import subprocess
import sys


def clone_repository(url, branch=None, target_dir=None, quiet=False):
    args = ["git", "clone", "--depth", "1"]
    if quiet:
        args.append("--quiet")
    if branch:
        args.extend(["--branch", branch])
    args.append(url)
    if target_dir:
        args.append(target_dir)
    subprocess.check_output(args).decode().strip()


def _update_file(path, pattern, replace):
    with open(path, "r+") as file:
        content = file.read()
        content_new = re.sub(pattern, replace, content, flags=re.M)
        if content_new == content:
            raise RuntimeError(
                f'File content unchanged. Failed to update file "{path}"!'
            )
        file.seek(0)
        file.write(content_new)
        file.truncate()


def replace_git_urls_from_requirements_file(
    requirements_filepath, github_credentials=None
):
    pattern = r"git\+(ssh:\/\/.*?\.git|https{0,1}:\/\/.*?\.git)@{0,1}(.*){0,1}#egg=(.*)"
    git_info = _replace_git_urls(requirements_filepath, pattern, -1)
    if github_credentials is not None:
        for dep_git_info in git_info:
            repo = dep_git_info["url"].split("github.com/")[-1]
            auth_url = f"{github_credentials}/{repo}"
            dep_git_info.update({"url": auth_url})
    print(git_info)
    return git_info


def replace_git_urls_from_setup_cfg_file(setup_cfg_filepath, github_credentials=None):
    pattern = r"([^\t\s\n]*)\s@\sgit\+(ssh:\/\/.*?\.git|https{0,1}:\/\/.*?\.git)@{0,1}(.*){0,1}"
    git_info = _replace_git_urls(setup_cfg_filepath, pattern)
    if github_credentials is not None:
        for dep_git_info in git_info:
            repo = dep_git_info["url"].split("github.com/")[-1]
            auth_url = f"{github_credentials}/{repo}"
            dep_git_info.update({"url": auth_url})
    print(git_info)
    return git_info


def _replace_git_urls(filepath, pattern, group_idx_offset=0):
    def _get_idx(raw_idx):
        return (raw_idx + group_idx_offset) % 3

    with open(filepath, "r") as file:
        content = file.read()
        git_info = [
            {"name": t[_get_idx(0)], "url": t[_get_idx(1)], "branch": t[_get_idx(2)]}
            for t in re.findall(pattern, content)
        ]
    name_group_idx = _get_idx(0) + 1
    if git_info:
        _update_file(filepath, pattern, rf"\g<{name_group_idx}>")
    return git_info


def generate_project_wheels(project_dir, wheel_generation_dir, github_credentials):
    current_dir = os.getcwd()
    clone_repositories_dir = os.path.join(wheel_generation_dir, "repositories")
    os.mkdir(clone_repositories_dir)
    wheelhouse_dir = os.path.join(wheel_generation_dir, "wheelhouse")
    os.mkdir(wheelhouse_dir)
    git_info = _generate_repository_wheels(
        project_dir, clone_repositories_dir, wheelhouse_dir, github_credentials
    )
    os.chdir(current_dir)
    return git_info


def _generate_repository_wheels(
    current_repository, clone_repositories_dir, wheelhouse_dir, github_credentials
):
    requirements_filepath = os.path.join(current_repository, "requirements.txt")
    setup_cfg_filepath = os.path.join(current_repository, "setup.cfg")
    git_info = []

    if os.path.isfile(requirements_filepath):
        git_info.extend(
            _generate_wheels_from_requirements_file(
                requirements_filepath,
                clone_repositories_dir,
                wheelhouse_dir,
                github_credentials,
            )
        )
    if os.path.isfile(setup_cfg_filepath):
        git_info.extend(
            _generate_wheels_from_setup_cfg_file(
                setup_cfg_filepath,
                clone_repositories_dir,
                wheelhouse_dir,
                github_credentials,
            )
        )
    return git_info


def _generate_wheels_from_requirements_file(
    requirements_filepath, clone_repositories_dir, wheelhouse_dir, github_credentials
):
    git_info = replace_git_urls_from_requirements_file(
        requirements_filepath, github_credentials
    )
    _generation_sub_repositories_wheels(
        git_info, clone_repositories_dir, wheelhouse_dir, github_credentials
    )
    return git_info


def _generate_wheels_from_setup_cfg_file(
    setup_cfg_filepath, clone_repositories_dir, wheelhouse_dir, github_credentials
):
    git_info = replace_git_urls_from_setup_cfg_file(
        setup_cfg_filepath, github_credentials
    )
    _generation_sub_repositories_wheels(
        git_info, clone_repositories_dir, wheelhouse_dir, github_credentials
    )
    return git_info


def _generation_sub_repositories_wheels(
    git_info, clone_repositories_dir, wheelhouse_dir, github_credentials
):
    def get_existing_wheel_names():
        def extract_wheel_name(filepath):
            filename = os.path.basename(filepath)
            wheel_name_search = re.search(pattern, filename)
            if not wheel_name_search:
                raise RuntimeError(
                    f'Failed to extract the wheel name from "{filename}"'
                )
            return wheel_name_search.group(1)

        pattern = r"(.+)-[0-9]*\.[0-9]*\.[0-9]*.*\.whl"
        filepaths = glob.glob(f"{wheelhouse_dir}/*.whl")
        return [extract_wheel_name(filepath) for filepath in filepaths]

    for dep_git_info in git_info:
        dep_name = dep_git_info["name"]
        existing_wheel_names = get_existing_wheel_names()
        if not dep_name in existing_wheel_names:
            target_dir = os.path.join(clone_repositories_dir, dep_name)
            clone_repository(
                url=dep_git_info["url"],
                branch=dep_git_info["branch"],
                target_dir=target_dir,
                quiet=True,
            )
            _generate_repository_wheels(
                target_dir, clone_repositories_dir, wheelhouse_dir, github_credentials
            )
            _run_setup_bdist_wheel(target_dir, wheelhouse_dir)


def _run_setup_bdist_wheel(cwd, dist_dir):
    return subprocess.check_output(
        [sys.executable, "setup.py", "bdist_wheel", f"--dist-dir={dist_dir}"], cwd=cwd
    )
