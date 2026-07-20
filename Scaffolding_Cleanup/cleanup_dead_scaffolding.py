from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scaffolding_cleanup import (
    DEFAULT_EXCLUDED_DIRECTORY_NAMES,
    DEFAULT_EXCLUDE_GLOBS,
    DEFAULT_PLACEHOLDER_FILE_NAMES,
    DEFAULT_README_NAMES,
    DEFAULT_REFERENCE_SUFFIXES,
    CleanupResult,
    backup_paths,
    discover_candidates,
    find_references,
    normalize_suffix,
    protected_hashes,
    remove_empty_functions_from_file,
    resolve_relative_path,
    write_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover and safely remove dead scaffolding from any Python project. "
            "Dry-run is the default; pass --apply to change files."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project directory to inspect. Default: current working directory.",
    )
    parser.add_argument(
        "--scan-root",
        action="append",
        default=[],
        help=(
            "Relative directory to scan. Repeat for multiple roots. "
            "Default: the whole project."
        ),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Relative glob to exclude. Repeatable, for example tests/fixtures/**.",
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
        help=(
            "Relative file or directory that must never be removed or modified. "
            "Repeatable."
        ),
    )
    parser.add_argument(
        "--empty-file-suffix",
        action="append",
        default=[],
        help="Suffix eligible for empty-file cleanup. Repeatable. Default: .py.",
    )
    parser.add_argument(
        "--readme-name",
        action="append",
        default=[],
        help="README filename allowed inside a scaffold directory. Repeatable.",
    )
    parser.add_argument(
        "--placeholder-file-name",
        action="append",
        default=[],
        help="Placeholder filename allowed inside a scaffold directory. Repeatable.",
    )
    parser.add_argument(
        "--no-empty-files",
        action="store_true",
        help="Do not detect or remove standalone empty files.",
    )
    parser.add_argument(
        "--no-scaffold-directories",
        action="store_true",
        help="Do not detect or remove empty/README-only directories.",
    )
    parser.add_argument(
        "--remove-empty-functions",
        action="store_true",
        help=(
            "Also detect and remove safe empty Python functions (pass, ..., or "
            "docstring-only). Disabled by default because empty hooks can be intentional."
        ),
    )
    parser.add_argument(
        "--top-level-functions-only",
        action="store_true",
        help="Do not remove empty class methods.",
    )
    parser.add_argument(
        "--include-decorated-functions",
        action="store_true",
        help=(
            "Allow decorated empty functions to be candidates. Abstract/property/"
            "overload-style functions remain protected."
        ),
    )
    parser.add_argument(
        "--include-dunder-functions",
        action="store_true",
        help="Allow empty __dunder__ functions to be candidates.",
    )
    parser.add_argument(
        "--include-package-init-files",
        action="store_true",
        help=(
            "Allow standalone empty __init__.py files to be deleted. They are still "
            "allowed inside a fully scaffold-only directory."
        ),
    )
    parser.add_argument(
        "--treat-docstring-only-file-as-empty",
        action="store_true",
        help="Treat a Python module containing only a module docstring as empty.",
    )
    parser.add_argument(
        "--skip-reference-check",
        action="store_true",
        help="Skip import/path-reference checks. Not recommended.",
    )
    parser.add_argument(
        "--reference-suffix",
        action="append",
        default=[],
        help="File suffix included in reference scanning. Repeatable.",
    )
    parser.add_argument(
        "--reference-ignore",
        action="append",
        default=[],
        help="Relative source file to exclude from reference scanning. Repeatable.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help=(
            "Optional backup directory. Relative values are resolved from the project root."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional JSON report/manifest path. Written in dry-run and apply modes.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the cleanup. Without this flag, only report candidates.",
    )
    return parser.parse_args()


def _relative_tool_path(project_root: Path, tool_path: Path) -> Path | None:
    try:
        return tool_path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return None


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
        reference_ignored = [
            resolve_relative_path(project_root, value)
            for value in args.reference_ignore
        ]
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    manifest_path = None
    if args.manifest:
        manifest_path = (
            args.manifest.resolve()
            if args.manifest.is_absolute()
            else (project_root / args.manifest).resolve()
        )
        relative_manifest = _relative_tool_path(project_root, manifest_path)
        if relative_manifest is not None:
            reference_ignored.append(relative_manifest)

    backup_root = None
    backup_relative = None
    if args.backup_dir:
        backup_root = (
            args.backup_dir.resolve()
            if args.backup_dir.is_absolute()
            else (project_root / args.backup_dir).resolve()
        )
        backup_relative = _relative_tool_path(project_root, backup_root)

    for own_path in (Path(__file__), Path(__file__).with_name("scaffolding_cleanup.py")):
        relative = _relative_tool_path(project_root, own_path)
        if relative is not None:
            reference_ignored.append(relative)

    excluded_directory_names = (
        set(DEFAULT_EXCLUDED_DIRECTORY_NAMES) | set(args.exclude_dir_name)
    )
    extra_excludes = set(args.exclude)
    if backup_relative is not None:
        extra_excludes.add(backup_relative.as_posix())
        extra_excludes.add(backup_relative.as_posix().rstrip("/") + "/**")
    exclude_globs = sorted(set(DEFAULT_EXCLUDE_GLOBS) | extra_excludes)
    empty_file_suffixes = {
        normalize_suffix(value) for value in (args.empty_file_suffix or [".py"])
    }
    reference_suffixes = {
        normalize_suffix(value)
        for value in (args.reference_suffix or DEFAULT_REFERENCE_SUFFIXES)
    }
    readme_names = set(args.readme_name or DEFAULT_README_NAMES)
    placeholder_names = set(
        args.placeholder_file_name or DEFAULT_PLACEHOLDER_FILE_NAMES
    )

    discovery = discover_candidates(
        project_root,
        scan_roots,
        empty_file_suffixes=empty_file_suffixes,
        readme_names=readme_names,
        placeholder_file_names=placeholder_names,
        excluded_directory_names=excluded_directory_names,
        exclude_globs=exclude_globs,
        protected_paths=protected_paths,
        detect_empty_files=not args.no_empty_files,
        detect_scaffold_directories=not args.no_scaffold_directories,
        detect_empty_functions=args.remove_empty_functions,
        treat_docstring_only_as_empty=args.treat_docstring_only_file_as_empty,
        include_methods=not args.top_level_functions_only,
        include_decorated_functions=args.include_decorated_functions,
        include_dunder_functions=args.include_dunder_functions,
        include_package_init_files=args.include_package_init_files,
    )

    candidate_paths = [
        *discovery.empty_files,
        *discovery.scaffold_directories,
    ]
    references = (
        []
        if args.skip_reference_check
        else find_references(
            project_root,
            scan_roots,
            candidate_paths,
            excluded_directory_names=excluded_directory_names,
            exclude_globs=exclude_globs,
            reference_suffixes=reference_suffixes,
            ignored_source_paths=reference_ignored,
        )
    )

    print("=" * 80)
    print("GENERIC DEAD-SCAFFOLDING CLEANUP")
    print("=" * 80)
    print(f"Project root: {project_root}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"Empty files: {len(discovery.empty_files)}")
    print(f"Scaffold directories: {len(discovery.scaffold_directories)}")
    print(f"Empty functions: {len(discovery.empty_functions)}")
    print(f"References blocking cleanup: {len(references)}")

    for path in discovery.empty_files:
        print(f"[EMPTY FILE] {path}")
    for path in discovery.scaffold_directories:
        print(f"[SCAFFOLD DIR] {path}")
    for item in discovery.empty_functions:
        print(
            f"[EMPTY FUNCTION] {item.file_path}:{item.start_line}-{item.end_line} "
            f"{item.qualified_name}"
        )
    for item in references:
        print(
            f"[REFERENCE] {item.source_path} -> {item.candidate_path} "
            f"({item.detail})"
        )

    before_hashes = protected_hashes(project_root, protected_paths)

    if references:
        result = CleanupResult(
            project_root=project_root,
            applied=False,
            removed_files=(),
            removed_directories=(),
            modified_function_files=(),
            empty_functions=discovery.empty_functions,
            references=tuple(references),
            protected_hashes_before=before_hashes,
            protected_hashes_after=before_hashes,
            backup_directory=backup_relative,
        )
        if manifest_path:
            write_manifest(manifest_path, result)
            print(f"Manifest: {manifest_path}")
        print("REFUSED: active references point to cleanup candidates.")
        return 1

    all_backup_paths = {
        *discovery.empty_files,
        *discovery.scaffold_directories,
        *(item.file_path for item in discovery.empty_functions),
    }

    if backup_root and all_backup_paths:
        if args.apply:
            backup_paths(project_root, all_backup_paths, backup_root)
            print(f"Backup created: {backup_root.resolve()}")
        else:
            print(f"Backup would be created: {backup_root.resolve()}")

    removed_files: list[Path] = []
    removed_directories: list[Path] = []
    modified_function_files: list[Path] = []

    if args.apply:
        functions_by_file: dict[Path, list] = {}
        for item in discovery.empty_functions:
            functions_by_file.setdefault(item.file_path, []).append(item)

        for relative, items in sorted(
            functions_by_file.items(), key=lambda pair: pair[0].as_posix()
        ):
            remove_empty_functions_from_file(project_root / relative, items)
            modified_function_files.append(relative)
            print(f"Modified functions in: {relative}")

        for relative in discovery.empty_files:
            path = project_root / relative
            if path.is_file():
                path.unlink()
                removed_files.append(relative)
                print(f"Deleted file: {relative}")

        for relative in sorted(
            discovery.scaffold_directories,
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            path = project_root / relative
            if path.is_dir():
                import shutil

                shutil.rmtree(path)
                removed_directories.append(relative)
                print(f"Deleted directory: {relative}")

    after_hashes = protected_hashes(project_root, protected_paths)
    if before_hashes != after_hashes:
        print("ERROR: a protected path changed during cleanup.")
        return 1

    result = CleanupResult(
        project_root=project_root,
        applied=args.apply,
        removed_files=tuple(removed_files),
        removed_directories=tuple(removed_directories),
        modified_function_files=tuple(modified_function_files),
        empty_functions=discovery.empty_functions,
        references=(),
        protected_hashes_before=before_hashes,
        protected_hashes_after=after_hashes,
        backup_directory=backup_relative,
    )

    if manifest_path:
        write_manifest(manifest_path, result)
        print(f"Manifest: {manifest_path}")

    print("-" * 80)
    if args.apply:
        print("CLEANUP STATUS: APPLIED")
    else:
        print("CLEANUP STATUS: DRY RUN PASSED")
        print("Run the same command with --apply after reviewing the candidates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
