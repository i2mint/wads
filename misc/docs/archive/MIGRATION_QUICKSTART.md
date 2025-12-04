# Quick Start Guide: Wads CI Migration Agent

Get your project migrated to wads v3 CI format in 5 minutes.

## Prerequisites

- Python 3.10 or later
- An Anthropic API key ([get one here](https://console.anthropic.com/))
- A project with either `pyproject.toml` or `setup.cfg`

## Step 1: Installation (1 minute)

```bash
# Clone or download the agent
cd /path/to/migration-agent

# Install dependencies
pip install anthropic

# Set your API key
export ANTHROPIC_API_KEY='your-api-key-here'
```

## Step 2: Test the Analysis (30 seconds)

First, run the demo to see what the agent will analyze:

```bash
python demo_analysis.py /path/to/your/project
```

This shows you what information will be extracted without making any API calls.

## Step 3: Run the Migration (2 minutes)

```bash
python wads_ci_migration_agent.py /path/to/your/project
```

For better dependency detection, add code analysis:

```bash
python wads_ci_migration_agent.py /path/to/your/project --analyze-code
```

## Step 4: Review the Output (2 minutes)

The agent creates `pyproject.toml.migrated` in your project directory.

```bash
# Compare with current config
cd /path/to/your/project
diff pyproject.toml pyproject.toml.migrated

# Or use a visual diff tool
code --diff pyproject.toml pyproject.toml.migrated
```

## Step 5: Apply the Migration

Once you're satisfied with the changes:

```bash
# Backup your current config
cp pyproject.toml pyproject.toml.backup

# Apply the migration
mv pyproject.toml.migrated pyproject.toml

# Update your CI workflow (replace with v3 template)
cp /path/to/github_ci_publish_2025.yml .github/workflows/ci.yml

# Commit the changes
git add pyproject.toml .github/workflows/ci.yml
git commit -m "Migrate to wads v3 CI format with PEP 725/804 compliance"
git push
```

## Common Scenarios

### Scenario 1: Simple Project (No System Dependencies)

Your project only needs Python packages.

**Before:**
```toml
[project]
name = "mypackage"
dependencies = ["requests", "click"]
```

**After running agent:**
```toml
[project]
name = "mypackage"
dependencies = ["requests", "click"]

[external]
# No system dependencies needed

[tool.wads.ci]
project_name = "mypackage"

[tool.wads.ci.testing]
python_versions = ["3.10", "3.12"]
# ... full CI configuration
```

### Scenario 2: Project with System Dependencies

Your project needs ODBC, ffmpeg, or other system libraries.

**CI has:**
```yaml
- name: Install deps
  run: |
    sudo apt-get install -y ffmpeg libsndfile1
    brew install ffmpeg libsndfile
```

**After running agent:**
```toml
[external]
dependencies = [
    "dep:generic/ffmpeg",
    "dep:generic/libsndfile"
]

[tool.wads.external.ops.ffmpeg]
canonical_id = "dep:generic/ffmpeg"
install.linux = "sudo apt-get install -y ffmpeg"
install.macos = "brew install ffmpeg"
# ... full operational metadata
```

### Scenario 3: Project with Custom Build Steps

Your CI has pre-test setup or custom commands.

**CI has:**
```yaml
- name: Setup
  run: python scripts/generate_test_data.py
- name: Test
  run: pytest --cov=mypackage
```

**After running agent:**
```toml
[tool.wads.ci.commands]
pre_test = ["python scripts/generate_test_data.py"]
test = ["pytest --cov=mypackage"]
```

## Troubleshooting

### Problem: "No pyproject.toml or setup.cfg found"

**Solution:** Create a minimal `pyproject.toml`:

```bash
cat > pyproject.toml << 'EOF'
[project]
name = "myproject"
version = "0.1.0"
EOF
```

### Problem: Agent suggests wrong DepURL

**Solution:** Manually edit `pyproject.toml.migrated`:

```toml
# Change from:
[external]
dependencies = ["dep:generic/gcc"]

# To:
[external]
build-requires = ["dep:virtual/compiler/c"]
```

### Problem: Missing some dependencies

**Solution:** Run with code analysis:

```bash
python wads_ci_migration_agent.py . --analyze-code
```

Or manually add them:

```toml
[external]
dependencies = [
    "dep:generic/unixodbc",
    "dep:generic/your-missing-dep",  # Add this
]

[tool.wads.external.ops.your-missing-dep]
canonical_id = "dep:generic/your-missing-dep"
install.linux = "sudo apt-get install -y your-missing-dep"
```

## Pro Tips

### Tip 1: Batch Migration

Migrate multiple projects at once:

```bash
for project in proj1 proj2 proj3; do
    echo "=== Migrating $project ==="
    python wads_ci_migration_agent.py "./$project" --analyze-code
done
```

### Tip 2: Version Control Integration

Create a branch for the migration:

```bash
cd /path/to/your/project
git checkout -b wads-v3-migration

# Run migration
python /path/to/wads_ci_migration_agent.py .

# Review and commit
git add pyproject.toml .github/workflows/ci.yml
git commit -m "Migrate to wads v3 CI format"
git push origin wads-v3-migration

# Create PR for review
```

### Tip 3: Test Before Committing

Test the new configuration locally:

```bash
# Install dev dependencies
pip install -e .[dev]

# Run tests
pytest

# Check linting
ruff check .

# Verify everything works before pushing
```

## What the Agent Does

1. ✅ **Reads your config** - Parses `pyproject.toml` or `setup.cfg`
2. ✅ **Analyzes your CI** - Extracts system dependencies, env vars, Python versions
3. ✅ **Converts to DepURLs** - Maps packages to PEP 725 format
4. ✅ **Generates metadata** - Creates platform-specific install commands
5. ✅ **Preserves settings** - Keeps all your existing configuration
6. ✅ **Explains changes** - Documents decisions and assumptions

## What You Need to Review

- [ ] **System dependencies** - Are all required packages listed?
- [ ] **Platform commands** - Do install commands work on your platforms?
- [ ] **Python versions** - Are you testing the right versions?
- [ ] **Environment variables** - Are secrets properly configured?
- [ ] **Build settings** - Are sdist/wheel settings correct?

## Next Steps

After migration:

1. **Test locally** - Ensure tests pass with new config
2. **Push to CI** - Let GitHub Actions validate the migration
3. **Monitor first run** - Check CI logs for any issues
4. **Iterate** - Fine-tune configuration as needed
5. **Document** - Update your README with new CI format

## Getting Help

- **Demo mode**: `python demo_analysis.py /path/to/project`
- **Full example**: See `EXAMPLE_OUTPUT.md`
- **Detailed docs**: See `AGENT_README.md`

## Resources

- [PEP 725 - External Dependencies](https://peps.python.org/pep-0725/)
- [PEP 804 - External Dependency Registry](https://peps.python.org/pep-0804/)
- [Wads Documentation](https://github.com/i2mint/wads)
- [DepURL Specification](https://github.com/package-url/purl-spec)

---

**Time saved:** ~2 hours of manual configuration per project 🎉
