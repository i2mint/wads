"""Canonical registry of CI secret names for wads-managed projects.

This module is the single source of truth for the *transport* layer of wads
CI secrets: what the reusable workflow (``uv-ci.yml``) declares in
``on.workflow_call.secrets`` and what the caller stub passes.

Transport: named by default, one JSON secret on request
-------------------------------------------------------
A GitHub *reusable* workflow's secret interface (``on.workflow_call.secrets``)
must be **static YAML** — it is parsed before any job runs and cannot be
parametrized from ``pyproject.toml``. ``secrets: inherit`` is documented to
work only when caller and callee share an org/enterprise, so it is unusable
for personal-account repos calling an ``i2mint``-owned workflow.

**Named (the default).** The workflow declares a *superset* of optional
secret names (:data:`DEFAULT_CI_SECRETS`), and each repo's stub passes, by
name, only ``PYPI_PASSWORD`` plus the backing secret of each env var its
``[tool.wads.ci.env]`` declares::

    secrets:
      PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

The called workflow receives those secrets and nothing else, each masked by
GitHub on its own. The bundled stub template is named; ``populate`` and every
re-render (``wads-migrate ci-to-stub``, ``ci-on-demand``, ``fleet-stub``)
write a named stub, converting a JSON one, unless ``--transport json`` is
asked for.

A name outside the superset makes GitHub reject the workflow at parse time
with an opaque ``startup_failure`` (issue #63). The superset therefore grows
**additively**: adding a ``required: false`` name never breaks an existing
stub (removing one can). A named stub never passes an out-of-superset name: it
is left out with a note (:func:`named_transport_names`, #107), and a
re-render with no explicit transport falls back to JSON for such a repo
rather than drop a real secret. A name recorded in
``[tool.wads.ci.env].variables`` (``wads-secrets add NAME --variable``) is a
repository variable, needs no transport, and never triggers either.

**JSON (opt-in).** ``wads-migrate ci-to-stub --transport json`` passes one
statically-declared secret, :data:`JSON_TRANSPORT_SECRET`
(``WADS_CI_SECRETS_JSON``), whose value is the caller's whole ``secrets``
context::

    secrets:
      WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}

Any secret name then reaches the workflow — but so does every secret the repo
can read, org-level ones included, and serialising the whole ``secrets``
context into a workflow in another repository is structurally what a
secret-exfiltration workflow looks like. GitHub's malicious-workflow scanner
holds such runs (``action_required``, zero jobs, no log, and the REST approve
endpoint refuses them; issues #74, #88, #101). It was seen first on new
repositories and later on an existing one; switching to named made the next
push run every time. Two details of the JSON form, verified empirically
(issue #63):

* **Double encoding** (``toJSON(toJSON(...))``) makes the transported value a
  *single-line* JSON string. A multiline secret is masked per line, and the
  pretty-printed form's ``{`` / ``}`` lines would become global masks that
  mangle every brace in the job log.
* **Re-masking**: values extracted from the blob are *not* automatically
  masked in the callee, so the ``export-ci-env`` action emits
  ``::add-mask::`` for each secret-sourced value before exporting it.

So there are two layers:

* **Transport** — named (default) or the JSON secret (opt-in), rendered into
  static YAML. Plumbing.
* **Env-assignment** — pyproject-driven, exact, per-repo: *which* transported
  secrets land in the job env, and which are required (see
  :mod:`wads.ci_config` and the ``export-ci-env`` action). Nothing is exported
  unless declared there. The thing users tune.

Keeping the names here (Python) and *rendering* them into the YAML (with a
test pinning the YAML to this module) gives a single SSOT while respecting
GitHub's parse-time-literal constraint.
"""

import re
import sys as _sys

# The single statically-declared secret through which an opt-in JSON-transport
# stub passes the caller's whole `secrets` context (double-encoded JSON; see
# the module docstring).
JSON_TRANSPORT_SECRET = "WADS_CI_SECRETS_JSON"

# The caller-side expression for the JSON transport. Double toJSON keeps the
# value single-line so per-line masking cannot register `{` / `}` as masks.
JSON_TRANSPORT_EXPRESSION = "${{ toJSON(toJSON(secrets)) }}"

# ---------------------------------------------------------------------------
# The superset of names a named-transport stub may pass — ADDITIVE ONLY.
#
# Grouped only for human readability; the public value is the flat, de-duped,
# order-preserving tuple ``DEFAULT_CI_SECRETS`` built below. Adding a name is
# safe for every existing stub (uv-ci.yml declares each one `required: false`);
# removing one breaks any stub that passes it. After adding, regenerate the
# uv-ci.yml block from render_workflow_call_secrets() (a test pins them equal).
# ---------------------------------------------------------------------------

