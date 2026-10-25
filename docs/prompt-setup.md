# Prompt discovery: setup and operation

This feature belongs to `OneSmarterInc/campus_scrapper`. SWARM is a separate repository.
The stable pre-feature checkpoint is branch `before-prompting`, commit
`34e3bb43973160e04a489012394090bd6a5bfcf7`.

## What happens after you enter a prompt

1. Groq interprets the original wording and checks that the plan preserves its requirements and exclusions.
2. Your SearXNG service searches for real pages. The model chooses only URLs returned by search or links actually found on retrieved pages.
3. Official faculty/office pages need supporting page quotations. Institution evidence can come from multiple pages on the same origin, with a check that they describe the same campus.
4. The existing CampusScraper crawler extracts published contacts. It keeps the existing student exclusion rules and never creates email addresses from name patterns.
5. Research, department, role and other person/page conditions are checked on the extracted records. Only matching records reach the final Excel and the portal directory.

Simple location-based requests do not need a model call for every faculty member.
When individual filtering is needed, small groups of records share one request.
The model does not generate the exported names, phone numbers or email addresses.
Ambiguous requests receive a clarification field. Requests for individual students
or other industries are unsupported. Staff-run placement and higher-studies offices are supported.

## Windows PowerShell setup

Run these commands from your existing campus scraper folder. Keep the application
on localhost; it is a local tool, not an authenticated public web service.

```powershell
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Put your Groq key after `GROQ_API_KEY=`. Optionally put a Gemini free-project key
after `GEMINI_API_KEY=`. Leave the Gemini value blank if you prefer waiting for
Groq capacity. Never send keys in chat or commit `.env`; it is ignored by Git.
Restart the server after changing environment settings.

Use accounts/projects that remain on the providers' free tiers. This program
does not upgrade accounts or use paid search tools. **It cannot detect your billing
tier or prevent provider charges if you supply a key for a paid account.** Its
local request/token budgets control usage; they are not a billing guarantee.

### Start SearXNG

You need a working Docker installation (Linux containers). Docker Engine on Linux
or WSL can host it; an existing SearXNG service also works. The portal itself runs
in your Python environment, outside Docker. No GPU or local language model is required.

```powershell
.\.venv\Scripts\python.exe tools\setup_search.py
docker compose -f compose.search.yml up -d
.\.venv\Scripts\python.exe tools\check_prompt_setup.py --live-model
```

The setup script generates a random search-service secret and preserves existing
settings on subsequent runs. The container listens on `127.0.0.1:8080`. JSON search
is enabled. Google, Bing, DuckDuckGo and Brave engines are configured; availability
depends on their current behavior. A blocked engine does not discard usable
results from the others. No results with engine failures causes a saved wait.

`--live-model` makes one small structured-output request to each configured
provider. Without that flag, the checker tests search and provider access only.
The checker never prints keys or provider response bodies. It does not prove
real-world faculty coverage or perfect prompt interpretation.

If search fails:

```powershell
docker compose -f compose.search.yml logs --tail 80
```

An existing search service can be selected through `SEARXNG_URL` in `.env`.
Use the service root, not its `/search` endpoint. It must allow `format=json`.
The included container uses the official image's `latest` tag. For a managed
installation, pin `SEARXNG_IMAGE` to the digest you have validated; test upgrades
before changing that digest.

### Open the portal

```powershell
.\.venv\Scripts\python.exe -m campusscraper serve --port 8001
```

Open <http://127.0.0.1:8001/#new>. Use **Find colleges and contacts from a prompt**.
For example: `Find 10 engineering colleges in Mumbai and their faculty contacts.
Exclude Navi Mumbai.` The default maximum is 10 colleges; increase it if your
prompt explicitly asks for more. Existing Excel uploads and one-site crawls remain available.

The UI separates interpretation, source discovery, extraction, record matching,
and file writing. A college crawl ending does not mark the overall run finished.
Coverage notes explain shortages, blocked pages and limits. No invented percentage
or completion time is shown while the total work is unknown.

## Quotas, pause and recovery

- Groq is attempted first; Gemini is used if configured and Groq cannot answer.
- The same schema and evidence checks apply to both providers. A fallback does
  not guarantee identical semantic judgment; live acceptance tests are still needed.
- Successful searches, retrieved pages, model decisions and extracted data are
  saved in SQLite. Completed colleges also keep the crawler's existing resume caches.
- When both providers are unavailable, the portal saves the job, shows the reason
  and next attempt, and retries while the server remains open. It does not switch
  to a paid service, rotate API keys, or export unfiltered contacts.
- Pause/Stop finish the current network operation. A paused/interrupted college
  may be crawled again on resume; completed colleges are reused. Discovery/model
  steps already saved are replayed without new requests.
- After a server restart, interrupted work requires **Resume saved run**. Jobs
  already waiting for quota can retry automatically. Use **Runs → Open** to view
  an older prompt job. Start a new job to change its prompt or budgets.
- Local budgets are conservative rolling windows shared by runs in this
  installation. Other apps using the same provider account can still exhaust the
  account's quota. Failed requests retain their token reservation when no usage
  figure is returned. The UI's usage counters are not an invoice.

Run one portal process per results directory. Do not run the CLI against the
same results database while the portal is running. This lightweight local
architecture uses one discovery worker and up to two college crawler workers;
it does not require Redis, Celery, a GPU or a separate database server.

Stop the app before backing up the **whole `results` folder**, including
`campusscraper.db`, `prompt-discovery.db`, any SQLite WAL/SHM files and per-college
caches. It contains prompts, retrieved evidence and working extraction data.
Deleting a prompt run from Runs removes its discovery journal and job files.

## Downloads and filtering

The final contacts workbook uses the existing Faculty, All people, Student offices,
Evidence, Pages, Colleges and Summary sheets. Both people sheets contain only
records that passed the prompt filters. Shared office contacts remain distinct
from personal contacts. Unknown contacts stay empty.

**Download source URLs** uses the standard college-upload columns. When a prompt
requires person/page filtering, these rows are marked `Enabled=no` with an
explanation: uploading them as an ordinary batch would otherwise lose the filters.
Use the prompt run's contacts workbook for the filtered output.

The evidence JSON records the interpretation, page decisions, supporting quotes,
record decisions and provider usage. Literal evidence checks prevent invented
quotes, but do not prove an LLM's semantic judgment or official-site ownership.
For explicit people counts, matching records are selected in college/name order;
they are not ranked by quality. Per-college counts are treated separately from
total people counts, and shortages are reported.

## Command line alternative

```powershell
.\.venv\Scripts\python.exe -m campusscraper discover "Find 10 engineering colleges in Mumbai and faculty contacts"
.\.venv\Scripts\python.exe -m campusscraper discover "Faculty pages for COEP and PICT" --sources-only
.\.venv\Scripts\python.exe -m campusscraper discover --resume YOUR_RUN_ID
```

The CLI exits with code 75 when it must wait for a service/quota. Resume using the
printed ID, or open the portal for automatic quota retries. Other incomplete or
clarification outcomes return code 2. Finished/partial exports return code 0.

## Validation and practical limits

See [the implementation validation record](prompt-validation.md) for the exact
checks run and the live checks that still require a configured installation.

Run the Python tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests_campus -q
```

