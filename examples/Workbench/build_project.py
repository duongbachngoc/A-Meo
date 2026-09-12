# -*- coding: utf-8 -*-
"""Standalone builder for the A Meo Workbench developer source package.

Reads ONLY `WorkbenchV1.1.txt` sitting next to this script and materializes
its `FILE:` blocks (the whole `modules/workbench/` tree) into a target
directory.

Usage:
    python build_project.py [--project-root PATH]

`--project-root` defaults to `./workbench_build` next to this script and is
created if missing. This script is fully self-contained: no absolute paths,
no dependency on the A Meo development workspace or Core source bundles, no
pip/npm install, does not launch anything. Works from any directory on any
OS (Windows / macOS / Linux).

The materialized module has exactly one external import,
`from src.core.hub.contracts import BaseCapability, HubResponse` -- the one
stable public Host type from the A Meo Public Module Contract v1, provided
by the A Meo Host at runtime. This builder treats that import as satisfied
by the Host and does not require it on disk.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_FILE = "WorkbenchV1.1.txt"
FILE_MARKER = "=" * 50
PROTECTED_INPUTS = {PACKAGE_FILE, "build_project.py"}

# Import prefixes the Host provides at runtime (Public Module Contract v1,
# section 5.2). Anything else under `src.` is NOT part of this package and
# is a packaging error if a module imports it.
HOST_PROVIDED_PREFIXES = ("src/core/hub/contracts",)

REQUIRED_FILES = (
    "modules/workbench/__init__.py",
    "modules/workbench/module_manifest.json",
    "modules/workbench/boot.py",
    "modules/workbench/capability.py",
    "modules/workbench/agent_loop.py",
    "modules/workbench/session.py",
    "modules/workbench/workspace.py",
    "modules/workbench/file_tools.py",
    "modules/workbench/safety.py",
)


def parse_package(source_root: Path) -> "dict[str, str]":
    """Read the whole package file before writing any output."""
    package_path = source_root / PACKAGE_FILE
    if not package_path.is_file():
        raise FileNotFoundError(f"Missing '{PACKAGE_FILE}' at: {package_path}")

    lines = package_path.read_text(encoding="utf-8").splitlines(keepends=True)
    generated: "dict[str, str]" = {}
    current_path: "str | None" = None
    current_lines: "list[str]" = []

    def commit() -> None:
        if current_path is not None:
            generated[current_path] = "".join(current_lines)

    for line in lines:
        stripped = line.strip()
        if stripped == FILE_MARKER:
            continue
        if stripped.startswith("FILE: "):
            commit()
            current_path = stripped[6:].strip().replace("\\", "/")
            current_lines = []
        elif current_path is not None:
            current_lines.append(line)
    commit()

    if not generated:
        raise RuntimeError(f"'{PACKAGE_FILE}' contains no valid FILE: blocks.")
    return generated


def safe_target(project_root: Path, relative_path: str) -> Path:
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Unsafe FILE path: {relative_path}")
    target = (project_root / rel).resolve()
    try:
        target.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"FILE path escapes project root: {relative_path}") from exc
    return target


def atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".wb-building")
    temp.write_text(content, encoding="utf-8", newline="")
    os.replace(temp, target)


def syntax_audit(project_root: Path, written_paths: "list[Path]") -> None:
    errors: "list[str]" = []
    for path in written_paths:
        if path.suffix.lower() != ".py":
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(project_root)}: {exc}")
    if errors:
        raise RuntimeError("Python syntax audit FAILED:\n" + "\n".join(errors))


def manifest_audit(package_files: "dict[str, str]") -> None:
    rel = "modules/workbench/module_manifest.json"
    if rel not in package_files:
        raise RuntimeError(f"Missing {rel}")
    try:
        m = json.loads(package_files[rel])
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"{rel} is not valid JSON: {exc}") from exc
    if m.get("module_id") != "workbench":
        raise RuntimeError(f"{rel}: module_id must be 'workbench', got {m.get('module_id')!r}")
    entry = m.get("entry_file")
    if not entry or f"modules/workbench/{entry}" not in package_files:
        raise RuntimeError(f"{rel}: entry_file {entry!r} not present in the package")


def required_files_audit(package_files: "dict[str, str]") -> None:
    missing = [p for p in REQUIRED_FILES if p not in package_files]
    if missing:
        raise RuntimeError("Package is incomplete -- missing required files:\n" + "\n".join(missing))


def _resolve_relative(module: str, level: int, current_path: str) -> "str | None":
    parts_dir = current_path.split("/")[:-1]
    base = parts_dir[: len(parts_dir) - (level - 1)] if level > 1 else parts_dir
    parts = base + (module.split(".") if module else [])
    return "/".join(parts) if parts else None


def internal_import_audit(package_files: "dict[str, str]") -> None:
    """Every project-internal import in a materialized .py must resolve to
    another materialized file, EXCEPT the Host-provided `src.core.hub.
    contracts`. Imports guarded by try/except ImportError are skipped."""

    def exists(module_path: str) -> bool:
        if module_path.startswith(HOST_PROVIDED_PREFIXES):
            return True
        return (module_path + ".py") in package_files or (module_path + "/__init__.py") in package_files

    def guarded_ids(tree: ast.AST) -> "set[int]":
        out: "set[int]" = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                names = []
                for h in node.handlers:
                    if h.type is None:
                        names.append("BaseException")
                    else:
                        elts = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
                        names += [n.id for n in elts if isinstance(n, ast.Name)]
                if {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"} & set(names):
                    for stmt in node.body:
                        for sub in ast.walk(stmt):
                            if isinstance(sub, (ast.Import, ast.ImportFrom)):
                                out.add(id(sub))
        return out

    errors: "list[str]" = []
    for rel_path, content in package_files.items():
        if not rel_path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content, filename=rel_path)
        except SyntaxError:
            continue
        gids = guarded_ids(tree)
        for node in ast.walk(tree):
            if id(node) in gids:
                continue
            targets: "list[str | None]" = []
            if isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    targets.append(_resolve_relative(node.module or "", node.level, rel_path))
                elif node.module and (node.module == "src" or node.module.startswith("src.")):
                    targets.append(node.module.replace(".", "/"))
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == "src" or a.name.startswith("src."):
                        targets.append(a.name.replace(".", "/"))
            for t in targets:
                if t and not exists(t):
                    errors.append(f"{rel_path}: unresolved internal import -> {t}")
    if errors:
        raise RuntimeError("Internal import audit FAILED:\n" + "\n".join(sorted(set(errors))))


def build(source_root: Path, project_root: Path) -> None:
    source_root = source_root.resolve()
    project_root = project_root.resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    generated = parse_package(source_root)
    package_files = {
        p.replace("\\", "/"): c
        for p, c in generated.items()
        if p.replace("\\", "/") not in PROTECTED_INPUTS
    }

    required_files_audit(package_files)
    manifest_audit(package_files)
    internal_import_audit(package_files)

    written: "list[Path]" = []
    for rel, content in package_files.items():
        target = safe_target(project_root, rel)
        atomic_write(target, content)
        written.append(target)

    syntax_audit(project_root, written)

    n_tests = sum(1 for p in package_files if p.startswith("modules/workbench/tests/") and p.endswith(".py"))
    print(f"Workbench V1.1 build OK: {len(written)} files -> {project_root}")
    print(f"  syntax audit PASS, manifest audit PASS, internal import audit PASS")
    print(f"  ({n_tests} test files; run: python -m pytest {project_root / 'modules' / 'workbench' / 'tests'})")
    print("  Note: the module needs `src.core.hub.contracts` (BaseCapability, HubResponse)")
    print("  from the A Meo Host on sys.path to import/run.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize the A Meo Workbench module from WorkbenchV1.1.txt.")
    parser.add_argument(
        "--project-root", type=Path, default=SCRIPT_DIR / "workbench_build",
        help="Target directory (created if missing). Default: ./workbench_build next to this script.",
    )
    args = parser.parse_args()
    try:
        build(SCRIPT_DIR, args.project_root)
    except Exception as exc:  # noqa: BLE001
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
