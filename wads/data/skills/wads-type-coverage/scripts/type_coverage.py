"""Type-annotation coverage audit for a wads-managed Python repo.

Measures public-API type completeness (pyright --verifytypes), collects an
agent-actionable missing-annotation work list (ruff ANN rules) bucketed
public/private, checks the py.typed marker (present locally? shipped in the
latest PyPI wheel?), and emits a py.typed recommendation.

READ-ONLY with respect to the target repo. The pyright measurement copies the
repo into a temp directory (adding py.typed there if missing, since pyright
refuses to score unmarked packages) and installs that copy into an ephemeral
uvx environment. External tools (ruff, pyright) are invoked via `uvx`.

Usage:
    python type_coverage.py [REPO_PATH] [--json] [--skip-pyright] [--skip-pypi]

    REPO_PATH        target repo root (default: current directory)
    --json           machine-readable output instead of the human report
    --skip-pyright   skip the completeness score (quick mode / offline)
    --skip-pypi      skip the released-wheel py.typed check (offline)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ANN_CODES = "ANN001,ANN201,ANN202,ANN204,ANN205,ANN206"
PY_TYPED_RECOMMEND_THRESHOLD = 0.90
PY_TYPED_BORDERLINE_THRESHOLD = 0.60
SUBPROCESS_TIMEOUT_SEC = 600
NETWORK_TIMEOUT_SEC = 30
COPY_IGNORE = shutil.ignore_patterns(
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".nox",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
    "*.egg-info",
)


def _read_project_name(repo: Path) -> str:
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        sys.exit(
            f"error: no pyproject.toml in {repo} — not a wads-managed repo "
            "(see the wads-migrate skill)"
        )
    raw = pyproject.read_bytes()
    try:
        try:
            import tomllib
        except ImportError:  # Python 3.10
            import tomli as tomllib  # type: ignore[no-redef]
        return tomllib.loads(raw.decode())["project"]["name"]
    except Exception:
        m = re.search(r'^name\s*=\s*"([^"]+)"', raw.decode(), re.MULTILINE)
        if m:
            return m.group(1)
        sys.exit("error: could not read [project].name from pyproject.toml")


def _resolve_package_dir(repo: Path, project_name: str) -> Path:
    pkg = project_name.replace("-", "_")
    for candidate in (repo / pkg, repo / "src" / pkg):
        if (candidate / "__init__.py").is_file():
            return candidate
    sys.exit(
        f"error: package dir for {project_name!r} not found "
        f"(tried {pkg}/ and src/{pkg}/)"
    )


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SEC,
        )
    except FileNotFoundError:
        sys.exit(f"error: {cmd[0]!r} not found on PATH (install uv: https://docs.astral.sh/uv/)")


# --------------------------------------------------------------------------
# ruff ANN findings, bucketed public/private via AST scope mapping
# --------------------------------------------------------------------------


def _scopes(source: str) -> list[tuple[int, int, str]]:
    """(start_line, end_line, dotted_name) for every def/class, innermost-resolvable."""
    out: list[tuple[int, int, str]] = []

    def visit(node: ast.AST, stack: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                name_stack = stack + (child.name,)
                out.append(
                    (child.lineno, child.end_lineno or child.lineno, ".".join(name_stack))
                )
                visit(child, name_stack)
            else:
                visit(child, stack)

    try:
        visit(ast.parse(source), ())
    except SyntaxError:
        pass
    return out


def _is_private(dotted: str, rel_path: Path) -> bool:
    """Private if any path/name component is single-underscore-prefixed (dunders pass)."""

    def private_component(name: str) -> bool:
        return name.startswith("_") and not (
            name.startswith("__") and name.endswith("__")
        )

    parts = [p[:-3] if p.endswith(".py") else p for p in rel_path.parts]
    return any(private_component(p) for p in parts) or any(
        private_component(n) for n in dotted.split(".") if n
    )


def ruff_annotation_findings(repo: Path, pkg_dir: Path) -> dict:
    proc = _run(
        ["uvx", "ruff", "check", "--select", ANN_CODES, "--output-format", "json",
         str(pkg_dir)],
        cwd=repo,  # so the repo's [tool.ruff] excludes/config apply
    )
    if proc.returncode not in (0, 1):
        return {"error": f"ruff failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}"}
    findings = json.loads(proc.stdout or "[]")

    scope_cache: dict[str, list[tuple[int, int, str]]] = {}
    by_code: dict[str, int] = {}
    per_file_public: dict[str, int] = {}
    n_public = n_private = 0
    public_items = []
    for f in findings:
        code = f.get("code") or "syntax-error"  # ruff reports null code for E999
        by_code[code] = by_code.get(code, 0) + 1
        fname = f["filename"]
        if fname not in scope_cache:
            try:
                scope_cache[fname] = _scopes(Path(fname).read_text())
            except OSError:
                scope_cache[fname] = []
        row = f["location"]["row"]
        enclosing = [s for s in scope_cache[fname] if s[0] <= row <= s[1]]
        dotted = max(enclosing, key=lambda s: s[0])[2] if enclosing else ""
        rel = Path(fname).resolve().relative_to(repo.resolve())
        if _is_private(dotted, rel):
            n_private += 1
        else:
            n_public += 1
            per_file_public[str(rel)] = per_file_public.get(str(rel), 0) + 1
            public_items.append(
                {"file": str(rel), "row": row, "code": code,
                 "symbol": dotted, "message": f["message"]}
            )
    return {
        "total": len(findings),
        "by_code": dict(sorted(by_code.items())),
        "public": n_public,
        "private": n_private,
        "per_file_public": dict(
            sorted(per_file_public.items(), key=lambda kv: -kv[1])
        ),
        "public_findings": sorted(public_items, key=lambda d: (d["file"], d["row"])),
    }


# --------------------------------------------------------------------------
# pyright --verifytypes (via temp copy + py.typed)
# --------------------------------------------------------------------------


def pyright_completeness(repo: Path, pkg_dir: Path) -> dict:
    pkg_rel = pkg_dir.resolve().relative_to(repo.resolve())
    with tempfile.TemporaryDirectory(prefix="wads_type_cov_") as tmp:
        tmp_repo = Path(tmp) / "repo"
        shutil.copytree(repo, tmp_repo, ignore=COPY_IGNORE, symlinks=False)
        (tmp_repo / pkg_rel / "py.typed").touch()
        proc = _run(
            ["uvx", "--with", str(tmp_repo), "pyright",
             "--verifytypes", pkg_dir.name, "--outputjson"]
        )
    # exit 0 only at 100% completeness; 1 with a valid score otherwise
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": f"pyright produced no JSON: {proc.stderr.strip()[:500]}"}
    diags = [d["message"] for d in data.get("generalDiagnostics", [])]
    if any("No py.typed file found" in m for m in diags):
        return {
            "error": "pyright could not see py.typed in the built temp copy — "
            "the build backend likely drops files it doesn't know about "
            "(non-hatchling backends need package-data config; "
            "see the wads-migrate skill)"
        }
    tc = data["typeCompleteness"]
    modules = {m["name"] for m in tc.get("modules", [])}
    per_module: dict[str, dict] = {}
    for s in tc.get("symbols", []):
        if not s.get("isExported"):
            continue
        name = s["name"]
        prefixes = [p for p in modules if name == p or name.startswith(p + ".")]
        mod = max(prefixes, key=len) if prefixes else name.split(".")[0]
        entry = per_module.setdefault(mod, {"exported": 0, "unknown": 0})
        entry["exported"] += 1
        if not s.get("isTypeKnown"):
            entry["unknown"] += 1
    return {
        "pyright_version": data.get("version"),
        "score": tc["completenessScore"],
        "exported_symbol_counts": tc["exportedSymbolCounts"],
        "per_module": dict(
            sorted(per_module.items(), key=lambda kv: -kv[1]["unknown"])
        ),
        "general_diagnostics": diags,
    }


# --------------------------------------------------------------------------
# py.typed: local presence + shipped-in-latest-wheel
# --------------------------------------------------------------------------


def py_typed_status(
    repo: Path, pkg_dir: Path, project_name: str, *, skip_pypi: bool
) -> dict:
    status: dict = {"local_present": (pkg_dir / "py.typed").is_file()}
    try:
        build_backend = (repo / "pyproject.toml").read_text()
        status["hatchling_backend"] = "hatchling" in build_backend
    except OSError:
        status["hatchling_backend"] = None
    if skip_pypi:
        status["shipped_in_latest_wheel"] = "skipped"
        return status
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{project_name}/json", timeout=NETWORK_TIMEOUT_SEC
        ) as resp:
            meta = json.load(resp)
        status["pypi_version"] = meta["info"]["version"]
        wheel = next(
            (u for u in meta["urls"] if u["packagetype"] == "bdist_wheel"), None
        )
        if wheel is None:
            status["shipped_in_latest_wheel"] = "no wheel on PyPI"
            return status
        with tempfile.TemporaryDirectory(prefix="wads_type_cov_whl_") as tmp:
            whl_path = Path(tmp) / "pkg.whl"
            with urllib.request.urlopen(wheel["url"], timeout=NETWORK_TIMEOUT_SEC) as r:
                whl_path.write_bytes(r.read())
            names = zipfile.ZipFile(whl_path).namelist()
        status["shipped_in_latest_wheel"] = any(
            n.endswith("/py.typed") or n == "py.typed" for n in names
        )
    except Exception as e:  # network failures are non-fatal: report, don't crash
        status["shipped_in_latest_wheel"] = f"unverifiable ({type(e).__name__})"
    return status


def recommendation(score: float | None, py_typed: dict) -> str:
    present = py_typed.get("local_present")
    if score is None:
        return "no completeness score (pyright skipped/failed) — no py.typed verdict"
    pct = f"{score:.0%}"
    if present and score < PY_TYPED_RECOMMEND_THRESHOLD:
        return (
            f"py.typed is present but the public API is only {pct} type-complete — "
            "downstream type-checkers are trusting incomplete annotations. "
            "Complete the annotations (priority) or discuss removing the marker."
        )
    if present:
        return f"py.typed present and public API {pct} complete — healthy."
    if score >= PY_TYPED_RECOMMEND_THRESHOLD:
        return (
            f"public API {pct} type-complete (>= {PY_TYPED_RECOMMEND_THRESHOLD:.0%}) — "
            "adding py.typed is justified; propose it to the user."
        )
    if score >= PY_TYPED_BORDERLINE_THRESHOLD:
        return (
            f"public API {pct} type-complete — borderline. Close the gap to "
            f">= {PY_TYPED_RECOMMEND_THRESHOLD:.0%} before adding py.typed."
        )
    return (
        f"public API only {pct} type-complete — do NOT add py.typed yet; "
        "premature py.typed is worse than none."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo", nargs="?", default=".", help="target repo root")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--skip-pyright", action="store_true")
    ap.add_argument("--skip-pypi", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    project_name = _read_project_name(repo)
    pkg_dir = _resolve_package_dir(repo, project_name)

    py_typed = py_typed_status(repo, pkg_dir, project_name, skip_pypi=args.skip_pypi)
    ruff = ruff_annotation_findings(repo, pkg_dir)
    pyright = (
        {"skipped": True} if args.skip_pyright else pyright_completeness(repo, pkg_dir)
    )
    score = pyright.get("score")
    result = {
        "project": project_name,
        "package_dir": str(pkg_dir),
        "py_typed": py_typed,
        "pyright": pyright,
        "ruff": ruff,
        "recommendation": recommendation(score, py_typed),
    }

    if args.json:
        # full findings only in --json; trim nothing
        print(json.dumps(result, indent=1))
        return

    print(f"Type coverage — {project_name} ({repo})")
    print(f"  py.typed: local={'present' if py_typed['local_present'] else 'ABSENT'}"
          f", latest wheel ships it: {py_typed.get('shipped_in_latest_wheel')}")
    if "error" in pyright:
        print(f"  pyright: ERROR — {pyright['error']}")
    elif not pyright.get("skipped"):
        c = pyright["exported_symbol_counts"]
        print(f"  public-API completeness (pyright): {score:.1%}  "
              f"(known {c['withKnownType']} / ambiguous {c['withAmbiguousType']} / "
              f"unknown {c['withUnknownType']})")
        print("  worst modules (unknown/exported):")
        for mod, e in list(pyright["per_module"].items())[:8]:
            if e["unknown"]:
                print(f"    {mod}: {e['unknown']}/{e['exported']}")
    if "error" in ruff:
        print(f"  ruff: ERROR — {ruff['error']}")
    else:
        print(f"  ruff missing-annotation findings: {ruff['total']} "
              f"(public {ruff['public']}, private {ruff['private']}) {ruff['by_code']}")
        print("  top files by public findings:")
        for fname, n in list(ruff["per_file_public"].items())[:8]:
            print(f"    {fname}: {n}")
    print(f"  verdict: {result['recommendation']}")


if __name__ == "__main__":
    main()
