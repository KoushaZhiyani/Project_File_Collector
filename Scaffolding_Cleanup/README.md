# Generic Dead-Scaffolding Cleanup Tool

This tool replaces project-specific cleanup allowlists with runtime arguments.
It supports:

- empty Python files (or other suffixes you opt in to),
- empty directories,
- directories containing only README/placeholder files and empty nested content,
- optional removal of safe empty Python functions/methods,
- path/import reference checks,
- protected path hashing,
- dry-run by default,
- optional backups and JSON manifests,
- configurable validation commands and import smoke tests.

## Files

```text
scaffolding_cleanup.py
cleanup_dead_scaffolding.py
validate_dead_scaffolding_cleanup.py
```

Keep the three files together, for example under `tools/cleanup/`.

## Safe dry-run

```bash
python tools/cleanup/cleanup_dead_scaffolding.py \
  --project-root "C:\path\to\project" \
  --scan-root src \
  --scan-root packages \
  --protect data \
  --protect storage \
  --exclude "tests/fixtures/**" \
  --manifest cleanup-report.json
```

## Apply after review

```bash
python tools/cleanup/cleanup_dead_scaffolding.py \
  --project-root "C:\path\to\project" \
  --scan-root src \
  --scan-root packages \
  --protect data \
  --protect storage \
  --exclude "tests/fixtures/**" \
  --backup-dir .cleanup-backup \
  --manifest cleanup-report.json \
  --apply
```

## Include empty functions

Empty functions can be intentional extension hooks, callbacks, abstract contracts,
or compatibility shims. They are therefore disabled by default.

```bash
python tools/cleanup/cleanup_dead_scaffolding.py \
  --project-root "C:\path\to\project" \
  --scan-root src \
  --remove-empty-functions
```

Decorated functions and dunder methods remain protected unless explicitly enabled.
Semantic decorators such as `abstractmethod`, `overload`, `property`, `staticmethod`,
and `classmethod` are never automatically removed.

## Validate

```bash
python tools/cleanup/validate_dead_scaffolding_cleanup.py \
  --project-root "C:\path\to\project" \
  --manifest cleanup-report.json \
  --protect data \
  --protect storage \
  --import-module your_package \
  --command "python -m pytest -q"
```

The validator has no hard-coded package names, databases, or test command.
