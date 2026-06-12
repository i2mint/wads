---
name: wads-skillify
description: >-
  Set up, lay out, and validate a repo's AI agent skills as part of repo
  improvement: assess whether a repo warrants skills (baseline: consumer +
  dev skill), put real skill files in ONE canonical non-hidden location
  (repo-root skills/ or {pkg}/data/skills/ for pip-shipped) with committed
  relative symlinks in .claude/skills/ so both gh skill and Claude Code
  discover them, and make every SKILL.md Agent-Skills-spec-clean
  (name==dirname, portable frontmatter, gh skill publish --dry-run).
  Use when the user says "skillify this repo", "does this repo need skills",
  "set up skills for this project", "where should skills live", "restructure
  the skills layout", "align/validate my skills", "make skills gh-skill
  compatible", or "why doesn't Claude Code see this repo's skills". Also
  trigger as the skills step of a repo health pass (wads-repo-doctor). Does
  NOT author skill content from scratch (skill-build / skill-creator), wire
  pip packaging (skill-enable), write README docs (skill-docs), or fix
  content drift (skill-sync).
metadata:
  audience: users
---

# Wads Skillify — repo skill setup, layout & compliance

Ensure a repo's skills exist, live in the right place, are spec-clean, and are
discoverable by both `gh skill` (and other agents) **and** Claude Code. This
skill owns **assessment** (does the repo warrant skills?), **layout** (where
the files live), and **compliance** (Agent Skills spec validation). It does
not write skill content — that's `skill-build`'s job.

Golden rule: **observe, don't invent**. Every finding comes from a command
output or a file read; every layout move is shown as a plan before applied.

## Step 0 — resolve the target repo and inventory existing skills

The target repo is the path the user gives, else the current working
directory. Never hardcode a repo. Run everything below from the target
repo's root.

Inventory ALL discovery locations — real files first, then agent-dir entries:

```bash
# Real SKILL.md files anywhere (covers skills/, {pkg}/data/skills/, .claude/skills/)
find . -name SKILL.md -not -path './.git/*' -not -path './node_modules/*' \
  -not -path './.venv/*' | sort

# Agent-dir entries — which are real dirs vs symlinks (and where links point)
ls -la .claude/skills/ 2>/dev/null
ls -la .agents/skills/ 2>/dev/null
```

⚠️ `find` does not descend into symlinked directories, so a symlink
`.claude/skills/<name> -> ../../skills/<name>` shows up only in the `ls -la`
output — that's how you tell real dirs from links. Record, per skill: where
the real files live, and which entries are symlinks.

Who reads what (the reason layout matters):

