"""Licensing"""

from wads import licenses_json_path
import difflib
import json
import os
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse


def resolve_author(
    author: Optional[str] = None,
    pyproject_authors: Optional[list] = None,
    url: Optional[str] = None,
) -> str:
    """
    Resolve the author name following a priority chain.

    Priority order:
    1. If author is explicitly provided, use it
    2. If pyproject_authors is provided, use the first author's name
    3. If url is a GitHub URL, extract the org/user from it
    4. If WADS_DFLT_AUTHOR env variable is set, use it
    5. Return placeholder if nothing else works

    Args:
        author: Explicitly provided author name
        pyproject_authors: List of author dicts from pyproject.toml
        url: Project URL (e.g., GitHub URL)

    Returns:
        Resolved author name or placeholder

    >>> resolve_author(author='John Doe')
    'John Doe'
    >>> resolve_author(pyproject_authors=[{'name': 'Jane Smith'}])
    'Jane Smith'
    >>> resolve_author(url='https://github.com/myorg/myrepo')
    'myorg'
    """
    # 1. Explicit author
    if author:
        return author

    # 2. Authors from pyproject.toml
    if pyproject_authors and isinstance(pyproject_authors, list):
        if pyproject_authors:
            first_author = pyproject_authors[0]
            if isinstance(first_author, dict) and "name" in first_author:
                return first_author["name"]
            elif isinstance(first_author, str):
                return first_author

    # 3. Extract from GitHub URL
    if url:
        # Handle both https and git URLs
        github_patterns = [
            r"https://github\.com/([^/]+)",
            r"git@github\.com:([^/]+)",
            r"http://github\.com/([^/]+)",
        ]
        for pattern in github_patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

    # 4. Environment variable
    env_author = os.environ.get("WADS_DFLT_AUTHOR")
    if env_author:
        return env_author

    # 5. Return placeholder
    return "[fullname]"


def substitute_license_placeholders(
    license_text: str,
    author: Optional[str] = None,
    year: Optional[int] = None,
) -> str:
    """
    Replace placeholders in license text with actual values.

    Common placeholders:
    - [yyyy], [year] -> current year
    - [fullname], [name of copyright owner] -> author name
    - (c) -> © (optional enhancement)

    Args:
        license_text: License text with placeholders
        author: Author/copyright owner name (if None, placeholder remains)
        year: Year for copyright (if None, uses current year)

    Returns:
        License text with substituted values

    >>> text = "Copyright [yyyy] [fullname]"
    >>> result = substitute_license_placeholders(text, author='John', year=2025)
    >>> result
    'Copyright 2025 John'
    """
    if not license_text:
        return license_text

    # Use current year if not provided
    if year is None:
        year = datetime.now().year

    result = license_text

    # Replace year placeholders
    year_patterns = [
        (r"\[yyyy\]", str(year)),
        (r"\[year\]", str(year)),
        (r"\(yyyy\)", str(year)),
    ]

    for pattern, replacement in year_patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # Replace author/name placeholders only if author is provided
    if author and author != "[fullname]":
        name_patterns = [
            r"\[fullname\]",
            r"\[name of copyright owner\]",
            r"\[name\]",
        ]

        for pattern in name_patterns:
            result = re.sub(pattern, author, result, flags=re.IGNORECASE)

    return result


def license_body(license=None, search_name_and_spdx_id=True, refresh=False):
    _license_info = license_info(license, search_name_and_spdx_id, refresh=refresh)
    if _license_info is not None:
        return _license_info["body"]


def require_license(license: str) -> dict:
    """The ``license_info`` of ``license``, or a ``ValueError`` naming the closest keys.

    ``license`` is a key, name or SPDX id, in any case, or a name
    :func:`wads.toml_util.pep639_license` knows (``Apache Software License``). An
    unknown one used to print the key list and carry on to write an empty LICENSE
    (issue #237).

    >>> require_license("mit")["spdx_id"], require_license("APACHE-2.0")["key"]
    ('MIT', 'apache-2.0')
    >>> require_license("Apache Software License")["key"]
    'apache-2.0'
    >>> require_license("apach")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
      ...
    ValueError: 'apach' is not a valid licence key; closest: apache-2.0 (...
    """
    from wads.toml_util import pep639_license

    licenses = licenses_dict()
    spellings = {}  # lowercased key / name / SPDX id -> key
    for info in licenses.values():
        for spelling in (info["key"], info["name"], info["spdx_id"]):
            spellings[str(spelling).lower()] = info["key"]
    spdx = pep639_license(license)  # a string when `license` names an SPDX id
    for candidate in (str(license), spdx if isinstance(spdx, str) else ""):
        if candidate.lower() in spellings:
            return licenses[spellings[candidate.lower()]]
    close = difflib.get_close_matches(str(license).lower(), spellings, n=3, cutoff=0.4)
    keys = list(dict.fromkeys(spellings[c] for c in close))
    suggestion = f"closest: {', '.join(keys)} " if keys else ""
    raise ValueError(
        f"{license!r} is not a valid licence key; {suggestion}"
        f"(all keys: {', '.join(sorted(licenses))})"
    )


def license_info(license=None, search_name_and_spdx_id=True, refresh=False):
    licenses = licenses_dict(refresh=refresh)
    if license not in licenses:
        if search_name_and_spdx_id:
            for ll in licenses.values():
                if license in {ll["name"], ll["spdx_id"]}:
                    return ll
        print("That's not a valid license key. Here is a list of valid license keys:")
        print("\t", *licenses, sep="\n\t")
    else:
        return licenses[license]


def licenses_dict(refresh=False):
    licenses = get_licenses(refresh=refresh)
    return {x["key"]: x for x in licenses}


def get_licenses(refresh=False):
    if refresh:
        try:
            licenses = get_licenses_from_github()
            json.dump(licenses, open(licenses_json_path, "w"))
        except Exception:
            raise

    with open(licenses_json_path) as f:
        return json.load(f)


def get_licenses_from_github():
    """get_licenses_json_from_github
    You need to have a github token placed in the right place for this!
    See pygithub for details.
    ```
    license_jsons = get_licenses_json_from_github()
    ```
    """

    from github import Github

    def gen():
        g = Github()
        license_getter = g.get_licenses()
        i = 0
        while True:
            more = license_getter.get_page(i)
            i += 1
            if len(more) > 0:
                yield more
            else:
                break

    from itertools import chain

    licenses = list(chain.from_iterable(gen()))
    licenses = [ll.raw_data for ll in licenses]
    return licenses
