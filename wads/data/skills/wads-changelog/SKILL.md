---
name: wads-changelog
description: >-
  Generate and maintain CHANGELOG.md for a wads-managed repo (one where CI
  auto-bumps the version and tags releases with bare version tags like 0.2.3)
  from git history. Diagnoses coverage (does a changelog exist, latest tag vs
  latest version covered, gap list), generates Keep-a-Changelog-style sections
  per version tag with CI noise filtered (bump commits, [skip ci]
  housekeeping, bare merges) and PR titles kept verbatim, and maintains the
  file idempotently: only inserts sections for missing versions, never
  rewrites hand-edits. Use for "generate a changelog", "create CHANGELOG.md",
  "update the changelog", "is the changelog up to date", "backfill the
  changelog", "what changed in 0.2.3", "release notes from git history",
  "changelog is behind the releases". Also trigger when wads-repo-doctor
  reports a missing/stale changelog. Does NOT add the [project.urls].Changelog
  link or polish PyPI metadata (wads-pypi-polish), and does NOT diagnose
  version-sync or CI problems (wads-ci-health).
metadata:
  audience: users
---

# Wads Changelog

Generate and maintain a `CHANGELOG.md` derived from what actually happened:
git version tags and the commits between them. The golden rule is **observe,
don't invent** — entries are commit subjects and PR titles *verbatim*, never
rewritten into marketing prose, and every section maps to a real git tag.

