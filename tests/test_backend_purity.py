"""Automated Test for Backend Purity & Framework Decoupling (Slice 0).

Ensures that:
1. Core backend modules (auth, core, database, cache, security, tools, llmops, memory)
   contain ZERO static imports of Streamlit.
2. Runtime imports of any backend module never pollute sys.modules with Streamlit.
"""

import os
import ast
import sys
import pytest


CORE_MODULE_DIRS = ["core", "cache", "security", "tools", "llmops", "memory"]
ROOT_CORE_FILES = ["database.py", "llm_fallback.py", "crew.py"]


def test_no_static_streamlit_imports_in_core_backend():
    """Verify via AST parsing that no core backend Python files import streamlit."""
    violations = []
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    files_to_scan = [os.path.join(project_root, f) for f in ROOT_CORE_FILES]

    for d in CORE_MODULE_DIRS:
        dir_path = os.path.join(project_root, d)
        if os.path.isdir(dir_path):
            for root, _, files in os.walk(dir_path):
                for f in files:
                    if f.endswith(".py"):
                        files_to_scan.append(os.path.join(root, f))

    # Also scan all auth files except ui.py (which is dedicated to Streamlit)
    auth_dir = os.path.join(project_root, "auth")
    for f in os.listdir(auth_dir):
        if f.endswith(".py") and f != "ui.py":
            files_to_scan.append(os.path.join(auth_dir, f))

    for file_path in files_to_scan:
        with open(file_path, "r", encoding="utf-8") as src:
            tree = ast.parse(src.read(), filename=file_path)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "streamlit" in alias.name:
                        violations.append(f"{os.path.relpath(file_path, project_root)}:{node.lineno} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module and "streamlit" in node.module:
                    violations.append(f"{os.path.relpath(file_path, project_root)}:{node.lineno} imports from '{node.module}'")

    assert not violations, f"Streamlit imports detected in core backend:\n" + "\n".join(violations)


def test_runtime_import_purity():
    """Verify that importing any backend module at runtime does not load Streamlit into sys.modules."""
    # Ensure streamlit is not already loaded
    if "streamlit" in sys.modules:
        del sys.modules["streamlit"]

    import database
    import cache
    import core
    import security
    import tools
    import auth

    assert "streamlit" not in sys.modules, "Runtime import of core backend modules leaked Streamlit into sys.modules"
