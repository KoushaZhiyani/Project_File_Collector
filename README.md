# 🧰 Toolbox

A collection of practical Python utilities and command-line tools designed to simplify common software development, data processing, database maintenance, project cleanup, automation, and documentation tasks.

Each tool is maintained in its own directory and includes dedicated documentation, usage examples, and tool-specific requirements.

---

## 🎯 Purpose

This repository serves as a centralized toolbox of reusable scripts and utilities created to solve recurring engineering problems.

Its goals are to:

* Keep practical development tools organized in one repository
* Avoid rewriting the same utility for multiple projects
* Make each tool independently usable and maintainable
* Provide safe command-line workflows for destructive operations
* Preserve clear documentation and usage examples for every utility

---

## 📦 Available Tools

### 📂 Project File Collector

A command-line utility that recursively scans a project directory and combines the contents of supported files into a single structured text document.

**Use cases:**

* AI-assisted code analysis
* Code reviews
* Documentation generation
* Project archiving
* Source code sharing

**Key features:**

* Recursive directory traversal
* Automatic file path headers
* Binary file filtering
* Custom ignore rules
* Single-file export

📖 See: `Project_File_Collector/README.md`

---

### 🧱 Scaffolding Cleanup

A generic command-line utility for discovering and safely removing dead scaffolding from Python projects without relying on project-specific paths or hard-coded package names.

The tool uses a dry-run-first workflow and can inspect empty files, empty directories, README-only placeholder directories, and optionally empty Python functions or methods.

**Use cases:**

* Removing abandoned architecture placeholders
* Cleaning empty Python modules
* Deleting README-only planning directories
* Preparing a project before refactoring
* Detecting unused scaffolding after code migration
* Validating that cleanup did not affect protected files

**Key features:**

* Dynamic project selection through `--project-root`
* Configurable scan roots, exclusions, and protected paths
* Empty Python file detection
* Empty and placeholder-only directory detection
* Optional empty-function and empty-method cleanup
* Python import and file-path reference checks
* Dry-run mode by default
* Optional backup creation before applying changes
* JSON cleanup manifest generation
* Protected-file hash verification
* Configurable import-smoke and test commands
* Separate cleanup and post-cleanup validation commands

📖 See: `Scaffolding_Cleanup/README.md`

---

### 🗄 SQLite Database Preview Tool

A lightweight utility for inspecting SQLite databases and exporting table structures together with sample records into a readable text report.

**Use cases:**

* Database auditing
* Data validation
* Migration verification
* Documentation generation
* Quick database inspection

**Key features:**

* Automatic table discovery
* Schema extraction
* Sample data preview
* UTF-8 support
* Timestamped reporting

📖 See: `SQLite_Database_Preview/README.md`

---

### 🧹 SQL Insert Cleaner

A lightweight utility for cleaning and transforming SQL `INSERT INTO` statements by removing unwanted columns and optionally renaming destination tables.

**Use cases:**

* Database migration
* ETL preprocessing
* Legacy system cleanup
* SQL dump transformation
* Schema refactoring

**Key features:**

* SQL `INSERT` parsing
* Flexible column exclusion rules
* Table renaming support
* Regex-based filtering
* SQL function preservation
* Clean output generation

📖 See: `SQL_Insert_Cleaner/README.md`

---

### 🗑 Rows Delete by Date

A command-line utility for deleting rows from database tables based on a specified date using `DATE`, `DATETIME`, or `TIMESTAMP` columns.

It supports multiple database engines through SQLAlchemy and includes a safe dry-run mode for previewing affected rows before deletion.

**Use cases:**

* Data cleanup
* Removing daily import records
* ETL reruns
* Test data reset
* Scheduled database maintenance

**Key features:**

* Multi-database support for DuckDB, SQLite, PostgreSQL, MySQL, and SQL Server
* Automatic table discovery
* Automatic date and time column detection
* Dry-run mode by default
* Interactive confirmation before deletion
* Single-table or all-table processing

📖 See: `Rows_Delete_by_Date/README.md`

---

## 🚀 Why This Repository Exists

Small utilities are often created while solving real project problems. When these scripts remain scattered across projects, they become difficult to discover, reuse, test, and maintain.

This repository provides a centralized location for:

* Reusable development scripts
* Project maintenance utilities
* Database inspection and cleanup tools
* SQL transformation tools
* Automation helpers
* Documentation generators
* Safe command-line workflows

Each project remains isolated inside its own directory so that it can evolve independently without creating unnecessary dependencies between tools.

---

## 📁 Repository Structure

```text
toolbox/
│
├── Project_File_Collector/
│   ├── README.md
│   └── ...
│
├── Scaffolding_Cleanup/
│   ├── README.md
│   ├── scaffolding_cleanup.py
│   ├── cleanup_dead_scaffolding.py
│   └── validate_dead_scaffolding_cleanup.py
│
├── SQLite_Database_Preview/
│   ├── README.md
│   └── ...
│
├── SQL_Insert_Cleaner/
│   ├── README.md
│   └── ...
│
├── Rows_Delete_by_Date/
│   ├── README.md
│   └── ...
│
├── LICENSE
└── README.md
```

---

## 🛠 Requirements

Most tools are built with:

* Python 3.9+
* The Python Standard Library whenever possible
* Command-line execution on Windows, Linux, or macOS

Some tools may require a newer Python version or additional packages. For example, `Scaffolding_Cleanup` requires Python 3.10+.

Tool-specific dependencies and setup instructions are documented in each project's `README.md` file.

---

## 🛡 Safety Principles

Utilities that modify source files or database records should follow a safe execution model whenever possible:

1. Preview the operation using dry-run mode
2. Review detected files, directories, or database rows
3. Protect important paths and data files
4. Create backups when supported
5. Apply the operation explicitly
6. Run the provided validation command afterward

These safeguards are especially important for tools such as `Scaffolding_Cleanup` and `Rows_Delete_by_Date`.

---

## 📈 Future Additions

Planned categories include:

* File processing tools
* Database utilities
* SQL transformation tools
* Data cleaning scripts
* Project maintenance tools
* Automation helpers
* CLI productivity tools
* Documentation generators
* Validation and auditing utilities

---

## 🤝 Contributions

Contributions, bug reports, and feature suggestions are welcome.

To contribute:

1. Fork the repository
2. Create a feature branch
3. Add or update the relevant documentation
4. Include tests or validation instructions when applicable
5. Submit a pull request

Each new utility should remain self-contained and include its own `README.md` file.

---

## 📜 License

This repository is licensed under the MIT License.

See the `LICENSE` file for details.

---

## 👨‍💻 Author

Created and maintained by Kousha Zhiyani.

A growing collection of practical tools built to solve everyday software engineering and data-processing problems.
