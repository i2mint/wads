---
name: setup-py-project
description: Use when the user wants to create a new Python project/package, name a project, set up a GitHub repo, or bootstrap a project from scratch. Triggers on requests like "help me set up a project", "create a package", "I need a name for...", "new repo for...".
argument-hint: "[project-name-or-description]"
---

# AI-Assisted Python Project Setup

You are helping the user create a new Python project from scratch (or partially). Use the `wads` package tools to do the heavy lifting. Always confirm before taking irreversible actions (repo creation, git push).

## Quick Reference: Key Functions

All functions are in `wads.project_setup` and `wads.user_dirs`:

```python
# Name checking
from wads.project_setup import check_name_availability, check_names, is_available_on_pypi, is_available_on_github

# Name candidate pools
from wads.project_setup import list_name_candidate_files, load_name_candidates

# GitHub operations
from wads.project_setup import detect_github_username, create_github_repo, repo_exists

# Full orchestration
from wads.project_setup import setup_project, create_misc_docs, setup_opsward_for_project

# User preferences
from wads.user_dirs import read_user_preferences, write_user_preferences, name_candidates_dir, config_dir
```

## Conversation Flow

### 1. Understand what the user wants

Determine the scope. The user may want:
- **Full setup**: Name → repo → files → commit/push (guide them through everything)
- **Just naming help**: Check availability, suggest names
- **Just populate**: An existing repo needs project files
- **Just create a repo**: Name and description are ready

### 2. Gather project information

**Always needed**: name (or help choosing one), short description.
**Detect automatically**: GitHub username/org, author name, license.
**Ask only if relevant**: org (if different from personal), license (if not MIT), extra dependencies.

Run this early to detect defaults:
```bash
python -c "
from wads.user_dirs import read_user_preferences
from wads.project_setup import detect_github_username
prefs = read_user_preferences()
username = detect_github_username()
print(f'Preferences: {prefs}')
print(f'GitHub username: {username}')
"
```

### 3. Name assistance protocol

If the user needs help with a name:

**Step A — Check name candidate pools:**
```bash
python -c "
from wads.project_setup import list_name_candidate_files, load_name_candidates
files = list_name_candidate_files()
if files:
    print('Available name pools:')
    for f in files:
        names = load_name_candidates(f)
        print(f'  {f.name}: {len(names)} names')
else:
    print('No name candidate files found.')
"
```

If no candidate files exist, tell the user:
> You don't have any name candidate pools set up. You can create text files (one name per line) in:
> `{name_candidates_dir path}`
> For example, create `short_words.txt` or `latin_names.txt` with names you like.
> I'll check them for availability next time.

**Step B — Generate suggestions:**
Use your own creativity to suggest 5-8 names based on the description. Consider:
- Short, memorable names (2-8 chars are ideal for Python packages)
- Relevant to the project's purpose
- Acronyms if the user has mentioned them
- Names from candidate pools that fit

If candidate pools exist, also filter pool names for relevance to the description and include good matches.

**Step C — Check all candidates:**
```bash
python -c "
from wads.project_setup import check_names
import json
names = ['name1', 'name2', 'name3']  # all candidates
results = check_names(names, org='USERNAME')
for r in results:
    status = []
    if not r['valid_pep508']: status.append('INVALID')
    if r['pypi_available'] == False: status.append(f'PyPI taken: {r[\"pypi_url\"]}')
    elif r['pypi_available']: status.append('PyPI ✓')
    if r['github_available'] == False: status.append(f'GitHub taken: {r[\"github_url\"]}')
    elif r['github_available']: status.append('GitHub ✓')
    print(f'{r[\"name\"]}: {\" | \".join(status)}')
"
```

**Step D — Present results** as a clear table and let the user pick or suggest alternatives.

### 4. Confirm before acting

Before creating a repo or populating files, present a summary:

> Here's what I'll do:
> - **Name**: `mypackage`
> - **Description**: "A tool for doing X"
> - **GitHub**: Create `username/mypackage` (public)
> - **Author**: Thor Whalen
> - **License**: MIT
> - **CI template**: uv-based (modern default)
>
> This will create the repo and populate it with pyproject.toml, CI workflow, README, etc.
> Shall I proceed?

### 5. Execute

For full setup, use `setup_project`:
```bash
python -c "
from wads.project_setup import setup_project
result = setup_project(
    'mypackage',
    description='A tool for doing X',
    org='username',
    author='Thor Whalen',
    license='mit',
    create_repo=True,
    populate=True,
    create_devdocs=False,
    setup_opsward=False,
)
print(result)
"
```

Or call individual functions for partial flows (populate only, repo only, etc.).

### 6. Post-creation options

After the main setup, offer (don't force) these extras:

1. **Dev docs**: "Would you like me to create `misc/docs/` with research, design, and roadmap templates?"
   ```python
   from wads.project_setup import create_misc_docs
   create_misc_docs('/path/to/project')
   ```

2. **AI agent setup**: Check if opsward is available first:
   ```bash
   python -c "import opsward; print('available')" 2>/dev/null && echo "opsward is installed"
   ```
   If available: "Would you like me to set up AI agent configuration with opsward?"

3. **Initial commit**: "Would you like me to make the initial commit and push?"
   ```bash
   cd /path/to/project && git add -A && git commit -m "Initial project setup via wads" && git push -u origin main
   ```

4. **Publish to PyPI**: "Would you like to publish to PyPI? (This runs `pack go .`)"

### 7. Save preferences

If this is the user's first time, offer to save detected defaults:
```python
from wads.user_dirs import write_user_preferences
write_user_preferences({
    "github_username": "detected_username",
    "default_author": "Author Name",
    "default_license": "mit",
    "default_org": "org_name",  # if different from username
})
```

## Important Notes

- **Never create a repo without confirmation.** Always present the plan first.
- **Always check availability before proposing a name as final.** Don't present a taken name as a good option.
- **If `gh` CLI is not installed**, tell the user and provide install instructions. You can still help with naming and populate (just skip repo creation).
- **populate_pkg_dir is idempotent** — it skips files that already exist. Safe to run on an existing project.
- **The uv CI template** (`github_ci_uv.yml`) is the modern default. It's automatically used by populate.
