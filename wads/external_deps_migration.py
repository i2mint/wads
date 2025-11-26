"""
Migration tools for PEP 725/804 external dependencies format.

This module helps migrate from:
- Old [tool.wads.ci.testing.system_dependencies] format
- setup.cfg system dependency declarations
- Hardcoded CI workflow system installs

To the new:
- [external] with DepURLs (PEP 725)
- [tool.wads.external.ops] operational metadata

Key Functions:
    migrate_system_deps_to_external: Convert legacy format to new format
    analyze_migration_needed: Check if migration is needed
    generate_migration_instructions: Create step-by-step instructions
    apply_migration: Automatically migrate pyproject.toml
"""

from typing import Dict, List, Tuple, Optional, Set
from pathlib import Path
from dataclasses import dataclass
import sys
import re

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

try:
    import tomli_w
except ImportError:
    tomli_w = None

from wads.ci_config import CIConfig, _depurl_to_simple_name
from wads.toml_util import read_pyproject_toml


# Package name to DepURL mapping (common packages)
COMMON_PACKAGE_DEPURLS = {
    # Audio/Video
    'ffmpeg': 'dep:generic/ffmpeg',
    'libsndfile': 'dep:generic/libsndfile',
    'libsndfile1': 'dep:generic/libsndfile',
    'portaudio': 'dep:generic/portaudio',
    'portaudio19-dev': 'dep:generic/portaudio',
    'libportaudio2': 'dep:generic/portaudio',

    # Development tools
    'git': 'dep:generic/git',
    'make': 'dep:generic/make',
    'cmake': 'dep:generic/cmake',
    'gcc': 'dep:virtual/compiler/c',
    'g++': 'dep:virtual/compiler/cpp',
    'clang': 'dep:virtual/compiler/c',

    # Database/ODBC
    'unixodbc': 'dep:generic/unixodbc',
    'unixodbc-dev': 'dep:generic/unixodbc',
    'msodbcsql18': 'dep:generic/msodbcsql18',
    'postgresql': 'dep:generic/postgresql',
    'libpq-dev': 'dep:generic/postgresql',
    'mysql': 'dep:generic/mysql',
    'libmysqlclient-dev': 'dep:generic/mysql',

    # Libraries
    'libffi': 'dep:generic/libffi',
    'libffi-dev': 'dep:generic/libffi',
    'libssl': 'dep:generic/openssl',
    'libssl-dev': 'dep:generic/openssl',
    'openssl': 'dep:generic/openssl',
    'zlib': 'dep:generic/zlib',
    'zlib1g-dev': 'dep:generic/zlib',

    # Other
    'curl': 'dep:generic/curl',
    'wget': 'dep:generic/wget',
    'docker': 'dep:generic/docker',
}


# Default install commands for common packages
DEFAULT_INSTALL_COMMANDS = {
    'ffmpeg': {
        'linux': 'sudo apt-get install -y ffmpeg',
        'macos': 'brew install ffmpeg',
        'windows': 'choco install ffmpeg'
    },
    'libsndfile': {
        'linux': 'sudo apt-get install -y libsndfile1',
        'macos': 'brew install libsndfile'
    },
    'portaudio': {
        'linux': 'sudo apt-get install -y libportaudio2 portaudio19-dev',
        'macos': 'brew install portaudio',
        'windows': 'choco install portaudio'
    },
    'git': {
        'linux': 'sudo apt-get install -y git',
        'macos': 'brew install git',
        'windows': 'choco install git'
    },
    'unixodbc': {
        'linux': ['sudo apt-get update', 'sudo apt-get install -y unixodbc unixodbc-dev'],
        'macos': 'brew install unixodbc'
    },
    'postgresql': {
        'linux': 'sudo apt-get install -y postgresql libpq-dev',
        'macos': 'brew install postgresql',
        'windows': 'choco install postgresql'
    },
    'mysql': {
        'linux': 'sudo apt-get install -y mysql-server libmysqlclient-dev',
        'macos': 'brew install mysql',
        'windows': 'choco install mysql'
    },
    'openssl': {
        'linux': 'sudo apt-get install -y libssl-dev',
        'macos': 'brew install openssl',
        'windows': 'choco install openssl'
    },
}


