#!/usr/bin/env python3
"""
WDE Autopatcher Engine — Semantic Code Injection

Instead of line-number-based .patch files, this engine:
1. Finds target functions/patterns by signature (regex anchors)
2. Injects antidetect code at the correct position
3. Works across Chromium versions as long as function signatures exist

Each "rule" defines:
  - target file path
  - anchor: regex to find the insertion point
  - position: "before_line", "after_line", "replace_line",
              "start_of_function", "before_return", "after_includes"
  - code: the C++ code to inject
  - includes: additional #include lines needed

Usage:
    python3 autopatcher/engine.py /path/to/chromium/src [--dry-run] [--verbose]
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Injection:
    """A single code injection rule."""
    id: str                       # Unique ID like "canvas-noise-toDataURL"
    description: str              # Human-readable description
    file: str                     # Relative path from chromium/src
    anchor: str                   # Regex to find the insertion point
    position: str                 # Where to inject relative to anchor
    code: str                     # Code to inject
    includes: list = field(default_factory=list)  # Extra #includes
    anchor_context: str = ""      # Secondary regex near anchor for disambiguation
    guard: str = ""               # If non-empty, skip if this string already exists in file
    priority: int = 0             # Lower = applied first


@dataclass
class PatchResult:
    injection_id: str
    file: str
    status: str  # "applied", "skipped_exists", "anchor_not_found", "file_not_found", "error"
    line: Optional[int] = None
    message: str = ""


class AutoPatcher:
    def __init__(self, chromium_src: str, dry_run: bool = False, verbose: bool = False):
        self.src = chromium_src
        self.dry_run = dry_run
        self.verbose = verbose
        self.results: list[PatchResult] = []
        # Cache of file contents {filepath: list_of_lines}
        self._file_cache: dict[str, list[str]] = {}
        # Track modified files
        self._modified: set[str] = set()

    def _read_file(self, relpath: str) -> Optional[list[str]]:
        """Read file into cache, return lines or None if not found."""
        fullpath = os.path.join(self.src, relpath)
        if relpath in self._file_cache:
            return self._file_cache[relpath]
        try:
            with open(fullpath, "r", errors="replace") as f:
                lines = f.readlines()
            self._file_cache[relpath] = lines
            return lines
        except FileNotFoundError:
            return None

    def _write_file(self, relpath: str):
        """Write cached file content back to disk."""
        if self.dry_run:
            return
        fullpath = os.path.join(self.src, relpath)
        lines = self._file_cache.get(relpath)
        if lines is None:
            return
        with open(fullpath, "w") as f:
            f.writelines(lines)

    def _find_anchor(self, lines: list[str], anchor: str, context: str = "") -> Optional[int]:
        """Find line index matching anchor regex. Returns 0-based index."""
        candidates = []
        for i, line in enumerate(lines):
            if re.search(anchor, line):
                candidates.append(i)

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0]

        # Multiple matches — use context to disambiguate
        if context:
            for idx in candidates:
                # Search within ±30 lines for context
                window = "".join(lines[max(0, idx-30):idx+30])
                if re.search(context, window):
                    return idx

        # Return first match as fallback
        return candidates[0]

    def _find_function_end(self, lines: list[str], start: int) -> Optional[int]:
        """Find the closing brace of a function starting near `start`."""
        depth = 0
        in_function = False
        for i in range(start, min(start + 500, len(lines))):
            for ch in lines[i]:
                if ch == '{':
                    depth += 1
                    in_function = True
                elif ch == '}':
                    depth -= 1
                    if in_function and depth == 0:
                        return i
        return None

    def _find_last_return(self, lines: list[str], start: int, end: int) -> Optional[int]:
        """Find the last 'return' statement between start and end."""
        last_return = None
        for i in range(start, end):
            if re.search(r'^\s*return\b', lines[i]):
                last_return = i
        return last_return

    def _find_last_include(self, lines: list[str]) -> int:
        """Find the last #include line in the file."""
        last = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("#include"):
                last = i
        return last

    def _insert_lines(self, relpath: str, at: int, new_lines: list[str]):
        """Insert lines at position in cached file."""
        lines = self._file_cache[relpath]
        for i, new_line in enumerate(new_lines):
            lines.insert(at + i, new_line if new_line.endswith("\n") else new_line + "\n")
        self._modified.add(relpath)

    def apply(self, injection: Injection) -> PatchResult:
        """Apply a single injection rule."""
        lines = self._read_file(injection.file)

        if lines is None:
            result = PatchResult(
                injection.id, injection.file, "file_not_found",
                message=f"File not found: {injection.file}"
            )
            self.results.append(result)
            return result

        # Check guard — skip if already applied
        if injection.guard:
            full_text = "".join(lines)
            if injection.guard in full_text:
                result = PatchResult(
                    injection.id, injection.file, "skipped_exists",
                    message=f"Guard string found, already applied"
                )
                self.results.append(result)
                return result

        # Find anchor
        anchor_line = self._find_anchor(lines, injection.anchor, injection.anchor_context)
        if anchor_line is None:
            result = PatchResult(
                injection.id, injection.file, "anchor_not_found",
                message=f"Anchor not found: {injection.anchor}"
            )
            self.results.append(result)
            return result

        # Determine insertion point
        insert_at = None
        code_lines = [l + "\n" for l in injection.code.split("\n")]

        if injection.position == "before_line":
            insert_at = anchor_line

        elif injection.position == "after_line":
            insert_at = anchor_line + 1

        elif injection.position == "start_of_function":
            # Find the opening brace after the anchor, insert after it
            for i in range(anchor_line, min(anchor_line + 10, len(lines))):
                if '{' in lines[i]:
                    insert_at = i + 1
                    break

        elif injection.position == "before_return":
            # Find the function end, then find the last return before it
            func_end = self._find_function_end(lines, anchor_line)
            if func_end:
                last_ret = self._find_last_return(lines, anchor_line, func_end)
                if last_ret:
                    insert_at = last_ret
                else:
                    insert_at = func_end  # Before closing brace

        elif injection.position == "after_includes":
            insert_at = self._find_last_include(lines) + 1

        elif injection.position == "replace_line":
            # Replace the anchor line with new code
            self._file_cache[injection.file][anchor_line] = injection.code + "\n"
            self._modified.add(injection.file)
            result = PatchResult(
                injection.id, injection.file, "applied",
                line=anchor_line + 1,
                message=f"Replaced line {anchor_line + 1}"
            )
            self.results.append(result)
            return result

        if insert_at is None:
            result = PatchResult(
                injection.id, injection.file, "error",
                message=f"Could not determine insertion point for position={injection.position}"
            )
            self.results.append(result)
            return result

        # Add includes first (at top of file)
        if injection.includes:
            last_inc = self._find_last_include(lines)
            inc_lines = []
            full_text = "".join(lines)
            for inc in injection.includes:
                if inc not in full_text:
                    inc_lines.append(inc + "\n")
            if inc_lines:
                self._insert_lines(injection.file, last_inc + 1, inc_lines)
                # Adjust insert_at for the lines we just added
                if insert_at > last_inc:
                    insert_at += len(inc_lines)

        # Insert the code
        self._insert_lines(injection.file, insert_at, code_lines)

        result = PatchResult(
            injection.id, injection.file, "applied",
            line=insert_at + 1,
            message=f"Injected at line {insert_at + 1}"
        )
        self.results.append(result)

        if self.verbose:
            print(f"    Injected {len(code_lines)} lines at {injection.file}:{insert_at + 1}")

        return result

    def flush(self):
        """Write all modified files to disk."""
        for relpath in self._modified:
            self._write_file(relpath)
        count = len(self._modified)
        self._modified.clear()
        return count

    def create_new_file(self, relpath: str, content: str):
        """Create a new file in the source tree."""
        fullpath = os.path.join(self.src, relpath)
        os.makedirs(os.path.dirname(fullpath), exist_ok=True)
        if not self.dry_run:
            with open(fullpath, "w") as f:
                f.write(content)
        if self.verbose:
            print(f"    Created {relpath}")

    def report(self) -> str:
        """Generate summary report."""
        lines = ["\n" + "=" * 60, "AUTOPATCHER REPORT", "=" * 60]
        applied = [r for r in self.results if r.status == "applied"]
        skipped = [r for r in self.results if r.status == "skipped_exists"]
        failed = [r for r in self.results if r.status not in ("applied", "skipped_exists")]

        lines.append(f"\nApplied:  {len(applied)}")
        lines.append(f"Skipped:  {len(skipped)} (already applied)")
        lines.append(f"Failed:   {len(failed)}")

        if failed:
            lines.append("\nFAILED INJECTIONS:")
            for r in failed:
                lines.append(f"  [{r.status}] {r.injection_id}")
                lines.append(f"    File: {r.file}")
                lines.append(f"    {r.message}")

        if applied:
            lines.append("\nAPPLIED INJECTIONS:")
            for r in applied:
                lines.append(f"  {r.injection_id} → {r.file}:{r.line}")

        return "\n".join(lines)
