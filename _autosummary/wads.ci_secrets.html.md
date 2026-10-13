# wads.ci_secrets

Canonical registry of CI secret names for wads-managed projects.

This module is the single source of truth for the *transport* layer of wads
CI secrets: what the reusable workflow (`uv-ci.yml`) declares in
`on.workflow_call.secrets` and what the caller stub passes.

## Transport: named by default, one JSON secret on request

A GitHub *reusable* workflow’s secret interface (`on.workflow_call.secrets`)
must be **static YAML** — it is parsed before any job runs and cannot be
parametrized from `pyproject.toml`. `secrets: inherit` is documented to
work only when caller and callee share an org/enterprise, so it is unusable
for personal-account repos calling an `i2mint`-owned workflow.

**Named (the default).** The workflow declares a *superset* of optional
secret names ([`DEFAULT_CI_SECRETS`](#wads.ci_secrets.DEFAULT_CI_SECRETS)), and each repo’s stub passes, by
name, only `PYPI_PASSWORD` plus the backing secret of each env var its
`[tool.wads.ci.env]` declares:

```default
secrets:
  PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

The called workflow receives those secrets and nothing else, each masked by
GitHub on its own. The bundled stub template is named; `populate` and every
re-render (`wads-migrate ci-to-stub`, `ci-on-demand`, `fleet-stub`)
write a named stub, converting a JSON one, unless `--transport json` is
asked for.

A name outside the superset makes GitHub reject the workflow at parse time
with an opaque `startup_failure` (issue #63). The superset therefore grows
**additively**: adding a `required: false` name never breaks an existing
stub (removing one can). A named stub never passes an out-of-superset name: it
is left out with a note ([`named_transport_names()`](#wads.ci_secrets.named_transport_names), #107), and a
re-render with no explicit transport falls back to JSON for such a repo
rather than drop a real secret. A name recorded in
`[tool.wads.ci.env].variables` (`wads-secrets add NAME --variable`) is a
repository variable, needs no transport, and never triggers either.

**JSON (opt-in).** `wads-migrate ci-to-stub --transport json` passes one
statically-declared secret, `JSON_TRANSPORT_SECRET`
(`WADS_CI_SECRETS_JSON`), whose value is the caller’s whole `secrets`
context:

```default
secrets:
  WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}
```

Any secret name then reaches the workflow — but so does every secret the repo
can read, org-level ones included, and serialising the whole `secrets`
context into a workflow in another repository is structurally what a
secret-exfiltration workflow looks like. GitHub’s malicious-workflow scanner
holds such runs (`action_required`, zero jobs, no log, and the REST approve
endpoint refuses them; issues #74, #88, #101). It was seen first on new
repositories and later on an existing one; switching to named made the next
push run every time. Two details of the JSON form, verified empirically
(issue #63):

* **Double encoding** (`toJSON(toJSON(...))`) makes the transported value a
  *single-line* JSON string. A multiline secret is masked per line, and the
  pretty-printed form’s `{` / `}` lines would become global masks that
  mangle every brace in the job log.
* **Re-masking**: values extracted from the blob are *not* automatically
  masked in the callee, so the `export-ci-env` action emits
  `::add-mask::` for each secret-sourced value before exporting it.

So there are two layers:

* **Transport** — named (default) or the JSON secret (opt-in), rendered into
  static YAML. Plumbing.
* **Env-assignment** — pyproject-driven, exact, per-repo: *which* transported
  secrets land in the job env, and which are required (see
  [`wads.ci_config`](wads.ci_config.html.md#module-wads.ci_config) and the `export-ci-env` action). Nothing is exported
  > unless declared there. The thing users tune.

Keeping the names here (Python) and *rendering* them into the YAML (with a
test pinning the YAML to this module) gives a single SSOT while respecting
GitHub’s parse-time-literal constraint.

### Module Attributes

| [`DEFAULT_CI_SECRETS`](#wads.ci_secrets.DEFAULT_CI_SECRETS)    | Ordered, de-duplicated superset of names a named-transport stub may pass (additive).   |
|------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| [`WORKFLOW_CALL_SECRETS`](#wads.ci_secrets.WORKFLOW_CALL_SECRETS) | the opt-in JSON transport secret + the superset.                                       |

### Functions

| [`is_valid_secret_name`](#wads.ci_secrets.is_valid_secret_name)(name)                        | Return `True` iff `name` is already a safe, valid secret name.              |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`named_transport_names`](#wads.ci_secrets.named_transport_names)(names)                      | The `names` a named-transport stub can pass; the rest are left out, loudly. |
| [`normalize_secret_name`](#wads.ci_secrets.normalize_secret_name)(name)                       | Force `name` to a valid `UPPER_SNAKE` secret/env-var name.                  |
| [`render_stub_json_transport`](#wads.ci_secrets.render_stub_json_transport)(\*[, indent])          | Render the caller stub's JSON-transport `secrets:` line (opt-in).           |
| [`render_stub_secrets_passthrough`](#wads.ci_secrets.render_stub_secrets_passthrough)([names, indent])  | Render a caller stub's *named* `secrets:` pass-through block (the default). |
| [`render_workflow_call_secrets`](#wads.ci_secrets.render_workflow_call_secrets)([names, indent])     | Render the `on.workflow_call.secrets:` body for the reusable workflow.      |
| [`stub_transport`](#wads.ci_secrets.stub_transport)(stub)                              | The secrets transport of a stub's content: `"json"` or `"named"`.           |
| [`stub_with_named_transport`](#wads.ci_secrets.stub_with_named_transport)(stub, names)            | Rewrite a stub's secrets region to the named transport, passing `names`.    |
| [`stub_with_transport`](#wads.ci_secrets.stub_with_transport)(stub, \*[, transport, names]) | Rewrite a stub's secrets region to the given transport.                     |
| [`warn_names_outside_superset`](#wads.ci_secrets.warn_names_outside_superset)(names)                | Warn loudly for names a named-transport stub cannot legally pass.           |

### Exceptions

| [`InvalidSecretName`](#wads.ci_secrets.InvalidSecretName)   | Raised when a string cannot be a safe, valid secret/env-var name.   |
|----------------------------------------------------------------------|---------------------------------------------------------------------|

### wads.ci_secrets.DEFAULT_CI_SECRETS *= ('PYPI_PASSWORD', 'TEST_PYPI_PASSWORD', 'NPM_TOKEN', 'SSH_PRIVATE_KEY', 'CODECOV_TOKEN', 'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY', 'COHERE_API_KEY', 'PERPLEXITY_API_KEY', 'REPLICATE_API_TOKEN', 'TOGETHER_API_KEY', 'XAI_API_KEY', 'FAL_KEY', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'TAVILY_API_KEY', 'COMPOSIO_API_KEY', 'SKILLSDIRECTORY_API_KEY', 'NEWSDATA_API_KEY', 'LANGSMITH_API_KEY', 'HF_TOKEN', 'HF_WRITE_TOKEN', 'HUGGINGFACE_TOKEN', 'KAGGLE_USERNAME', 'KAGGLE_KEY', 'WANDB_API_KEY', 'PINECONE_API_KEY', 'ELEVEN_API_KEY', 'ELEVENLABS_API_KEY', 'SUNO_API_KEY', 'SPOTIFY_API_CLIENT_ID', 'SPOTIFY_API_CLIENT_SECRET', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET', 'ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'GCP_SA_KEY', 'GOOGLE_APPLICATION_CREDENTIALS_JSON', 'SLACK_BOT_TOKEN', 'SLACK_WEBHOOK_URL', 'DISCORD_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'SENDGRID_API_KEY', 'STRIPE_SECRET_KEY', 'DATABASE_URL', 'MONGODB_URI', 'REDIS_URL')*

Ordered, de-duplicated superset of names a named-transport stub may pass (additive).

### *exception* wads.ci_secrets.InvalidSecretName

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

Raised when a string cannot be a safe, valid secret/env-var name.

### wads.ci_secrets.WORKFLOW_CALL_SECRETS *= ('WADS_CI_SECRETS_JSON', 'PYPI_PASSWORD', 'TEST_PYPI_PASSWORD', 'NPM_TOKEN', 'SSH_PRIVATE_KEY', 'CODECOV_TOKEN', 'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY', 'COHERE_API_KEY', 'PERPLEXITY_API_KEY', 'REPLICATE_API_TOKEN', 'TOGETHER_API_KEY', 'XAI_API_KEY', 'FAL_KEY', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'TAVILY_API_KEY', 'COMPOSIO_API_KEY', 'SKILLSDIRECTORY_API_KEY', 'NEWSDATA_API_KEY', 'LANGSMITH_API_KEY', 'HF_TOKEN', 'HF_WRITE_TOKEN', 'HUGGINGFACE_TOKEN', 'KAGGLE_USERNAME', 'KAGGLE_KEY', 'WANDB_API_KEY', 'PINECONE_API_KEY', 'ELEVEN_API_KEY', 'ELEVENLABS_API_KEY', 'SUNO_API_KEY', 'SPOTIFY_API_CLIENT_ID', 'SPOTIFY_API_CLIENT_SECRET', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET', 'ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'GCP_SA_KEY', 'GOOGLE_APPLICATION_CREDENTIALS_JSON', 'SLACK_BOT_TOKEN', 'SLACK_WEBHOOK_URL', 'DISCORD_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'SENDGRID_API_KEY', 'STRIPE_SECRET_KEY', 'DATABASE_URL', 'MONGODB_URI', 'REDIS_URL')*

the opt-in JSON transport secret + the superset.

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

### wads.ci_secrets.named_transport_names(names)

The `names` a named-transport stub can pass; the rest are left out, loudly.

A named stub may only pass names in the superset
([`DEFAULT_CI_SECRETS`](#wads.ci_secrets.DEFAULT_CI_SECRETS)): one more line and GitHub rejects the whole
workflow at parse time (issue #63). So a name outside it is *left out* of
the stub rather than written there. It can then reach CI only as a
repository variable (declared env vars fall back to `vars`). A note on
stderr lists what was left out and how to pass it (#107). Names recorded
in `[tool.wads.ci.env].variables` never get here: they are not secrets.
Order-preserving.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

```pycon
>>> named_transport_names(["PYPI_PASSWORD", "HF_TOKEN"])
['PYPI_PASSWORD', 'HF_TOKEN']
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

Render the caller stub’s JSON-transport `secrets:` line (opt-in).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> print(render_stub_json_transport())
      WADS_CI_SECRETS_JSON: ${{ toJSON(toJSON(secrets)) }}
```

### wads.ci_secrets.render_stub_secrets_passthrough(names=('PYPI_PASSWORD', 'TEST_PYPI_PASSWORD', 'NPM_TOKEN', 'SSH_PRIVATE_KEY', 'CODECOV_TOKEN', 'DOCKERHUB_USERNAME', 'DOCKERHUB_TOKEN', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY', 'COHERE_API_KEY', 'PERPLEXITY_API_KEY', 'REPLICATE_API_TOKEN', 'TOGETHER_API_KEY', 'XAI_API_KEY', 'FAL_KEY', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'TAVILY_API_KEY', 'COMPOSIO_API_KEY', 'SKILLSDIRECTORY_API_KEY', 'NEWSDATA_API_KEY', 'LANGSMITH_API_KEY', 'HF_TOKEN', 'HF_WRITE_TOKEN', 'HUGGINGFACE_TOKEN', 'KAGGLE_USERNAME', 'KAGGLE_KEY', 'WANDB_API_KEY', 'PINECONE_API_KEY', 'ELEVEN_API_KEY', 'ELEVENLABS_API_KEY', 'SUNO_API_KEY', 'SPOTIFY_API_CLIENT_ID', 'SPOTIFY_API_CLIENT_SECRET', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET', 'ALPACA_API_KEY', 'ALPACA_SECRET_KEY', 'APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'GCP_SA_KEY', 'GOOGLE_APPLICATION_CREDENTIALS_JSON', 'SLACK_BOT_TOKEN', 'SLACK_WEBHOOK_URL', 'DISCORD_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'SENDGRID_API_KEY', 'STRIPE_SECRET_KEY', 'DATABASE_URL', 'MONGODB_URI', 'REDIS_URL'), , indent=6)

Render a caller stub’s *named* `secrets:` pass-through block (the default).

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

### wads.ci_secrets.stub_transport(stub)

The secrets transport of a stub’s content: `"json"` or `"named"`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> stub_transport("    secrets:\n" + render_stub_json_transport() + "\n")
'json'
>>> stub_transport("    secrets:\n      PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}\n")
'named'
```

### wads.ci_secrets.stub_with_named_transport(stub, names)

Rewrite a stub’s secrets region to the named transport, passing `names`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> stub = "jobs:\n  ci:\n    secrets:\n" + render_stub_json_transport() + "\n"
>>> stub_with_named_transport(stub, ["PYPI_PASSWORD"]).endswith(
...     "      PYPI_PASSWORD: ${{ secrets.PYPI_PASSWORD }}\n")
True
```

### wads.ci_secrets.stub_with_transport(stub, , transport='named', names=('PYPI_PASSWORD',))

Rewrite a stub’s secrets region to the given transport.

Works on a stub of either transport, so it converts JSON to named, named
to JSON, and re-lists a named stub’s names; the comment lines directly
above `secrets:` are replaced too, so a stub never describes a transport
it does not use. `names` is used by the named transport only. A stub
whose `ci` job has no `secrets:` mapping block (`secrets: inherit`,
say) raises `ValueError`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
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
```

### wads.ci_secrets.warn_names_outside_superset(names)

Warn loudly for names a named-transport stub cannot legally pass.

A caller may only pass secrets the reusable workflow declares. With
`transport="named"` that universe is the superset in
[`wads.ci_secrets.DEFAULT_CI_SECRETS`](#wads.ci_secrets.DEFAULT_CI_SECRETS); a stub naming anything outside
it produces a workflow GitHub rejects at parse time — zero jobs, an opaque
`startup_failure` (issue #63). Returns the offending names.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)
