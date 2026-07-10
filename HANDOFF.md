# Handoff: WebEngage Dashboard — Phase 2 (Navigation + Visual Design System)

**Date:** 2026-07-10
**Repo:** `c:\Users\54led\vs_projects\WE_campaigns_report_dashboard`
**Branch:** `webengage-marketing-analytics-dashboard`
**This session was run in an IDE-integrated Claude Code session; you are picking this up in a terminal Claude Code session.**

This file is self-contained — everything needed to resume is here. Read it fully before touching code.

---

## 1. What's done, what's next

| Phase | Status |
|---|---|
| Phase 1 — Data trust foundation (Section 1: accuracy, Section 2: unified ag-Grid tables) | **Section 2 DONE. Section 1 only 1c done (1a/1b not wired up — see below).** |
| Phase 2 — Navigation reorg + visual design system (Section 3 + 4) | **NOT STARTED — this is your task** |
| Phase 3 — Export system (Section 5) | Not started |
| Phase 4 — AI router (Section 6) | Not started |

Full spec: `docs/superpowers/specs/2026-07-10-production-ready-enhancements-design.md` (just updated with accurate STATUS blocks for Sections 1 & 2 — read those before starting, they correct some inaccuracies in the original draft).

Full Phase 2 task-by-task plan (12 tasks, already written, ready to execute): `docs/superpowers/plans/2026-07-10-phase2-navigation-visual-design.md`

**Your job: execute that plan.** It's already fully specified with exact code snippets per task. Don't re-derive the design — follow the plan, adapting only where the current codebase has drifted from what the plan assumed (see section 3 below for known drift).

---

## 2. What Phase 1 actually built (context you need before touching nav/pages)

### The table component: `components/table.py`

Every page's tables now go through `render_table()`, backed by `streamlit-aggrid` (already installed, v1.2.1.post2 — do NOT reinstall or change version). Real signature:

```python
def render_table(
    df, key=None, column_config=None,
    comparison_df=None, compare_on=None,
    height=400, use_container_width=True, hide_index=True,
    column_order=None, total_row=None,
) -> None
```

- `column_config={"Revenue (SAR)": st.column_config.NumberColumn(format="compact")}` → sortable `125.23K`-style cells. `format="compact"` is a real, native Streamlit 1.56 `NumberColumn` option (verified against the installed library source — not a workaround).
- `comparison_df` + `compare_on="Channel"` (or whatever the key column is) → pass a **raw, unformatted** prior-period DataFrame with matching columns. The component internally builds hidden `f"{col}__comp"` shadow columns and a JS `valueFormatter`/`cellStyle` that renders `"125.23K ▲12.0%"` (green/red/teal "NEW") in one cell, sorting on the real current value.
- `total_row={col: value, ...}` → pinned, highlighted bottom row via ag-Grid's `pinnedBottomRowData`. Include `f"{col}__total_comp"` keys for the pinned row's own delta. **Never** `pd.concat()` a manual total row into the DataFrame — that was a real bug found and fixed in 6 places this session; it sorts the "Total" row into the middle of the table.
- Theme auto-syncs to Streamlit's dark/light mode via ag-Grid's `theme='streamlit'` default — no manual dark-mode CSS was needed for tables. This matters for Phase 2 Task 7 (theme toggle): when you flip `st.session_state["theme"]`, ag-Grid tables should already follow along for free. **Verify this still holds after you build the toggle** — don't assume, check with Playwright (see section 4).

All ~15 pages are migrated off raw `st.dataframe()` / hand-built `to_html()` HTML tables onto this component. If you find one that isn't, that's drift — fix it opportunistically but don't scope-creep into a full audit unless something's visibly broken.

### Known pre-existing bug, NOT in scope for Phase 2

`pages/05_journeys.py` throws `KeyError: 'Column not found: Delivered Rate'` in the smoke-test harness. Confirmed via `git stash` that this reproduces even without any table-migration changes applied — it predates all this session's work. Leave it alone unless the user asks you to fix it specifically.

### Section 1 (Data Accuracy) is NOT fully done — don't assume otherwise

`dashboard/verification.py` has `create_audit_trail()`, `get_audit_tooltip()`, `validate_metric()`, `DERIVED_METRICS` — but **zero pages actually call these functions**. A previous handoff doc overclaimed this as done; it isn't. This is out of scope for Phase 2 but flagging so you don't build Phase 2 assuming audit tooltips exist anywhere.

---

## 3. Known drift from the Phase 2 plan doc — read before executing

The plan at `docs/superpowers/plans/2026-07-10-phase2-navigation-visual-design.md` was written before this session's table work. A few things to double check as you go, since the plan's line numbers/context snippets may have shifted:

