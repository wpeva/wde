#!/usr/bin/env python3
"""Tests for the autopatcher engine."""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import AutoPatcher, Injection


def make_src(tmpdir, files: dict):
    """Create a fake chromium/src with given files."""
    src = os.path.join(tmpdir, "src")
    os.makedirs(src, exist_ok=True)
    # create BUILD.gn marker
    with open(os.path.join(src, "BUILD.gn"), "w") as f:
        f.write("# root\n")
    for relpath, content in files.items():
        fullpath = os.path.join(src, relpath)
        os.makedirs(os.path.dirname(fullpath), exist_ok=True)
        with open(fullpath, "w") as f:
            f.write(content)
    return src


def read_file(src, relpath):
    with open(os.path.join(src, relpath)) as f:
        return f.read()


def test_start_of_function():
    """Test injecting at start of function body."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {
            "foo.cc": (
                '#include "foo.h"\n'
                '\n'
                'String Foo::bar() const {\n'
                '  return "hello";\n'
                '}\n'
            )
        })
        patcher = AutoPatcher(src)
        rule = Injection(
            id="test-1", description="test",
            file="foo.cc",
            anchor=r'String Foo::bar\(\) const',
            position="start_of_function",
            guard="// INJECTED",
            code='  // INJECTED\n  if (true) return "world";',
        )
        result = patcher.apply(rule)
        patcher.flush()
        assert result.status == "applied", f"Expected applied, got {result.status}: {result.message}"
        content = read_file(src, "foo.cc")
        assert "// INJECTED" in content
        assert content.index("// INJECTED") < content.index('return "hello"')
        print("  PASS: start_of_function")
    finally:
        shutil.rmtree(tmpdir)


def test_before_return():
    """Test injecting before the last return."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {
            "foo.cc": (
                '#include "foo.h"\n'
                '\n'
                'String Foo::getData() {\n'
                '  if (empty) return "";\n'
                '  auto data = compute();\n'
                '  return data;\n'
                '}\n'
            )
        })
        patcher = AutoPatcher(src)
        rule = Injection(
            id="test-2", description="test",
            file="foo.cc",
            anchor=r'String Foo::getData\(\)',
            position="before_return",
            guard="// NOISE",
            code='  // NOISE\n  addNoise(data);',
        )
        result = patcher.apply(rule)
        patcher.flush()
        assert result.status == "applied", f"Expected applied, got {result.status}: {result.message}"
        content = read_file(src, "foo.cc")
        assert "// NOISE" in content
        # Should be before "return data;" but after 'return "";'
        lines = content.split("\n")
        noise_line = next(i for i, l in enumerate(lines) if "// NOISE" in l)
        last_return = max(i for i, l in enumerate(lines) if "return data;" in l)
        assert noise_line < last_return, "Noise should be before last return"
        print("  PASS: before_return")
    finally:
        shutil.rmtree(tmpdir)


def test_replace_line():
    """Test replacing a specific line."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {
            "foo.js": "var KEY = 'cdc_abc123';\nvar other = 1;\n"
        })
        patcher = AutoPatcher(src)
        rule = Injection(
            id="test-3", description="test",
            file="foo.js",
            anchor=r"var KEY\s*=\s*'cdc_",
            position="replace_line",
            guard="replaced_key",
            code="var KEY = 'replaced_key';",
        )
        result = patcher.apply(rule)
        patcher.flush()
        assert result.status == "applied"
        content = read_file(src, "foo.js")
        assert "replaced_key" in content
        assert "cdc_" not in content
        print("  PASS: replace_line")
    finally:
        shutil.rmtree(tmpdir)


def test_guard_prevents_double_apply():
    """Test that guard string prevents re-application."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {
            "foo.cc": (
                '#include "foo.h"\n'
                '// ALREADY_APPLIED\n'
                'void Foo::bar() {\n'
                '}\n'
            )
        })
        patcher = AutoPatcher(src)
        rule = Injection(
            id="test-4", description="test",
            file="foo.cc",
            anchor=r'void Foo::bar\(\)',
            position="start_of_function",
            guard="ALREADY_APPLIED",
            code='  // This should not appear',
        )
        result = patcher.apply(rule)
        assert result.status == "skipped_exists"
        print("  PASS: guard_prevents_double_apply")
    finally:
        shutil.rmtree(tmpdir)


