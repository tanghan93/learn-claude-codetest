"""
AST Parser and Refactoring Tool

Provides utilities to parse Python source code into an Abstract Syntax Tree (AST),
analyze code structure, and perform automated refactoring operations.

Uses Python's built-in `ast` module for parsing and code generation.
"""

import ast
import os
import sys
from pathlib import Path
from typing import Any, Optional, Union
from collections import defaultdict


# --- Exceptions -----------------------------------------------------------------

class ASTError(Exception):
    """Custom exception for AST parsing errors."""
    pass


# --- Code Analyzer --------------------------------------------------------------

class CodeAnalyzer(ast.NodeVisitor):
    """Analyzes Python source code and extracts structural information.

    Visits all nodes in an AST and collects information about:
    - Functions and their signatures
    - Classes and their methods
    - Imports
    - Global variables
    - Code complexity metrics
    """

    def __init__(self):
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.imports: list[dict[str, Any]] = []
        self.global_vars: list[dict[str, Any]] = []
        self.total_lines = 0
        self.total_nodes = 0
        self.depth = 0
        self.max_depth = 0
        self._current_class: Optional[str] = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Collect information about a function definition."""
        func_info = {
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "class_name": self._current_class,
            "args": self._extract_args(node.args),
            "decorators": [ast.unparse(d) for d in node.decorator_list],
            "docstring": ast.get_docstring(node),
            "body_length": len(node.body),
            "returns": ast.unparse(node.returns) if node.returns else None,
        }
        self.functions.append(func_info)

        # Visit child nodes to find nested functions
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Collect information about an async function definition."""
        func_info = {
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "class_name": self._current_class,
            "args": self._extract_args(node.args),
            "decorators": [ast.unparse(d) for d in node.decorator_list],
            "docstring": ast.get_docstring(node),
            "body_length": len(node.body),
            "returns": ast.unparse(node.returns) if node.returns else None,
            "async": True,
        }
        self.functions.append(func_info)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Collect information about a class definition."""
        class_info = {
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "bases": [ast.unparse(b) for b in node.bases],
            "decorators": [ast.unparse(d) for d in node.decorator_list],
            "docstring": ast.get_docstring(node),
            "methods": [],
        }
        self._current_class = node.name
        self.generic_visit(node)
        # Collect methods defined within this class
        class_info["methods"] = [
            f for f in self.functions if f["class_name"] == node.name
        ]
        self.classes.append(class_info)
        self._current_class = None

    def visit_Import(self, node: ast.Import) -> None:
        """Collect import information."""
        for alias in node.names:
            self.imports.append({
                "module": alias.name,
                "alias": alias.asname,
                "lineno": node.lineno,
            })

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Collect from-import information."""
        module = node.module or ""
        for alias in node.names:
            self.imports.append({
                "module": module,
                "name": alias.name,
                "alias": alias.asname,
                "lineno": node.lineno,
            })

    def visit_Assign(self, node: ast.Assign) -> None:
        """Collect global variable assignments."""
        for target in node.targets:
            if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store):
                self.global_vars.append({
                    "name": target.id,
                    "lineno": node.lineno,
                    "value": ast.unparse(node.value),
                })
        self.generic_visit(node)

    def visit(self, node: ast.AST) -> Any:
        """Override visit to track depth and node count."""
        self.total_nodes += 1
        self.depth += 1
        self.max_depth = max(self.max_depth, self.depth)
        result = super().visit(node)
        self.depth -= 1
        return result

    @staticmethod
    def _extract_args(args: ast.arguments) -> dict[str, Any]:
        """Extract function argument information."""
        return {
            "positional": [arg.arg for arg in args.args],
            "defaults": [ast.unparse(d) for d in args.defaults],
            "vararg": args.vararg.arg if args.vararg else None,
            "kwonly": [arg.arg for arg in args.kwonlyargs],
            "kwonly_defaults": (
                [ast.unparse(d) for d in args.kw_defaults]
                if args.kw_defaults else []
            ),
            "kwarg": args.kwarg.arg if args.kwarg else None,
        }