1. **Task 2 (merge Failed Reasons into Channels as a tab)** — `pages/07_channels.py` was substantially rewritten this session (ag-Grid migration). Re-read the current file fresh before inserting the `st.tabs()` wrapper — do not trust the plan's "existing content starts with `st.header("Channel Analysis")`" as a literal line number, but the header text itself is still accurate as of this handoff.
2. **Task 9 (Plotly template dark mode)** — check `utils.py`'s current `configure_plotly_template()` signature before overwriting; it may have picked up unrelated changes.
3. **Task 8 (`render_kpi_card()`)** — the plan's code sample has a typo bug already called out inline in the plan itself (`st.markdowm` → `st.markdown`) — the plan document already corrects this in its own text, just make sure you use the corrected version, not the first buggy snippet shown.
4. Run `git status --short` and `git diff --stat` first thing to see exactly what's uncommitted before you start — there may still be uncommitted Phase 1 cleanup sitting in the working tree that hasn't been committed. Check with the user before committing anything that isn't yours if you're unsure it's intentional.

---

## 4. How to verify your work — use Playwright for real visual checks

Playwright is installed in this environment (`pip show playwright` confirms `playwright-1.61.0`, Chromium browser downloaded to `~/.cache/ms-playwright` equivalent on Windows). **Use it to actually see what you built, not just to check "no Python exception."** This was essential this session — several bugs (column truncation, wrong table rendering, theme mismatches) were only caught by literally screenshotting the running app, not by smoke tests or pytest.

### 4a. Running the app with a real CSV, no manual upload

`app.py` has a test-only fallback already wired in (search for `DASHBOARD_TEST_CSV` in `app.py`) — set this env var to a real WebEngage CSV path and the app loads it automatically on start, skipping the manual file-upload UI:

```bash
# PowerShell
$env:DASHBOARD_TEST_CSV = "D:\WORK\ME\report-1782276044546_u984psb_Mestores _ Production Dashboard_311c5018.csv"
python -m streamlit run app.py --server.headless true --server.port 8510
```

```bash
# Git Bash / POSIX
DASHBOARD_TEST_CSV="D:/WORK/ME/report-1782276044546_u984psb_Mestores _ Production Dashboard_311c5018.csv" python -m streamlit run app.py --server.headless true --server.port 8510
```