# Package metadata (rationale, URLs)
PACKAGE_METADATA = {
    'ffmpeg': {
        'rationale': 'Multimedia framework for audio and video processing',
        'url': 'https://ffmpeg.org/'
    },
    'libsndfile': {
        'rationale': 'Library for reading and writing audio files',
        'url': 'http://www.mega-nerd.com/libsndfile/'
    },
    'portaudio': {
        'rationale': 'Cross-platform audio I/O library',
        'url': 'http://www.portaudio.com/'
    },
    'git': {
        'rationale': 'Distributed version control system',
        'url': 'https://git-scm.com/'
    },
    'unixodbc': {
        'rationale': 'ODBC driver interface for database connectivity',
        'url': 'https://www.unixodbc.org/'
    },
    'postgresql': {
        'rationale': 'PostgreSQL database and client libraries',
        'url': 'https://www.postgresql.org/'
    },
    'mysql': {
        'rationale': 'MySQL database and client libraries',
        'url': 'https://www.mysql.com/'
    },
    'openssl': {
        'rationale': 'Cryptography and SSL/TLS toolkit',
        'url': 'https://www.openssl.org/'
    },
}


@dataclass
class MigrationAnalysis:
    """Analysis of what needs to be migrated."""
    has_legacy_system_deps: bool
    has_legacy_env_install: bool
    has_external_section: bool
    has_external_ops: bool
    legacy_packages: List[str]
    legacy_platform_specific: Dict[str, List[str]]
    current_depurls: List[str]
    recommendations: List[str]
    can_auto_migrate: bool
    source_path: Optional[Path] = None  # Path to pyproject.toml for reference


def normalize_package_name(package: str) -> str:
    """
    Normalize package name by removing version suffixes and dev packages.

    Examples:
        "libsndfile1" -> "libsndfile"
        "unixodbc-dev" -> "unixodbc"
        "python3.10" -> "python"
    """
    # Remove common suffixes
    name = package.lower().strip()
    name = re.sub(r'-dev$', '', name)
    name = re.sub(r'\d+$', '', name)  # trailing numbers
    name = re.sub(r'lib(.+)', r'\1', name)  # lib prefix
    return name


def guess_depurl_for_package(package: str) -> str:
    """
    Guess appropriate DepURL for a package name.

    Args:
        package: Package name (e.g., "ffmpeg", "libsndfile1")

    Returns:
        DepURL string (e.g., "dep:generic/ffmpeg")
    """
    package_lower = package.lower().strip()

    # Check exact match first
    if package_lower in COMMON_PACKAGE_DEPURLS:
        return COMMON_PACKAGE_DEPURLS[package_lower]

    # Try normalized name
    normalized = normalize_package_name(package)
    if normalized in COMMON_PACKAGE_DEPURLS:
        return COMMON_PACKAGE_DEPURLS[normalized]

    # Default to generic with normalized name
    return f"dep:generic/{normalized}"


