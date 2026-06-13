---
name: wads-skillify
description: >-
  The skills step of a wads repo-improvement pass: assess whether a repo warrants
  AI agent skills (baseline: a consumer + a dev skill) and dispatch the work.
  Layout, distribution, and spec compliance are DEFERRED to the canonical
  authority — the `skill-package-setup` skill in the `skill` package. Use when
  the user says "skillify this repo", "does this repo need skills", "set up
  skills for this project", "where should skills live", "restructure the skills
  layout", "align/validate my skills", "make skills gh-skill compatible", or "why
  doesn't Claude Code see this repo's skills". Also trigger as the skills step of
  a repo health pass (wads-repo-doctor). Does NOT author skill content
  (skill-build / skill-creator), write README docs (skill-docs), or fix content
  drift (skill-sync).
metadata:
  audience: users
---

# Wads Skillify — repo skill assessment & dispatch

The skills step of a `wads` repo-improvement pass. This skill owns the
**wads-specific assessment** (does the repo warrant skills, and which?) and the
**dispatch** to the specialist skills. It **defers layout, distribution, and
spec compliance to `skill-package-setup`** — the canonical, agent-agnostic
authority.

Golden rule: **observe, don't invent.** Every layout move is shown as a plan
before it's applied; never break tests without asking.

## Prerequisite — the `skill` package

This skill relies on the **`skill`** package: it provides `skill-package-setup`
(the layout authority) and the `skill` CLI (`skill validate`, `skill link-skills`).
Ensure it's installed:

```bash
pip install 'wads[skills]'        # `skill` is an optional dependency of wads
# or: pip install skill
```

If the **skill-package-setup** skill isn't already available to your agent:

```bash
gh skill install thorwhalen/skill skill-package-setup
```

Then **follow `skill-package-setup` (and its `references/migration-runbook.md`)
for ALL layout decisions, file moves, symlinks, and spec compliance.** The rest
of this skill is the wads-fleet wrapper around it.

## Step 0 — resolve target repo & inventory

Run from the target repo root (the path the user gives, else cwd):

```bash
find . -name SKILL.md -not -path './.git/*' -not -path './node_modules/*' \
  -not -path './.venv/*' | sort
ls -la .claude/skills/ 2>/dev/null        # real dirs vs symlinks (find won't descend symlinks)
```

Record per skill: where the real files live, and which `.claude/skills/` entries
are symlinks. (skill-package-setup's runbook has the full inventory + duplicate check.)

## Step 1 — assess: does this repo warrant skills, and which? (the wads-specific part)

Baseline for any real package (something with users beyond its author): **two
skills minimum**:

- a **consumer skill** — how to *use* the package: main workflows, gotchas, real
  API examples. More than one if the repo has several distinct capabilities.
- a **dev skill** — how to *contribute and maintain*: architecture map, how to run
  the tests, release flow.

| Situation | Action |
|---|---|
| Real package, zero skills | Propose the consumer+dev pair; delegate authoring to **skill-build** |
| Skills exist but coverage is lopsided (e.g. dev-only) | Propose the missing half; delegate to **skill-build** |
| Scratch repo, throwaway code, no external users | Skills probably not warranted — say so and stop |
| Unclear whether the repo has distinct capabilities worth separate skills | Ask the user before proposing a skill list |

This skill decides *that* and *how many*; **skill-build** decides *what goes in
them*. Don't draft skill bodies here.

## Step 2 — layout, distribution & spec → defer to skill-package-setup

The policy in one paragraph (skill-package-setup is authoritative): real skill
files live in **exactly one non-hidden location** — `{pkg}/data/skills/` for a
pip-installable package whose skills should ship with `pip install` (this `wads`
repo itself uses that: its skills are in `wads/data/skills/`), else top-level
`skills/`. **Never both.** `gh skill` discovers any non-hidden `**/skills/*/SKILL.md`;
Claude Code reads only `.claude/skills/`, so commit one **relative** symlink per
skill there. Frontmatter must be Agent-Skills-spec-clean (folder name == `name`;
custom keys like `audience` under `metadata`; no Claude-only fields).

For the exact `git mv` + symlink commands, the spec table, the mechanical
frontmatter check, and the symlink/Windows gotchas → **follow `skill-package-setup`
and run `gh skill publish --dry-run` (or `skill validate`) to verify.**

## Step 3 — discoverability (propose, never auto-apply)

Public-facing, so present as proposals:

```bash
gh repo edit OWNER/REPO --add-topic agent-skills      # recommended topic for skill repos
gh skill publish --tag v0.1.0                         # tagged release so consumers can pin
```

Document install paths in the README (wording/placement is **skill-docs**' job);
the facts to hand it:

```text
gh skill install OWNER/REPO NAME --agent claude-code
npx skills add OWNER/REPO --skill NAME
pip install PKG        # where skills ship in {pkg}/data/skills (+ skill link-skills)
```

## Step 4 — align existing skills (delegate)

| Finding | Delegate to |
|---|---|
| Skill content stale vs the code it describes | **skill-sync** |
| Description weak / skill under-triggers | **skill-creator** |
| Skill should ship with `pip install` (package-data wiring) | **skill-enable** |
| Skills missing from the README | **skill-docs** |
| Repo needs a new skill written | **skill-build** |

## Scope guardrails

- Layout/spec is **skill-package-setup**'s; this skill assesses and dispatches.
  Don't restate or fork the layout policy here.
- Steps 0–1 are read-only; layout moves are local/reversible but shown as a plan
  first; Step 3 is public-facing — proposed, never auto-run.
- Never delete a skill. Never touch `~/.claude/skills/` — operate on the target repo.
- Skills get committed to public repos: no secrets, no absolute local paths, no
  machine/user names in any skill file you touch.

## Related skills

- **skill-package-setup** — THE layout/distribution/spec authority this skill
  defers to (in the `skill` package; `pip install 'wads[skills]'`).
- **wads-repo-doctor** — the orchestrator that dispatches here.
- **skill-build** / **skill-creator** — author skill content + optimize descriptions.
- **skill-enable** — ship skills via `pip` (`{pkg}/data/skills/` wiring).
- **skill-docs** — README/skills documentation.
- **skill-sync** — keep skill content in sync with code.

## Closing checklist

- [ ] Repo has (at least) its consumer + dev skill pair, or a recorded decision
      that skills aren't warranted.
- [ ] Layout, symlinks, and spec verified per **skill-package-setup**
      (`gh skill publish --dry-run` passes; `.claude/skills/<name>` are relative
      symlinks that resolve; one real non-hidden location, no duplicates).
- [ ] Skills load in a fresh Claude Code session (a new top-level `.claude/skills/`
      entry needs a session restart to appear).
