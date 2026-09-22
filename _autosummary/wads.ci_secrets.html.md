# wads.ci_secrets

Canonical registry of CI secret names for wads-managed projects.

This module is the single source of truth for the *transport* layer of wads
CI secrets: what the reusable workflow (`uv-ci.yml`) declares in
`on.workflow_call.secrets` and what the caller stub passes.

## Transport: one JSON secret (the modern default)

A GitHub *reusable* workflow’s secret interface (`on.workflow_call.secrets`)
must be **static YAML** — it is parsed before any job runs and cannot be
parametrized from `pyproject.toml`. `secrets: inherit` is documented to
work only when caller and callee share an org/enterprise, so it is unusable
for personal-account repos calling an `i2mint`-owned workflow.

The static-interface constraint is satisfied with a single statically-declared
secret, `JSON_TRANSPORT_SECRET` (`WADS_CI_SECRETS_JSON`), whose value
is the caller’s whole `secrets` context serialized by the stub:

```default
secrets:
  WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}
```

(The documented context-availability table allows the `secrets` context in
`jobs.<job_id>.secrets.<id>`, so this expression is legal in the caller.)
With this, *any* secret name a repo has reaches the reusable workflow — there
is no fixed name list to be “outside of”, which eliminates the parse-time
`startup_failure` class of issue #63 entirely.

