# CampusScraper

Give it a college website (home page, faculty page, department page, or one faculty profile). It crawls the same site and builds two lists with rules only, no API key and no AI model:

1. **Faculty**: name, designation, department, degrees, experience, email and phone, research areas, subjects, Google Scholar, ORCID, Scopus, ResearchGate, LinkedIn and Vidwan/IRINS links.
2. **Student offices**: the college's Training & Placement cell, Higher Studies / Study Abroad cell, student chapters and clubs (IEEE, ACM, CSI), alumni office, international office and student-affairs office, with their office emails and phones, the faculty or staff who run them, and any higher-studies figures the page publishes ("42 students admitted to universities in the USA for MS").

Student offices are how you reach students. Pages that name individual students (student coordinators, club office-bearers, "III Year CSE", roll numbers) are read, but those students' names, phones and emails are left out of every output. The **Student Lines Left Out** column counts them, so you can see when a page had more.

CampusScraper uses the same crawler engine as OncoScraper (`OneSmarterInc/oncology-swarm`, branch `onco-scraper`).

## Setup on Windows (one time)

Double-click `setup_windows.bat`, or run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Check the install (no internet needed)

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests_campus
```

Expect `15 passed`. Then try the fictional demo college. Window 1:

```powershell
.\.venv\Scripts\python.exe tests_campus\demo_site.py
```

Window 2:

```powershell
.\.venv\Scripts\python.exe -m campusscraper scrape http://127.0.0.1:8766/ --allow-local --delay 0 --out demo_college.xlsx
```

Expect 8 faculty and 4 student offices.

## Web UI

Double-click `run_ui.bat`, or:

```powershell
.\.venv\Scripts\python.exe -m campusscraper serve --port 8001
```

Open http://127.0.0.1:8001/. Port 8001 lets it run next to the OncoScraper UI on port 8000. Paste a URL, optionally type departments (`CSE, IT, ECE`), click **Start crawl**, then **Download Excel**. Use **Test one page** first to see what it reads from a single faculty or placement page.

### Portal pages

| Page | What it shows |
|---|---|
| Dashboard | Faculty, colleges, departments, contact and Scholar/ORCID coverage, student offices (placement and higher-studies cells) across all runs; a per-college table (click a college to open it in the directory, or its office count to open its offices); recent runs. |
| New run | Upload a college list (batch) or crawl one website; progress, pause/resume/stop, downloads. |
| Runs | Every past run with status, faculty and offices saved. Download its Excel, Run again (one website), Resume (a batch cut off when the app closed: finished colleges are not crawled again), Delete. |
| Faculty directory | Everyone found so far, each person once (newest copy). Search; filter by college, department, city, has own email / phone / any contact, has Scholar/ORCID/Scopus; include non-teaching staff. Export Excel or CSV of the filtered list. |
| Student offices | Placement, higher-studies, student-chapter, alumni and international offices across all runs. Filter by college, office type, has email / phone, publishes higher-studies figures. Export Excel or CSV. |

History is saved in `results\campusscraper.db` (one SQLite file). Copy that file to back it up; delete it to start fresh.

URLs you give (in the start box or the college list) are always fetched first, so a placement or higher-studies page in your list is read even when the page budget is small.

## Command line

| Goal | Command |
|---|---|
| Crawl one college | `python -m campusscraper scrape https://www.college.ac.in --out college.xlsx` |
| Only some departments in the Faculty sheet | add `--departments "CSE,IT,ECE"` |
| Faculty only, skip student-office pages | add `--no-offices` |
| One page, print what was found | `python -m campusscraper page https://www.college.ac.in/faculty/dr-name` |
| Many colleges from a list | `python -m campusscraper batch campus_sources\india_colleges_seed.xlsx --out india_colleges.xlsx` |
| Blank college-list template | `python -m campusscraper template --out my_colleges.xlsx` |

All OncoScraper options also work: `--max-pages`, `--depth`, `--delay`, `--show-browser`, `--save-html`, `--subdomains`, `--pattern`.

## Speed

| Setting | Default | What it does |
|---|---|---|
| Colleges at once (`--colleges-at-once`, batch box in the UI) | 3 | Crawls several colleges at the same time. Each college is a different website, so no site gets more requests. Rows on the same website never run together. |
| `--workers` | 3 | Fetches up to 3 pages of one site at a time. The gap between requests to that site stays `--delay`, so a slow server no longer holds up the crawl. |
| `--patience` | 80 | Stops a site after 80 pages in a row add nobody new. The Colleges sheet notes when this happened. `0` turns it off. |
| `--delay` | 1.5 s | Gap between requests to one site. `1` is faster and still polite; a site's robots.txt crawl-delay always wins. |

