"""Declarative, template-source-driven generation engine.

The core idea (issue #32, originally #3): a *template source* is any
``Mapping[str, str]`` mapping a relative path to template *content*. Three
concrete kinds are supported, exactly matching the original spec:

- an **in-memory mapping** -- a plain ``dict`` (or one loaded from JSON/YAML),
- a **local filesystem folder** -- :class:`FilesystemTemplateSource`,
- a **remote folder** hosted on GitHub -- :class:`GithubTemplateSource`.

Because a template source is just a ``Mapping``, any key-value store (including
``dol``-style stores) can be used as one without wads depending on it.

Rendering is a thin layer over Jinja2 using **custom delimiters** so template
markup never collides with GitHub Actions ``${{ ... }}`` expressions or shell
``${...}``:

==================  ===================
Jinja2 default      wads delimiter
==================  ===================
``{{ var }}``       ``<< var >>``
``{% block %}``     ``<% block %>``
``{# comment #}``   ``<# comment #>``
==================  ===================

A small set of *render strategies* lets the engine reproduce historical wads
output exactly: ``copy`` (verbatim), ``jinja`` (Jinja2 with the delimiters
above), and ``placeholder`` (legacy ``#TOKEN#`` substitution kept for old CI
templates).

An :class:`Artifact` declaratively describes one generated file: its target
path, how its content is produced, and an optional condition. A *profile* is
just a list of artifacts; :func:`generate` walks one and writes the files,
honoring an ``overwrite`` set and recording actions on an optional tracker.

>>> source = {"greeting.txt": "Hello << name >>!"}
>>> render(source["greeting.txt"], {"name": "world"})
'Hello world!'
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Sequence, Union

# --------------------------------------------------------------------------------------
# Template sources: Mapping[str, str] of relative-path -> template content
# --------------------------------------------------------------------------------------


class FilesystemTemplateSource(Mapping):
    """A template source backed by a local folder.

    Keys are POSIX-style relative paths of the files under ``root``; values are
    the (text) file contents, read lazily on access.

    >>> import tempfile, os
    >>> d = tempfile.mkdtemp()
    >>> _ = open(os.path.join(d, "a.txt"), "w").write("A")
    >>> src = FilesystemTemplateSource(d)
    >>> src["a.txt"]
    'A'
    >>> list(src)
    ['a.txt']
    """

    def __init__(self, root: str, *, encoding: str = "utf-8"):
        self.root = os.path.abspath(os.path.expanduser(root))
        self.encoding = encoding

    def _abspath(self, key: str) -> str:
        return os.path.join(self.root, *key.split("/"))

    def __getitem__(self, key: str) -> str:
        path = self._abspath(key)
        if not os.path.isfile(path):
            raise KeyError(key)
        with open(path, encoding=self.encoding) as f:
            return f.read()

    def __iter__(self):
        for dirpath, _, filenames in os.walk(self.root):
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self.root)
                yield rel.replace(os.sep, "/")

    def __len__(self) -> int:
        return sum(1 for _ in self)


class GithubTemplateSource(Mapping):
    """A template source backed by a folder in a GitHub repository.

    Files are fetched lazily from ``raw.githubusercontent.com``. Uses the
    standard library only (no ``requests`` dependency) so it stays usable in a
    light install.

    :param repo: ``"owner/name"`` slug.
    :param ref: branch, tag, or commit (default ``"master"``).
    :param subdir: folder within the repo to treat as the template root.

    Listing (``__iter__`` / ``__len__``) uses the GitHub trees API and is only
    needed when enumerating; direct ``source[key]`` access does not list.
    """

    def __init__(self, repo: str, *, ref: str = "master", subdir: str = ""):
        self.repo = repo.strip("/")
        self.ref = ref
        self.subdir = subdir.strip("/")

    def _raw_url(self, key: str) -> str:
        prefix = f"{self.subdir}/" if self.subdir else ""
        return f"https://raw.githubusercontent.com/{self.repo}/{self.ref}/{prefix}{key}"

    def __getitem__(self, key: str) -> str:
        from urllib.request import urlopen
        from urllib.error import HTTPError

        try:
            with urlopen(self._raw_url(key)) as resp:
                return resp.read().decode("utf-8")
        except HTTPError as e:
            if e.code == 404:
                raise KeyError(key) from e
            raise

    def __iter__(self):
        import json
        from urllib.request import urlopen

        api = (
            f"https://api.github.com/repos/{self.repo}/git/trees/{self.ref}?recursive=1"
        )
        with urlopen(api) as resp:
            tree = json.loads(resp.read().decode("utf-8")).get("tree", [])
        prefix = f"{self.subdir}/" if self.subdir else ""
        for entry in tree:
            if entry.get("type") != "blob":
                continue
            path = entry["path"]
            if prefix:
                if not path.startswith(prefix):
                    continue
                yield path[len(prefix) :]
            else:
                yield path

    def __len__(self) -> int:
        return sum(1 for _ in self)


TemplateSource = Mapping  # any Mapping[str, str]


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------

#: Jinja2 delimiters chosen to avoid colliding with ``${{ ... }}`` (GitHub
#: Actions) and ``${...}`` (shell).
JINJA_DELIMITERS = dict(
    variable_start_string="<<",
    variable_end_string=">>",
    block_start_string="<%",
    block_end_string="%>",
    comment_start_string="<#",
    comment_end_string="#>",
)


def make_jinja_env(**overrides):
    """Build a Jinja2 environment with wads's custom delimiters.

    Extra keyword arguments override the defaults (e.g. ``undefined``).
    """
    import jinja2

    kwargs = dict(
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
        **JINJA_DELIMITERS,
    )
    kwargs.update(overrides)
    return jinja2.Environment(**kwargs)


def render(content: str, context: Mapping, *, env=None) -> str:
    """Render ``content`` as a Jinja2 template with wads delimiters.

    >>> render("v<< major >>.<< minor >>", {"major": 1, "minor": 2})
    'v1.2'
    """
    env = env or make_jinja_env()
    return env.from_string(content).render(**dict(context))


def apply_placeholders(content: str, mapping: Mapping[str, str]) -> str:
    """Legacy ``#TOKEN#`` substitution used by the older CI templates.

    >>> apply_placeholders("name=#NAME#", {"#NAME#": "wads"})
    'name=wads'
    """
    for token, value in mapping.items():
        content = content.replace(token, value)
    return content


# --------------------------------------------------------------------------------------
# Declarative artifacts and the generation loop
# --------------------------------------------------------------------------------------

# A content producer turns the resolved config/context into the file's text.
# Returning ``None`` means "skip this artifact".
ContentProducer = Callable[[Mapping], Optional[str]]


@dataclass
class Artifact:
    """One file to generate within a project.

    :param target: relative path of the file in the generated project.
    :param content: a callable ``context -> str | None`` producing the file
        text (``None`` to skip). Use the ``from_*`` constructors for the common
        ``copy`` / ``jinja`` / ``placeholder`` strategies.
    :param when: optional predicate ``context -> bool`` gating generation.
    :param binary: if True, ``content`` returns ``bytes`` and is written binary.
    """

    target: str
    content: ContentProducer
    when: Optional[Callable[[Mapping], bool]] = None
    binary: bool = False

    @classmethod
    def from_copy(cls, target: str, source_key: str, source: TemplateSource, **kw):
        """Artifact that copies ``source[source_key]`` verbatim."""
        return cls(target, lambda ctx: source[source_key], **kw)

    @classmethod
    def from_jinja(cls, target: str, source_key: str, source: TemplateSource, **kw):
        """Artifact that renders ``source[source_key]`` with Jinja2."""
        return cls(target, lambda ctx: render(source[source_key], ctx), **kw)

    @classmethod
    def from_placeholder(
        cls,
        target: str,
        source_key: str,
        source: TemplateSource,
        placeholders: Callable[[Mapping], Mapping[str, str]],
        **kw,
    ):
        """Artifact that applies ``#TOKEN#`` substitution to a template."""
        return cls(
            target,
            lambda ctx: apply_placeholders(source[source_key], placeholders(ctx)),
            **kw,
        )