# --- AST Transformer -----------------------------------------------------------

class FunctionRenamer(ast.NodeTransformer):
    """Renames a function (and all calls to it) throughout the AST."""

    def __init__(self, old_name: str, new_name: str):
        self.old_name = old_name
        self.new_name = new_name
        self.rename_count = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        if node.name == self.old_name:
            node.name = self.new_name
            self.rename_count += 1
        self.generic_visit(node)
        return node

    def visit_Call(self, node: ast.Call) -> ast.Call:
        if isinstance(node.func, ast.Name) and node.func.id == self.old_name:
            node.func.id = self.new_name
            self.rename_count += 1
        self.generic_visit(node)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        # Handle method calls: obj.old_name -> obj.new_name
        if node.attr == self.old_name:
            node.attr = self.new_name
            self.rename_count += 1
        self.generic_visit(node)
        return node


class DocstringUpdater(ast.NodeTransformer):
    """Updates docstrings for functions and classes."""

    def __init__(self, target_name: str, new_docstring: str):
        self.target_name = target_name
        self.new_docstring = new_docstring
        self.updated = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        if node.name == self.target_name:
            node = self._update_docstring(node)
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        if node.name == self.target_name:
            node = self._update_docstring(node)
        self.generic_visit(node)
        return node

    def _update_docstring(self, node: Union[ast.FunctionDef, ast.ClassDef]) -> Union[ast.FunctionDef, ast.ClassDef]:
        """Replace or add a docstring to the node."""
        new_expr = ast.Expr(value=ast.Constant(value=self.new_docstring))

        if (node.body and isinstance(node.body[0], ast.Expr) and
                isinstance(node.body[0].value, ast.Constant) and
                isinstance(node.body[0].value.value, str)):
            # Replace existing docstring
            node.body[0] = new_expr
        else:
            # Insert docstring at the beginning
            node.body.insert(0, new_expr)

        self.updated = True
        return node


# --- Main Parser Class ----------------------------------------------------------

