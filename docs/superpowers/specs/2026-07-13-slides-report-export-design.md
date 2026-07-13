# Design: WebEngage Client Review Deck (PowerPoint Export)

**Date:** 2026-07-13
**Status:** Approved design, pending spec review
**Branch:** enhanced_ui

## 1. Goal

Add a one-click export on the Export tab that generates a **client-facing PowerPoint
deck** reviewing WebEngage performance for the currently-filtered data. The deck must
look like an analyst hand-made it — branded, visual, with insights, recommendations
that map findings to real WebEngage features, and a final action plan. A validated
visual sample has been approved (`scratchpad/sample_slide.pptx`).

## 2. Core principle (inherited from `llm_narrative.py`)

**Python owns every number and chart; the LLM only phrases.** No figure, table, or
chart is ever produced by the model. DeepSeek receives pre-computed fact sheets and
writes prose, insight callouts, recommendations, and WebEngage feature justifications.
This is the anti-hallucination boundary and it is non-negotiable for a client artifact.

| Layer | Owner |
|---|---|
| Numbers, tables, chart data | Python (`insights_engine`, `analysis.py`) |
| Layout, theme, fonts, transitions | `python-pptx` |
| Insight wording, recommendations, feature picks | DeepSeek (via `llm_narrative` pattern) |

## 3. Deployment constraints (Streamlit Community Cloud)

The app runs server-side on Streamlit Cloud. See memory `deployment-target-streamlit-cloud`.

1. **No COM/PowerPoint on the server.** The feature only *builds* the `.pptx` and serves
   it via `st.download_button`. It never renders. (The COM render used to preview during
   development is local-only and not part of shipped code.)
2. **kaleido 1.2.0 needs Chromium.** Plotly→PNG requires a system Chrome. Provide it via
   a `packages.txt` containing `chromium`, and verify the current correct method during
   implementation using the developing-with-streamlit skill / Context7 / Firecrawl (the
   kaleido-v1 chrome-provisioning story changes; do not hardcode from memory).
   **Fallback:** if Chromium proves unavailable/unreliable on the host, render deck charts
   with **matplotlib** (no browser dependency). Charts are rebuilt for print anyway, so
   this is an isolated swap behind one `_fig_to_png`-style seam.
3. **Fonts:** the server has no DM Sans and neither may the client. The deck **embeds
   DM Sans** so it renders identically everywhere (see §8).
4. **Latest libraries** (memory `keep-libraries-latest`): add `python-pptx` at latest
   stable; keep `kaleido`/`plotly` current; verify usage via Context7 rather than memory.

## 4. Architecture / files

- **`slides_export.py`** (new) — the deck builder. Public entry: `build_deck(filtered_df,
  client_name, period_label) -> bytes`. Internally: theme constants, layout helpers
  (`_tile`, `_styled_table`, `_insight_box`, `_recommendation_strip`, `_add_morph`),
  chart builders (`_chart_trend`, `_chart_channels`, `_chart_journey_sankey`), a
  `_fig_to_png(fig)` seam, and one `add_slide_*` function per slide type. Kept focused;
  if it grows past ~500 lines, split charts into `slides_charts.py`.
- **`slides_narrative.py`** (new, confirmed) — DeepSeek functions that return slide prose
  and recommendation text from fact sheets, plus the curated WebEngage feature map (§7).
  Kept separate from `llm_narrative.py` for organization. Reuses `llm_narrative`'s client
  helper and anti-hallucination discipline.
- **`pages/13_export.py`** (edit) — add a "Generate Client Review Deck (PowerPoint)"
  button + client-name input; on click, spinner → `build_deck(ctx.filtered_df, ...)` →
  `st.download_button`. Existing CSV/Excel buttons stay.
- **`requirements.txt`** (edit) — add `python-pptx`.
- **`packages.txt`** (new) — `chromium` (for kaleido), pending §3.2 verification.
- **`assets/fonts/`** (new) — bundled DM Sans TTFs (Regular/Medium/Bold) for embedding.
- **`tests/test_slides_export.py`** (new) — see §12.

## 5. Theme

Single constants block in `slides_export.py`:

- Slide background: white `#FFFFFF`
- Brand / titles / accents: `#006FA2`; darker depth `#005379`
- Table header fill `#4472C4`, white bold text; cells white, hairline `#E3E8EB` separators
- Body ink `#1B2A32`; muted labels `#6C7A82`; insight callout fill `#EAF3F8`
- Delta up `#1E9E62`, down `#C03A2B`
- Font: **DM Sans** (Regular / Medium / Bold), embedded
- 16:9, 13.333in × 7.5in

## 6. Slides (10) and data sources

Data always comes from the **active `filtered_df`** ("what you see is what you export").
Each data slide = visual on one side, AI-written interpretation on the other. Numbers
from Python; if DeepSeek is unavailable, fall back to `insights_engine`'s deterministic
titles/messages (§9).

