"""Tests for the refactor_ast module."""

import pytest
import tempfile
import os
from pathlib import Path
from refactor_ast import (
    SourceParser,
    CodeAnalyzer,
    FunctionRenamer,
    DocstringUpdater,
    ASTError,
    find_python_files,
    parse_directory,
    generate_refactoring_report,
)


# Sample Python code for testing
SAMPLE_CODE = '''
"""Module docstring."""

import os
import sys
from typing import Optional, List


class Greeter:
    """A class for greeting people."""

    def __init__(self, name: str):
        """Initialize the greeter."""
        self.name = name

    def greet(self, formal: bool = False) -> str:
        """Generate a greeting.

        Args:
            formal: Whether to use formal language.

        Returns:
            A greeting string.
        """
        if formal:
            return f"Good day, {self.name}."
        return f"Hello, {self.name}!"


def add(a: int, b: int) -> int:
    """Add two numbers together.

    Args:
        a: First number.
        b: Second number.

    Returns:
        The sum of a and b.
    """
    return a + b


def unused_function():
    """This function is never called."""
    pass
'''


class TestSourceParser:
    """Tests for SourceParser class."""

    def test_load_string(self):
        """Test loading code from string."""
        parser = SourceParser()
        parser.load_string(SAMPLE_CODE)
        assert parser.tree is not None
        assert parser.source_code == SAMPLE_CODE

    def test_load_file(self):
        """Test loading code from a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(SAMPLE_CODE)
            tmp_path = f.name

        try:
            parser = SourceParser(tmp_path)
            assert parser.tree is not None
            assert parser.filename == tmp_path
        finally:
            os.unlink(tmp_path)

    def test_parse_invalid_syntax(self):
        """Test parsing invalid syntax raises error."""
        parser = SourceParser()
        with pytest.raises(ASTError):
            parser.load_string("def invalid syntax here {{")

    def test_analyze_functions(self):
        """Test analysis finds all functions."""
        parser = SourceParser()
        parser.load_string(SAMPLE_CODE)
        analyzer = parser.analyze()

        func_names = [f["name"] for f in analyzer.functions]
        assert "__init__" in func_names
        assert "greet" in func_names
        assert "add" in func_names
        assert "unused_function" in func_names

    def test_analyze_classes(self):
        """Test analysis finds all classes."""
        parser = SourceParser()
        parser.load_string(SAMPLE_CODE)
        analyzer = parser.analyze()

        class_names = [c["name"] for c in analyzer.classes]
        assert "Greeter" in class_names

    def test_analyze_imports(self):
        """Test analysis finds all imports."""
        parser = SourceParser()
        parser.load_string(SAMPLE_CODE)
        analyzer = parser.analyze()

        assert len(analyzer.imports) >= 3
        modules = [imp["module"] for imp in analyzer.imports]
        assert "os" in modules or "" in modules  # from typing import...

    def test_analyze_docstrings(self):
        """Test analysis detects docstrings."""
        parser = SourceParser()
        parser.load_string(SAMPLE_CODE)
        analyzer = parser.analyze()

        for func in analyzer.functions:
            if func["name"] == "add":
                assert func["docstring"] is not None
                assert "Add two numbers" in func["docstring"]

    def test_get_line_count(self):
        """Test getting line count."""
        parser = SourceParser()
        parser.load_string(SAMPLE_CODE)
        assert parser.get_line_count() > 0

    def test_get_source_lines(self):
        """Test getting source lines."""
        parser = SourceParser()
        parser.load_string("line1\nline2\nline3")
        lines = parser.get_source_lines()
        assert lines == ["line1", "line2", "line3"]

    def test_get_code_snippet(self):
        """Test getting code snippet by line numbers."""
        parser = SourceParser()
        parser.load_string("a\nb\nc\nd\ne")
        snippet = parser.get_code_snippet(2, 4)
        assert snippet == "b\nc\nd"

    def test_to_string(self):
        """Test converting AST back to string."""
        parser = SourceParser()
        parser.load_string("x = 42\n")
        result = parser.to_string()
        assert "42" in result

    def test_rename_function(self):
        """Test renaming a function."""
        code = """
