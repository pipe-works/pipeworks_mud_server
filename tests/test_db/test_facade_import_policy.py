"""Import-path policy tests for the DB facade migration."""

from __future__ import annotations

import ast
from pathlib import Path


def _iter_app_layer_python_files() -> list[Path]:
    """
    Return app-layer Python files that must consume DB via the facade module.

    Scope intentionally excludes ``mud_server.db`` repository modules because
    those modules still implement/refactor compatibility wrappers internally.
    """

    src_root = Path(__file__).resolve().parents[2] / "src" / "mud_server"
    files: list[Path] = []

    for relative_dir in ("api", "core", "services"):
        files.extend((src_root / relative_dir).rglob("*.py"))

    files.append(src_root / "cli.py")
    return sorted(files)


def test_app_layer_imports_db_via_facade_only():
    """
    Enforce facade-only DB import usage in app layers.

    Why this test exists:
    - The refactor standardizes app-layer imports on ``mud_server.db.facade``.
    - Many existing tests monkeypatch ``mud_server.db.database`` symbols.
    - Mixing direct database imports with facade imports makes monkeypatch
      behavior inconsistent and fragile.

    This guard fails when app-layer modules import either:
    - ``from mud_server.db import database``
    - ``from mud_server.db.database import ...``
    - ``import mud_server.db.database``
    """

    violations: list[str] = []

    for file_path in _iter_app_layer_python_files():
        module_ast = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(module_ast):
            if isinstance(node, ast.ImportFrom):
                if node.module == "mud_server.db" and any(
                    alias.name == "database" for alias in node.names
                ):
                    violations.append(
                        f"{file_path}:{node.lineno} imports mud_server.db.database alias"
                    )
                if node.module == "mud_server.db.database":
                    violations.append(
                        f"{file_path}:{node.lineno} imports mud_server.db.database directly"
                    )
            elif isinstance(node, ast.Import):
                if any(alias.name == "mud_server.db.database" for alias in node.names):
                    violations.append(
                        f"{file_path}:{node.lineno} imports mud_server.db.database module"
                    )

    assert not violations, "Facade import policy violations:\n" + "\n".join(violations)
