#!/usr/bin/env python3
"""
WDE Autopatcher — Main Entry Point

Usage:
    python3 autopatcher/apply.py /path/to/chromium/src [--dry-run] [--verbose]

This replaces `git apply patches/*.patch` with a version-agnostic approach
that finds insertion points by function signatures, not line numbers.
"""

import argparse
import os
import sys

# Allow importing from same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import AutoPatcher
from rules import RULES, ANTIDETECT_UTILS_H, ANTIDETECT_BUILD_GN


def main():
    parser = argparse.ArgumentParser(description="WDE Autopatcher")
    parser.add_argument("chromium_src", help="Path to chromium/src directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't write files, just show what would happen")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed output")
    parser.add_argument("--only", type=str, default="",
                        help="Only apply rules matching this prefix (e.g. 'canvas', 'webgl')")
    args = parser.parse_args()

    chromium_src = os.path.abspath(args.chromium_src)

    if not os.path.isfile(os.path.join(chromium_src, "BUILD.gn")):
        print(f"Error: {chromium_src}/BUILD.gn not found.")
        print("Is this a Chromium source directory?")
        sys.exit(1)

    patcher = AutoPatcher(chromium_src, dry_run=args.dry_run, verbose=args.verbose)

    # Step 1: Create antidetect_utils.h (the shared header)
    utils_path = "third_party/blink/renderer/core/antidetect/antidetect_utils.h"
    build_path = "third_party/blink/renderer/core/antidetect/BUILD.gn"

    print("[1/3] Creating antidetect shared module...")
    patcher.create_new_file(utils_path, ANTIDETECT_UTILS_H)
    patcher.create_new_file(build_path, ANTIDETECT_BUILD_GN)

    # Step 2: Apply all injection rules
    print("[2/3] Applying injection rules...")
    rules = RULES
    if args.only:
        rules = [r for r in RULES if args.only.lower() in r.id.lower()]
        print(f"  Filtered to {len(rules)} rules matching '{args.only}'")

    # Sort by priority
    rules.sort(key=lambda r: r.priority)

    for rule in rules:
        prefix = "  "
        result = patcher.apply(rule)
        status_icon = {
            "applied": "OK",
            "skipped_exists": "SKIP",
            "anchor_not_found": "MISS",
            "file_not_found": "NOFILE",
            "error": "ERR",
        }.get(result.status, "???")
        print(f"{prefix}[{status_icon:>6}] {rule.id}: {result.message}")

    # Step 3: Write all changes
    print("[3/3] Writing changes to disk...")
    count = patcher.flush()
    print(f"  Modified {count} files")

    # Report
    print(patcher.report())

    # Exit code: 0 if all applied or skipped, 1 if any failed
    failed = [r for r in patcher.results
              if r.status not in ("applied", "skipped_exists")]
    if failed:
        print(f"\n{len(failed)} rules failed. Manual intervention may be needed.")
        sys.exit(1)
    else:
        print("\nAll rules applied successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