def old_name():
    pass

def caller():
    old_name()
"""
        parser = SourceParser()
        parser.load_string(code)
        count, new_code = parser.rename_function("old_name", "new_name")
        assert count >= 2  # definition + call
        assert "new_name" in new_code
        assert "old_name" not in new_code

    def test_rename_method(self):
        """Test renaming a method."""
        code = """
class MyClass:
    def old_method(self):
        pass

obj = MyClass()
obj.old_method()
"""
        parser = SourceParser()
        parser.load_string(code)
        count, new_code = parser.rename_function("old_method", "new_method")
        assert count >= 2
        assert "new_method" in new_code
        assert "old_method" not in new_code

    def test_update_docstring(self):
        """Test updating a docstring."""
        code = '''
def hello():
    """Old docstring."""
    pass
'''
        parser = SourceParser()
        parser.load_string(code)
        updated, new_code = parser.update_docstring("hello", "New docstring.")
        assert updated is True
        assert "Old docstring" not in new_code
        assert "New docstring" in new_code

    def test_update_docstring_no_existing(self):
        """Test adding a docstring to a function without one."""
        code = '''
def hello():
    pass
'''
        parser = SourceParser()
        parser.load_string(code)
        updated, new_code = parser.update_docstring("hello", "New docstring.")
        assert updated is True
        assert "New docstring" in new_code

    def test_remove_unused_imports(self):
        """Test removing unused imports."""
        code = """
import os
import sys
from typing import List

def greet():
    return "hello"
"""
        parser = SourceParser()
        parser.load_string(code)
        removed, new_code = parser.remove_unused_imports()
        # Both 'os' and 'sys' and 'List' are unused
        assert len(removed) >= 2
        assert "import os" not in new_code
        assert "import sys" not in new_code

    def test_analyze_multiple_files(self):
        """Test parsing a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a Python file
            filepath = os.path.join(tmpdir, "test_mod.py")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("def foo(): pass\n")

            parsers = parse_directory(tmpdir)
            assert len(parsers) == 1
            assert "test_mod.py" in list(parsers.keys())[0]

    def test_generate_report(self):
        """Test generating a refactoring report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_mod.py")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("def foo(): pass\n")

            report = generate_refactoring_report(tmpdir)
            assert "AST REFACTORING ANALYSIS REPORT" in report
            assert "test_mod.py" in report
            assert "Functions:" in report


class TestCodeAnalyzer:
    """Tests for CodeAnalyzer class."""

    def test_async_function(self):
        """Test detecting async functions."""
        code = """
async def fetch_data():
    return "data"
"""
        parser = SourceParser()
        parser.load_string(code)
        analyzer = parser.analyze()
        func = analyzer.functions[0]
        assert func.get("async") is True
        assert func["name"] == "fetch_data"

    def test_class_with_bases(self):
        """Test detecting class inheritance."""
        code = """
class Animal:
    pass

class Dog(Animal):
    pass
"""
        parser = SourceParser()
        parser.load_string(code)
        analyzer = parser.analyze()
        dog = [c for c in analyzer.classes if c["name"] == "Dog"][0]
        assert "Animal" in dog["bases"]

    def test_max_depth(self):
        """Test nesting depth tracking."""
        code = """
if True:
    if True:
        if True:
            pass
"""
        parser = SourceParser()
        parser.load_string(code)
        analyzer = parser.analyze()
        assert analyzer.max_depth >= 3

    def test_global_vars(self):
        """Test detecting global variables."""
        code = """