_PUBLISHING = (
    "PYPI_PASSWORD",  # wads-historical name; it is a PyPI *token*. Required to publish.
    "TEST_PYPI_PASSWORD",
    "NPM_TOKEN",
    "SSH_PRIVATE_KEY",
    "CODECOV_TOKEN",
    "DOCKERHUB_USERNAME",
    "DOCKERHUB_TOKEN",
)

_LLM_AND_AI = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "PERPLEXITY_API_KEY",
    "REPLICATE_API_TOKEN",
    "TOGETHER_API_KEY",
    "XAI_API_KEY",
    "FAL_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
)

_AGENT_AND_SEARCH = (
    "TAVILY_API_KEY",
    "COMPOSIO_API_KEY",
    "SKILLSDIRECTORY_API_KEY",
    "NEWSDATA_API_KEY",
    "LANGSMITH_API_KEY",
)

_HUGGINGFACE_AND_DATA = (
    "HF_TOKEN",
    "HF_WRITE_TOKEN",  # custom; HF's own convention is HF_TOKEN.
    "HUGGINGFACE_TOKEN",  # legacy alias of HF_TOKEN.
    "KAGGLE_USERNAME",
    "KAGGLE_KEY",
    "WANDB_API_KEY",
    "PINECONE_API_KEY",
)

_AUDIO_AND_MEDIA = (
    "ELEVEN_API_KEY",  # user's spelling
    "ELEVENLABS_API_KEY",  # official SDK env var
    "SUNO_API_KEY",  # third-party; no official API convention
    "SPOTIFY_API_CLIENT_ID",  # user's spelling
    "SPOTIFY_API_CLIENT_SECRET",
    "SPOTIPY_CLIENT_ID",  # spotipy's official env vars
    "SPOTIPY_CLIENT_SECRET",
)

_FINANCE = (
    "ALPACA_API_KEY",  # user's spelling
    "ALPACA_SECRET_KEY",
    "APCA_API_KEY_ID",  # alpaca-py's official env vars
    "APCA_API_SECRET_KEY",
)

_CLOUD = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GCP_SA_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS_JSON",
)

_MESSAGING_AND_STORAGE = (
    "SLACK_BOT_TOKEN",
    "SLACK_WEBHOOK_URL",
    "DISCORD_WEBHOOK_URL",
    "TELEGRAM_BOT_TOKEN",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "SENDGRID_API_KEY",
    "STRIPE_SECRET_KEY",
    "DATABASE_URL",
    "MONGODB_URI",
    "REDIS_URL",
)

_GROUPS = (
    _PUBLISHING,
    _LLM_AND_AI,
    _AGENT_AND_SEARCH,
    _HUGGINGFACE_AND_DATA,
    _AUDIO_AND_MEDIA,
    _FINANCE,
    _CLOUD,
    _MESSAGING_AND_STORAGE,
)


def _dedupe_preserving_order(names):
    """Yield names once each, preserving first-seen order.

    >>> list(_dedupe_preserving_order(["A", "B", "A", "C", "B"]))
    ['A', 'B', 'C']
    """
    seen = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            yield name


DEFAULT_CI_SECRETS = tuple(
    _dedupe_preserving_order(name for group in _GROUPS for name in group)
)
"""Ordered, de-duplicated superset of names a named-transport stub may pass (additive)."""

WORKFLOW_CALL_SECRETS = (JSON_TRANSPORT_SECRET, *DEFAULT_CI_SECRETS)
"""Every secret ``uv-ci.yml`` declares: the opt-in JSON transport secret + the superset."""


# ---------------------------------------------------------------------------
# Name normalization / validation
# ---------------------------------------------------------------------------

# A valid GitHub Actions secret / env-var name. GitHub additionally reserves the
# ``GITHUB_`` prefix for its own secrets, which we reject explicitly below.
_VALID_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

# Characters allowed in a *name-like* input before normalization. Anything else
# (``/``, ``+``, ``=``, ``:`` ...) signals a pasted secret *value*, which we
# refuse — the whole point of forcing UPPER_SNAKE names is to make it hard to
# accidentally commit a secret value.
_NAMELIKE_RE = re.compile(r"^[A-Za-z0-9_.\- ]+$")

_MAX_NAME_LEN = 64


