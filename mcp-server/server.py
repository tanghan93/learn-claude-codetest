#!/usr/bin/env python3
"""
Coding Tools MCP Server

Provides Claude with coding workspace tools for the learn-claude-codetest project.
Run: python server.py
Register: Add to ~/.claude/mcp.json
"""

import subprocess
import json
from pathlib import Path
from datetime import datetime

from mcp.server.fastmcp import FastMCP

# Create server instance
server = FastMCP(
    "coding-tools",
    instructions="Tools for analyzing and navigating a Python coding project workspace.",
    host="127.0.0.1",
    port=0,  # stdio mode (no HTTP server needed)
)

WORKDIR = Path.cwd()


# =============================================================================
# TOOLS
# =============================================================================

@server.tool()
async def project_tree(directory: str = ".") -> str:
    """Show the project directory structure as an ASCII tree.

    Args:
        directory: Relative path from project root (default: ".")
    """
    target = WORKDIR / directory
    if not target.exists():
        return f"Error: Directory '{directory}' not found"
    if not target.is_dir():
        return f"Error: '{directory}' is not a directory"

    lines = []
    target_path = target.resolve()

    def walk(dir_path: Path, prefix: str = ""):
        entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        # Skip hidden directories and __pycache__
        entries = [e for e in entries if not e.name.startswith((".", "__")) or e.name == "__init__.py"]
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                walk(entry, prefix + extension)

    lines.append(f"{target.name}/")
    walk(target)
    return "\n".join(lines[:200])  # Limit to 200 lines


@server.tool()
async def search_files(pattern: str, directory: str = ".") -> str:
    """Search for files by name pattern (uses glob matching).

    Args:
        pattern: File pattern to search for (e.g. "*.py", "test_*", "*.md")
        directory: Relative directory to search in (default: ".")
    """
    target = WORKDIR / directory
    if not target.exists():
        return f"Error: Directory '{directory}' not found"

    matches = sorted(target.rglob(pattern))
    # Filter out hidden/__pycache__ paths
    matches = [m for m in matches if not any(p.startswith(".") or p == "__pycache__" for p in m.relative_to(WORKDIR).parts)]

    if not matches:
        return f"No files matching '{pattern}' found in '{directory}'"

    result = [f"Found {len(matches)} file(s) matching '{pattern}':\n"]
    for m in matches:
        rel = m.relative_to(WORKDIR)
        size = m.stat().st_size
        result.append(f"  {rel}  ({_format_size(size)})")
    return "\n".join(result)


@server.tool()
async def grep_search(query: str, directory: str = ".", file_pattern: str = "*.py") -> str:
    """Search file contents for a text pattern (like grep).

    Args:
        query: Text to search for (case-insensitive)
        directory: Relative directory to search in (default: ".")
        file_pattern: File pattern to filter by (default: "*.py")
    """
    target = WORKDIR / directory
    if not target.exists():
        return f"Error: Directory '{directory}' not found"

    import fnmatch
    matches = []
    query_lower = query.lower()

    for fpath in target.rglob(file_pattern):
        if any(p.startswith(".") or p == "__pycache__" for p in fpath.relative_to(WORKDIR).parts):
            continue
        try:
            for i, line in enumerate(fpath.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if query_lower in line.lower():
                    rel = fpath.relative_to(WORKDIR)
                    matches.append(f"  {rel}:{i}: {line.strip()[:200]}")
        except Exception:
            continue

    if not matches:
        return f"No matches for '{query}' in {directory}/{file_pattern}"

    header = f"Found {len(matches)} match(es) for '{query}':\n"
    return header + "\n".join(matches[:100])  # Limit to 100 results


@server.tool()
async def count_lines(file_path: str) -> str:
    """Count lines of code in a file (total, blank, comment, code).

    Args:
        file_path: Relative path to the file
    """
    target = WORKDIR / file_path
    if not target.exists():
        return f"Error: File '{file_path}' not found"
    if not target.is_file():
        return f"Error: '{file_path}' is not a file"

    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(1 for l in lines if l.strip().startswith(("#", "//", "/*", "*", "\"\"\"")))
    code = total - blank - comment

    ext = target.suffix
    lang = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".html": "HTML", ".css": "CSS", ".md": "Markdown",
        ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
        ".txt": "Text", ".bat": "Batch", ".ps1": "PowerShell",
    }.get(ext, "Unknown")

    return (
        f"File: {file_path}\n"
        f"Language: {lang}\n"
        f"Size: {_format_size(target.stat().st_size)}\n"
        f"─────\n"
        f"Total:    {total:>5} lines\n"
        f"Code:     {code:>5} lines\n"
        f"Comment:  {comment:>5} lines\n"
        f"Blank:    {blank:>5} lines"
    )


@server.tool()
async def git_status() -> str:
    """Show current git repository status (modified, staged, untracked files)."""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=WORKDIR, capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            return "Not a git repository or git not available"

        output = r.stdout.strip()
        if not output:
            return "Working tree clean — no changes detected."

        lines = output.splitlines()
        staged = []
        modified = []
        untracked = []
        for line in lines:
            status = line[:2]
            path = line[3:]
            if status[0] != " " and status[0] != "?":
                staged.append(path)
            if status[1] != " ":
                modified.append(path)
            if status == "??":
                untracked.append(path)

        result = ["Git Status:"]
        if staged:
            result.append(f"\n  Staged ({len(staged)}):")
            for f in staged[:20]:
                result.append(f"    ● {f}")
        if modified:
            result.append(f"\n  Modified ({len(modified)}):")
            for f in modified[:20]:
                result.append(f"    ✏️  {f}")
        if untracked:
            result.append(f"\n  Untracked ({len(untracked)}):")
            for f in untracked[:20]:
                result.append(f"    ? {f}")
        if len(lines) > 60:
            result.append(f"\n  ... and {len(lines) - 60} more changes")

        return "\n".join(result)

    except subprocess.TimeoutExpired:
        return "Error: git status timed out"
    except FileNotFoundError:
        return "Error: git not found on this system"


