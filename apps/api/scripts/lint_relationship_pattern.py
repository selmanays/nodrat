#!/usr/bin/env python3
"""Phase 8 PR-8b-4 — Relationship pattern lint.

Static AST guard for T8 precondition 1 (string-form relationship pattern).

SQLAlchemy 2.0 best practice: `relationship()` references should be either:
  - string class name:   `relationship("ClassName", back_populates="...")`
  - no positional arg:   `relationship(back_populates="...")` (with `Mapped[...]` annotation)

The **class-form** is forbidden because it forces eager class-resolution order
and breaks modular model splitting:

  ❌ relationship(Conversation, ...)   # imports Conversation class directly
  ✅ relationship("Conversation", ...) # late-bound string ref
  ✅ relationship(back_populates="conversation") # Mapped[Class] handles ref

The runtime `configure_mappers()` test (tests/unit/test_mapper_resolution.py,
PR-8b-3) would also catch many of these, but this static lint:
- runs in api-lint CI job (no DB, no docker, ~1s)
- gives faster pre-merge feedback
- pinpoints the exact file:line on violation

Audit (2026-05-24): 14 relationship() calls in app/models/*.py, 0 class-form.

Exit codes:
  0 — clean
  1 — violations detected (file:line + class-name printed)
  2 — usage error
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def find_class_form_relationships(source: str, path: Path) -> list[tuple[int, str]]:
    """Return [(lineno, offender_text), ...] for class-form relationship() calls.

    A class-form call has a first positional argument that is `ast.Name` whose
    id starts with an uppercase letter (heuristic for class name). String
    literals (`ast.Constant` with `str` value) and keyword-only calls are OK.
    """
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        print(f"SYNTAX ERROR in {path}: {exc}", file=sys.stderr)
        return []

    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match `relationship(...)` — bare name or `something.relationship(...)`
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if name != "relationship":
            continue
        if not node.args:
            continue  # no positional arg → safe
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            continue  # string-form → safe
        if isinstance(first, ast.Name) and first.id[:1].isupper():
            # Class-form — violation
            violations.append((node.lineno, first.id))
    return violations


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] in {"-h", "--help"}:
        print(__doc__)
        return 2

    models_dir = Path(__file__).resolve().parent.parent / "app" / "models"
    if not models_dir.is_dir():
        print(f"ERROR: {models_dir} not found", file=sys.stderr)
        return 2

    py_files = sorted(p for p in models_dir.glob("*.py") if p.name != "__init__.py")
    total_violations = 0
    for path in py_files:
        for lineno, class_name in find_class_form_relationships(path.read_text(), path):
            rel_path = path.relative_to(models_dir.parent.parent.parent.parent)
            print(
                f"{rel_path}:{lineno}: class-form relationship({class_name}, ...) — "
                'use string form: relationship("' + class_name + '", ...)',
                file=sys.stderr,
            )
            total_violations += 1

    if total_violations:
        print(
            f"\nFAIL: {total_violations} class-form relationship() call(s) detected. "
            "T8 precondition 1 (string-form pattern) violated.",
            file=sys.stderr,
        )
        return 1

    file_count = len(py_files)
    print(f"OK: scanned {file_count} model file(s); 0 class-form relationship() calls.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