@dataclass
class GenerationResult:
    """Outcome of :func:`generate`."""

    added: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    errored: list = field(default_factory=list)


def generate(
    target_dir: str,
    artifacts: Sequence[Artifact],
    context: Mapping,
    *,
    overwrite: Union[Sequence[str], set, str] = (),
    on_add: Optional[Callable[[str], None]] = None,
    on_skip: Optional[Callable[[str], None]] = None,
    on_error: Optional[Callable[[str, Exception], None]] = None,
) -> GenerationResult:
    """Apply a list of :class:`Artifact` to ``target_dir``.

    An artifact is written when its target does not exist *or* its target is in
    ``overwrite``. Parent directories are created as needed. Each action is
    reported through the optional ``on_*`` callbacks and accumulated in the
    returned :class:`GenerationResult`.
    """
    if isinstance(overwrite, str):
        overwrite = {overwrite}
    else:
        overwrite = set(overwrite)

    result = GenerationResult()

    def should_write(target: str) -> bool:
        return target in overwrite or not os.path.isfile(
            os.path.join(target_dir, target)
        )

    for art in artifacts:
        if art.when is not None and not art.when(context):
            continue
        if not should_write(art.target):
            result.skipped.append(art.target)
            if on_skip:
                on_skip(art.target)
            continue
        try:
            content = art.content(context)
            if content is None:
                continue
            dest = os.path.join(target_dir, art.target)
            parent = os.path.dirname(dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            mode = "wb" if art.binary else "w"
            with open(dest, mode) as f:
                f.write(content)
            result.added.append(art.target)
            if on_add:
                on_add(art.target)
        except Exception as e:  # noqa: BLE001 - report, don't abort the batch
            result.errored.append((art.target, str(e)))
            if on_error:
                on_error(art.target, e)

    return result