The automated suite includes provider contracts, fallback and quota interruptions,
process-restart checkpoints, exact quotation checks, plan auditing, per-person
filters, private DNS/redirect rejection, the standard template adapter and the
full search → HTTP crawl → filtered Excel/history flow using a fictional college.
Semantic-service answers in these integration tests are controlled fixtures;
these are not claims that a live model achieves a measured recall score.

Optional browser-free DOM checks require Node.js and `jsdom@26.1.0` in your
development environment; they are not production dependencies:

```powershell
npm install --prefix "$env:TEMP\campus-ui-tests" jsdom@26.1.0 --no-save --ignore-scripts
$env:NODE_PATH = "$env:TEMP\campus-ui-tests\node_modules"
node --test tests_campus/prompt_ui.test.cjs
```

Before accepting the live feature, run the setup checker and compare real prompt
results with the manual-upload baseline for the same colleges. Check missing
institutions, matching faculty, email/phone attribution, exclusions, student
exclusion, quota recovery, elapsed time and peak memory. Include English, Hinglish,
named colleges, unspecified locations, research topics and ambiguous requests.
The deploy-time live checks require your configured keys and SearXNG service.

Search coverage, robots policies, inaccessible websites, outdated pages, scanned
PDFs and unpublished contacts still limit recall. Discovery evaluates bounded
text windows and navigation links; extraction reads the full fetched pages within
the existing crawl budget. Any model reasoning can be wrong. Finishing a run does
not prove it found every person. There is no unlimited free cloud quota promise.

Automatic discovery additionally checks public DNS destinations and HTTP redirect
targets. Browser subrequests also reject non-public destinations. This does not
turn the local unauthenticated portal into a hardened multi-tenant service; keep
it bound to localhost and leave `CAMPUSSCRAPER_ALLOW_PRIVATE` unset outside tests.

Primary implementation references:

- <https://console.groq.com/docs/structured-outputs>
- <https://console.groq.com/docs/rate-limits>
- <https://ai.google.dev/api/generate-content>
- <https://ai.google.dev/gemini-api/docs/pricing>
- <https://docs.searxng.org/dev/search_api.html>
- <https://docs.searxng.org/admin/settings/settings.html>

## Return to the pre-prompt version

Stop the server, back up `results`, then inspect the checkpoint on a new branch:

```powershell
git fetch origin
git switch -c inspect-before-prompting origin/before-prompting
```

This preserves later commits. Do not use a hard reset to inspect the checkpoint.
