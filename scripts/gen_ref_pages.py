"""Generate API reference pages automatically."""

import sys
from pathlib import Path

import mkdocs_gen_files

# Add src to Python path so mkdocstrings can find modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Source directory
src_root = Path("src")
nav_items = []

# Iterate through all Python files in the package
for path in sorted(src_root.rglob("*.py")):
    # Get module path relative to src
    module_path = path.relative_to(src_root).with_suffix("")
    doc_path = path.relative_to(src_root).with_suffix(".md")
    full_doc_path = Path("reference", doc_path)

    # Convert path to module name
    parts = tuple(module_path.parts)

    # Skip __pycache__ and similar
    if "__pycache__" in parts:
        continue

    # Skip __init__.py files (they'll be covered by package docs)
    if parts[-1] == "__init__":
        # Still create a page for the package itself
        parts = parts[:-1]
        doc_path = doc_path.with_name("index.md")
        full_doc_path = Path("reference", module_path.parent, "index.md")

        if not parts:  # Skip root __init__.py
            continue

    # Create navigation items (store doc_path without 'reference/' prefix for nav)
    nav_items.append((parts, doc_path))

    # Write the markdown file with mkdocstrings reference
    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        module_name = ".".join(parts)
        print(f"::: {module_name}", file=fd)

    # Set edit path
    mkdocs_gen_files.set_edit_path(full_doc_path, path)

# Generate the navigation file
with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.write("# API Reference\n\n")

    # Organize by top-level modules
    current_module = None
    for parts, doc_path in sorted(nav_items):
        if not parts:
            continue

        # Top-level module
        top_module = parts[0]
        if top_module != current_module:
            current_module = top_module
            nav_file.write(f"\n## {top_module}\n\n")

        # Create indented navigation - use relative path from reference/
        indent = "  " * (len(parts) - 1)
        title = parts[-1].replace("_", " ").title()
        nav_file.write(f"{indent}* [{title}]({doc_path})\n")
