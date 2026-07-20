from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Sequence


DEFAULT_EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
}

DEFAULT_EXCLUDE_GLOBS = {
    "**/.git/**",
    "**/.venv/**",
    "**/venv/**",
    "**/node_modules/**",
    "**/build/**",
    "**/dist/**",
}

DEFAULT_README_NAMES = {
    "readme",
    "readme.md",
    "readme.rst",
    "readme.txt",
}

DEFAULT_PLACEHOLDER_FILE_NAMES = {
    ".gitkeep",
    ".keep",
}

DEFAULT_REFERENCE_SUFFIXES = {
    ".bat",
    ".cfg",
    ".cmd",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".rst",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True, slots=True)
class EmptyFunction:
    file_path: Path
    qualified_name: str
    start_line: int
    end_line: int
    parent_kind: str
    parent_start_line: int | None = None
    parent_indent: int | None = None
    parent_needs_pass: bool = False


@dataclass(frozen=True, slots=True)
class Reference:
    source_path: Path
    candidate_path: Path
    detail: str


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    empty_files: tuple[Path, ...]
    scaffold_directories: tuple[Path, ...]
    empty_functions: tuple[EmptyFunction, ...]


@dataclass(frozen=True, slots=True)
class CleanupResult:
    project_root: Path
    applied: bool
    removed_files: tuple[Path, ...]
    removed_directories: tuple[Path, ...]
    modified_function_files: tuple[Path, ...]
    empty_functions: tuple[EmptyFunction, ...]
    references: tuple[Reference, ...]
    protected_hashes_before: dict[str, str]
    protected_hashes_after: dict[str, str]
    backup_directory: Path | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_suffix(value: str) -> str:
    value = value.strip().lower()
    if not value:
        raise ValueError("File suffix cannot be empty")
    return value if value.startswith(".") else f".{value}"


def resolve_relative_path(project_root: Path, value: str | Path) -> Path:
    root = project_root.resolve()
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        return resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {value}") from exc


def absolute_from_relative(project_root: Path, relative: Path) -> Path:
    return (project_root / relative).resolve()


def path_matches_globs(relative: Path, patterns: Sequence[str]) -> bool:
    text = relative.as_posix()
    return any(
        fnmatch.fnmatch(text, pattern)
        or fnmatch.fnmatch(f"/{text}", pattern)
        for pattern in patterns
    )


def path_is_protected(relative: Path, protected_paths: Sequence[Path]) -> bool:
    for protected in protected_paths:
        if relative == protected:
            return True
        if protected in relative.parents:
            return True
        if relative in protected.parents:
            return True
    return False


def _walk_project(
    project_root: Path,
    scan_roots: Sequence[Path],
    excluded_directory_names: set[str],
    exclude_globs: Sequence[str],
) -> Iterator[tuple[Path, list[str], list[str]]]:
    root = project_root.resolve()
    seen: set[Path] = set()

    for relative_scan_root in scan_roots:
        absolute_scan_root = absolute_from_relative(root, relative_scan_root)
        if not absolute_scan_root.exists() or not absolute_scan_root.is_dir():
            continue

        for current, directory_names, file_names in os.walk(absolute_scan_root):
            current_path = Path(current).resolve()
            if current_path in seen:
                directory_names[:] = []
                continue
            seen.add(current_path)

            relative_current = current_path.relative_to(root)
            if relative_current != Path(".") and path_matches_globs(
                relative_current, exclude_globs
            ):
                directory_names[:] = []
                continue

            kept_directories: list[str] = []
            for name in directory_names:
                relative_child = relative_current / name
                if name in excluded_directory_names:
                    continue
                if path_matches_globs(relative_child, exclude_globs):
                    continue
                kept_directories.append(name)
            directory_names[:] = kept_directories

            yield current_path, directory_names, file_names


