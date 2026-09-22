# wads.templating

Declarative, template-source-driven generation engine.

The core idea (issue #32, originally #3): a *template source* is any
`Mapping[str, str]` mapping a relative path to template *content*. Three
concrete kinds are supported, exactly matching the original spec:

- an **in-memory mapping** – a plain `dict` (or one loaded from JSON/YAML),
- a **local filesystem folder** – [`FilesystemTemplateSource`](#wads.templating.FilesystemTemplateSource),
- a **remote folder** hosted on GitHub – [`GithubTemplateSource`](#wads.templating.GithubTemplateSource).

Because a template source is just a `Mapping`, any key-value store (including
`dol`-style stores) can be used as one without wads depending on it.

Rendering is a thin layer over Jinja2 using **custom delimiters** so template
markup never collides with GitHub Actions `${{ ... }}` expressions or shell
`${...}`:

| Jinja2 default   | wads delimiter   |
|------------------|------------------|
| `{{ var }}`      | `<< var >>`      |
| `{% block %}`    | `<% block %>`    |
| `{# comment #}`  | `<# comment #>`  |

A small set of *render strategies* lets the engine reproduce historical wads
output exactly: `copy` (verbatim), `jinja` (Jinja2 with the delimiters
above), and `placeholder` (legacy `#TOKEN#` substitution kept for old CI
templates).

An [`Artifact`](#wads.templating.Artifact) declaratively describes one generated file: its target
path, how its content is produced, and an optional condition. A *profile* is
just a list of artifacts; [`generate()`](#wads.templating.generate) walks one and writes the files,
honoring an `overwrite` set and recording actions on an optional tracker.

```pycon
>>> source = {"greeting.txt": "Hello << name >>!"}
>>> render(source["greeting.txt"], {"name": "world"})
'Hello world!'
```

### Module Attributes

| [`JINJA_DELIMITERS`](#wads.templating.JINJA_DELIMITERS)   | Jinja2 delimiters chosen to avoid colliding with <br/><br/>```<br/>``<br/>```<br/><br/>${{ .   |
|---------------------------------------------------------------------|------------------------------------------------------------------------------------------------|

### Functions

| [`apply_placeholders`](#wads.templating.apply_placeholders)(content, mapping)         | Legacy `#TOKEN#` substitution used by the older CI templates.                              |
|-----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| [`generate`](#wads.templating.generate)(target_dir, artifacts, context, \*) | Apply a list of [`Artifact`](#wads.templating.Artifact) to `target_dir`. |
| [`make_jinja_env`](#wads.templating.make_jinja_env)(\*\*overrides)                | Build a Jinja2 environment with wads's custom delimiters.                                  |
| [`render`](#wads.templating.render)(content, context, \*[, env])          | Render `content` as a Jinja2 template with wads delimiters.                                |

### Classes

| [`Artifact`](#wads.templating.Artifact)(target, content[, when, binary])      | One file to generate within a project.                                  |
|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`FilesystemTemplateSource`](#wads.templating.FilesystemTemplateSource)(root, \*[, encoding]) | A template source backed by a local folder.                             |
| [`GenerationResult`](#wads.templating.GenerationResult)([added, skipped, errored])    | Outcome of [`generate()`](#wads.templating.generate). |
| [`GithubTemplateSource`](#wads.templating.GithubTemplateSource)(repo, \*[, ref, subdir])  | A template source backed by a folder in a GitHub repository.            |

### *class* wads.templating.Artifact(target, content, when=None, binary=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One file to generate within a project.

* **Parameters:**
  * **target** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – relative path of the file in the generated project.
  * **content** ([`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)], [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]) – a callable `context -> str | None` producing the file
    text (`None` to skip). Use the `from_*` constructors for the common
    `copy` / `jinja` / `placeholder` strategies.
  * **when** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)], [`bool`](https://docs.python.org/3/builtins/functions.html#bool)]]) – optional predicate `context -> bool` gating generation.
  * **binary** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – if True, `content` returns `bytes` and is written binary.

#### *classmethod* from_copy(target, source_key, source, \*\*kw)

Artifact that copies `source[source_key]` verbatim.

#### *classmethod* from_jinja(target, source_key, source, \*\*kw)

Artifact that renders `source[source_key]` with Jinja2.

#### *classmethod* from_placeholder(target, source_key, source, placeholders, \*\*kw)

Artifact that applies `#TOKEN#` substitution to a template.

### *class* wads.templating.FilesystemTemplateSource(root, , encoding='utf-8')

Bases: [`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)

A template source backed by a local folder.

Keys are POSIX-style relative paths of the files under `root`; values are
the (text) file contents, read lazily on access.

```pycon
>>> import tempfile, os
>>> d = tempfile.mkdtemp()
>>> _ = open(os.path.join(d, "a.txt"), "w").write("A")
>>> src = FilesystemTemplateSource(d)
>>> src["a.txt"]
'A'
>>> list(src)
['a.txt']
```

### *class* wads.templating.GenerationResult(added=<factory>, skipped=<factory>, errored=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Outcome of [`generate()`](#wads.templating.generate).

### *class* wads.templating.GithubTemplateSource(repo, , ref='master', subdir='')

Bases: [`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)

A template source backed by a folder in a GitHub repository.

Files are fetched lazily from `raw.githubusercontent.com`. Uses the
standard library only (no `requests` dependency) so it stays usable in a
light install.

* **Parameters:**
  * **repo** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – `"owner/name"` slug.
  * **ref** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – branch, tag, or commit (default `"master"`).
  * **subdir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – folder within the repo to treat as the template root.

Listing (`__iter__` / `__len__`) uses the GitHub trees API and is only
needed when enumerating; direct `source[key]` access does not list.

### wads.templating.JINJA_DELIMITERS *= {'block_end_string': '%>', 'block_start_string': '<%', 'comment_end_string': '#>', 'comment_start_string': '<#', 'variable_end_string': '>>', 'variable_start_string': '<<'}*

Jinja2 delimiters chosen to avoid colliding with `${{ ... }}` (GitHub
Actions) and `${...}` (shell).

### wads.templating.apply_placeholders(content, mapping)

Legacy `#TOKEN#` substitution used by the older CI templates.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> apply_placeholders("name=#NAME#", {"#NAME#": "wads"})
'name=wads'
```

### wads.templating.generate(target_dir, artifacts, context, , overwrite=(), on_add=None, on_skip=None, on_error=None)

Apply a list of [`Artifact`](#wads.templating.Artifact) to `target_dir`.

An artifact is written when its target does not exist *or* its target is in
`overwrite`. Parent directories are created as needed. Each action is
reported through the optional `on_*` callbacks and accumulated in the
returned [`GenerationResult`](#wads.templating.GenerationResult).

* **Return type:**
  [`GenerationResult`](#wads.templating.GenerationResult)

### wads.templating.make_jinja_env(\*\*overrides)

Build a Jinja2 environment with wads’s custom delimiters.

Extra keyword arguments override the defaults (e.g. `undefined`).

### wads.templating.render(content, context, , env=None)

Render `content` as a Jinja2 template with wads delimiters.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> render("v<< major >>.<< minor >>", {"major": 1, "minor": 2})
'v1.2'
```