Measured on three fictional colleges whose server takes 1.2 s per page: a batch went from 82 s to 23 s with the same results.

## College list (batch)

One row per college. College Name and one URL are required.

| Column | What to put |
|---|---|
| College Name | e.g. `Vasavi College of Engineering` |
| Official Website | home page |
| Faculty Page URLs | faculty or "people" page(s); several allowed |
| Department URLs | department home pages |
| Student Office URLs | Training & Placement, Higher Studies cell, IEEE/ACM chapter, alumni pages |
| Sample Faculty Profile URL | one profile; the profile URL pattern is learned from it |
| Departments | keep only these in the Faculty sheet, e.g. `CSE, IT` |
| City, State, College Type, Max Pages, Include Subdomains, Use Browser, Enabled, Notes | optional |

`campus_sources/india_colleges_seed.xlsx` has 62 colleges from the NIRF higher-studies list (`indian-colleges-us-ms-feeders-all-india.csv` in the Ashish project). Their websites are the hosts of each college's own NIRF data file. The other colleges in that list had their NIRF file on nirfindia.org or Careers360, so their websites still need adding. Your existing CSV also loads directly once you add a `Website` column: the `College`, `City`, `State` and `Type` columns are recognised as they are.

Faculty and student-office URLs give much better results than the home page alone. The crawler finds them from the home page, but that spends more of the page budget.

## Output (Excel)

| Sheet | Contents |
|---|---|
| Summary | run settings, counts, field coverage |
| Colleges | batch only: pages, people, faculty, offices and contact counts per college |
| Faculty | teaching faculty (in the chosen departments, if any) |
| All people | everyone found, including non-teaching staff and office staff |
| Student offices | one row per office or body, with office contacts and coordinators |
| Evidence | each value, which rule found it, the page text and URL |
| Pages | every URL visited, status and page type |

**Alumni are left out.** People in alumni, testimonial, topper, recruiter, guest-speaker or governing-body sections are not taken, even when they hold a title like Professor or Director elsewhere. The section is recognised from its heading ("Prestigious Alumni", "What our students say") or its wrapper (`alumni-slider`, `testimonial`), and whole pages such as "Notable Alumni" are skipped. Cards that say "Alumnus", "Batch 2015" or "Software Engineer at X" are skipped too.

**Who counts as faculty.** A teaching title (Professor, Associate/Assistant Professor, Lecturer, HOD, Dean, Principal), or a postgraduate degree on a faculty page. Lab assistants, technicians, clerks and librarians go to All people only. With `--departments`, faculty of other departments also go to All people only.

**Contacts.** Only what the page publishes. Faculty Email/Phone holds the person's own address or mobile. Department / Office Email and Phone hold shared mailboxes (`hodcse@`, `tpo@`, `principal@`) and landlines. A contact that appears for two or more people, or in the site header or footer, is moved to the office columns.

**Departments** are written in one form across colleges: `CSE`, `Dept. of CSE` and `Computer Science and Engineering` all become `Computer Science and Engineering`.

## Rules it follows

- robots.txt is read and obeyed.
- Only the start site is crawled (`--subdomains` to include sub-sites).
- At least 1.5 s between requests to one site by default.
- Admissions, news, events, exams, results, circulars, NIRF/NAAC/NBA, careers and login pages are skipped.
- Individual students are never recorded.

## What it cannot read yet

- Faculty lists published only as PDF.
- Pages behind a login (ERP portals, student portals).
- Sites that block automated access even in a real browser.

## Project layout

```
campusscraper/
  vocab.py      departments, degrees, titles, labels, office types, student markers, URL hints
  profile.py    one faculty profile: labels, sections, patterns, academic links
  listing.py    faculty card grids and staff tables
  offices.py    student-facing office pages; student lines are left out
  relevance.py  who goes in the Faculty sheet; department filter
  extract.py    page classifier and layer orchestration
  crawl.py      frontier, sitemaps, faculty/office link priority, merging
  sources.py    college-list template
  batch.py      many colleges, per-site budget, resume
  export.py     Excel / CSV / JSON
  store.py      run history, faculty and office directories, dashboard (SQLite)
  web.py        local web UI and portal (static/)
  fetch.py, render.py, robots.py, dom.py, annotate.py, structured.py, emails.py, phones.py, contacts.py
                shared crawler code from OncoScraper
tests_campus/   fictional college site and 15 tests
campus_sources/ india_colleges_seed.xlsx (62 colleges), college_list_template.xlsx
```
