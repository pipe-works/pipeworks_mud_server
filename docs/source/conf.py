"""Sphinx configuration for PipeWorks MUD Server documentation.

This configuration uses sphinx-autoapi for fully automated documentation
generation from code docstrings. No manual .rst files needed for API docs.
"""

import logging
import sys
import tomllib
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))


def get_version_from_pyproject() -> str:
    """Read version from pyproject.toml to maintain single source of truth."""
    pyproject_path = project_root / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


# -- Project information -----------------------------------------------------
project = "PipeWorks MUD Server"
copyright = "2026, PipeWorks Team"
author = "PipeWorks Team"
release = get_version_from_pyproject()
version = release

# -- General configuration ---------------------------------------------------
extensions = [
    # AutoAPI for fully automated API documentation from code
    "autoapi.extension",
    # Standard Sphinx extensions
    "sphinx.ext.napoleon",  # Support for Google/NumPy style docstrings
    "sphinx.ext.viewcode",  # Add links to source code
    "sphinx.ext.intersphinx",  # Link to other project docs
    "sphinx_autodoc_typehints",  # Better type hint rendering
    "myst_parser",  # Support for Markdown files
]

# -- AutoAPI configuration ---------------------------------------------------
# This is the key to full automation - autoapi discovers and documents all code
autoapi_type = "python"
autoapi_dirs = [
    str(project_root / "src" / "mud_server"),
]
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
]
autoapi_ignore = [
    "*/__pycache__/*",
    "*/tests/*",
    "*/test_*",
]
autoapi_add_toctree_entry = True
autoapi_keep_files = False  # Clean up generated files after build
autoapi_member_order = "bysource"
# Include both class and __init__ docstrings for complete documentation
autoapi_python_class_content = "both"

# -- Napoleon settings for Google-style docstrings --------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = True
napoleon_attr_annotations = True

# -- Autodoc typehints settings ----------------------------------------------
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"

# -- Intersphinx mapping -----------------------------------------------------
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- Path configuration ------------------------------------------------------
templates_path = ["_templates"]
exclude_patterns = []

# -- Source file configuration -----------------------------------------------
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# -- HTML output options -----------------------------------------------------
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_theme_options = {
    "navigation_depth": 4,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "includehidden": True,
    "titles_only": False,
}

# -- MyST parser configuration -----------------------------------------------
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

# -- Warning suppression -----------------------------------------------------
suppress_warnings = [
    "myst.header",  # MyST parser header warnings
    "docutils",  # Inline emphasis warnings from underscores in code
]

nitpicky = False  # Set to True to enable strict type checking


# -- Custom warning filter for dataclass duplicate warnings -----------------
class FilterDuplicateObjectWarnings(logging.Filter):
    """
    Filter to suppress 'duplicate object description' warnings for dataclass attributes.

    These warnings occur because autoapi_python_class_content = "both" causes
    Sphinx to document attributes from both the class docstring and the
    auto-generated __init__ method. This is expected behavior for dataclasses
    and the generated documentation is correct.
    """

    def filter(self, record):
        is_duplicate_warning = (
            "duplicate object description of %s, other instance in %s, use :no-index: for one of them"
            in record.msg
        )
        return not is_duplicate_warning


def setup(app):
    """Sphinx setup hook to register custom warning filter."""
    logger = logging.getLogger("sphinx")
    logger.addFilter(FilterDuplicateObjectWarnings())
