# Improved Migration Tool Output

## Before (What you experienced)

```bash
$ python -m wads.external_deps_migration apply . --dry-run

Error: Cannot auto-migrate this project
Please review the migration instructions manually
```

**Problems:**
- ❌ Doesn't explain WHY it can't migrate
- ❌ Doesn't tell you WHERE to find instructions
- ❌ Doesn't show what's actually in your config

---

## After (Improved output)

### 1. Better `apply` command output

```bash
$ python -m wads.external_deps_migration apply . --dry-run

======================================================================
❌ CANNOT AUTO-MIGRATE
======================================================================

Reasons:
• Found [tool.wads.ci.env.install] but it requires manual migration
  (install commands need to be mapped to specific packages)
• No system dependencies declared to migrate

📋 Next Steps:

1. Get detailed migration instructions:
   python -m wads.external_deps_migration instructions /path/to/project

2. View the migration guide:
   /Users/you/wads/PEP_725_MIGRATION_GUIDE.md

3. For [tool.wads.ci.env.install] format:
   - Identify which packages the install commands relate to
   - Create [external] entries with DepURLs for each package
   - Move install commands to [tool.wads.external.ops.{name}]

Current legacy format detected:
  [tool.wads.ci.env.install]
  (Contains install commands that need package mapping)

======================================================================
```

### 2. Improved `instructions` command

```bash
$ python -m wads.external_deps_migration instructions .

======================================================================
MIGRATION TO PEP 725 EXTERNAL DEPENDENCIES
======================================================================

⚠️  FOUND LEGACY INSTALL COMMANDS:
  [tool.wads.ci.env.install]

  Current install commands:
    [linux]
      curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
      curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
      sudo apt-get update
      sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev

  This format contains install commands but doesn't specify
  which packages they install. You'll need to:

  A. Identify the packages (look at apt-get/brew/choco commands)
  B. Create DepURLs for each package
  C. Move install commands to [tool.wads.external.ops]

MIGRATION STEPS:

1. Migrate [tool.wads.ci.env.install] commands to [tool.wads.external.ops]

⚠️  MANUAL MIGRATION REQUIRED

For [tool.wads.ci.env.install] format:

Step 1: Examine your current install commands
  Look at: [tool.wads.ci.env.install.linux/macos/windows]
  Identify which packages are being installed

Step 2: For each package, create entries like this:

  [external]
  dependencies = ["dep:generic/{package_name}"]

  [tool.wads.external.ops.{package_name}]
  canonical_id = "dep:generic/{package_name}"
  rationale = "Why you need this package"
  url = "https://package-homepage.org/"

  install.linux = "sudo apt-get install -y {package}"
  install.macos = "brew install {package}"
  install.windows = "choco install {package}"

Step 3: Remove old [tool.wads.ci.env.install] section

📚 DOCUMENTATION:

  Migration Guide:
    /Users/you/wads/PEP_725_MIGRATION_GUIDE.md

  Setup Utils Guide:
    /Users/you/wads/SETUP_UTILS_GUIDE.md

======================================================================
```

### 3. Improved `analyze` command

```bash
$ python -m wads.external_deps_migration analyze .

Legacy system_dependencies: False
Legacy env.install: True
Has [external]: False
Has [tool.wads.external.ops]: False
Can auto-migrate: False

Recommendations:
  - Migrate [tool.wads.ci.env.install] commands to [tool.wads.external.ops]

💡 Run with 'instructions' subcommand for detailed help:
   python -m wads.external_deps_migration instructions .
```

---

## Key Improvements

### ✅ Clear Reasons
- Explicitly states WHY auto-migration isn't possible
- Differentiates between different scenarios

### ✅ Actionable Steps
- Shows exact commands to run next
- Provides file paths to documentation
- Includes example TOML structure

### ✅ Shows Current State
- Displays actual install commands from your config
- Helps you identify which packages are being installed
- Makes it clear what needs to be mapped

### ✅ Better Documentation Links
- Points to specific guide files
- Shows full file paths when available
- Falls back to repo references

---

## Example: odbcdol Migration

### Step 1: Analyze
```bash
$ python -m wads.external_deps_migration instructions /path/to/odbcdol
```

Shows you have these install commands:
```bash
[linux]
  curl https://packages.microsoft.com/.../microsoft.asc | sudo apt-key add -
  sudo apt-get update
  sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev
```

### Step 2: Identify Packages
From the commands, you can see:
- `msodbcsql18` - Microsoft ODBC Driver
- `unixodbc-dev` - unixODBC development files

### Step 3: Create New Format

```toml
[external]
host-requires = [
    "dep:generic/unixodbc",
    "dep:generic/msodbcsql18"
]

[tool.wads.external.ops.unixodbc]
canonical_id = "dep:generic/unixodbc"
rationale = "ODBC driver interface for database connectivity"
url = "https://www.unixodbc.org/"

install.linux = [
    "sudo apt-get update",
    "sudo apt-get install -y unixodbc-dev"
]
install.macos = "brew install unixodbc"

[tool.wads.external.ops.msodbcsql18]
canonical_id = "dep:generic/msodbcsql18"
rationale = "Microsoft ODBC Driver 18 for SQL Server"
url = "https://docs.microsoft.com/sql/connect/odbc/"

install.linux = [
    "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -",
    "curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list",
    "sudo apt-get update",
    "sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18"
]
```

### Step 4: Remove old section
Comment out or remove:
```toml
# [tool.wads.ci.env]
# install.linux = [...]  # DEPRECATED
```

### Step 5: Verify
```bash
$ python -m wads.setup_utils diagnose /path/to/odbcdol
```

---

## Summary

The improved migration tool now:

1. **Explains failures clearly** - Shows exactly why auto-migration isn't possible
2. **Provides context** - Displays your current config for reference
3. **Gives actionable guidance** - Exact commands and steps to follow
4. **Links to docs** - Shows file paths to detailed guides
5. **Shows examples** - Template TOML for the new format

This makes manual migration straightforward instead of frustrating!