def analyze_migration_needed(pyproject_path: str | Path) -> MigrationAnalysis:
    """
    Analyze if migration is needed and what needs to be migrated.

    Args:
        pyproject_path: Path to pyproject.toml or directory containing it

    Returns:
        MigrationAnalysis with detailed information
    """
    pyproject_path = Path(pyproject_path)
    if pyproject_path.is_dir():
        pyproject_path = pyproject_path / "pyproject.toml"

    if not pyproject_path.exists():
        return MigrationAnalysis(
            has_legacy_system_deps=False,
            has_legacy_env_install=False,
            has_external_section=False,
            has_external_ops=False,
            legacy_packages=[],
            legacy_platform_specific={},
            current_depurls=[],
            recommendations=["No pyproject.toml found"],
            can_auto_migrate=False
        )

    with open(pyproject_path, 'rb') as f:
        data = tomllib.load(f)

    config = CIConfig(data)

    # Check for legacy formats
    system_deps = config.system_dependencies
    has_legacy_system_deps = bool(system_deps)

    # Legacy env.install format
    legacy_env_install = (
        data.get('tool', {})
        .get('wads', {})
        .get('ci', {})
        .get('env', {})
        .get('install', {})
    )
    has_legacy_env_install = bool(legacy_env_install)

    # Check for new format
    external = data.get('external', {})
    has_external_section = bool(
        external.get('build-requires') or
        external.get('host-requires') or
        external.get('dependencies')
    )

    external_ops = (
        data.get('tool', {})
        .get('wads', {})
        .get('external', {})
        .get('ops', {})
    )
    has_external_ops = bool(external_ops)

    # Extract legacy packages
    legacy_packages = []
    legacy_platform_specific = {}

    if isinstance(system_deps, list):
        legacy_packages = system_deps
        legacy_platform_specific = {'ubuntu': system_deps}
    elif isinstance(system_deps, dict):
        legacy_platform_specific = system_deps
        # Collect all unique packages
        for packages in system_deps.values():
            legacy_packages.extend(packages)
        legacy_packages = list(set(legacy_packages))

    # Extract current DepURLs
    current_depurls = []
    if has_external_section:
        current_depurls = (
            external.get('build-requires', []) +
            external.get('host-requires', []) +
            external.get('dependencies', [])
        )

    # Generate recommendations
    recommendations = []

    if has_legacy_system_deps and not has_external_section:
        recommendations.append(
            "Migrate [tool.wads.ci.testing.system_dependencies] to [external] with DepURLs"
        )

    if has_external_section and not has_external_ops and current_depurls:
        recommendations.append(
            "Add [tool.wads.external.ops] sections for operational metadata"
        )

    if has_legacy_env_install:
        recommendations.append(
            "Migrate [tool.wads.ci.env.install] commands to [tool.wads.external.ops]"
        )

    if not recommendations:
        if has_external_section and has_external_ops:
            recommendations.append("✓ Already using PEP 725 format")
        else:
            recommendations.append("No external dependencies declared")

    can_auto_migrate = (
        has_legacy_system_deps and
        not has_external_section and
        all(guess_depurl_for_package(pkg) for pkg in legacy_packages)
    )

    return MigrationAnalysis(
        has_legacy_system_deps=has_legacy_system_deps,
        has_legacy_env_install=has_legacy_env_install,
        has_external_section=has_external_section,
        has_external_ops=has_external_ops,
        legacy_packages=legacy_packages,
        legacy_platform_specific=legacy_platform_specific,
        current_depurls=current_depurls,
        recommendations=recommendations,
        can_auto_migrate=can_auto_migrate,
        source_path=pyproject_path
    )


def generate_migration_toml(analysis: MigrationAnalysis) -> str:
    """
    Generate TOML content for migrated external dependencies.

    Args:
        analysis: MigrationAnalysis result

    Returns:
        TOML string to add to pyproject.toml
    """
    lines = []

    if not analysis.legacy_packages:
        return "# No legacy dependencies to migrate"

    lines.append("# ============================================================================")
    lines.append("# EXTERNAL DEPENDENCIES (PEP 725)")
    lines.append("# ============================================================================")
    lines.append("# Migrated from [tool.wads.ci.testing.system_dependencies]")
    lines.append("")

    # Group packages and generate DepURLs
    depurls = []
    seen_depurls = set()

    for package in analysis.legacy_packages:
        depurl = guess_depurl_for_package(package)
        if depurl not in seen_depurls:
            depurls.append(depurl)
            seen_depurls.add(depurl)

    # Add to [external] section
    lines.append("[external]")
    lines.append("# Runtime dependencies")
    lines.append("dependencies = [")
    for depurl in depurls:
        lines.append(f'    "{depurl}",')
    lines.append("]")
    lines.append("")

    # Generate operational metadata
    lines.append("# ============================================================================")
    lines.append("# WADS EXTERNAL OPERATIONS")
    lines.append("# ============================================================================")
    lines.append("")

    for depurl in depurls:
        simple_name = _depurl_to_simple_name(depurl)

        lines.append(f"[tool.wads.external.ops.{simple_name}]")
        lines.append(f'canonical_id = "{depurl}"')

        # Add metadata if available
        if simple_name in PACKAGE_METADATA:
            metadata = PACKAGE_METADATA[simple_name]
            lines.append(f'rationale = "{metadata["rationale"]}"')
            lines.append(f'url = "{metadata["url"]}"')

        # Add install commands
        if simple_name in DEFAULT_INSTALL_COMMANDS:
            install_cmds = DEFAULT_INSTALL_COMMANDS[simple_name]

            for platform, cmd in install_cmds.items():
                if isinstance(cmd, list):
                    lines.append(f"install.{platform} = [")
                    for c in cmd:
                        lines.append(f'    "{c}",')
                    lines.append("]")
                else:
                    lines.append(f'install.{platform} = "{cmd}"')
        else:
            # Generate basic install commands
            lines.append(f'install.linux = "sudo apt-get install -y {simple_name}"')
            lines.append(f'install.macos = "brew install {simple_name}"')

        lines.append("")

    return '\n'.join(lines)


