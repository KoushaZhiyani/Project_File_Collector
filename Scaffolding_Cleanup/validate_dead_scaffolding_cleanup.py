from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from scaffolding_cleanup import (
    DEFAULT_EXCLUDED_DIRECTORY_NAMES,
    DEFAULT_EXCLUDE_GLOBS,
    DEFAULT_PLACEHOLDER_FILE_NAMES,
    DEFAULT_README_NAMES,
    discover_candidates,
    load_manifest,
    normalize_suffix,
    protected_hashes,
    resolve_relative_path,
    validate_python_syntax,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a generic dead-scaffolding cleanup."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project directory. Default: current working directory.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Cleanup manifest produced by cleanup_dead_scaffolding.py.",
    )
    parser.add_argument(
        "--scan-root",
        action="append",
        default=[],
        help="Relative directory to scan. Repeatable. Default: whole project.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Relative glob to exclude. Repeatable.",
    )
    parser.add_argument(
        "--exclude-dir-name",
        action="append",
        default=[],
        help="Directory name to prune everywhere. Repeatable.",
    )
    parser.add_argument(
        "--protect",
        action="append",
        default=[],
        help="Relative file/directory that must remain unchanged. Repeatable.",
    )
    parser.add_argument(
        "--empty-file-suffix",
        action="append",
        default=[],
        help="Suffix eligible for empty-file detection. Default: .py.",
    )
    parser.add_argument(
        "--readme-name",
        action="append",
        default=[],
        help="README filename allowed inside scaffold directories. Repeatable.",
    )
    parser.add_argument(
        "--placeholder-file-name",
        action="append",
        default=[],
        help="Placeholder filename allowed inside scaffold directories. Repeatable.",
    )
    parser.add_argument(
        "--check-empty-functions",
        action="store_true",
        help="Fail when safe empty functions remain.",
    )
    parser.add_argument(
        "--top-level-functions-only",
        action="store_true",
        help="When checking functions, ignore class methods.",
    )
    parser.add_argument(
        "--include-decorated-functions",
        action="store_true",
        help="Include decorated functions except semantic API decorators.",
    )
    parser.add_argument(
        "--include-dunder-functions",
        action="store_true",
        help="Include empty dunder functions.",
    )
    parser.add_argument(
        "--include-package-init-files",
        action="store_true",
        help="Treat standalone empty __init__.py files as cleanup candidates.",
    )
    parser.add_argument(
        "--treat-docstring-only-file-as-empty",
        action="store_true",
        help="Treat a module containing only a docstring as empty.",
    )
    parser.add_argument(
        "--skip-clean-check",
        action="store_true",
        help="Skip checking for remaining cleanup candidates.",
    )
    parser.add_argument(
        "--skip-python-syntax",
        action="store_true",
        help="Skip AST parsing of Python files.",
    )
    parser.add_argument(
        "--import-module",
        action="append",
        default=[],
        help="Python module to import as a smoke test. Repeatable.",
    )
    parser.add_argument(
        "--command",
        action="append",
        default=[],
        help=(
            "Validation command executed from the project root. Repeatable, for "
            "example: --command \"python -m pytest -q\"."
        ),
    )
    return parser.parse_args()


def run_import_smoke(project_root: Path, modules: list[str]) -> None:
    if not modules:
        return
    expression = "; ".join(f"import {module}" for module in modules)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(
        [sys.executable, "-c", expression],
        cwd=project_root,
        env=env,
        check=True,
    )