This file is ~8MB, 31,604 rows, date range 2025-12-31 to 2026-06-24. Real production data — use it for all visual verification instead of the tiny synthetic smoke-test fixture (which only has 2 rows and can't catch layout/theme issues).

**This env var only activates when no file is uploaded through the UI — it's inert in normal production use. Do not remove it without asking the user first**, it's a deliberate test affordance, not leftover debug code.

### 4b. Screenshotting with Playwright — the pattern that worked all session

Write a small throwaway Python script (not part of the app, just a scratch file), run it with plain `python`, not pytest:

```python
# save to a scratch path, e.g. C:\Users\54led\AppData\Local\Temp\claude\...\scratchpad\shot.py
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()  # headless by default — no visible window, screenshots only
    page = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")  # or "light"
    page.goto("http://localhost:8510", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(5000)  # Streamlit + ag-Grid need real time to render client-side JS

    # Navigate the sidebar like a real user:
    page.get_by_role("link", name="Channels").click()  # NOT get_by_text — sidebar nav items appear
                                                          # twice in the DOM (link + hidden duplicate),
                                                          # get_by_text throws "strict mode violation"
    page.wait_for_timeout(4000)

    page.screenshot(path=r"C:\Users\54led\AppData\Local\Temp\my_check.png", full_page=True)
    browser.close()
```

Run it, then use the Read tool on the resulting PNG to actually view it — that's how every visual bug this session was actually confirmed fixed, not just "probably fine."

**Gotchas encountered this session, worth knowing up front:**
- `color_scheme="dark"` on `new_page()` is how you force dark mode in the headless browser — the app itself doesn't control this, Streamlit follows the OS/browser preference. Without setting this explicitly, Playwright defaults to light, which can make you think something's "not themed" when it's actually fine.
- Streamlit's sidebar nav links appear twice in the DOM (visible `<p>` + an accessibility duplicate) — always use `page.get_by_role("link", name="...")`, never `get_by_text(..., exact=True)`, or you'll get a strict-mode violation error.
- The BaseWeb date-range calendar widget in the sidebar (`st.date_input`) is finicky to drive via Playwright — clicking month/year dropdown labels directly (`page.get_by_text("March", exact=True).click()`) worked; clicking arrow buttons by `aria-label` did not (labels didn't match `"Next month"` as expected, caused multiple timeouts this session). If you need to script a date range change, prefer the dropdown-label approach, or just ask the user to set it manually and screenshot after.
- After any Python file edit, Streamlit auto-reloads a running dev server — you don't need to restart it, just wait ~2-3s and re-screenshot. If you do need a clean restart (e.g. changed `.streamlit/config.toml`, which is NOT hot-reloaded), kill and relaunch:
  ```bash
  pkill -f "streamlit run" 2>/dev/null; taskkill //F //IM streamlit.exe 2>/dev/null
  ```
- Always screenshot AFTER a `.streamlit/config.toml` change with a full server restart — theme config is read once at startup, not on every rerun.

### 4c. What to actually check visually for this Phase 2 work

- **Task 4 (nav restructure):** screenshot the sidebar — confirm 4 collapsible section headers appear with the right pages grouped underneath, confirm Executive Overview loads by default when you hit `http://localhost:PORT/` with no path.
- **Task 6/7 (theme toggle + config.toml):** screenshot both dark and light mode (toggle it, or force via `color_scheme` in a fresh Playwright context after restarting the server so config.toml is picked up) — confirm sidebar, main background, and specifically **the ag-Grid tables** all switch consistently. This is the one place Phase 1's table work and Phase 2's theme work intersect — don't skip it.
- **Task 8 (KPI cards):** screenshot Executive Overview page, confirm cards render with icon/value/delta/progress bar as designed, in both themes.
- **Task 11 (CSS injection):** screenshot to confirm Inter font is actually applied (check computed font in a `page.evaluate()` call if you want to be rigorous, or just eyeball the rendering — Inter has a distinctive look vs the Streamlit default).
- **Task 1/2 (tab merges):** screenshot Time Series page and Channels page, confirm both tabs render and both have working content (click into the second tab, screenshot again).

---

## 5. Verification checklist (non-visual) — run before considering any task done

```bash
# Syntax check every file you touch
python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read()); print('ok')"

# Full test suite — must stay green, currently 32 passed
python -m pytest tests/ -q

# Smoke test any page file you modify (executes the page with fake seeded data,
# catches NameError/ImportError that ast.parse cannot)
python .superpowers/sdd/smoke-test-snippet.py pages/07_channels.py
# Expect last line: PAGE RAN OK
# ("missing ScriptRunContext" warnings are expected noise, ignore them)
```

The smoke-test fixture at `.superpowers/sdd/smoke-test-snippet.py` seeds `comparison_result=None` — it will NOT exercise any comparison-mode code path. That's a known, accepted gap from Phase 1 — rely on the real-CSV Playwright screenshots (section 4) for anything comparison-mode or visual, and on the smoke test only for "does this page still import and run at all."

---

## 6. Don't do this

- Don't touch `components/table.py` unless you find a genuine bug — it's fresh, tested, working code from this session.
- Don't reintroduce ag-Grid `format` combos that don't exist — there's no native "compact + custom currency + delta" single format string in Streamlit's `NumberColumn`; this was verified via context7 + the installed library source this session. If a new page needs that combo, follow the `comparison_df`/`total_row` pattern already built, don't invent a new one.
- Don't remove the `DASHBOARD_TEST_CSV` env var fallback in `app.py` — it's a deliberate, safe (env-gated, inert by default) test affordance.
- Don't assume Section 1a/1b (audit trail tooltips) exist anywhere — they don't, despite the module being present.
- Per this project's standing convention (see `.claude`/memory notes): **always verify library/API claims via context7 (fallback: web search) before implementing**, especially anything touching Streamlit APIs, ag-Grid, or Plotly — don't rely on training-data assumptions about what a given `st.*` function supports. This caught real, load-bearing facts this session (e.g. `NumberColumn(format="compact")` being genuinely native, vs. assuming it wasn't and reaching for a workaround).

---

## 7. Suggested first message to yourself in the terminal session

> "Resume the WebEngage dashboard project. Read `HANDOFF.md` at the repo root — it's self-contained. Phase 1 (data trust + unified ag-Grid tables) is done except Section 1a/1b (audit trail — not wired up anywhere, out of scope for now). Start Phase 2: execute `docs/superpowers/plans/2026-07-10-phase2-navigation-visual-design.md` task-by-task, using Playwright screenshots (pattern described in HANDOFF.md section 4) to visually verify navigation, theme toggle, and KPI cards — don't just check for Python exceptions. Use `DASHBOARD_TEST_CSV` env var with a real CSV for visual checks, not the tiny smoke-test fixture."