class InvalidSecretName(ValueError):
    """Raised when a string cannot be a safe, valid secret/env-var name."""


def normalize_secret_name(name: str) -> str:
    """Force ``name`` to a valid ``UPPER_SNAKE`` secret/env-var name.

    Hyphens, dots and spaces become underscores; the result is upper-cased.
    Inputs that look like a *value* rather than a *name* are rejected, to guard
    against accidentally committing a secret value.

    >>> normalize_secret_name("my-api.key")
    'MY_API_KEY'
    >>> normalize_secret_name("OPENAI_API_KEY")
    'OPENAI_API_KEY'
    >>> normalize_secret_name("  hf token  ")
    'HF_TOKEN'

    Rejects value-looking and reserved inputs:

    >>> normalize_secret_name("sk-proj-aBc/123+xyz=")  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    InvalidSecretName: ...
    >>> normalize_secret_name("GITHUB_TOKEN")  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    InvalidSecretName: ...
    """
    if not isinstance(name, str):
        raise InvalidSecretName(f"secret name must be a string, got {type(name)}")
    stripped = name.strip()
    if not stripped:
        raise InvalidSecretName("secret name must not be empty")
    if len(stripped) > _MAX_NAME_LEN:
        raise InvalidSecretName(
            f"{stripped[:12]!r}... is too long to be a name ({len(stripped)} > "
            f"{_MAX_NAME_LEN}); did you paste a secret value?"
        )
    if not _NAMELIKE_RE.match(stripped):
        raise InvalidSecretName(
            f"{name!r} contains characters not allowed in a name; "
            "did you paste a secret value? (names use letters, digits, _ - . space)"
        )
    normalized = re.sub(r"[\s.\-]+", "_", stripped).upper()
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not _VALID_NAME_RE.match(normalized):
        raise InvalidSecretName(f"{name!r} does not normalize to a valid name")
    if normalized.startswith("GITHUB_"):
        raise InvalidSecretName(
            "the GITHUB_ prefix is reserved by GitHub; GITHUB_TOKEN is provided "
            "automatically and must not be declared as a CI secret"
        )
    return normalized


def is_valid_secret_name(name: str) -> bool:
    """Return ``True`` iff ``name`` is already a safe, valid secret name.

    >>> is_valid_secret_name("OPENAI_API_KEY")
    True
    >>> is_valid_secret_name("my-key")
    False
    >>> is_valid_secret_name("GITHUB_TOKEN")
    False
    """
    try:
        return normalize_secret_name(name) == name
    except InvalidSecretName:
        return False


# ---------------------------------------------------------------------------
# YAML renderers (used to keep the static workflow/stub YAML in sync with the
# Python SSOT; pinned by a drift test).
# ---------------------------------------------------------------------------


def render_workflow_call_secrets(
    names=WORKFLOW_CALL_SECRETS, *, indent: int = 4
) -> str:
    """Render the ``on.workflow_call.secrets:`` body for the reusable workflow.

    Every secret is declared ``required: false`` — the publish job enforces
    ``PYPI_PASSWORD`` at run time with a clear message, and the export action
    enforces any repo-declared ``required_envvars``.

    >>> print(render_workflow_call_secrets(["PYPI_PASSWORD", "OPENAI_API_KEY"]))
        PYPI_PASSWORD:
          required: false
        OPENAI_API_KEY:
          required: false
    """
    pad = " " * indent
    lines = []
    for name in names:
        lines.append(f"{pad}{name}:")
        lines.append(f"{pad}  required: false")
    return "\n".join(lines)


def render_stub_secrets_passthrough(
    names=DEFAULT_CI_SECRETS, *, indent: int = 6
) -> str:
    """Render a caller stub's *named* ``secrets:`` pass-through block (the default).

    >>> print(render_stub_secrets_passthrough(["PYPI_PASSWORD", "NPM_TOKEN"]))
          PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
    """
    pad = " " * indent
    return "\n".join(f"{pad}{name}: ${{{{ secrets.{name} }}}}" for name in names)


def render_stub_json_transport(*, indent: int = 6) -> str:
    """Render the caller stub's JSON-transport ``secrets:`` line (opt-in).

    >>> print(render_stub_json_transport())
          WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}
    """
    pad = " " * indent
    return f"{pad}{JSON_TRANSPORT_SECRET}: {JSON_TRANSPORT_EXPRESSION}"


