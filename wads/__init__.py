"""
Console Scripts
---------------

To see available commands
::

    wads --help

"""

import setuptools  # to avoid a warning due to distutils_patch.py
import os
import json

root_dir = os.path.dirname(__file__)
root_dir_name = os.path.basename(root_dir)
rjoin = lambda *paths: os.path.join(root_dir, *paths)

data_dir = rjoin("data")
licenses_json_path = rjoin(data_dir, "github_licenses.json")
setup_tpl_path = rjoin(data_dir, "setup_tpl")
gitignore_tpl_path = rjoin(data_dir, ".gitignore_tpl")
github_ci_tpl_path = rjoin(data_dir, "github_ci_tpl.yml")
gitlab_ci_tpl_path = rjoin(data_dir, "gitlab_ci_tpl.yml")
github_ci_tpl_deploy_path = rjoin(data_dir, "github_ci_tpl_deploy.yml")
github_ci_tpl_publish_path = rjoin(data_dir, "github_ci_tpl_publish.yml")

pkg_dir = os.path.dirname(root_dir)
pkg_join = lambda *paths: os.path.join(pkg_dir, *paths)

# TODO: Change to use ini format? (Or yaml or toml?)
wads_configs_file = rjoin(data_dir, "wads_configs.json")
try:
    wads_configs = json.load(open(wads_configs_file))
except FileNotFoundError:
    wads_configs = {
        "populate_dflts": {
            "description": "There is a bit of an air of mystery around this project...",
            "root_url": None,
            "author": None,
            "license": "mit",
            "description_file": "README.md",
            "long_description": "file:README.md",
            "long_description_content_type": "text/markdown",
            "keywords": None,
            "install_requires": None,
            "verbose": None,
            "version": "0.0.1",
            "project_type": "lib",
        }
    }

pkg_path_names = (".gitignore", "setup.py")

from wads.populate import populate_pkg_dir


def main():
    import argh  # pip install argh

    from wads.pack import argh_kwargs as pack_kw

    # from wads.docs_gen import argh_kwargs as docs_gen_kw

    parser = argh.ArghParser()
    parser.add_commands(**pack_kw)
    # parser.add_commands(**docs_gen_kw)
    parser.dispatch()


if __name__ == "__main__":
    main()