def test_includes_added_and_deduplicated():
    """Test that includes are added and not duplicated."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {
            "foo.cc": (
                '#include "foo.h"\n'
                '#include "bar.h"\n'
                '\n'
                'void Foo::a() {\n'
                '  return;\n'
                '}\n'
                '\n'
                'void Foo::b() {\n'
                '  return;\n'
                '}\n'
            )
        })
        patcher = AutoPatcher(src)

        rule1 = Injection(
            id="test-5a", description="test",
            file="foo.cc",
            anchor=r'void Foo::a\(\)',
            position="start_of_function",
            guard="// RULE_A",
            includes=['#include "new.h"'],
            code='  // RULE_A',
        )
        rule2 = Injection(
            id="test-5b", description="test",
            file="foo.cc",
            anchor=r'void Foo::b\(\)',
            position="start_of_function",
            guard="// RULE_B",
            includes=['#include "new.h"', '#include "another.h"'],
            code='  // RULE_B',
        )

        r1 = patcher.apply(rule1)
        r2 = patcher.apply(rule2)
        patcher.flush()

        assert r1.status == "applied", f"Rule A: {r1.status}: {r1.message}"
        assert r2.status == "applied", f"Rule B: {r2.status}: {r2.message}"

        content = read_file(src, "foo.cc")
        # new.h should appear exactly once (dedup)
        inc_count = content.count('#include "new.h"')
        assert inc_count == 1, f"new.h appeared {inc_count} times"
        # another.h should appear once
        assert content.count('#include "another.h"') == 1
        # Both rules should be injected
        assert "// RULE_A" in content
        assert "// RULE_B" in content
        print("  PASS: includes_added_and_deduplicated")
    finally:
        shutil.rmtree(tmpdir)


def test_multi_rule_same_file():
    """Test multiple rules targeting different functions in same file."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {
            "nav.cc": (
                '#include "nav.h"\n'
                '\n'
                'String Nav::userAgent() const {\n'
                '  return ua_;\n'
                '}\n'
                '\n'
                'String Nav::platform() const {\n'
                '  return platform_;\n'
                '}\n'
            )
        })
        patcher = AutoPatcher(src)

        r1 = patcher.apply(Injection(
            id="ua", description="test",
            file="nav.cc",
            anchor=r'String Nav::userAgent\(\) const',
            position="start_of_function",
            guard="// UA_OVERRIDE",
            code='  // UA_OVERRIDE\n  if (spoofed) return "spoofed";',
        ))
        r2 = patcher.apply(Injection(
            id="platform", description="test",
            file="nav.cc",
            anchor=r'String Nav::platform\(\) const',
            position="start_of_function",
            guard="// PLAT_OVERRIDE",
            code='  // PLAT_OVERRIDE\n  if (spoofed) return "Linux";',
        ))
        patcher.flush()

        assert r1.status == "applied", f"UA: {r1.message}"
        assert r2.status == "applied", f"Platform: {r2.message}"

        content = read_file(src, "nav.cc")
        assert "// UA_OVERRIDE" in content
        assert "// PLAT_OVERRIDE" in content
        # UA override should be inside userAgent, not platform
        ua_pos = content.index("// UA_OVERRIDE")
        plat_pos = content.index("// PLAT_OVERRIDE")
        ua_func_pos = content.index("userAgent")
        plat_func_pos = content.index("platform")
        assert ua_pos > ua_func_pos and ua_pos < plat_func_pos, \
            "UA override in wrong function"
        assert plat_pos > plat_func_pos, "Platform override in wrong function"
        print("  PASS: multi_rule_same_file")
    finally:
        shutil.rmtree(tmpdir)


def test_file_not_found():
    """Test handling of missing file."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {})
        patcher = AutoPatcher(src)
        result = patcher.apply(Injection(
            id="missing", description="test",
            file="nonexistent.cc",
            anchor=r'void foo\(\)',
            position="start_of_function",
            code='// test',
        ))
        assert result.status == "file_not_found"
        print("  PASS: file_not_found")
    finally:
        shutil.rmtree(tmpdir)


def test_anchor_not_found():
    """Test handling of missing anchor."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {
            "foo.cc": '#include "foo.h"\nvoid bar() {}\n'
        })
        patcher = AutoPatcher(src)
        result = patcher.apply(Injection(
            id="miss", description="test",
            file="foo.cc",
            anchor=r'void nonexistent\(\)',
            position="start_of_function",
            code='// test',
        ))
        assert result.status == "anchor_not_found"
        print("  PASS: anchor_not_found")
    finally:
        shutil.rmtree(tmpdir)


def test_no_extra_blank_lines():
    """Test that code injection doesn't add extra blank lines."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {
            "foo.cc": (
                '#include "foo.h"\n'
                '\n'
                'void Foo::bar() {\n'
                '  doSomething();\n'
                '}\n'
            )
        })
        patcher = AutoPatcher(src)
        rule = Injection(
            id="test-blank", description="test",
            file="foo.cc",
            anchor=r'void Foo::bar\(\)',
            position="start_of_function",
            guard="// INJECTED",
            # Note: leading and trailing newlines in the triple-quoted string
            code="""
  // INJECTED
  if (true) return;
""",
        )
        result = patcher.apply(rule)
        patcher.flush()
        assert result.status == "applied"
        content = read_file(src, "foo.cc")
        lines = content.split("\n")
        # Find the injected code
        injected_idx = next(i for i, l in enumerate(lines) if "// INJECTED" in l)
        # The line before should be the opening brace, not a blank line
        assert lines[injected_idx - 1].strip() != "", \
            f"Unexpected blank line before injection: '{lines[injected_idx - 1]}'"
        print("  PASS: no_extra_blank_lines")
    finally:
        shutil.rmtree(tmpdir)


def test_create_new_file():
    """Test creating a new file."""
    tmpdir = tempfile.mkdtemp()
    try:
        src = make_src(tmpdir, {})
        patcher = AutoPatcher(src)
        patcher.create_new_file("new/dir/file.h", "// new file content\n")
        assert os.path.exists(os.path.join(src, "new/dir/file.h"))
        content = read_file(src, "new/dir/file.h")
        assert content == "// new file content\n"
        print("  PASS: create_new_file")
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    print("Running autopatcher engine tests...\n")
    tests = [
        test_start_of_function,
        test_before_return,
        test_replace_line,
        test_guard_prevents_double_apply,
        test_includes_added_and_deduplicated,
        test_multi_rule_same_file,
        test_file_not_found,
        test_anchor_not_found,
        test_no_extra_blank_lines,
        test_create_new_file,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