def generate_migration_instructions(analysis: MigrationAnalysis) -> str:
    """
    Generate human-readable migration instructions.

    Args:
        analysis: MigrationAnalysis result

    Returns:
        Formatted instructions string
    """
    lines = []

    lines.append("="*70)
    lines.append("MIGRATION TO PEP 725 EXTERNAL DEPENDENCIES")
    lines.append("="*70)
    lines.append("")

    # Status
    if analysis.has_external_section and analysis.has_external_ops:
        lines.append("✓ Your project already uses PEP 725 format!")
        lines.append("")
        lines.append(f"Current DepURLs: {len(analysis.current_depurls)}")
        return '\n'.join(lines)

    # What needs to be migrated
    if analysis.has_legacy_system_deps:
        lines.append("FOUND LEGACY FORMAT:")
        lines.append("  [tool.wads.ci.testing.system_dependencies]")
        lines.append(f"  Packages: {', '.join(analysis.legacy_packages)}")
        lines.append("")

    if analysis.has_legacy_env_install:
        lines.append("⚠️  FOUND LEGACY INSTALL COMMANDS:")
        lines.append("  [tool.wads.ci.env.install]")
        lines.append("")

        # Try to read and show actual commands
        if analysis.source_path and analysis.source_path.exists():
            try:
                with open(analysis.source_path, 'rb') as f:
                    data = tomllib.load(f)

                env_install = (
                    data.get('tool', {})
                    .get('wads', {})
                    .get('ci', {})
                    .get('env', {})
                    .get('install', {})
                )

                if env_install:
                    lines.append("  Current install commands:")
                    for platform, cmds in env_install.items():
                        lines.append(f"    [{platform}]")
                        if isinstance(cmds, list):
                            for cmd in cmds:
                                lines.append(f"      {cmd}")
                        else:
                            lines.append(f"      {cmds}")
                    lines.append("")
            except Exception:
                pass

        lines.append("  This format contains install commands but doesn't specify")
        lines.append("  which packages they install. You'll need to:")
        lines.append("")
        lines.append("  A. Identify the packages (look at apt-get/brew/choco commands)")
        lines.append("  B. Create DepURLs for each package")
        lines.append("  C. Move install commands to [tool.wads.external.ops]")
        lines.append("")

    # Recommendations
    lines.append("MIGRATION STEPS:")
    lines.append("")

    for i, rec in enumerate(analysis.recommendations, 1):
        lines.append(f"{i}. {rec}")

    lines.append("")

    # Auto-migration option
    if analysis.can_auto_migrate:
        lines.append("✓ This project can be AUTO-MIGRATED")
        lines.append("")
        lines.append("Run: python -m wads.external_deps_migration apply /path/to/project")
        lines.append("")
    else:
        lines.append("⚠️  MANUAL MIGRATION REQUIRED")
        lines.append("")

        # Detailed manual steps for env.install case
        if analysis.has_legacy_env_install:
            lines.append("For [tool.wads.ci.env.install] format:")
            lines.append("")
            lines.append("Step 1: Examine your current install commands")
            lines.append("  Look at: [tool.wads.ci.env.install.linux/macos/windows]")
            lines.append("  Identify which packages are being installed")
            lines.append("")
            lines.append("Step 2: For each package, create entries like this:")
            lines.append("")
            lines.append("  [external]")
            lines.append('  dependencies = ["dep:generic/{package_name}"]')
            lines.append("")
            lines.append("  [tool.wads.external.ops.{package_name}]")
            lines.append('  canonical_id = "dep:generic/{package_name}"')
            lines.append('  rationale = "Why you need this package"')
            lines.append('  url = "https://package-homepage.org/"')
            lines.append("")
            lines.append('  install.linux = "sudo apt-get install -y {package}"')
            lines.append('  install.macos = "brew install {package}"')
            lines.append('  install.windows = "choco install {package}"')
            lines.append("")
            lines.append("Step 3: Remove old [tool.wads.ci.env.install] section")
            lines.append("")

        if not analysis.has_legacy_env_install:
            lines.append("General steps:")
            lines.append("1. Add the generated [external] section to your pyproject.toml")
            lines.append("2. Add [tool.wads.external.ops.{name}] sections for each dependency")
            lines.append("3. Test with: python -m wads.setup_utils diagnose /path/to/project")
            lines.append("4. Remove old sections once verified")
            lines.append("")

    # Documentation reference
    lines.append("📚 DOCUMENTATION:")
    lines.append("")
    lines.append("  Migration Guide:")
    migration_guide = Path(__file__).parent.parent / "PEP_725_MIGRATION_GUIDE.md"
    if migration_guide.exists():
        lines.append(f"    {migration_guide}")
    else:
        lines.append("    PEP_725_MIGRATION_GUIDE.md (in wads repository)")
    lines.append("")
    lines.append("  Setup Utils Guide:")
    setup_guide = Path(__file__).parent.parent / "SETUP_UTILS_GUIDE.md"
    if setup_guide.exists():
        lines.append(f"    {setup_guide}")
    else:
        lines.append("    SETUP_UTILS_GUIDE.md (in wads repository)")
    lines.append("")

    # Preview of migration
    if analysis.legacy_packages:
        lines.append("PREVIEW OF MIGRATION:")
        lines.append("")
        lines.append("Will convert:")
        for package in analysis.legacy_packages[:5]:  # Show first 5
            depurl = guess_depurl_for_package(package)
            lines.append(f'  "{package}" → "{depurl}"')
        if len(analysis.legacy_packages) > 5:
            lines.append(f"  ... and {len(analysis.legacy_packages) - 5} more")
        lines.append("")

    lines.append("="*70)

    return '\n'.join(lines)


