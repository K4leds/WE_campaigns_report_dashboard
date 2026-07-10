"""
Migration consistency test: verify no page files use format_metric.apply()
on DataFrame columns feeding st.dataframe().

The anti-pattern:
    df['col'] = df['col'].apply(format_metric)
    st.dataframe(df)

converts numeric values to display strings (e.g. "1.2K"), which prevents
sorting, filtering, and Plotly chart rendering.

After migration, all DataFrame display should use either:
  - render_table(df, ...)  — unified wrapper with st.column_config.NumberColumn
  - st.dataframe(df, column_config={...})  — direct use with column_config
  - Styler.format(formatters)  — for style_total_row() paths

format_metric() is still OK for:
  - st.metric() calls (label/value display)
  - HTML string formatting (e.g., .to_html())
  - f-string interpolation
"""

import ast
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PAGES_DIR = PROJECT_ROOT / "pages"

# Known exceptions: files that legitimately use format_metric.apply()
# Keyed by filename, reason why it's allowed
ALLOWED_APPLY_CALLS = {
    "07_channels.py": {
        "reason": "HTML-copy path: format_metric feeds .to_html() string rendering",
        "allowed_lines": [],  # any line in this file is OK
    },
}

# Files that should have render_table import
FILES_EXPECTING_RENDER_TABLE = {
    "02_overview.py",
    "03_marketing_actions.py",
    "04_campaigns.py",
    "05_journeys.py",
    "06_segments.py",
    "07_channels.py",
    "08_time_series.py",
    "09_correlations.py",
    "10_ab_testing.py",
    "11_attribution.py",
    "12_failed_reasons.py",
    "14_comparisons.py",
    "15_ai_insights.py",
}


def _get_page_files():
    """Return sorted list of Python page files."""
    if not PAGES_DIR.exists():
        return []
    return sorted(PAGES_DIR.glob("*.py"))


def _read_file(path: Path) -> str:
    """Read file content as string."""
    return path.read_text(encoding="utf-8")


def _find_apply_format_metric_calls(source: str, filename: str) -> list[tuple[int, str]]:
    """
    Find lines containing .apply(format_metric) — the anti-pattern
    that converts numeric columns to display strings and breaks sorting.

    This does NOT flag apply(lambda ...) calls that don't reference
    format_metric (e.g., emoji prefixes, percentage formatting for
    non-DataFrame paths).
    """
    violations = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Only flag .apply(format_metric) — the actual anti-pattern
        if ".apply(format_metric)" in stripped:
            violations.append((i, stripped))
        # Also check .apply(lambda ... format_metric
        if ".apply(lambda" in stripped and "format_metric" in stripped:
            violations.append((i, stripped))
    return violations


def _has_render_table_import(source: str) -> bool:
    """Check if file imports render_table."""
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "render_table":
                        return True
                    if alias.name == "table" or (isinstance(node, ast.ImportFrom) and node.module and "table" in node.module):
                        # Check if render_table is imported from components.table
                        if isinstance(node, ast.ImportFrom) and node.module == "components.table":
                            for alias2 in node.names:
                                if alias2.name == "render_table":
                                    return True
            # Also check wildcard: from components.table import render_table
            if isinstance(node, ast.ImportFrom):
                if node.module == "components.table":
                    for alias in node.names:
                        if alias.name == "render_table":
                            return True
    except SyntaxError:
        # Fall back to string search
        return "render_table" in source
    return False


def _count_st_dataframe_calls(source: str) -> int:
    """Count st.dataframe() calls (rough estimate via string search)."""
    return source.count("st.dataframe(")


def _count_st_dot_metric_calls(source: str) -> int:
    """Count st.metric() calls (format_metric is fine here)."""
    return source.count("st.metric(")


def _count_render_table_calls(source: str) -> int:
    """Count render_table() calls."""
    return source.count("render_table(")


# ---- Tests ----


def test_all_page_files_exist():
    """Sanity check: the pages directory has files."""
    files = _get_page_files()
    assert len(files) > 0, f"No page files found in {PAGES_DIR}"
    print(f"Found {len(files)} page files to check")


def test_no_format_metric_apply_on_dataframes():
    """
    No page file should call .apply(format_metric) on a DataFrame column.
    format_metric() returns display strings (e.g. "1.2K") that break sorting
    and Plotly chart rendering.
    """
    violations = []
    for fpath in _get_page_files():
        source = _read_file(fpath)
        file_violations = _find_apply_format_metric_calls(source, fpath.name)

        for lineno, line in file_violations:
            # Check if this file is globally allowed
            if fpath.name in ALLOWED_APPLY_CALLS:
                continue  # Entire file exempted (e.g. 07_channels.py HTML path)
            violations.append((fpath.name, lineno, line))

    if violations:
        msg_parts = ["format_metric.apply() calls found (removes numeric sortability):"]
        for filename, lineno, line in violations:
            msg_parts.append(f"  {filename}:{lineno}: {line}")
        assert False, "\n".join(msg_parts)


def test_render_table_import_present():
    """
    Page files that display DataFrames should import render_table
    from components.table.
    """
    missing = []
    has_st_dataframe = []
    for fpath in _get_page_files():
        source = _read_file(fpath)
        name = fpath.name

        # Files without any st.dataframe() don't need render_table
        if _count_st_dataframe_calls(source) == 0 and _count_render_table_calls(source) == 0:
            continue

        if name == "01_automated_insights.py" or name == "13_export.py":
            continue  # No table rendering

        # Accept either render_table() OR st.dataframe(column_config=...) as valid
        has_column_config = "column_config" in source
        has_render_table = _has_render_table_import(source) or _count_render_table_calls(source) > 0

        if not has_render_table and not has_column_config:
            missing.append(name)

    if missing:
        # This is still information worth surfacing
        assert False, (
            f"Files use st.dataframe() without render_table() or column_config:\n"
            + "\n".join(f"  {f}" for f in missing)
            + "\n\nConsider migrating to render_table() or adding column_config for sort-safe numeric display."
        )