The core invariant is **regeneration preserves hand-edits**: maintenance only
*inserts* sections for versions not yet present in the file. Existing
sections — including any line a human added, reworded, or reordered — are
never touched. Once every tagged version has a section, re-running is a
no-op. (With `--max-versions N` each run *intentionally* advances the
backfill by N more versions — that's progress, not a violation.)

## The release model you're reading (wads-managed repos)

Facts the extraction is built on (verify them on the target repo — shapes
below were confirmed on github.com/i2mint/wads):

- CI auto-bumps the version on every default-branch merge and creates a
  **bare version tag** (`0.2.3` — no `v` prefix), pointing at the bump commit.
- The bump commit subject is
  `**CI** Formatted code + Updated version to X.Y.Z [skip ci]` — with older
  variants (`...Updated version number and documentation. [skip ci]`, a
  missing-space variant, even one prefixed `--commit-message=`). All carry
  `[skip ci]`, which is what the noise filter keys on.
- PR merges appear either as squash commits (`subject (#NN)` — the PR title
  is the subject) or merge commits (`Merge pull request #NN from ...` — the
  PR title is the **first body line**).
- So: the commits "in" version `X` are `git log --first-parent PREV_TAG..X`;
  the very first release has no predecessor (`root..TAG`); version `X`'s own
  bump commit sits inside its range and gets filtered.

## Step 0 — resolve the target repo and fetch tags

Operate on the repo path the user gives, else the current working directory.
Tags are the backbone of the whole skill, and they're fetched lazily by many
git setups — sync them first (a ref-only update; it touches no files):

```bash
cd /path/to/repo
git fetch --tags
git tag --list | wc -l        # expect roughly one tag per released version
git tag --sort=-v:refname | head -3
```

No version tags at all → this repo has never released through wads CI (or
tags were never pushed). Don't fabricate a changelog from nothing; check
`gh api repos/OWNER/REPO/tags --jq '.[0:3][].name'` and the **wads-ci-health**
skill's version-sync check before going further.

## Diagnose

Run the bundled script (read-only by default; `scripts/` is relative to this
skill, the repo path defaults to cwd):

```bash
python scripts/changelog_gen.py /path/to/repo > /tmp/changelog_report.txt
echo "exit: $?"; head -20 /tmp/changelog_report.txt
python scripts/changelog_gen.py /path/to/repo --json   # machine-readable
```

It reports:

- whether `CHANGELOG.md` exists, and the **latest version it covers** vs the
  **latest git tag** (a heading counts as covering `X.Y.Z` if it matches
  `## [X.Y.Z]`, `## X.Y.Z`, or `## vX.Y.Z ...`);
- the **gap list** — every tagged version with no section in the file;
- a warning if origin has version tags your local clone doesn't
  (the `git fetch --tags` you skipped); `--no-remote-check` skips this
  read-only network call when offline;
- commits since the latest tag (**unreleased** — reported, never written:
  there's no tag to key the section to, and writing it would break
  idempotency);
- a rendered preview of every missing section.

Use `--max-versions N` to preview/backfill only the N newest missing versions
— useful on first contact with a repo that has a hundred-plus tags.

### What a generated section looks like

```markdown
## [0.2.3] - 2026-06-02

### Fixed

- fix(secrets): wads-secrets add shouldn't short-circuit on an existing declaration ([#50](https://github.com/i2mint/wads/pull/50))
```

The rules behind it (all deterministic, all in the script):

| Rule | Detail |
|---|---|
| Date | the tag's `creatordate` — release-cut time for the annotated tags wads CI creates; equals the commit date for lightweight tags |
| Noise dropped | bump commits and anything `[skip ci]`; bare `Merge branch ...` commits |
| PR merge commits | replaced by the PR title (first body line) + `(#NN)` |
| Squash merges / direct pushes | subject kept **verbatim** |
| Categories | conventional-commit prefixes only: `feat:`→Added, `fix:`→Fixed, `docs:`→Docs, `refactor:`→Changed. Anything else lands in an uncategorized bullet list directly under the version heading — never invent a category for an unclear message |
| PR links | `#NN` becomes a markdown link only when `origin` is a github.com remote; otherwise it stays bare `#NN` |
| Empty-after-filtering range | an explicit "Maintenance only" bullet, so every tag still gets a section |

## Generate / Maintain — the one sanctioned write

`--write` is **the only mode that writes, and the only sanctioned write in
this skill suite** (every other suite script is read-only on the target
repo). It inserts the missing sections into `CHANGELOG.md` — creating the
file with a standard Keep-a-Changelog-style header if absent — and never
modifies, reorders, or deletes an existing line:

```bash
python scripts/changelog_gen.py /path/to/repo --write
# then prove idempotency — repeat with the SAME flags; once the backfill is
# complete (no --max-versions remainder), the second run must be a no-op:
cp /path/to/repo/CHANGELOG.md /tmp/changelog_before.md
python scripts/changelog_gen.py /path/to/repo --write
diff /tmp/changelog_before.md /path/to/repo/CHANGELOG.md && echo "idempotent"
```

Placement is version-aware and purely additive: a new section goes right
before the first existing section *older* than it (so a hand-maintained
`## [Unreleased]` block stays on top, and a backfilled middle version lands
between its neighbors), or at the end if everything existing is newer.

After writing:

1. **Review the diff** (`git -C /path/to/repo diff -- CHANGELOG.md`) before
   any commit — especially the preview of what the noise filter dropped.
2. Show the result to the user; committing is their call.

⚠️ **Pitfall: committing the changelog cuts a release.** On a wads-managed
repo, any default-branch push that passes validation triggers the auto-bump
and a PyPI publish. For a changelog-only commit, either put `[skip ci]` in
the commit message (the ecosystem's own bump commits use it) or fold the
changelog into a PR that's shipping anyway. Don't silently cause version
N+1 to exist because of a docs file.

⚠️ **Pitfall: `[skip ci]` filtering is greedy by design.** Humans sometimes
mark real changes `[skip ci]` (observed in wads: a `feat: ...` docs commit).
Those get filtered as housekeeping. Scan the preview before `--write`; if a
filtered commit deserves an entry, add it by hand after writing — hand-edits
are exactly what regeneration preserves.

⚠️ **Pitfall: version numbers skip — that's real, not a bug.** wads itself
has no `0.1.90`–`0.1.92` tags (push-back failures burn version numbers; see
the wads-ci-fix skill). Tags are the single source of truth: never infer "missing
versions" from pyproject history or PyPI, and never fabricate a section for
an untagged version.

⚠️ **Pitfall: tag dates vs commit dates.** `git log -1 --format=%cs TAG`
gives the *tagged commit's* date, which can predate the release. The script
uses `creatordate` (tag-creation time for annotated tags), which is the
honest release date. If you compute dates by hand, match that.

⚠️ **Pitfall: don't hand-roll the ranges.** `TAG~N..TAG` counts commits, not
versions, and breaks across merges; the first release has no predecessor tag
at all (the script uses `root..TAG` there). Use consecutive *version-sorted
tags* — `git tag --sort=-v:refname` — as range endpoints, like the script does.

## Ties to the rest of the ecosystem

- **`[project.urls].Changelog`** — once `CHANGELOG.md` exists and is
  committed, the **wads-pypi-polish** skill adds the link to pyproject so it
  shows on the PyPI sidebar. Don't add it here; just mention it in your
  report.
- **GitHub Releases** — i2mint repos do *not* create a GitHub Release per
  tag, and that's deliberate (the tag + PyPI + changelog carry the
  information). Don't propose `gh release create` backfills; if the user
  explicitly wants release notes for one tag, the generated section text is
  paste-ready.

## Scope guardrails

- **One write, loudly scoped**: the only mutation this skill ever performs is
  `changelog_gen.py --write` inserting missing version sections into
  `CHANGELOG.md`. Diagnosis, JSON, and previews are read-only.
- **Never rewrite existing sections.** Wording fixes to existing entries are
  hand-edits — propose them to the user; don't automate them.
- **Never rewrite history's voice**: subjects and PR titles stay verbatim; no
  summarizing, no marketing prose, no invented categories.
- **Never create tags, bump versions, push, or commit** — committing the
  changelog (and the `[skip ci]` decision) belongs to the user.
- Version-sync anomalies you notice (PyPI ahead of pyproject, missing tags)
  are findings to delegate, not things to repair here.

## Related skills

- **wads-repo-doctor** — the orchestrator; runs this skill when a repo health
  pass finds no (or a stale) `CHANGELOG.md`.
- **wads-pypi-polish** — owns `[project.urls]` (adds the Changelog link once
  the file exists) and the rest of the PyPI-facing metadata.
- **wads-ci-health** — owns version-sync diagnosis (pyproject vs PyPI vs
  tags); its findings explain gaps in the tag sequence.
- **wads-ci-fix** — repairs the push-back failure that causes missing tags /
  skipped version numbers in the first place.

## Closing checklist

- [ ] Target repo resolved; `git fetch --tags` run (or remote-check warning clean)
- [ ] Diagnosis reported: exists? latest covered vs latest tag, gap list
- [ ] Preview reviewed — noise filtering sane, nothing meaningful dropped silently
- [ ] `--write` run only with user intent; diff shown before any commit
- [ ] Idempotency proven with the SAME flags (no-op once backfill is complete)
- [ ] Idempotency proven (second `--write` + `diff` = no change)
- [ ] Hand-edits and `## [Unreleased]` confirmed untouched
- [ ] Unreleased commits reported but not written
- [ ] `[project.urls].Changelog` delegated to wads-pypi-polish; no `gh release` pushed
- [ ] No tags created, no versions bumped, nothing committed by the skill