class SourceParser:
    """Parse Python source code into AST and provide analysis and transformation tools.

    This is the main entry point for parsing source code files and performing
    refactoring operations on them.
    """

    def __init__(self, source_path: Optional[str] = None):
        self.source_path = source_path
        self.tree: Optional[ast.AST] = None
        self.source_code: Optional[str] = None
        self.analyzer: Optional[CodeAnalyzer] = None
        self.filename: str = ""

        if source_path:
            self.load_file(source_path)

    def load_file(self, filepath: str) -> "SourceParser":
        """Load and parse a Python source file.

        Args:
            filepath: Path to the Python source file.

        Returns:
            Self for chaining.

        Raises:
            ASTError: If the file cannot be parsed.
            FileNotFoundError: If the file does not exist.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        self.filename = str(path)
        self.source_code = path.read_text(encoding="utf-8")
        return self.parse_source(self.source_code)

    def load_string(self, code: str, filename: str = "<string>") -> "SourceParser":
        """Load and parse a string of Python source code.

        Args:
            code: Python source code string.
            filename: Virtual filename (for error reporting).

        Returns:
            Self for chaining.
        """
        self.filename = filename
        self.source_code = code
        return self.parse_source(code)

    def parse_source(self, source_code: str) -> "SourceParser":
        """Parse a string of Python source code into an AST.

        Args:
            source_code: Python source code string.

        Returns:
            Self for chaining.

        Raises:
            ASTError: If the source code cannot be parsed.
        """
        try:
            self.tree = ast.parse(source_code, filename=self.filename)
        except SyntaxError as e:
            raise ASTError(f"Failed to parse source: {e}") from e
        return self

    def analyze(self) -> CodeAnalyzer:
        """Run code analysis on the parsed AST.

        Returns:
            A CodeAnalyzer with collected information.
        """
        if self.tree is None:
            raise ASTError("No AST loaded. Call load_file() or load_string() first.")

        self.analyzer = CodeAnalyzer()
        self.analyzer.visit(self.tree)
        return self.analyzer

    def get_source_lines(self) -> list[str]:
        """Get the source code as a list of lines."""
        if self.source_code is None:
            raise ASTError("No source code loaded.")
        return self.source_code.splitlines()

    def get_line_count(self) -> int:
        """Get the total number of lines in the source."""
        lines = self.get_source_lines()
        return len(lines)

    def get_code_snippet(self, start_line: int, end_line: int) -> str:
        """Get a snippet of code between line numbers (1-indexed)."""
        lines = self.get_source_lines()
        start = max(0, start_line - 1)
        end = min(len(lines), end_line)
        return "\n".join(lines[start:end])

    # --- AST Transformation Methods -----------------------------------------

    def rename_function(self, old_name: str, new_name: str) -> tuple[int, str]:
        """Rename a function throughout the AST.

        Args:
            old_name: Current function name.
            new_name: New function name.

        Returns:
            Tuple of (number_of_renames, new_source_code).
        """
        if self.tree is None:
            raise ASTError("No AST loaded.")

        renamer = FunctionRenamer(old_name, new_name)
        self.tree = renamer.visit(self.tree)
        ast.fix_missing_locations(self.tree)
        new_code = ast.unparse(self.tree)
        return renamer.rename_count, new_code

    def update_docstring(self, target_name: str, new_docstring: str) -> tuple[bool, str]:
        """Update the docstring of a function or class.

        Args:
            target_name: Name of the function or class.
            new_docstring: New docstring text.

        Returns:
            Tuple of (was_updated, new_source_code).
        """
        if self.tree is None:
            raise ASTError("No AST loaded.")

        updater = DocstringUpdater(target_name, new_docstring)
        self.tree = updater.visit(self.tree)
        ast.fix_missing_locations(self.tree)
        new_code = ast.unparse(self.tree)
        return updater.updated, new_code

    def remove_unused_imports(self) -> tuple[list[dict[str, Any]], str]:
        """Remove imports that are not used in the code.

        Returns:
            Tuple of (removed_imports_list, new_source_code).
        """
        if self.tree is None:
            raise ASTError("No AST loaded.")

        # Collect all names used in the code
        used_names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                used_names.add(node.attr)

        # Find imports that are not used
        removed_imports = []

        class UnusedImportRemover(ast.NodeTransformer):
            def __init__(self, parent):
                self.parent = parent
                self.removed = []

            def visit_Import(self, node: ast.Import) -> Any:
                kept_aliases = []
                for alias in node.names:
                    if alias.name in used_names or alias.asname in used_names:
                        kept_aliases.append(alias)
                    else:
                        self.removed.append({"module": alias.name, "alias": alias.asname})
                if kept_aliases:
                    node.names = kept_aliases
                    return node
                return None  # Remove the entire import

            def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
                kept_aliases = []
                for alias in node.names:
                    if alias.name in used_names or alias.asname in used_names:
                        kept_aliases.append(alias)
                    else:
                        self.removed.append({
                            "module": node.module or "",
                            "name": alias.name,
                            "alias": alias.asname,
                        })
                if kept_aliases:
                    node.names = kept_aliases
                    return node
                return None  # Remove the entire import

        remover = UnusedImportRemover(self)
        self.tree = remover.visit(self.tree)
        ast.fix_missing_locations(self.tree)
        new_code = ast.unparse(self.tree)
        return remover.removed, new_code

    # --- Utility Methods ----------------------------------------------------

    def to_string(self) -> str:
        """Unparse the AST back to source code string."""
        if self.tree is None:
            raise ASTError("No AST loaded.")
        return ast.unparse(self.tree)

    def save(self, filepath: Optional[str] = None) -> None:
        """Save the (possibly transformed) AST back to a file.

        Args:
            filepath: Output file path. If None, overwrites the original file.
        """
        output_path = filepath or self.filename
        code = self.to_string()

        path = Path(output_path)
        path.write_text(code, encoding="utf-8")
        print(f"Saved to {output_path}")

    def print_ast_tree(self, show_attrs: bool = False) -> None:
        """Pretty-print the AST tree structure.

        Args:
            show_attrs: If True, also show node attributes.
        """
        if self.tree is None:
            raise ASTError("No AST loaded.")
        self._print_node(self.tree, show_attrs=show_attrs)

    def _print_node(self, node: ast.AST, indent: str = "", show_attrs: bool = False) -> None:
        """Recursively print an AST node."""
        node_name = type(node).__name__
        print(f"{indent} +-- {node_name}", end="")

        # Show relevant attributes
        attrs = {}
        if hasattr(node, "lineno"):
            attrs["line"] = node.lineno
        if hasattr(node, "col_offset"):
            attrs["col"] = node.col_offset
        if hasattr(node, "end_lineno"):
            attrs["end"] = node.end_lineno
        if isinstance(node, ast.Name):
            attrs["id"] = node.id
        if isinstance(node, ast.Constant):
            attrs["value"] = repr(node.value)
        if isinstance(node, ast.FunctionDef):
            attrs["name"] = node.name
        if isinstance(node, ast.ClassDef):
            attrs["name"] = node.name

        if attrs and show_attrs:
            print(f" {attrs}", end="")
        print()

        # Recurse into children
        for child in ast.iter_child_nodes(node):
            self._print_node(child, indent + "  ", show_attrs)

    def print_summary(self) -> None:
        """Print a summary of the parsed source code."""
        if self.analyzer is None:
            self.analyze()

        a = self.analyzer
        print("=" * 60)
        print(f"  AST Analysis Summary: {self.filename or '<string>'}")
        print("=" * 60)
        print(f"  Total nodes:       {a.total_nodes}")
        print(f"  Max nesting depth: {a.max_depth}")
        print(f"  Total lines:       {len(self.get_source_lines())}")
        print()

        if a.imports:
            print(f"  Imports ({len(a.imports)}):")
            for imp in a.imports:
                if "name" in imp:
                    print(f"    from {imp['module']} import {imp['name']}")
                else:
                    alias = f" as {imp['alias']}" if imp['alias'] else ""
                    print(f"    import {imp['module']}{alias}")

        if a.functions:
            print(f"\n  Functions ({len(a.functions)}):")
            for func in a.functions:
                cls = f"{func['class_name']}." if func['class_name'] else ""
                args_str = ", ".join(func['args']['positional'])
                doc = " (has docstring)" if func['docstring'] else " (no docstring)"
                deco = f" @{', @'.join(func['decorators'])}" if func['decorators'] else ""
                print(f"    {cls}{func['name']}({args_str}){deco}{doc}")
                if func['docstring']:
                    # Show first line of docstring
                    doc_first = func['docstring'].split('\n')[0][:60]
                    print(f"      -> {doc_first}")

        if a.classes:
            print(f"\n  Classes ({len(a.classes)}):")
            for cls in a.classes:
                bases = f"({', '.join(cls['bases'])})" if cls['bases'] else ""
                print(f"    {cls['name']}{bases}")
                for method in cls['methods']:
                    args = ", ".join(method['args']['positional'])
                    print(f"      {method['name']}({args})")

        print("=" * 60)


# --- Batch Processing -----------------------------------------------------------

def find_python_files(directory: str = ".") -> list[str]:
    """Find all Python files in a directory recursively.

    Args:
        directory: Root directory to search.

    Returns:
        List of file paths.
    """
    path = Path(directory)
    return [str(p) for p in path.rglob("*.py")
            if not any(part.startswith(".") or part == "__pycache__" or part == ".venv"
                       for part in p.parts)]


def parse_directory(directory: str = ".") -> dict[str, SourceParser]:
    """Parse all Python files in a directory.

    Args:
        directory: Root directory to search.

    Returns:
        Dictionary mapping file paths to SourceParser instances.
    """
    parsers = {}
    for filepath in find_python_files(directory):
        try:
            parser = SourceParser(filepath)
            parser.analyze()
            parsers[filepath] = parser
        except (ASTError, SyntaxError) as e:
            print(f"  Error parsing {filepath}: {e}", file=sys.stderr)
    return parsers


def generate_refactoring_report(directory: str = ".") -> str:
    """Generate a comprehensive refactoring report for a project.

    Args:
        directory: Root directory of the project.

    Returns:
        A formatted report string.
    """
    parsers = parse_directory(directory)

    total_files = len(parsers)
    total_functions = 0
    total_classes = 0
    total_lines = 0
    total_nodes = 0

    lines = []
    lines.append("=" * 70)
    lines.append("  AST REFACTORING ANALYSIS REPORT")
    lines.append("=" * 70)

    for filepath, parser in sorted(parsers.items()):
        a = parser.analyzer
        rel_path = os.path.relpath(filepath, directory)
        file_lines = parser.get_line_count()

        lines.append(f"\n  [{rel_path}] - {file_lines} lines, {a.total_nodes} nodes")

        if a.imports:
            lines.append(f"    Imports: {len(a.imports)}")
        if a.functions:
            lines.append(f"    Functions: {len(a.functions)}")
        if a.classes:
            lines.append(f"    Classes: {len(a.classes)}")

        # Show top-level functions
        for func in a.functions:
            if not func['class_name']:
                doc = " [OK]" if func['docstring'] else " [MISSING DOCSTRING]"
                lines.append(f"      def {func['name']}(){doc}")

        # Show classes
        for cls in a.classes:
            lines.append(f"    class {cls['name']}:")
            for method in cls['methods']:
                doc = " [OK]" if method['docstring'] else " [MISSING DOCSTRING]"
                lines.append(f"      def {method['name']}(){doc}")

        total_functions += len(a.functions)
        total_classes += len(a.classes)
        total_lines += file_lines
        total_nodes += a.total_nodes

    lines.append("\n" + "=" * 70)
    lines.append(f"  SUMMARY:")
    lines.append(f"    Files:      {total_files}")
    lines.append(f"    Lines:      {total_lines}")
    lines.append(f"    Functions:  {total_functions}")
    lines.append(f"    Classes:    {total_classes}")
    lines.append(f"    AST Nodes:  {total_nodes}")
    lines.append("=" * 70)

    return "\n".join(lines)


# --- CLI Entry Point ------------------------------------------------------------

def main_cli():
    """Command-line interface for the AST parser."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse Python source code into AST for refactoring"
    )
    parser.add_argument("path", nargs="?", default=".",
                        help="File or directory to analyze (default: current dir)")
    parser.add_argument("-s", "--summary", action="store_true",
                        help="Print analysis summary")
    parser.add_argument("-t", "--tree", action="store_true",
                        help="Print AST tree structure")
    parser.add_argument("--attrs", action="store_true",
                        help="Show node attributes in tree view")
    parser.add_argument("-r", "--report", action="store_true",
                        help="Generate full refactoring report")

    args = parser.parse_args()

    path = Path(args.path)

    if args.report:
        print(generate_refactoring_report(str(path)))
        return

    if path.is_file():
        try:
            parser_obj = SourceParser(str(path))
            parser_obj.analyze()

            if args.tree:
                parser_obj.print_ast_tree(show_attrs=args.attrs)
            elif args.summary:
                parser_obj.print_summary()
            else:
                parser_obj.print_summary()

        except (FileNotFoundError, ASTError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif path.is_dir():
        parsers = parse_directory(str(path))
        if not parsers:
            print("No Python files found.")
            return

        if args.tree:
            for filepath, p in sorted(parsers.items()):
                print(f"\n=== {filepath} ===")
                p.print_ast_tree(show_attrs=args.attrs)
        else:
            print(generate_refactoring_report(str(path)))
    else:
        print(f"Error: {path} does not exist", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