# The comment + `secrets:` header of each transport. The bundled stub template
# carries NAMED_TRANSPORT_COMMENT verbatim (a test pins it), and
# stub_with_transport swaps one region for the other.
NAMED_TRANSPORT_COMMENT = """\
    # Transport (named): passes ONLY the secrets listed below — PYPI_PASSWORD
    # (for the publish job) plus the secret behind each env var declared in
    # [tool.wads.ci.env]. `wads-secrets add VAR_NAME` declares a var and adds
    # its secret here. Every listed name must be declared by the reusable
    # workflow (the superset in wads/ci_secrets.py) or GitHub rejects this
    # workflow at parse time; a missing name is a one-line addition there.
    # (Cross-owner `secrets: inherit` does not propagate secrets, so it
    # cannot replace this list.)
    #
    # Opt-in alternative: `wads-migrate ci-to-stub --transport json` passes
    # this repo's WHOLE secrets context — every secret it can read, including
    # org-level ones — as one WADS_CI_SECRETS_JSON secret. GitHub's
    # malicious-workflow scanner may hold runs that do that: `action_required`,
    # zero jobs, no log (i2mint/wads#74, #101).
    #
    # *Which* of these become job env vars — and which are required — is
    # driven entirely by [tool.wads.ci.env] in pyproject.toml; nothing is
    # exported unless declared there. Non-sensitive values don't need a secret:
    # use [tool.wads.ci.env].defaults (committed literals) or a repository
    # *variable* (`gh variable set NAME`) — declared names fall back to
    # repo variables automatically.
    secrets:
"""

JSON_TRANSPORT_COMMENT = """\
    # Transport (JSON, opt-in): this repo's whole `secrets` context, serialized
    # into the one secret the reusable workflow declares. Double-encoded
    # (toJSON twice) so the value is a single line — a multiline secret would
    # register its `{` and `}` lines as global log masks. Any secret name
    # works, but EVERY secret this repo can read (org-level ones included)
    # reaches the called workflow, and GitHub's malicious-workflow scanner may
    # hold the runs: `action_required`, zero jobs, no log (i2mint/wads#74,
    # #101). `wads-migrate ci-to-stub` (no --transport) writes the default
    # named transport instead, when every name [tool.wads.ci.env] declares
    # is in the wads superset.
    #
    # *Which* secrets become job env vars — and which are required — is
    # driven entirely by [tool.wads.ci.env] in pyproject.toml; nothing is
    # exported unless declared there.
    secrets:
"""

# A stub's transport region: the comment lines directly above the `ci` job's
# `secrets:` header, the header, and its entries (lines indented deeper than it,
# with any blank or comment lines between them).
_TRANSPORT_REGION_RE = re.compile(
    r"(?:^    #[^\n]*\n)*"
    r"^    secrets:[ \t]*\n"
    r"(?:^      [^\n]*(?:\n|\Z)"
    r"|^[ \t]*(?:#[^\n]*)?\n(?=(?:[ \t]*(?:#[^\n]*)?\n)*      ))*",
    re.MULTILINE,
)


def stub_transport(stub: str) -> str:
    """The secrets transport of a stub's content: ``"json"`` or ``"named"``.

    >>> stub_transport("    secrets:\\n" + render_stub_json_transport() + "\\n")
    'json'
    >>> stub_transport("    secrets:\\n      PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}\\n")
    'named'
    """
    return "json" if f"{JSON_TRANSPORT_SECRET}:" in stub else "named"


def stub_with_transport(
    stub: str, *, transport: str = "named", names=("PYPI_PASSWORD",)
) -> str:
    r"""Rewrite a stub's secrets region to the given transport.

    Works on a stub of either transport, so it converts JSON to named, named
    to JSON, and re-lists a named stub's names; the comment lines directly
    above ``secrets:`` are replaced too, so a stub never describes a transport
    it does not use. ``names`` is used by the named transport only. A stub
    whose ``ci`` job has no ``secrets:`` mapping block (``secrets: inherit``,
    say) raises ``ValueError``.

    >>> json_stub = (
    ...     "jobs:\n  ci:\n    uses: x\n    # Transport: whole context.\n"
    ...     "    secrets:\n" + render_stub_json_transport() + "\n"
    ... )
    >>> named = stub_with_transport(json_stub, names=["PYPI_PASSWORD", "HF_TOKEN"])
    >>> named.endswith("      HF_TOKEN: ${{ secrets.HF_TOKEN }}\n")
    True
    >>> "toJSON" in named, stub_transport(named)
    (False, 'named')
    >>> back = stub_with_transport(named, transport="json")
    >>> stub_transport(back), "HF_TOKEN" in back
    ('json', False)
    >>> stub_with_transport(back, names=["PYPI_PASSWORD"]) == stub_with_transport(
    ...     json_stub, names=["PYPI_PASSWORD"])
    True
    """
    if transport == "named":
        region = NAMED_TRANSPORT_COMMENT + render_stub_secrets_passthrough(names)
    elif transport == "json":
        region = JSON_TRANSPORT_COMMENT + render_stub_json_transport()
    else:
        raise ValueError(f"transport must be 'json' or 'named', got {transport!r}")
    new_stub, n_replaced = _TRANSPORT_REGION_RE.subn(
        lambda _: region + "\n", stub, count=1
    )
    if n_replaced != 1:
        raise ValueError(
            "not a wads CI stub: found no `secrets:` block under the `ci` job"
        )
    return new_stub