| # | Slide | Visual | Data source |
|---|---|---|---|
| 1 | Title / cover | brand cover, client name, period | params |
| 2 | Executive summary | 4–6 KPI stat tiles + AI read | `generate_executive_summary()` headline_metrics + `generate_ai_summary()` |
| 3 | Performance trend | time-series line/area chart | `analysis.time_series_analysis()` |
| 4 | Channel performance | grouped bar + styled table | `analysis.channel_analysis()` |
| 5 | Top campaigns | styled table + insight callout | `analysis.top_campaigns()` + `explain_table_data()` |
| 6 | Top journeys | styled table + **journey-flow Sankey** | `analysis.get_top_journeys()`, journey funnel data |
| 7 | What's working | AI opportunities, cite real numbers | narrative_insights.opportunities |
| 8 | What's at risk | AI alerts, cite real numbers | narrative_insights.performance_alerts |
| 9 | Recommendations | findings → WebEngage feature (pill) | `generate_top_actions()` + feature map (§7) |
| 10 | Action plan | prioritized "do next" list | `generate_top_actions()` |

**Segments slide intentionally dropped** (data not useful — user decision).

**Future growth:** slide count will increase over time (user note). Keep slide construction
modular — one self-contained `add_slide_*(prs, ...)` per slide and a simple ordered list
that `build_deck` iterates — so adding a slide is appending one function, not restructuring.

### Journey-flow Sankey (slide 6)
Plotly Sankey, brand-blue progression links, grey drop-off links, green convert / red
abandon terminals. Stage values from the selected top journey's funnel (entry → delivered
→ opened → clicked → converted, with drop-offs). Rendered to PNG via `_fig_to_png`.
Fit to its content box (bug found in sample: size by height, not width, to avoid overflow).

## 7. WebEngage feature recommendations

A hardcoded curated map of **real** WebEngage features so the model cannot invent one.
Examples: Journey Designer, Send Time Optimization (STO), Preferred Channel, Frequency
Capping / Channel Fatigue, Personalization / Dynamic Content, Catalog & Recommendations,
A/B Testing, RFM / Predictive Segments, Web/Mobile Push, WhatsApp, In-app, On-site
overlays (Nudges), Relay (transactional), Funnels/Cohorts/Path analytics.

DeepSeek is given the finding + this list and must (a) pick the best-fit feature(s) from
the list only, and (b) write a one-line justification tied to the finding's numbers. The
chosen feature name renders as the pill on slides 9. If DeepSeek is unavailable, a simple
finding-type→feature lookup provides a deterministic default pill.

## 8. Font embedding

**Hard-required for v1** (user decision). `python-pptx` has no native font embedding.
Implement by post-processing the OOXML package: add DM Sans TTFs as
`/ppt/fonts/fontN.fntdata` parts, wire relationships, and add `<p:embeddedFontLst>` to
`presentation.xml`. Isolated in one `_embed_fonts(pptx_bytes)` helper with a clear seam.

**Google Slides caveat:** Google Slides discards embedded fonts on `.pptx` import and
substitutes from its own font list — but DM Sans is a native Google Fonts option in
Slides, so it renders correctly there anyway. The embed therefore matters for viewers who
open the raw `.pptx` in desktop PowerPoint (no DM Sans installed); in the Google-Slides
workflow, native DM Sans does the work. We validate the actual look after the first real
export before considering any change.

## 9. Graceful degradation

- No `DEEPSEEK_API_KEY` or any API failure → deck still builds using `insights_engine`
  deterministic titles/messages and the feature-lookup default. Never surface an AI error.
- Chart render failure (Chromium missing) → matplotlib fallback (§3.2); if that too fails,
  the slide shows the table/numbers without the chart rather than crashing the export.
- Empty/degenerate `filtered_df` → button shows a friendly "no data for current filters"
  message instead of producing a broken deck.

## 10. Morph transitions

`_add_morph(slide)` injects `<p:transition><p14:morph option="byObject"/></p:transition>`
into each slide's XML (validated in the sample). Applied to every slide.

## 11. Export tab UX

New section above the existing CSV/Excel buttons: a text input for client/brand name
(default from a config or blank), the generate button, a spinner during chart render
(2–6s), then a download button yielding `WebEngage_Review_<client>_<period>.pptx`.

## 12. Testing / verification

- `tests/test_slides_export.py`: build a deck from a small synthetic `filtered_df` with the
  DeepSeek path stubbed (monkeypatch to return None → exercises deterministic fallback).
  Assert: returns non-empty bytes, opens as a valid `Presentation`, has exactly 10 slides,
  and slide 1 contains the client name. No frameworks beyond pytest.
- Manual verification: generate against real filtered data locally, open the `.pptx`,
  confirm theme/fonts/Sankey/Morph. (Server render is not testable via COM; the `.pptx`
  build is the server behavior and is unit-tested.)

## 13. Out of scope (YAGNI)

- Google Slides / GWS export, scheduled/emailed decks, multi-language, per-slide theming
  UI, editable in-app preview, PDF export. Revisit only if asked.
