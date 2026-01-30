"""Sphinx configuration for PipeWorks MUD Server documentation."""

import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# -- Project information -----------------------------------------------------
project = "PipeWorks MUD Server"
copyright = "2025, PipeWorks Team"
author = "PipeWorks Team"
release = "0.1.0"
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
autoapi_keep_files = False
autoapi_member_order = "bysource"
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
    "myst.header",
    "docutils",
]

nitpicky = False


# -- Custom warning filter for dataclass duplicate warnings -----------------
class FilterDuplicateObjectWarnings(logging.Filter):
    """Filter to suppress 'duplicate object description' warnings for dataclasses."""

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