Two details, both verified empirically (see issue #63):

* **Double encoding** (`toJSON(toJSON(...))`) makes the transported value a
  *single-line* JSON string. A multiline secret is masked per line, and the
  pretty-printed form’s `{` / `}` lines would become global masks that
  mangle every brace in the job log. Single-line ⇒ only the whole blob is
  masked.
* **Re-masking**: individual values extracted from the blob are *not*
  automatically masked in the callee, so the `export-ci-env` action emits
  `::add-mask::` for each secret-sourced value before exporting it.

*Which* secrets actually land in the job env (and which are required) remains
a separate, dynamic decision driven by `[tool.wads.ci.env]` in the
consumer’s `pyproject.toml` (see [`wads.ci_config`](wads.ci_config.html.md#module-wads.ci_config) and the
`export-ci-env` action). Nothing is exported unless declared there.

## The named superset (legacy transport, kept for back-compat)

Before the JSON transport, the workflow declared a generous *superset* of
optional secret names ([`DEFAULT_CI_SECRETS`](#wads.ci_secrets.DEFAULT_CI_SECRETS)) and each repo’s stub passed
a named subset. That design failed whenever a repo needed a name outside the
superset — GitHub rejects an undeclared secret at parse time with an opaque
`startup_failure` (issue #63).

The superset is still declared by `uv-ci.yml` so that already-deployed
named-transport stubs keep working, but it is **frozen**: new names should not
be added — a repo that needs a new name should switch to the JSON transport
stub (`wads-migrate ci-to-stub`), which transports everything.

So there are two layers:

* **Transport** — the JSON secret (modern) or the frozen superset (legacy),
  rendered into static YAML. Plumbing.
* **Env-assignment** — pyproject-driven, exact, per-repo. The thing users tune.

Keeping the names here (Python) and *rendering* them into the YAML (with a
test pinning the YAML to this module) gives a single SSOT while respecting
GitHub’s parse-time-literal constraint.

### Module Attributes

| [`DEFAULT_CI_SECRETS`](#wads.ci_secrets.DEFAULT_CI_SECRETS)    | Ordered, de-duplicated legacy superset of named CI secrets (frozen).   |
|------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`WORKFLOW_CALL_SECRETS`](#wads.ci_secrets.WORKFLOW_CALL_SECRETS) | the JSON transport + the legacy superset.                              |

### Functions

| [`is_valid_secret_name`](#wads.ci_secrets.is_valid_secret_name)(name)                       | Return `True` iff `name` is already a safe, valid secret name.         |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`normalize_secret_name`](#wads.ci_secrets.normalize_secret_name)(name)                      | Force `name` to a valid `UPPER_SNAKE` secret/env-var name.             |
| [`render_stub_json_transport`](#wads.ci_secrets.render_stub_json_transport)(\*[, indent])         | Render the caller stub's JSON-transport `secrets:` line (the default). |
| [`render_stub_secrets_passthrough`](#wads.ci_secrets.render_stub_secrets_passthrough)([names, indent]) | Render a caller stub's *named* `secrets:` pass-through block (legacy). |
| [`render_workflow_call_secrets`](#wads.ci_secrets.render_workflow_call_secrets)([names, indent])    | Render the `on.workflow_call.secrets:` body for the reusable workflow. |

### Exceptions

| [`InvalidSecretName`](#wads.ci_secrets.InvalidSecretName)   | Raised when a string cannot be a safe, valid secret/env-var name.   |
|----------------------------------------------------------------------|---------------------------------------------------------------------|

### wads.ci_secrets.DEFAULT_CI_SECRETS *= ('PYPI_PASSWORD', 'TEST_PYPI_PASSWORD', 'NPM_TOKEN', 'SSH_PRIVATE_KEY', 'CODECOV_TOKEN', 'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY', 'COHERE_API_KEY', 'PERPLEXITY_API_KEY', 'REPLICATE_API_TOKEN', 'TOGETHER_API_KEY', 'XAI_API_KEY', 'FAL_KEY', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'TAVILY_API_KEY', 'COMPOSIO_API_KEY', 'SKILLSDIRECTORY_API_KEY', 'NEWSDATA_API_KEY', 'LANGSMITH_API_KEY', 'HF_TOKEN', 'HF_WRITE_TOKEN', 'HUGGINGFACE_TOKEN', 'KAGGLE_USERNAME', 'KAGGLE_KEY', 'WANDB_API_KEY', 'PINECONE_API_KEY', 'ELEVEN_API_KEY', 'ELEVENLABS_API_KEY', 'SUNO_API_KEY', 'SPOTIFY_API_CLIENT_ID', 'SPOTIFY_API_CLIENT_SECRET', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET', 'ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'GCP_SA_KEY', 'GOOGLE_APPLICATION_CREDENTIALS_JSON', 'SLACK_BOT_TOKEN', 'SLACK_WEBHOOK_URL', 'DISCORD_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'SENDGRID_API_KEY', 'STRIPE_SECRET_KEY', 'DATABASE_URL', 'MONGODB_URI', 'REDIS_URL')*

Ordered, de-duplicated legacy superset of named CI secrets (frozen).

### *exception* wads.ci_secrets.InvalidSecretName

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

Raised when a string cannot be a safe, valid secret/env-var name.

### wads.ci_secrets.WORKFLOW_CALL_SECRETS *= ('WADS_CI_SECRETS_JSON', 'PYPI_PASSWORD', 'TEST_PYPI_PASSWORD', 'NPM_TOKEN', 'SSH_PRIVATE_KEY', 'CODECOV_TOKEN', 'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY', 'COHERE_API_KEY', 'PERPLEXITY_API_KEY', 'REPLICATE_API_TOKEN', 'TOGETHER_API_KEY', 'XAI_API_KEY', 'FAL_KEY', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'TAVILY_API_KEY', 'COMPOSIO_API_KEY', 'SKILLSDIRECTORY_API_KEY', 'NEWSDATA_API_KEY', 'LANGSMITH_API_KEY', 'HF_TOKEN', 'HF_WRITE_TOKEN', 'HUGGINGFACE_TOKEN', 'KAGGLE_USERNAME', 'KAGGLE_KEY', 'WANDB_API_KEY', 'PINECONE_API_KEY', 'ELEVEN_API_KEY', 'ELEVENLABS_API_KEY', 'SUNO_API_KEY', 'SPOTIFY_API_CLIENT_ID', 'SPOTIFY_API_CLIENT_SECRET', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET', 'ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'GCP_SA_KEY', 'GOOGLE_APPLICATION_CREDENTIALS_JSON', 'SLACK_BOT_TOKEN', 'SLACK_WEBHOOK_URL', 'DISCORD_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'SENDGRID_API_KEY', 'STRIPE_SECRET_KEY', 'DATABASE_URL', 'MONGODB_URI', 'REDIS_URL')*

the JSON transport + the legacy superset.

* **Type:**
  Every secret `uv-ci.yml` declares

### wads.ci_secrets.is_valid_secret_name(name)

Return `True` iff `name` is already a safe, valid secret name.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> is_valid_secret_name("OPENAI_API_KEY")
True
>>> is_valid_secret_name("my-key")
False
>>> is_valid_secret_name("GITHUB_TOKEN")
False
```

### wads.ci_secrets.normalize_secret_name(name)

Force `name` to a valid `UPPER_SNAKE` secret/env-var name.

Hyphens, dots and spaces become underscores; the result is upper-cased.
Inputs that look like a *value* rather than a *name* are rejected, to guard
against accidentally committing a secret value.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> normalize_secret_name("my-api.key")
'MY_API_KEY'
>>> normalize_secret_name("OPENAI_API_KEY")
'OPENAI_API_KEY'
>>> normalize_secret_name("  hf token  ")
'HF_TOKEN'
```

Rejects value-looking and reserved inputs:

```pycon
>>> normalize_secret_name("sk-proj-aBc/123+xyz=")
Traceback (most recent call last):
InvalidSecretName: ...
>>> normalize_secret_name("GITHUB_TOKEN")
Traceback (most recent call last):
InvalidSecretName: ...
```

### wads.ci_secrets.render_stub_json_transport(, indent=6)

Render the caller stub’s JSON-transport `secrets:` line (the default).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> print(render_stub_json_transport())
      WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}
```

### wads.ci_secrets.render_stub_secrets_passthrough(names=('PYPI_PASSWORD', 'TEST_PYPI_PASSWORD', 'NPM_TOKEN', 'SSH_PRIVATE_KEY', 'CODECOV_TOKEN', 'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY', 'COHERE_API_KEY', 'PERPLEXITY_API_KEY', 'REPLICATE_API_TOKEN', 'TOGETHER_API_KEY', 'XAI_API_KEY', 'FAL_KEY', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'TAVILY_API_KEY', 'COMPOSIO_API_KEY', 'SKILLSDIRECTORY_API_KEY', 'NEWSDATA_API_KEY', 'LANGSMITH_API_KEY', 'HF_TOKEN', 'HF_WRITE_TOKEN', 'HUGGINGFACE_TOKEN', 'KAGGLE_USERNAME', 'KAGGLE_KEY', 'WANDB_API_KEY', 'PINECONE_API_KEY', 'ELEVEN_API_KEY', 'ELEVENLABS_API_KEY', 'SUNO_API_KEY', 'SPOTIFY_API_CLIENT_ID', 'SPOTIFY_API_CLIENT_SECRET', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET', 'ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'GCP_SA_KEY', 'GOOGLE_APPLICATION_CREDENTIALS_JSON', 'SLACK_BOT_TOKEN', 'SLACK_WEBHOOK_URL', 'DISCORD_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'SENDGRID_API_KEY', 'STRIPE_SECRET_KEY', 'DATABASE_URL', 'MONGODB_URI', 'REDIS_URL'), , indent=6)

Render a caller stub’s *named* `secrets:` pass-through block (legacy).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> print(render_stub_secrets_passthrough(["PYPI_PASSWORD", "NPM_TOKEN"]))
      PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}
      NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

### wads.ci_secrets.render_workflow_call_secrets(names=('WADS_CI_SECRETS_JSON', 'PYPI_PASSWORD', 'TEST_PYPI_PASSWORD', 'NPM_TOKEN', 'SSH_PRIVATE_KEY', 'CODECOV_TOKEN', 'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY', 'COHERE_API_KEY', 'PERPLEXITY_API_KEY', 'REPLICATE_API_TOKEN', 'TOGETHER_API_KEY', 'XAI_API_KEY', 'FAL_KEY', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'TAVILY_API_KEY', 'COMPOSIO_API_KEY', 'SKILLSDIRECTORY_API_KEY', 'NEWSDATA_API_KEY', 'LANGSMITH_API_KEY', 'HF_TOKEN', 'HF_WRITE_TOKEN', 'HUGGINGFACE_TOKEN', 'KAGGLE_USERNAME', 'KAGGLE_KEY', 'WANDB_API_KEY', 'PINECONE_API_KEY', 'ELEVEN_API_KEY', 'ELEVENLABS_API_KEY', 'SUNO_API_KEY', 'SPOTIFY_API_CLIENT_ID', 'SPOTIFY_API_CLIENT_SECRET', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET', 'ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'GCP_SA_KEY', 'GOOGLE_APPLICATION_CREDENTIALS_JSON', 'SLACK_BOT_TOKEN', 'SLACK_WEBHOOK_URL', 'DISCORD_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'SENDGRID_API_KEY', 'STRIPE_SECRET_KEY', 'DATABASE_URL', 'MONGODB_URI', 'REDIS_URL'), , indent=4)

Render the `on.workflow_call.secrets:` body for the reusable workflow.

Every secret is declared `required: false` — the publish job enforces
`PYPI_PASSWORD` at run time with a clear message, and the export action
enforces any repo-declared `required_envvars`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> print(render_workflow_call_secrets(["PYPI_PASSWORD", "OPENAI_API_KEY"]))
    PYPI_PASSWORD:
      required: false
    OPENAI_API_KEY:
      required: false
```