| Location | `gh skill` discovers? | Claude Code reads? |
|---|---|---|
| `skills/<name>/` (repo root) | yes — the ecosystem convention | **no** (open issue anthropics/claude-code#31005) |
| `{pkg}/data/skills/<name>/` | yes — the discovery glob matches `skills/` under any non-hidden prefix | no |
| `.claude/skills/<name>/` | no — hidden dirs skipped by default | **yes** |
| `.agents/skills/<name>/` | install *destination* for Copilot/Cursor/Codex/Gemini/…, not a source convention | no |

So no single location serves everyone — hence the layout policy in Step 2:
real files in one non-hidden location, per-skill symlinks in `.claude/skills/`.

## Step 1 — assess: does this repo warrant skills, and which?

Baseline for any real package (something with users beyond its author): **two
skills minimum**:

- a **consumer skill** — how to *use* the package: main workflows, gotchas,
  real API examples. More than one if the repo has several distinct
  capabilities.
- a **dev skill** — how to *contribute and maintain*: architecture map, how to
  run the tests, release flow.

| Situation | Action |
|---|---|
| Real package, zero skills | Propose the consumer+dev pair; delegate analysis and authoring to **skill-build** |
| Skills exist but coverage is lopsided (e.g. dev-only) | Propose the missing half; delegate to **skill-build** |
| Scratch repo, throwaway code, no external users | Skills probably not warranted — say so and stop |
| Unclear whether the repo has distinct capabilities worth separate skills | Ask the user before proposing a skill list |

This skill decides *that* and *how many*; `skill-build` decides *what goes in
them*. Don't draft skill bodies here.

## Step 2 — layout policy (the core of this skill)

**Rule: real skill files live in exactly ONE non-hidden location.** Pick it:

| Repo kind | Canonical location |
|---|---|
| Pip-installable package whose skills should ship with `pip install` | `{pkg}/data/skills/<name>/` (gh skill's nested-prefix glob discovers it — the wads repo itself proves this layout works) |
| Everything else (apps, skill-only repos, docs repos) | `skills/<name>/` at repo root — the ecosystem-wide convention (`gh skill`, `npx skills`, anthropics/skills) |

⚠️ **Never both.** `gh skill` discovers every non-hidden match, so real files
in both `skills/` and `{pkg}/data/skills/` mean duplicate skills for every
installer. The Step 0 `find` output is your duplicate check.

⚠️ Whether `gh skill install` dereferences *committed symlinks* in a source
repo is undocumented — keep the real files in the canonical non-hidden path
and use symlinks only as Claude Code plumbing in `.claude/skills/`.

### The Claude Code bridge: committed per-skill relative symlinks

Claude Code does not read repo-root `skills/` (see the table above), so commit
one relative symlink per skill:

```bash
mkdir -p .claude/skills   # if .claude/ doesn't exist, create it with ONLY these symlinks

# Canonical location = repo-root skills/
ln -s ../../skills/NAME .claude/skills/NAME

# Canonical location = {pkg}/data/skills/  (PKG = the package dir)
ln -s ../../PKG/data/skills/NAME .claude/skills/NAME

git add .claude/skills/NAME
```

The `../../` climbs from `.claude/skills/` to the repo root; everything after
it is the canonical path from the root. Git stores the link as a tiny blob
containing that relative path, so it resolves in every clone. Verify:

```bash
readlink .claude/skills/NAME        # must print a RELATIVE path (no leading /)
ls -lL .claude/skills/NAME/         # dereferences; must list SKILL.md
```

⚠️ **Never symlink the whole `.claude/skills` directory** to somewhere else —
Claude Code writes `.system/` files into it, which breaks directory-level
links (anthropics/claude-code#20820). Per-skill symlinks are the verified
pattern (it's also what `npx skills add` does by default).

⚠️ Absolute symlinks (`/home/...`) work on the machine that made them and
break for every other clone. Catch them:

```bash
for L in .claude/skills/*; do
  [ -L "$L" ] && case "$(readlink "$L")" in /*) echo "ABSOLUTE symlink (fix): $L";; esac
done
```

⚠️ **Windows contributors:** git symlinks need `core.symlinks=true` plus
Windows developer mode, and silently check out as plain text files otherwise.
If the repo has Windows contributors, offer the alternative: commit real
*copies* in `.claude/skills/` and add a small sync script (or pre-commit hook)
that re-copies from the canonical location — accepting the duplication in
exchange for portability.

### Relocating real skills that live under `.claude/skills/`

If Step 0 found real (non-symlink) skill dirs inside `.claude/skills/`, move
them to the canonical location and leave a relative symlink behind:

```bash
mkdir -p skills                                # or PKG/data/skills
git mv .claude/skills/NAME skills/NAME
ln -s ../../skills/NAME .claude/skills/NAME
git add .claude/skills/NAME
ls -lL .claude/skills/NAME/                    # verify the link resolves
```

(`git mv` needs the destination parent dir to exist first — hence the
`mkdir -p`.) Nothing changes for Claude Code; the skills become visible to
`gh skill` and every other installer.

## Step 3 — spec compliance per skill

The Agent Skills spec (agentskills.io/specification), as validated by
`gh skill publish`:

| Field | Rule |
|---|---|
| `name` | required; 1–64 chars; lowercase `a-z0-9` + hyphens, no leading/trailing/consecutive hyphens; **must equal the parent directory name** |
| `description` | required; 1–1024 chars; covers what the skill does AND when to use it |
| `allowed-tools` | if present, a space-separated **string** — `gh skill publish` rejects YAML lists (Claude Code tolerates lists; standardize on string) |
| `license`, `compatibility` | optional (`compatibility` ≤ 500 chars) |
| `metadata` | arbitrary string map — put `author`, `version`, `audience` here |
| Claude-Code-only fields | `when_to_use`, `argument-hint`, `disable-model-invocation`, `paths`, `hooks`, … — keep them OUT of portable skills (other agents ignore or reject them) |

Quick mechanical pre-check (stdlib-only, read-only; feed it the Step 0 paths):

```bash
python - $(find . -name SKILL.md -not -path './.git/*' -not -path './node_modules/*' \
  -not -path './.venv/*' -not -path './venv/*') <<'PY'
import re, sys, pathlib
problems = []
for p in map(pathlib.Path, sys.argv[1:]):
    t = p.read_text(encoding='utf-8')
    m = re.match(r'---\s*\n(.*?)\n---\s*\n', t, re.S)
    if not m:
        problems.append(f'{p}: no YAML frontmatter'); continue
    fm = m.group(1)
    nm = re.search(r'^name:\s*(.+?)\s*$', fm, re.M)
    name = nm.group(1).strip('\'"') if nm else ''
    if name != p.parent.name:
        problems.append(f'{p}: name {name!r} != directory {p.parent.name!r}')
    if not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', name) or not (1 <= len(name) <= 64):
        problems.append(f'{p}: name {name!r} violates spec (1-64 chars, lowercase a-z0-9, single hyphens)')
    if not re.search(r'^description:', fm, re.M):
        problems.append(f'{p}: missing description')
    if re.search(r'^allowed-tools:\s*\[', fm, re.M) or re.search(r'^allowed-tools:\s*\n\s+-\s', fm, re.M):
        problems.append(f'{p}: allowed-tools must be a space-separated string, not a YAML list')
    for f in ('when_to_use', 'argument-hint', 'disable-model-invocation', 'paths', 'hooks', 'context'):
        if re.search(rf'^{f}:', fm, re.M):
            problems.append(f'{p}: Claude-Code-only field {f!r} (not portable)')
print('\n'.join(problems) or 'OK: mechanical checks pass')
sys.exit(1 if problems else 0)
PY
```

(It doesn't measure multi-line description length — `gh skill` validates
that.) Then the real validator:

```bash
# gh skill is built into GitHub CLI >= 2.90.0 (2026-04). Check first:
gh skill --help >/dev/null 2>&1 || echo "gh too old — need >= 2.90.0; check: gh --version"

gh skill publish --dry-run         # validate all discovered skills against the spec; no release
gh skill publish --dry-run --fix   # additionally apply automatic fixes
```

⚠️ `gh skill` is in public preview; flags above are from the gh manual
(cli.github.com/manual/gh_skill_publish) and may change. If gh is too old to
upgrade, the spec's reference validator is an alternative:
`skills-ref validate ./skills/NAME` (from github.com/agentskills/agentskills).

## Step 4 — discoverability (optional — propose, never auto-apply)

These touch public-facing repo state, so present them as proposals:

```bash
# 1. The repo topic GitHub recommends for skill repos
gh repo edit OWNER/REPO --add-topic agent-skills

# 2. A tagged release so consumers can pin (gh skill install OWNER/REPO NAME@v0.1.0)
gh skill publish --tag v0.1.0
```

3. Document the install paths in the README — the section's wording and
placement is **skill-docs**' job; the facts to hand it:

```text
gh skill install OWNER/REPO NAME --agent claude-code
npx skills add OWNER/REPO --skill NAME
pip install PKG   # where applicable — plus the package's own skill installer
                  # (e.g. wads's `wads-install-skills`), or
                  # gh skill install <path-to-installed-data/skills> --from-local
```

## Step 5 — align existing skills (delegate)

Layout and spec problems are yours (Steps 2–3). Everything else is a named
hand-off:

| Finding | Delegate to |
|---|---|
| Skill content stale vs the code it describes | **skill-sync** |
| Description weak / skill under-triggers | **skill-creator** (description-optimization eval loop) |
| Skill should ship with `pip install` (package-data wiring, installer) | **skill-enable** |
| Skills missing from the README | **skill-docs** |
| Repo needs a new skill written | **skill-build** |

## Scope guardrails

- **Do not** write or rewrite skill *content* — only frontmatter spec fixes
  and file moves. Content is skill-build / skill-creator / skill-sync
  territory.
- Steps 0–1 and the Step 3 checks are read-only. Layout moves (Step 2) are
  local and reversible but still presented as a plan first. Step 4 actions
  (repo topic, tagged release) are public-facing — proposed, never auto-run.
- Never delete a skill. Never touch the user-scope `~/.claude/skills/` — this
  skill operates on the target repo only.
- Skills get committed to public repos: no secrets, no absolute local paths,
  no machine/user names in any skill file you touch.

## Related skills

- **wads-repo-doctor** — the orchestrator that dispatches here during a full
  repo health pass.
- **skill-build** — analyze a package and author its skills (Step 1 hand-off).
- **skill-enable** — ship skills in pip distributions (`{pkg}/data/skills/`
  package-data wiring).
- **skill-docs** — README/skills documentation.
- **skill-sync** — keep skill content in sync with code.
- **skill-creator** — generic skill creation + description optimization.

## Closing checklist

- [ ] Real skill files in exactly ONE non-hidden location (Step 0 `find`
      shows no duplicates across `skills/` and `{pkg}/data/skills/`)
- [ ] Every `.claude/skills/<name>` symlink is **relative** and resolves:
      `for L in .claude/skills/*; do [ -e "$L" ] || echo "BROKEN: $L"; done`
      prints nothing (⚠️ bare `ls -lL <dir>` silently *omits* broken links —
      don't rely on it)
- [ ] Frontmatter `name` == directory name for every skill (mechanical check
      passes)
- [ ] `gh skill publish --dry-run` passes (where gh >= 2.90.0 is available)
- [ ] Skills load in a fresh Claude Code session — a NEW top-level dir under
      `.claude/skills/` needs a session restart to appear
- [ ] Repo has (at least) its consumer + dev skill pair, or a recorded
      decision that skills aren't warranted