def iter_project_files(
    project_root: Path,
    scan_roots: Sequence[Path],
    *,
    excluded_directory_names: set[str],
    exclude_globs: Sequence[str],
    suffixes: set[str] | None = None,
) -> Iterator[Path]:
    for current, _, file_names in _walk_project(
        project_root,
        scan_roots,
        excluded_directory_names,
        exclude_globs,
    ):
        for name in file_names:
            path = current / name
            if suffixes is not None and path.suffix.lower() not in suffixes:
                continue
            yield path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def python_module_is_placeholder(
    path: Path,
    *,
    treat_docstring_only_as_empty: bool,
) -> bool:
    try:
        source = read_text(path)
        tree = ast.parse(source, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return False

    if not tree.body:
        return True

    if treat_docstring_only_as_empty and len(tree.body) == 1:
        statement = tree.body[0]
        return (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )

    return False


def discover_empty_files(
    project_root: Path,
    scan_roots: Sequence[Path],
    *,
    suffixes: set[str],
    excluded_directory_names: set[str],
    exclude_globs: Sequence[str],
    protected_paths: Sequence[Path],
    treat_docstring_only_as_empty: bool,
    include_package_init_files: bool,
) -> list[Path]:
    result: list[Path] = []
    root = project_root.resolve()

    for path in iter_project_files(
        root,
        scan_roots,
        excluded_directory_names=excluded_directory_names,
        exclude_globs=exclude_globs,
        suffixes=suffixes,
    ):
        relative = path.resolve().relative_to(root)
        if path_is_protected(relative, protected_paths):
            continue
        if path.name == "__init__.py" and not include_package_init_files:
            continue

        if path.suffix.lower() == ".py":
            if python_module_is_placeholder(
                path,
                treat_docstring_only_as_empty=treat_docstring_only_as_empty,
            ):
                result.append(relative)
            continue

        try:
            if not read_text(path).strip():
                result.append(relative)
        except UnicodeDecodeError:
            if path.stat().st_size == 0:
                result.append(relative)

    return sorted(set(result), key=lambda item: item.as_posix())


def _function_body_is_empty(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            body = body[1:]

    return all(
        isinstance(statement, ast.Pass)
        or (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and statement.value.value is Ellipsis
        )
        for statement in body
    )


def _decorator_name(decorator: ast.expr) -> str:
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    if isinstance(decorator, ast.Call):
        return _decorator_name(decorator.func)
    return ""


def _is_safe_empty_function_candidate(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    include_decorated: bool,
    include_dunder: bool,
) -> bool:
    if not _function_body_is_empty(node):
        return False
    if not include_dunder and node.name.startswith("__") and node.name.endswith("__"):
        return False
    if node.decorator_list and not include_decorated:
        return False

    semantic_decorators = {
        "abstractmethod",
        "classmethod",
        "deleter",
        "overload",
        "property",
        "setter",
        "staticmethod",
    }
    if any(_decorator_name(item) in semantic_decorators for item in node.decorator_list):
        return False
    return True


def _node_start_line(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    lines = [node.lineno]
    lines.extend(decorator.lineno for decorator in node.decorator_list)
    return min(lines)


def _collect_empty_functions_from_body(
    body: list[ast.stmt],
    *,
    file_path: Path,
    prefix: str,
    parent_kind: str,
    parent_start_line: int | None,
    parent_indent: int | None,
    include_methods: bool,
    include_decorated: bool,
    include_dunder: bool,
) -> list[EmptyFunction]:
    candidates: list[EmptyFunction] = []

    function_nodes = [
        item
        for item in body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _is_safe_empty_function_candidate(
            item,
            include_decorated=include_decorated,
            include_dunder=include_dunder,
        )
    ]

    candidate_ids = {id(node) for node in function_nodes}
    parent_needs_pass = (
        parent_kind == "class"
        and bool(body)
        and all(id(item) in candidate_ids for item in body)
    )

    for node in function_nodes:
        candidates.append(
            EmptyFunction(
                file_path=file_path,
                qualified_name=f"{prefix}{node.name}",
                start_line=_node_start_line(node),
                end_line=node.end_lineno or node.lineno,
                parent_kind=parent_kind,
                parent_start_line=parent_start_line,
                parent_indent=parent_indent,
                parent_needs_pass=parent_needs_pass,
            )
        )

    for item in body:
        if isinstance(item, ast.ClassDef) and include_methods:
            candidates.extend(
                _collect_empty_functions_from_body(
                    item.body,
                    file_path=file_path,
                    prefix=f"{prefix}{item.name}.",
                    parent_kind="class",
                    parent_start_line=item.lineno,
                    parent_indent=item.col_offset,
                    include_methods=include_methods,
                    include_decorated=include_decorated,
                    include_dunder=include_dunder,
                )
            )

    return candidates


def discover_empty_functions(
    project_root: Path,
    scan_roots: Sequence[Path],
    *,
    excluded_directory_names: set[str],
    exclude_globs: Sequence[str],
    protected_paths: Sequence[Path],
    include_methods: bool,
    include_decorated: bool,
    include_dunder: bool,
) -> list[EmptyFunction]:
    root = project_root.resolve()
    result: list[EmptyFunction] = []

    for path in iter_project_files(
        root,
        scan_roots,
        excluded_directory_names=excluded_directory_names,
        exclude_globs=exclude_globs,
        suffixes={".py"},
    ):
        relative = path.resolve().relative_to(root)
        if path_is_protected(relative, protected_paths):
            continue
        if path.name.endswith(".pyi"):
            continue

        try:
            tree = ast.parse(read_text(path), filename=str(relative))
        except (UnicodeDecodeError, SyntaxError):
            continue

        result.extend(
            _collect_empty_functions_from_body(
                tree.body,
                file_path=relative,
                prefix="",
                parent_kind="module",
                parent_start_line=None,
                parent_indent=None,
                include_methods=include_methods,
                include_decorated=include_decorated,
                include_dunder=include_dunder,
            )
        )

    return sorted(
        result,
        key=lambda item: (
            item.file_path.as_posix(),
            item.start_line,
            item.qualified_name,
        ),
    )


def _directory_is_scaffolding(
    directory: Path,
    *,
    readme_names: set[str],
    placeholder_file_names: set[str],
    empty_file_paths: set[Path],
    project_root: Path,
    protected_paths: Sequence[Path],
    excluded_directory_names: set[str],
    exclude_globs: Sequence[str],
) -> bool:
    relative_directory = directory.resolve().relative_to(project_root)
    if relative_directory == Path("."):
        return False
    if path_is_protected(relative_directory, protected_paths):
        return False

    try:
        entries = list(directory.iterdir())
    except OSError:
        return False

    for entry in entries:
        relative_entry = entry.resolve().relative_to(project_root)
        if path_is_protected(relative_entry, protected_paths):
            return False
        if path_matches_globs(relative_entry, exclude_globs):
            return False

        if entry.is_dir():
            if entry.name in excluded_directory_names:
                return False
            if not _directory_is_scaffolding(
                entry,
                readme_names=readme_names,
                placeholder_file_names=placeholder_file_names,
                empty_file_paths=empty_file_paths,
                project_root=project_root,
                protected_paths=protected_paths,
                excluded_directory_names=excluded_directory_names,
                exclude_globs=exclude_globs,
            ):
                return False
            continue

        normalized_name = entry.name.lower()
        if normalized_name in readme_names:
            continue
        if normalized_name in placeholder_file_names:
            continue
        if relative_entry in empty_file_paths:
            continue
        return False

    return True


def discover_scaffold_directories(
    project_root: Path,
    scan_roots: Sequence[Path],
    *,
    readme_names: set[str],
    placeholder_file_names: set[str],
    empty_file_paths: Sequence[Path],
    excluded_directory_names: set[str],
    exclude_globs: Sequence[str],
    protected_paths: Sequence[Path],
) -> list[Path]:
    root = project_root.resolve()
    empty_set = set(empty_file_paths)
    all_directories: list[Path] = []

    for current, directory_names, _ in _walk_project(
        root,
        scan_roots,
        excluded_directory_names,
        exclude_globs,
    ):
        relative = current.resolve().relative_to(root)
        if relative == Path("."):
            continue
        if path_is_protected(relative, protected_paths):
            directory_names[:] = []
            continue
        all_directories.append(current)

    candidates = [
        directory.resolve().relative_to(root)
        for directory in sorted(
            all_directories,
            key=lambda item: len(item.parts),
            reverse=True,
        )
        if _directory_is_scaffolding(
            directory,
            readme_names=readme_names,
            placeholder_file_names=placeholder_file_names,
            empty_file_paths=empty_set,
            project_root=root,
            protected_paths=protected_paths,
            excluded_directory_names=excluded_directory_names,
            exclude_globs=exclude_globs,
        )
    ]

    # Keep only highest-level candidates. Deleting a parent already removes children.
    candidate_set = set(candidates)
    top_level = [
        candidate
        for candidate in candidate_set
        if not any(parent in candidate_set for parent in candidate.parents)
    ]
    return sorted(top_level, key=lambda item: item.as_posix())


def discover_candidates(
    project_root: Path,
    scan_roots: Sequence[Path],
    *,
    empty_file_suffixes: set[str],
    readme_names: set[str],
    placeholder_file_names: set[str],
    excluded_directory_names: set[str],
    exclude_globs: Sequence[str],
    protected_paths: Sequence[Path],
    detect_empty_files: bool,
    detect_scaffold_directories: bool,
    detect_empty_functions: bool,
    treat_docstring_only_as_empty: bool,
    include_methods: bool,
    include_decorated_functions: bool,
    include_dunder_functions: bool,
    include_package_init_files: bool,
) -> DiscoveryResult:
    all_empty_files = (
        discover_empty_files(
            project_root,
            scan_roots,
            suffixes=empty_file_suffixes,
            excluded_directory_names=excluded_directory_names,
            exclude_globs=exclude_globs,
            protected_paths=protected_paths,
            treat_docstring_only_as_empty=treat_docstring_only_as_empty,
            include_package_init_files=True,
        )
        if detect_empty_files or detect_scaffold_directories
        else []
    )

    standalone_empty_files = [
        path
        for path in all_empty_files
        if include_package_init_files or path.name != "__init__.py"
    ]

    scaffold_directories = (
        discover_scaffold_directories(
            project_root,
            scan_roots,
            readme_names={item.lower() for item in readme_names},
            placeholder_file_names={item.lower() for item in placeholder_file_names},
            empty_file_paths=all_empty_files,
            excluded_directory_names=excluded_directory_names,
            exclude_globs=exclude_globs,
            protected_paths=protected_paths,
        )
        if detect_scaffold_directories
        else []
    )

    scaffold_directory_set = set(scaffold_directories)
    filtered_empty_files = [
        path
        for path in standalone_empty_files
        if detect_empty_files
        and not any(parent in scaffold_directory_set for parent in path.parents)
    ]

    empty_functions = (
        discover_empty_functions(
            project_root,
            scan_roots,
            excluded_directory_names=excluded_directory_names,
            exclude_globs=exclude_globs,
            protected_paths=protected_paths,
            include_methods=include_methods,
            include_decorated=include_decorated_functions,
            include_dunder=include_dunder_functions,
        )
        if detect_empty_functions
        else []
    )

    empty_functions = [
        item
        for item in empty_functions
        if not any(parent in scaffold_directory_set for parent in item.file_path.parents)
        and item.file_path not in set(filtered_empty_files)
    ]

    return DiscoveryResult(
        empty_files=tuple(filtered_empty_files),
        scaffold_directories=tuple(scaffold_directories),
        empty_functions=tuple(empty_functions),
    )


def relative_path_to_module(path: Path) -> str | None:
    if path.suffix == ".py":
        parts = list(path.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
    elif path.suffix:
        return None
    else:
        parts = list(path.parts)

    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def module_imports_candidate(tree: ast.AST, candidate_module: str) -> bool:
    parent_module, _, leaf_name = candidate_module.rpartition(".")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported = alias.name
                if imported == candidate_module or imported.startswith(
                    candidate_module + "."
                ):
                    return True

        elif isinstance(node, ast.ImportFrom):
            imported_from = node.module or ""
            if imported_from == candidate_module or imported_from.startswith(
                candidate_module + "."
            ):
                return True
            if parent_module and imported_from == parent_module:
                if any(alias.name == leaf_name for alias in node.names):
                    return True

    return False


def find_references(
    project_root: Path,
    scan_roots: Sequence[Path],
    candidate_paths: Sequence[Path],
    *,
    excluded_directory_names: set[str],
    exclude_globs: Sequence[str],
    reference_suffixes: set[str],
    ignored_source_paths: Sequence[Path],
) -> list[Reference]:
    root = project_root.resolve()
    candidate_set = set(candidate_paths)
    ignored_set = set(ignored_source_paths)
    modules = {
        candidate: relative_path_to_module(candidate)
        for candidate in candidate_paths
    }
    references: list[Reference] = []

    for source_path in iter_project_files(
        root,
        scan_roots,
        excluded_directory_names=excluded_directory_names,
        exclude_globs=exclude_globs,
        suffixes=reference_suffixes,
    ):
        relative_source = source_path.resolve().relative_to(root)
        if relative_source in candidate_set or relative_source in ignored_set:
            continue
        if any(parent in candidate_set for parent in relative_source.parents):
            continue

        try:
            source_text = read_text(source_path)
        except UnicodeDecodeError:
            continue

        normalized_source_text = source_text.replace("\\", "/")
        parsed_tree: ast.AST | None = None
        if source_path.suffix.lower() == ".py":
            try:
                parsed_tree = ast.parse(source_text, filename=str(relative_source))
            except SyntaxError:
                parsed_tree = None

        for candidate in candidate_paths:
            candidate_text = candidate.as_posix().rstrip("/")
            if candidate_text and candidate_text in normalized_source_text:
                references.append(
                    Reference(
                        source_path=relative_source,
                        candidate_path=candidate,
                        detail="literal path reference",
                    )
                )

            module = modules[candidate]
            if parsed_tree is not None and module and module_imports_candidate(
                parsed_tree, module
            ):
                references.append(
                    Reference(
                        source_path=relative_source,
                        candidate_path=candidate,
                        detail=f"Python import of {module}",
                    )
                )

    unique = {
        (item.source_path, item.candidate_path, item.detail): item
        for item in references
    }
    return sorted(
        unique.values(),
        key=lambda item: (
            item.candidate_path.as_posix(),
            item.source_path.as_posix(),
            item.detail,
        ),
    )


def validate_python_syntax(
    project_root: Path,
    scan_roots: Sequence[Path],
    *,
    excluded_directory_names: set[str],
    exclude_globs: Sequence[str],
) -> list[str]:
    root = project_root.resolve()
    errors: list[str] = []

    for path in iter_project_files(
        root,
        scan_roots,
        excluded_directory_names=excluded_directory_names,
        exclude_globs=exclude_globs,
        suffixes={".py"},
    ):
        relative = path.resolve().relative_to(root)
        try:
            ast.parse(read_text(path), filename=str(relative))
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{relative}: {type(exc).__name__}: {exc}")

    return errors


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def protected_hashes(
    project_root: Path,
    protected_paths: Sequence[Path],
) -> dict[str, str]:
    root = project_root.resolve()
    result: dict[str, str] = {}

    for relative in protected_paths:
        absolute = root / relative
        if absolute.is_file():
            result[relative.as_posix()] = sha256(absolute)
            continue
        if absolute.is_dir():
            for path in sorted(absolute.rglob("*")):
                if path.is_file():
                    nested = path.resolve().relative_to(root)
                    result[nested.as_posix()] = sha256(path)
    return result


def backup_paths(
    project_root: Path,
    relative_paths: Iterable[Path],
    backup_root: Path,
) -> None:
    root = project_root.resolve()
    backup_root = backup_root.resolve()
    backup_root.mkdir(parents=True, exist_ok=True)

    for relative in sorted(set(relative_paths), key=lambda item: item.as_posix()):
        source = root / relative
        if not source.exists():
            continue
        destination = backup_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)


def remove_empty_functions_from_file(
    path: Path,
    candidates: Sequence[EmptyFunction],
) -> None:
    original = path.read_text(encoding="utf-8-sig")
    lines = original.splitlines(keepends=True)

    class_groups: dict[int, list[EmptyFunction]] = {}
    for candidate in candidates:
        if candidate.parent_kind == "class" and candidate.parent_start_line is not None:
            class_groups.setdefault(candidate.parent_start_line, []).append(candidate)

    replacements: dict[tuple[int, int], str] = {}
    for group in class_groups.values():
        if group and group[0].parent_needs_pass:
            first = min(group, key=lambda item: item.start_line)
            indent = (first.parent_indent or 0) + 4
            replacements[(first.start_line, first.end_line)] = " " * indent + "pass\n"

    for candidate in sorted(candidates, key=lambda item: item.start_line, reverse=True):
        start_index = candidate.start_line - 1
        end_index = candidate.end_line
        replacement = replacements.get((candidate.start_line, candidate.end_line), "")
        lines[start_index:end_index] = [replacement] if replacement else []

    updated = "".join(lines)
    ast.parse(updated, filename=str(path))
    atomic_write_text(path, updated)


def write_manifest(path: Path, result: CleanupResult) -> None:
    payload = {
        "schema_version": 1,
        "created_at": utc_now_iso(),
        "project_root": str(result.project_root),
        "applied": result.applied,
        "removed_files": [item.as_posix() for item in result.removed_files],
        "removed_directories": [
            item.as_posix() for item in result.removed_directories
        ],
        "modified_function_files": [
            item.as_posix() for item in result.modified_function_files
        ],
        "empty_functions": [
            {
                **asdict(item),
                "file_path": item.file_path.as_posix(),
            }
            for item in result.empty_functions
        ],
        "references": [
            {
                "source_path": item.source_path.as_posix(),
                "candidate_path": item.candidate_path.as_posix(),
                "detail": item.detail,
            }
            for item in result.references
        ],
        "protected_hashes_before": result.protected_hashes_before,
        "protected_hashes_after": result.protected_hashes_after,
        "backup_directory": (
            result.backup_directory.as_posix()
            if result.backup_directory is not None
            else None
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