def apply_migration(
    pyproject_path: str | Path,
    backup: bool = True,
    dry_run: bool = False
) -> bool:
    """
    Automatically migrate pyproject.toml to PEP 725 format.

    Args:
        pyproject_path: Path to pyproject.toml or directory containing it
        backup: Create .bak file before modifying
        dry_run: Show what would be done without making changes

    Returns:
        True if migration was successful
    """
    if tomli_w is None:
        print("Error: tomli_w required for writing TOML")
        print("Install with: pip install tomli_w")
        return False

    pyproject_path = Path(pyproject_path)
    if pyproject_path.is_dir():
        pyproject_path = pyproject_path / "pyproject.toml"

    if not pyproject_path.exists():
        print(f"Error: {pyproject_path} not found")
        return False

    # Analyze
    analysis = analyze_migration_needed(pyproject_path)

    if not analysis.can_auto_migrate:
        print("\n" + "="*70)
        print("❌ CANNOT AUTO-MIGRATE")
        print("="*70)
        print("")

        # Explain WHY we can't auto-migrate
        reasons = []

        if not analysis.has_legacy_system_deps and not analysis.has_legacy_env_install:
            reasons.append("• No legacy format found to migrate from")

        if analysis.has_external_section:
            reasons.append("• Project already has [external] section (manual merge needed)")

        if analysis.has_legacy_env_install and not analysis.legacy_packages:
            reasons.append("• Found [tool.wads.ci.env.install] but it requires manual migration")
            reasons.append("  (install commands need to be mapped to specific packages)")

        if not analysis.legacy_packages:
            reasons.append("• No system dependencies declared to migrate")

        if reasons:
            print("Reasons:")
            for reason in reasons:
                print(reason)
            print("")

        # Provide clear next steps
        print("📋 Next Steps:")
        print("")
        print("1. Get detailed migration instructions:")
        print(f"   python -m wads.external_deps_migration instructions {pyproject_path.parent}")
        print("")
        print("2. View the migration guide:")
        migration_guide = Path(__file__).parent.parent / "PEP_725_MIGRATION_GUIDE.md"
        if migration_guide.exists():
            print(f"   cat {migration_guide}")
        else:
            print("   See PEP_725_MIGRATION_GUIDE.md in the wads repository")
        print("")
        print("3. For [tool.wads.ci.env.install] format:")
        print("   - Identify which packages the install commands relate to")
        print("   - Create [external] entries with DepURLs for each package")
        print("   - Move install commands to [tool.wads.external.ops.{name}]")
        print("")

        # Show current state for context
        if analysis.has_legacy_env_install:
            print("Current legacy format detected:")
            print("  [tool.wads.ci.env.install]")
            print("  (Contains install commands that need package mapping)")
            print("")

        print("="*70)
        return False

    # Read current content
    with open(pyproject_path, 'rb') as f:
        data = tomllib.load(f)

    if dry_run:
        print("DRY RUN - Would perform the following:")
        print("")
        print(generate_migration_toml(analysis))
        return True

    # Create backup
    if backup:
        backup_path = pyproject_path.with_suffix('.toml.bak')
        with open(pyproject_path, 'rb') as src:
            with open(backup_path, 'wb') as dst:
                dst.write(src.read())
        print(f"✓ Created backup: {backup_path}")

    # Add [external] section
    if 'external' not in data:
        data['external'] = {}

    # Convert packages to DepURLs
    depurls = []
    seen_depurls = set()

    for package in analysis.legacy_packages:
        depurl = guess_depurl_for_package(package)
        if depurl not in seen_depurls:
            depurls.append(depurl)
            seen_depurls.add(depurl)

    data['external']['dependencies'] = depurls

    # Add [tool.wads.external.ops]
    if 'tool' not in data:
        data['tool'] = {}
    if 'wads' not in data['tool']:
        data['tool']['wads'] = {}
    if 'external' not in data['tool']['wads']:
        data['tool']['wads']['external'] = {}
    if 'ops' not in data['tool']['wads']['external']:
        data['tool']['wads']['external']['ops'] = {}

    ops = data['tool']['wads']['external']['ops']

    for depurl in depurls:
        simple_name = _depurl_to_simple_name(depurl)

        if simple_name in ops:
            continue  # Don't overwrite existing ops

        ops[simple_name] = {'canonical_id': depurl}

        # Add metadata
        if simple_name in PACKAGE_METADATA:
            metadata = PACKAGE_METADATA[simple_name]
            ops[simple_name]['rationale'] = metadata['rationale']
            ops[simple_name]['url'] = metadata['url']

        # Add install commands
        if simple_name in DEFAULT_INSTALL_COMMANDS:
            ops[simple_name]['install'] = DEFAULT_INSTALL_COMMANDS[simple_name]

    # Comment out old system_dependencies (can't remove with tomli_w, need manual)
    # Note: tomli_w doesn't preserve comments, so we'll print a warning

    # Write updated file
    with open(pyproject_path, 'wb') as f:
        tomli_w.dump(data, f)

    print(f"✓ Migrated {len(depurls)} dependencies to PEP 725 format")
    print("")
    print("⚠ IMPORTANT: Please manually remove or comment out the old format:")
    print("  [tool.wads.ci.testing]")
    print("  system_dependencies = ...")
    print("")
    print("Run diagnostics to verify:")
    print(f"  python -m wads.setup_utils diagnose {pyproject_path.parent}")

    return True