x = 42
y = "hello"
"""
        parser = SourceParser()
        parser.load_string(code)
        analyzer = parser.analyze()
        var_names = [v["name"] for v in analyzer.global_vars]
        assert "x" in var_names
        assert "y" in var_names


class TestFunctionRenamer:
    """Tests for FunctionRenamer transformer."""

    def test_rename_function_def(self):
        """Test renaming function definitions."""
        tree = SourceParser()
        tree.load_string("def foo(): pass\n")
        renamer = FunctionRenamer("foo", "bar")
        renamer.visit(tree.tree)
        assert renamer.rename_count == 1

    def test_rename_only_matching(self):
        """Test renaming only the specified function."""
        code = """
def foo():
    pass

def bar():
    pass
"""
        tree = SourceParser()
        tree.load_string(code)
        renamer = FunctionRenamer("foo", "new_foo")
        renamer.visit(tree.tree)
        assert renamer.rename_count == 1


class TestDocstringUpdater:
    """Tests for DocstringUpdater transformer."""

    def test_update_function_docstring(self):
        """Test updating function docstring."""
        code = '''
def foo():
    """Old doc."""
    pass
'''
        tree = SourceParser()
        tree.load_string(code)
        updater = DocstringUpdater("foo", "New doc.")
        updater.visit(tree.tree)
        assert updater.updated is True

    def test_update_class_docstring(self):
        """Test updating class docstring."""
        code = '''
class MyClass:
    """Old class doc."""
    pass
'''
        tree = SourceParser()
        tree.load_string(code)
        updater = DocstringUpdater("MyClass", "New class doc.")
        updater.visit(tree.tree)
        assert updater.updated is True

    def test_no_update_non_matching(self):
        """Test not updating non-matching targets."""
        code = '''
def foo():
    pass
'''
        tree = SourceParser()
        tree.load_string(code)
        updater = DocstringUpdater("nonexistent", "New doc.")
        updater.visit(tree.tree)
        assert updater.updated is False


class TestFindPythonFiles:
    """Tests for find_python_files function."""

    def test_finds_py_files(self):
        """Test finding .py files in a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a.py").write_text("")
            Path(tmpdir, "b.py").write_text("")
            Path(tmpdir, "data.txt").write_text("")
            os.makedirs(os.path.join(tmpdir, "sub"), exist_ok=True)
            Path(tmpdir, "sub", "c.py").write_text("")

            files = find_python_files(tmpdir)
            assert len(files) >= 3

    def test_excludes_venv(self):
        """Test excluding .venv directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".venv"), exist_ok=True)
            Path(tmpdir, ".venv", "ignored.py").write_text("")
            Path(tmpdir, "real.py").write_text("")

            files = find_python_files(tmpdir)
            assert len(files) == 1
            assert "real.py" in files[0]


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file(self):
        """Test parsing an empty file."""
        parser = SourceParser()
        parser.load_string("")
        assert parser.tree is not None

    def test_file_not_found(self):
        """Test loading a non-existent file raises error."""
        parser = SourceParser()
        with pytest.raises(FileNotFoundError):
            parser.load_file("/nonexistent/file.py")

    def test_analyze_before_load(self):
        """Test analyzing without loading raises error."""
        parser = SourceParser()
        with pytest.raises(ASTError):
            parser.analyze()

    def test_to_string_before_load(self):
        """Test to_string without loading raises error."""
        parser = SourceParser()
        with pytest.raises(ASTError):
            parser.to_string()

    def test_print_summary_before_analyze(self):
        """Test print_summary triggers analyze automatically."""
        parser = SourceParser()
        parser.load_string("x = 1\n")
        # Should not raise - analyze is called automatically
        parser.print_summary()

    def test_complex_expression_unused_import(self):
        """Test unused import removal with complex code."""
        code = """
import math
import json
import random

def calc():
    return math.sqrt(16)
"""
        parser = SourceParser()
        parser.load_string(code)
        removed, new_code = parser.remove_unused_imports()
        removed_modules = [r["module"] for r in removed]
        assert "json" in removed_modules or "random" in removed_modules
        assert "math" not in removed_modules  # math is used