def stub_with_named_transport(stub: str, names) -> str:
    r"""Rewrite a stub's secrets region to the named transport, passing ``names``.

    >>> stub = "jobs:\n  ci:\n    secrets:\n" + render_stub_json_transport() + "\n"
    >>> stub_with_named_transport(stub, ["PYPI_PASSWORD"]).endswith(
    ...     "      PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}\n")
    True
    """
    return stub_with_transport(stub, transport="named", names=names)


def named_transport_names(names) -> list:
    """The ``names`` a named-transport stub can pass; the rest are left out, loudly.

    A named stub may only pass names in the superset
    (:data:`DEFAULT_CI_SECRETS`): one more line and GitHub rejects the whole
    workflow at parse time (issue #63). So a name outside it is *left out* of
    the stub rather than written there. It can then reach CI only as a
    repository variable (declared env vars fall back to ``vars``). A note on
    stderr lists what was left out and how to pass it (#107). Names recorded
    in ``[tool.wads.ci.env].variables`` never get here: they are not secrets.
    Order-preserving.

    >>> named_transport_names(["PYPI_PASSWORD", "HF_TOKEN"])
    ['PYPI_PASSWORD', 'HF_TOKEN']
    """
    passable = [n for n in names if n in DEFAULT_CI_SECRETS]
    left_out = [n for n in names if n not in DEFAULT_CI_SECRETS]
    if left_out:
        print(
            f"note: the stub does not pass {left_out}: they are outside the wads "
            f"secrets superset, and a named stub passing them could not start "
            f"(i2mint/wads#63). They reach CI only as repository variables. "
            f"For each one:\n"
            f"  - not sensitive: `wads-secrets add NAME --variable` (sets the "
            f"repo variable and records it in [tool.wads.ci.env].variables, "
            f"which silences this note); or\n"
            f"  - a real secret: add it to the superset in wads "
            f"(wads/ci_secrets.py; additions are safe for every stub; if it "
            f"is already there, upgrade wads), or opt into the JSON transport (`wads-migrate ci-to-stub "
            f"--transport json`, whose runs GitHub may hold: i2mint/wads#74, "
            f"#101).",
            file=_sys.stderr,
        )
    return passable


def warn_names_outside_superset(names) -> list:
    """Warn loudly for names a named-transport stub cannot legally pass.

    A caller may only pass secrets the reusable workflow declares. With
    ``transport="named"`` that universe is the superset in
    :data:`wads.ci_secrets.DEFAULT_CI_SECRETS`; a stub naming anything outside
    it produces a workflow GitHub rejects at parse time — zero jobs, an opaque
    ``startup_failure`` (issue #63). Returns the offending names.
    """
    outside = [n for n in names if n not in DEFAULT_CI_SECRETS]
    for name in outside:
        print(
            f"warning: {name!r} is not in the wads secrets superset, so a stub "
            f"passing it by name CANNOT START (GitHub rejects the workflow at "
            f"parse time with `startup_failure`). Either:\n"
            f"  - if the value is not actually sensitive, store it as a "
            f"repository VARIABLE (`gh variable set {name}`) — declared env "
            f"vars fall back to repo variables automatically; or\n"
            f"  - add {name!r} to the superset in wads (wads/ci_secrets.py; "
            f"additions are safe for every stub); it reaches `@master` "
            f"stubs at merge and pinned stubs from the next tag; or\n"
            f"  - opt into the JSON transport (`wads-migrate ci-to-stub "
            f"--transport json`), which passes every secret (but GitHub may "
            f"hold its runs, i2mint/wads#74, #101); or\n"
            f"  - keep the inline workflow (`wads-migrate ci-to-uv`, don't "
            f"stub-ify).",
            file=_sys.stderr,
        )
    return outside