def run_commands(project_root: Path, commands: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for command in commands:
        subprocess.run(
            command,
            cwd=project_root,
            env=env,
            shell=True,
            check=True,
        )


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"ERROR: project root is not a directory: {project_root}")
        return 2

    try:
        scan_roots = [
            resolve_relative_path(project_root, value)
            for value in (args.scan_root or ["."])
        ]
        protected_paths = [
            resolve_relative_path(project_root, value) for value in args.protect
        ]
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    manifest_path = None
    manifest = None
    if args.manifest:
        manifest_path = (
            args.manifest.resolve()
            if args.manifest.is_absolute()
            else (project_root / args.manifest).resolve()
        )
        try:
            manifest = load_manifest(manifest_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"ERROR: cannot load manifest: {exc}")
            return 2

    excluded_directory_names = (
        set(DEFAULT_EXCLUDED_DIRECTORY_NAMES) | set(args.exclude_dir_name)
    )
    extra_excludes = set(args.exclude)
    if manifest and manifest.get("backup_directory"):
        backup_relative = Path(str(manifest["backup_directory"]))
        extra_excludes.add(backup_relative.as_posix())
        extra_excludes.add(backup_relative.as_posix().rstrip("/") + "/**")
    exclude_globs = sorted(set(DEFAULT_EXCLUDE_GLOBS) | extra_excludes)
    empty_file_suffixes = {
        normalize_suffix(value) for value in (args.empty_file_suffix or [".py"])
    }
    readme_names = set(args.readme_name or DEFAULT_README_NAMES)
    placeholder_names = set(
        args.placeholder_file_name or DEFAULT_PLACEHOLDER_FILE_NAMES
    )

    print("=" * 80)
    print("GENERIC DEAD-SCAFFOLDING VALIDATION")
    print("=" * 80)
    print(f"Project root: {project_root}")

    before_hashes = protected_hashes(project_root, protected_paths)

    try:
        if manifest is not None:
            expected_absent = [
                Path(value)
                for key in ("removed_files", "removed_directories")
                for value in manifest.get(key, [])
            ]
            remaining = [
                relative
                for relative in expected_absent
                if (project_root / relative).exists()
            ]
            if remaining:
                raise RuntimeError(
                    "Manifest cleanup targets still exist: "
                    + ", ".join(str(item) for item in remaining)
                )
            print("Manifest target check: PASSED")

        if not args.skip_clean_check:
            discovery = discover_candidates(
                project_root,
                scan_roots,
                empty_file_suffixes=empty_file_suffixes,
                readme_names=readme_names,
                placeholder_file_names=placeholder_names,
                excluded_directory_names=excluded_directory_names,
                exclude_globs=exclude_globs,
                protected_paths=protected_paths,
                detect_empty_files=True,
                detect_scaffold_directories=True,
                detect_empty_functions=args.check_empty_functions,
                treat_docstring_only_as_empty=args.treat_docstring_only_file_as_empty,
                include_methods=not args.top_level_functions_only,
                include_decorated_functions=args.include_decorated_functions,
                include_dunder_functions=args.include_dunder_functions,
                include_package_init_files=args.include_package_init_files,
            )
            if (
                discovery.empty_files
                or discovery.scaffold_directories
                or discovery.empty_functions
            ):
                details = [
                    *(f"empty file: {item}" for item in discovery.empty_files),
                    *(
                        f"scaffold directory: {item}"
                        for item in discovery.scaffold_directories
                    ),
                    *(
                        f"empty function: {item.file_path}:{item.start_line} "
                        f"{item.qualified_name}"
                        for item in discovery.empty_functions
                    ),
                ]
                raise RuntimeError(
                    "Cleanup candidates remain: " + "; ".join(details)
                )
            print("Residual candidate check: PASSED")

        if not args.skip_python_syntax:
            syntax_errors = validate_python_syntax(
                project_root,
                scan_roots,
                excluded_directory_names=excluded_directory_names,
                exclude_globs=exclude_globs,
            )
            if syntax_errors:
                raise RuntimeError(
                    "Python syntax errors: " + "; ".join(syntax_errors)
                )
            print("Python syntax check: PASSED")

        if args.import_module:
            run_import_smoke(project_root, args.import_module)
            print("Import smoke check: PASSED")

        if args.command:
            run_commands(project_root, args.command)
            print("Validation commands: PASSED")

        after_hashes = protected_hashes(project_root, protected_paths)
        if before_hashes != after_hashes:
            raise RuntimeError("A protected path changed during validation")
        print("Protected path hash check: PASSED")

    except (
        FileNotFoundError,
        RuntimeError,
        subprocess.CalledProcessError,
        ValueError,
    ) as exc:
        print("-" * 80)
        print("VALIDATION STATUS: FAILED")
        print(f"{type(exc).__name__}: {exc}")
        return 1

    print("-" * 80)
    print("VALIDATION STATUS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