@server.tool()
async def git_log(count: int = 10) -> str:
    """Show recent git commit history.

    Args:
        count: Number of recent commits to show (default: 10, max: 50)
    """
    count = min(max(count, 1), 50)
    try:
        r = subprocess.run(
            ["git", "log", f"--max-count={count}", "--pretty=format:%h|%ai|%s"],
            cwd=WORKDIR, capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            return "Not a git repository or git not available"
        if not r.stdout.strip():
            return "No commits found."

        result = [f"Recent {count} commits:"]
        for entry in r.stdout.strip().splitlines():
            parts = entry.split("|", 2)
            if len(parts) == 3:
                hash_short, date_str, message = parts
                try:
                    dt = datetime.fromisoformat(date_str)
                    date = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    date = date_str[:10]
                result.append(f"  {hash_short}  {date}  {message[:80]}")

        return "\n".join(result)

    except subprocess.TimeoutExpired:
        return "Error: git log timed out"
    except FileNotFoundError:
        return "Error: git not found on this system"


@server.tool()
async def analyze_project() -> str:
    """Analyze the entire project: file counts, line counts, language breakdown."""
    total_files = 0
    total_lines = 0
    by_ext = {}

    for fpath in WORKDIR.rglob("*"):
        if fpath.is_file() and fpath.suffix:
            # Skip hidden/__pycache__
            if any(p.startswith(".") or p == "__pycache__" for p in fpath.relative_to(WORKDIR).parts):
                continue
            total_files += 1
            try:
                lines = len(fpath.read_text(encoding="utf-8", errors="replace").splitlines())
                total_lines += lines
                ext = fpath.suffix.lower()
                by_ext[ext] = by_ext.get(ext, {"files": 0, "lines": 0})
                by_ext[ext]["files"] += 1
                by_ext[ext]["lines"] += lines
            except Exception:
                continue

    result = [
        f"📁  Project: {WORKDIR.name}",
        f"📄  Total files: {total_files}",
        f"📝  Total lines: {total_lines:,}",
        "",
        "By extension:"
    ]

    for ext in sorted(by_ext, key=lambda e: by_ext[e]["lines"], reverse=True):
        info = by_ext[ext]
        pct = info["lines"] / total_lines * 100 if total_lines else 0
        result.append(f"  {ext:>6}: {info['files']:>4} files, {info['lines']:>7,} lines ({pct:.1f}%)")

    return "\n".join(result)


@server.tool()
async def read_config_value(key: str) -> str:
    """Read a value from the project config file (agents/config.py).

    Args:
        key: Variable name to look up (e.g. DEFAULT_MODEL, DEEPSEEK_API_KEY)
    """
    config_path = WORKDIR / "agents" / "config.py"
    if not config_path.exists():
        return "Error: agents/config.py not found"

    text = config_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(key + " =") or stripped.startswith(key + "="):
            # Return the value, masking sensitive info
            value = stripped.split("=", 1)[1].strip()
            if "API_KEY" in key or "SECRET" in key or "TOKEN" in key:
                if len(value) > 8:
                    value = value[:4] + "****" + value[-4:]
            return f"{key} = {value}"

    return f"Error: Key '{key}' not found in config.py"


@server.tool()
async def get_current_time() -> str:
    """Get the current date and time."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


# =============================================================================
# RESOURCES (read-only data)
# =============================================================================

@server.resource("project://structure")
async def project_structure() -> str:
    """The top-level project directory listing."""
    entries = sorted(WORKDIR.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    entries = [e for e in entries if not e.name.startswith(".")]
    lines = [f"{WORKDIR.name}/"]
    for e in entries:
        marker = "/" if e.is_dir() else ""
        lines.append(f"  {'📁' if e.is_dir() else '📄'} {e.name}{marker}")
    return "\n".join(lines)


@server.resource("config://settings")
async def config_settings() -> str:
    """Current agent configuration settings (API model, keys masked)."""
    return read_config_value.__wrapped__.__code__  # Placeholder - return from config

# Actually implement config properly
@server.resource("config://models")
async def config_models() -> str:
    """Information about available models from config."""
    config_path = WORKDIR / "agents" / "config.py"
    if not config_path.exists():
        return "Config file not found"

    text = config_path.read_text(encoding="utf-8")
    result = ["Model Configuration:"]
    for line in text.splitlines():
        stripped = line.strip()
        if "MODEL" in stripped and "=" in stripped and not stripped.startswith("#"):
            key, val = stripped.split("=", 1)
            result.append(f"  {key.strip()} = {val.strip()}")
    return "\n".join(result)


# =============================================================================
# HELPERS
# =============================================================================

def _format_size(size: int) -> str:
    """Format file size in human-readable form."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} TB"


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print(f"Coding Tools MCP Server — {WORKDIR}")
    print("Starting in stdio mode...")
    server.run(transport="stdio")