# CLI interface
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Migrate to PEP 725 external dependencies format'
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # analyze command
    analyze_cmd = subparsers.add_parser('analyze', help='Analyze migration needed')
    analyze_cmd.add_argument('path', help='Path to pyproject.toml or directory')

    # instructions command
    instructions_cmd = subparsers.add_parser('instructions', help='Generate migration instructions')
    instructions_cmd.add_argument('path', help='Path to pyproject.toml or directory')

    # preview command
    preview_cmd = subparsers.add_parser('preview', help='Preview migrated TOML')
    preview_cmd.add_argument('path', help='Path to pyproject.toml or directory')

    # apply command
    apply_cmd = subparsers.add_parser('apply', help='Apply automatic migration')
    apply_cmd.add_argument('path', help='Path to pyproject.toml or directory')
    apply_cmd.add_argument('--no-backup', action='store_true', help='Skip backup creation')
    apply_cmd.add_argument('--dry-run', action='store_true', help='Show what would be done')

    args = parser.parse_args()

    if args.command == 'analyze':
        analysis = analyze_migration_needed(args.path)
        print(f"Legacy system_dependencies: {analysis.has_legacy_system_deps}")
        print(f"Legacy env.install: {analysis.has_legacy_env_install}")
        print(f"Has [external]: {analysis.has_external_section}")
        print(f"Has [tool.wads.external.ops]: {analysis.has_external_ops}")
        print(f"Can auto-migrate: {analysis.can_auto_migrate}")
        print("")
        print("Recommendations:")
        for rec in analysis.recommendations:
            print(f"  - {rec}")

    elif args.command == 'instructions':
        analysis = analyze_migration_needed(args.path)
        print(generate_migration_instructions(analysis))

    elif args.command == 'preview':
        analysis = analyze_migration_needed(args.path)
        print(generate_migration_toml(analysis))

    elif args.command == 'apply':
        success = apply_migration(
            args.path,
            backup=not args.no_backup,
            dry_run=args.dry_run
        )
        sys.exit(0 if success else 1)

    else:
        parser.print_help()
