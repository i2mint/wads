"""Canonical registry of CI secret names for wads-managed projects.

This module is the single source of truth for the *transport* layer of wads
CI secrets: what the reusable workflow (``uv-ci.yml``) declares in
``on.workflow_call.secrets`` and what the caller stub passes.

Transport: one JSON secret (the modern default)
-----------------------------------------------
A GitHub *reusable* workflow's secret interface (``on.workflow_call.secrets``)
must be **static YAML** — it is parsed before any job runs and cannot be
parametrized from ``pyproject.toml``. ``secrets: inherit`` is documented to
work only when caller and callee share an org/enterprise, so it is unusable
for personal-account repos calling an ``i2mint``-owned workflow.

The static-interface constraint is satisfied with a single statically-declared
secret, :data:`JSON_TRANSPORT_SECRET` (``WADS_CI_SECRETS_JSON``), whose value
is the caller's whole ``secrets`` context serialized by the stub::

    secrets:
      WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}

(The documented context-availability table allows the ``secrets`` context in
``jobs.<job_id>.secrets.<id>``, so this expression is legal in the caller.)
With this, *any* secret name a repo has reaches the reusable workflow — there
is no fixed name list to be "outside of", which eliminates the parse-time
``startup_failure`` class of issue #63 entirely.

Two details, both verified empirically (see issue #63):

* **Double encoding** (``toJSON(toJSON(...))``) makes the transported value a
  *single-line* JSON string. A multiline secret is masked per line, and the
  pretty-printed form's ``{`` / ``}`` lines would become global masks that
  mangle every brace in the job log. Single-line ⇒ only the whole blob is
  masked.
* **Re-masking**: individual values extracted from the blob are *not*
  automatically masked in the callee, so the ``export-ci-env`` action emits
  ``::add-mask::`` for each secret-sourced value before exporting it.

*Which* secrets actually land in the job env (and which are required) remains
a separate, dynamic decision driven by ``[tool.wads.ci.env]`` in the
consumer's ``pyproject.toml`` (see :mod:`wads.ci_config` and the
``export-ci-env`` action). Nothing is exported unless declared there.

The named superset (legacy transport, kept for back-compat)
-----------------------------------------------------------
Before the JSON transport, the workflow declared a generous *superset* of
optional secret names (:data:`DEFAULT_CI_SECRETS`) and each repo's stub passed
a named subset. That design failed whenever a repo needed a name outside the
superset — GitHub rejects an undeclared secret at parse time with an opaque
``startup_failure`` (issue #63).

The superset is still declared by ``uv-ci.yml`` so that already-deployed
named-transport stubs keep working, but it is **frozen**: new names should not
be added — a repo that needs a new name should switch to the JSON transport
stub (``wads-migrate ci-to-stub``), which transports everything.

So there are two layers:

* **Transport** — the JSON secret (modern) or the frozen superset (legacy),
  rendered into static YAML. Plumbing.
* **Env-assignment** — pyproject-driven, exact, per-repo. The thing users tune.

Keeping the names here (Python) and *rendering* them into the YAML (with a
test pinning the YAML to this module) gives a single SSOT while respecting
GitHub's parse-time-literal constraint.
"""

import re

# The single statically-declared secret through which a stub transports the
# caller's whole `secrets` context (double-encoded JSON; see module docstring).
JSON_TRANSPORT_SECRET = "WADS_CI_SECRETS_JSON"

# The caller-side expression for the JSON transport. Double toJSON keeps the
# value single-line so per-line masking cannot register `{` / `}` as masks.
JSON_TRANSPORT_EXPRESSION = "${{ toJSON(toJSON(secrets)) }}"

# ---------------------------------------------------------------------------
# The legacy named superset — FROZEN.
#
# Grouped only for human readability; the public value is the flat, de-duped,
# order-preserving tuple ``DEFAULT_CI_SECRETS`` built below. It exists so that
# named-transport stubs deployed before the JSON transport keep working; do
# not widen it — a repo needing a name outside it should regenerate its stub
# (`wads-migrate ci-to-stub`), which transports every secret via
# JSON_TRANSPORT_SECRET.
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
"""Ordered, de-duplicated legacy superset of named CI secrets (frozen)."""

WORKFLOW_CALL_SECRETS = (JSON_TRANSPORT_SECRET, *DEFAULT_CI_SECRETS)
"""Every secret ``uv-ci.yml`` declares: the JSON transport + the legacy superset."""


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
    """Render a caller stub's *named* ``secrets:`` pass-through block (legacy).

    >>> print(render_stub_secrets_passthrough(["PYPI_PASSWORD", "NPM_TOKEN"]))
          PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
    """
    pad = " " * indent
    return "\n".join(f"{pad}{name}: ${{{{ secrets.{name} }}}}" for name in names)


def render_stub_json_transport(*, indent: int = 6) -> str:
    """Render the caller stub's JSON-transport ``secrets:`` line (the default).

    >>> print(render_stub_json_transport())
          WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}
    """
    pad = " " * indent
    return f"{pad}{JSON_TRANSPORT_SECRET}: {JSON_TRANSPORT_EXPRESSION}"
