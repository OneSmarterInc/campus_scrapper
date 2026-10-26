# Prompt discovery validation

## 2026-10-26 — discovery relevance and resume correction

The next supplied evidence report preserved sensible Pune/engineering queries,
but showed zero pages and a `planning` report status after the screenshot had
already shown five pages. Provider usage had increased to nine requests. Code
inspection confirmed that discovery rebuilt its queue/report on every retry,
while failed fetches were not cached. The screenshot also showed unrelated
dictionary pages being fetched. The old export lacked returned search metadata,
so it cannot establish which upstream engine produced those results or why.

The fix saves the discovery queue, pending page/chunk, context and report together
in SQLite, and commits each completed step before honoring a pause. Search metadata
and skipped-source reasons are exported. Known dictionary hosts are excluded before
fetch, result ranking uses query relevance without a college/city/TLD allowlist,
and queries can relax exact-phrase/TLD syntax without weakening final eligibility.
Permanent fetch failures are reused; transient errors have bounded cache backoff.

- **190 Python tests passed**, including a new-process SQLite reopen during a
  discovery quota wait that then completes actual local HTTP crawling, person
  filtering and Excel export. No completed search, page fetch or planning call
  repeats in that test; page counts never reset.
- Other interruption tests cover multi-chunk pages, completed blocked pages,
  pending searches, refinement, incomplete engines, and pause immediately after
  a successful operation. A controlled SERP using the exact three supplied Pune
  queries skips dictionary URLs and returns two observed campus candidates with
  both institution-type and location evidence.
- **8 DOM tests passed**; compilation and Git whitespace checks passed. The one
  Starlette test-client deprecation warning remains. External proxy variables
  were unset for the local HTTP tests, as in the earlier test run.

No live provider credentials are available here. The controlled SERP/campus
fixtures establish workflow behavior, not real-college recall, inference quality,
or a measured speed/token improvement. Existing quota budgets are unchanged.
Update and restart the Windows portal, then start a new run with the same prompt;
the new report will expose returned sources and engine availability if needed.

## 2026-10-26 — planning failure correction

The reported run stopped before search when a model-supplied `prompt_quote` did
not occur literally in the prompt. Its original evidence export omitted the
rejected plan and error, so the exact offending quotation cannot be recovered
from that report. Replaying the old code with the user's Pune prompt and a
case-only quotation change reproduced the same error with zero searches.

The correction restores original quote spans for case/whitespace differences,
allows one bounded model repair for other mismatches, and retains the independent
semantic audit and all search/page/person evidence checks. Planner instructions
separate counts/output instructions and built-in policy from user eligibility
criteria. Rejected proposals and grounding errors are now saved, and evidence
exports include the actual job state and error. The UI no longer says it is
interpreting a failed or waiting request.

- **173 Python tests passed**, including repaired prompt → real local HTTP crawl
  → person filtering → Excel; a quota interruption during repair resumes using
  the saved initial response. Invalid plans never search or enable final export.
- **8 DOM integration tests passed**. A Chromium visual check with controlled API
  responses also verified the failed-run message, enabled new-run control,
  disabled final export and absence of JavaScript errors.
- Regression cases cover both reported prompts, Hinglish negation, whitespace
  and case, paraphrased/combined/invented quotations, semantic-audit rejection,
  and genuinely missing context. Compilation, JS syntax and whitespace checks
  passed. Local HTTP tests ran with this environment's external proxy variables
  unset; the one Starlette test-client deprecation warning remains.

No live Groq/Gemini credentials are available here. These controlled tests do not
establish live-college accuracy or recall. Restart the updated portal, hard-refresh
the page and rerun the Pune prompt on the configured Windows installation.

## 2026-10-25 — original integration

### Automated results

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

### What the integration tests establish

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

### What had not been validated at original integration

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


## Search response quality repair (2026-10-26)

Run 073d72c45b correctly interpreted the Mumbai request, but every returned
result came from Bing while Google, DuckDuckGo and Brave were unavailable.
Replay of its five recorded query responses rejects all 47 unrelated result
entries before crawling. No live model call is needed for this triage.

Search now screens metadata for minimal query overlap, requests strict safe
search, and tries one alternative-engine request if every result is unrelated.
Failure to recover is an explicit search configuration/availability failure,
not an empty success or an indefinite model-quota wait. Evidence retains rejected
results and recovery diagnostics. This is a heuristic, not a guarantee of
location, official ownership, faculty coverage or semantic correctness; those
still require page verification. Sparse metadata and short queries remain eligible.

Live end-to-end validation remains blocked here: no configured Groq/Gemini key
and no reachable SearXNG instance. The recorded-response replay and mocked
recovery tests do not establish that the user's unavailable engines are restored.


## Query-local recovery and navigation audit (2026-10-26)

The follow-up screenshot exposed a regression in the quality gate: one unusable
query terminated the entire job. SearchQualityError now denotes a query-local
failure. Discovery records it, continues the other planned queries and adds
bounded relaxed/institution-based queries within the existing search budget.
Real configuration errors (e.g. JSON access refused) still stop with evidence.
An all-unrelated run produces no candidates, rather than inventing URLs or
repeatedly charging the model for bad pages.

A second regression test covers 30 About links before a faculty link: staff
navigation now survives the 20-link model budget. URL safety checks remain active.

Validation: 199 Python tests and 8 DOM tests passed. Controlled recovery tests
cover five distinct college pages, exhausted bad searches, configuration errors,
and navigation crowding. Live fetches of SPIT, TSEC and VJTI were attempted but
DNS resolution failed in this execution environment. No live Groq/SearXNG
end-to-end success or production accuracy is claimed.


## Engine isolation, model repair and results UI (2026-10-26)

Run 5a92c45a06 exposed category/engine union behavior in SearXNG: an explicit
alternative engine selection combined with categories=general re-added Bing.
Confirmed against upstream searx/webadapter.py parse_generic. Recovery now omits
categories and rejects Bing-only provenance. Generated settings can be upgraded
to include Startpage, Yahoo and Qwant, preserving the secret and an ignored backup.

Completed but invalid structured model responses get one bounded repair attempt.
The counter survives quota waits/restarts, raw failed responses are not stored,
and local schema length/list limits are stated in model instructions. Optional
refinement failure retains verified source results rather than failing the whole
job. Required evidence and semantic checks remain enforced.

UI now states failure/no-output explicitly, distinguishes evidence logs from
result files, exposes source-only/contact mode, displays requested-count
shortfalls, and hides extraction stages for URL-only runs. Headless Chromium
verified ready and failed states with controlled API fixtures and no JS errors.

Validation includes the full Python suite, DOM tests, controlled actual crawler
and Excel integration, engine-isolation/provenance regressions, malformed-model
repair and resume bounds, and settings migration/secret preservation. These are
not live-provider accuracy measurements. This environment has no configured
Groq/Gemini credentials or reachable SearXNG, and direct college-domain DNS probes
failed. Full live completion remains unverified; do not label this release a
proven production accuracy result or an exhaustive security audit.
