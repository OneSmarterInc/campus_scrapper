# Prompt discovery validation — 2026-10-25

## Automated results

- **156 Python tests passed**, including the existing campus crawler and discovery
  prototype regression tests. One dependency deprecation warning was reported
  by Starlette's HTTP test client; there were no test failures.
- **6 browser-free DOM tests passed** with Node.js and jsdom 26.1.0, executing the
  portal scripts with controlled API responses.
- Python compilation, JavaScript syntax checks and Git whitespace checks passed.
- The SearXNG Compose file was parsed, and setup generation/idempotence were tested.

Commands:

```text
python -m pytest tests_campus -q
node --test tests_campus/prompt_ui.test.cjs
python -m compileall -q campusscraper tools
node --check campusscraper/static/prompt.js
node --check campusscraper/static/portal.js
git diff --check
```

The DOM checks require the optional jsdom development dependency; see
[setup instructions](prompt-setup.md).

## What the integration tests establish

The integration suite starts local HTTP services for a fictional college and a
SearXNG-compatible search fixture. It uses the actual HTTP fetcher, campus crawler,
SQLite journals/history and Excel exporter. Model responses and quota failures
are scripted HTTP fixtures, so the suite checks application behavior rather than
measuring live model quality.

| Check | Observed result |
|---|---|
| Unfiltered prompt versus manual crawl of the same fixture | Identical faculty names, emails and phone numbers, and identical office contacts; at least eight faculty records checked. |
| Research-specific prompt | Matching faculty exported; unrelated faculty and students excluded. |
| Quota interruption during record filtering | Job enters a saved waiting state; resume reuses completed discovery and extraction. |
| Provider failure | Configured fallback receives the same schema; unavailable providers cause a saved wait or an explicit setup error. |
| Empty search with some failed engines | Other queries can still supply candidates; usable results are retained. |
| Process restart and user controls | Interrupted work is resumable; paused jobs stay paused. |
| Prompt fidelity | Controlled English/Hinglish, exclusions, individual criteria, counts and clarification cases preserve their intended constraints. |
| Evidence checks | Invented quotation text, missing decisions and invalid record/link IDs are rejected. |
| Portal/export boundary | Final download stays unavailable until filtering finishes; working unfiltered exports are not served by the prompt API. |
| Resource destinations | Private DNS destinations and redirects are rejected in automatic discovery. |
| UI behavior | Quota waits, partial coverage, clarification, empty input, output escaping and final-download gating pass DOM tests. |

## What has not been validated here

No live Groq or Gemini key, running SearXNG service, or Docker executable was
available in the implementation environment. Real-provider inference, current
search-engine availability, Docker startup, ten-college recall, elapsed time and
peak memory on the user's Windows machine remain unmeasured.

A visual browser check was attempted, but the available browser could not reach
the local server. Installing a local Chromium binary also failed in this
environment. DOM tests do not substitute for a visual/end-to-end browser check.

Consequently, these results do **not** establish that automatic discovery matches
or exceeds manual ChatGPT/Claude research on real institutions. They establish a
tested workflow with durable recovery, evidence checks and explicit coverage
limits. Literal quotations constrain invented evidence but do not prove that a
model correctly understood a page or identified its official owner.

## Live acceptance on a configured machine

1. Start SearXNG and run `python tools/check_prompt_setup.py --live-model`.
2. Open the portal and run a small prompt for two known colleges. Check source
   ownership, constraints, progress states, links and workbook contents.
3. Run the same ten-college benchmark through ordinary Excel upload and prompt
   discovery. Compare institutions, faculty identities, correct email/phone
   attribution, omissions and student exclusion against official pages.
4. Try a research/department filter, an exclusion, a named-college request, an
   ambiguous prompt and Hinglish wording. Check both missing and extra records.
5. Pause/resume and restart an active run. Check the saved state and repeated
   request counts. Test fallback with provider credentials controlled by the
   operator; do not deliberately exhaust a shared provider quota.
6. Record wall-clock time, peak application/browser/container memory and provider
   token counts before increasing crawl budgets or accepting the feature for
   routine use.

The original stable branch `before-prompting` remains available at
`34e3bb43973160e04a489012394090bd6a5bfcf7`. This change belongs only to the
`campus_scrapper` repository; SWARM remains separate.