def test_st_dataframe_has_column_config():
    """
    All st.dataframe() calls should include explicit column_config
    to ensure numeric sorting works.
    This is a heuristic: scans for st.dataframe( with column_config= nearby.
    """
    suspicious = []
    for fpath in _get_page_files():
        source = _read_file(fpath)
        name = fpath.name
        if name in ("01_automated_insights.py", "13_export.py"):
            continue

        # Count st.dataframe calls that also mention column_config
        total_df = _count_st_dataframe_calls(source)
        if total_df > 0 and "column_config" not in source:
            suspicious.append((name, total_df))

    if suspicious:
        msg = "\n".join(
            f"  {name}: {count} st.dataframe() call(s) without column_config"
            for name, count in suspicious
        )
        # Warn but don't fail — some st.dataframe calls may have different purposes
        import warnings
        warnings.warn(
            f"st.dataframe() calls missing column_config might break sortability:\n{msg}"
        )


def test_format_metric_not_on_dataframe_columns():
    """
    More thorough check: scan for any assignment pattern like
        df['col'] = df['col'].apply(format_metric, ...)
    or
        df['col'] = df['col'].apply(lambda x: format_metric(x, ...))
    """
    apply_patterns = []
    for fpath in _get_page_files():
        source = _read_file(fpath)
        name = fpath.name

        for i, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            # Check for df['col'].apply( patterns
            if ".apply(" in stripped:
                # Check if the apply target is format_metric
                if "format_metric" in stripped:
                    # Only flag if this isn't in an exempted file
                    if name not in ALLOWED_APPLY_CALLS:
                        apply_patterns.append((name, i, stripped))

    if apply_patterns:
        msg = "\n".join(
            f"  {name}:{lineno}: {line}"
            for name, lineno, line in apply_patterns
        )
        assert False, (
            f"Found {len(apply_patterns)} .apply(format_metric) call(s) "
            f"feeding DataFrame columns:\n{msg}"
        )


def test_render_table_usage_consistent():
    """
    Verify that render_table call sites use proper patterns:
    - No pre-formatted string columns passed to render_table
    - Key parameter is provided (for Streamlit component identity)
    """
    issues = []
    for fpath in _get_page_files():
        source = _read_file(fpath)
        name = fpath.name

        render_calls = _count_render_table_calls(source)
        if render_calls == 0:
            continue

        # Check that render_table calls include a key (Streamlit best practice)
        for i, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("render_table("):
                if "key=" not in stripped and "key =" not in stripped:
                    # Multi-line call — skip (might have key on next line)
                    # Only flag single-line render_table calls without key
                    if stripped.endswith(")"):
                        issues.append((name, i, "render_table() call missing 'key' parameter"))

    if issues:
        msg = "\n".join(
            f"  {name}:{lineno}: {desc}"
            for name, lineno, desc in issues
        )
        # Warning-level: not a blocker
        import warnings
        warnings.warn(
            f"render_table() calls missing 'key' parameter:\n{msg}"
        )


def test_known_exception_still_valid():
    """
    07_channels.py should still have format_metric in its HTML path.
    This confirms the exception is still needed and hasn't been accidentally removed.
    """
    fpath = PAGES_DIR / "07_channels.py"
    if not fpath.exists():
        return  # Skip if file not present

    source = _read_file(fpath)
    # Must still use format_metric somewhere (for HTML rendering)
    assert "format_metric" in source, (
        "07_channels.py no longer uses format_metric — update ALLOWED_APPLY_CALLS "
        "if the exception is no longer needed"
    )


def test_no_hidden_anti_pattern():
    """
    Check for related anti-patterns:
    - Importing format_metric and using it in a list comprehension on a DataFrame column
    - Using Styler.format() without calling render_table or providing column_config
    """
    issues = []
    for fpath in _get_page_files():
        source = _read_file(fpath)
        name = fpath.name

        # Check: [format_metric(x) for x in df['col']]
        for i, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "format_metric(x" in stripped or "format_metric(x," in stripped:
                if "for x in" in stripped:
                    if name not in ALLOWED_APPLY_CALLS:
                        issues.append((name, i, stripped))

    if issues:
        msg = "\n".join(
            f"  {name}:{lineno}: {line}"
            for name, lineno, line in issues
        )
        assert False, (
            f"format_metric() used in list comprehension over DataFrame column:\n{msg}"
        )


if __name__ == "__main__":
    """Run tests manually."""
    test_all_page_files_exist()
    print("✓ test_all_page_files_exist")

    test_no_format_metric_apply_on_dataframes()
    print("✓ test_no_format_metric_apply_on_dataframes")

    test_render_table_import_present()
    print("✓ test_render_table_import_present")

    test_st_dataframe_has_column_config()
    print("✓ test_st_dataframe_has_column_config")

    test_format_metric_not_on_dataframe_columns()
    print("✓ test_format_metric_not_on_dataframe_columns")

    test_render_table_usage_consistent()
    print("✓ test_render_table_usage_consistent")

    test_known_exception_still_valid()
    print("✓ test_known_exception_still_valid")

    test_no_hidden_anti_pattern()
    print("✓ test_no_hidden_anti_pattern")

    print("\nAll tests passed!")
