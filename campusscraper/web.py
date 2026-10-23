"""Local web UI: paste a college URL or upload a college list, watch the crawl, download the Excel file."""
from __future__ import annotations

import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from .config import ScrapeConfig
from .crawl import Crawler, CrawlResult
from .export import to_csv, to_json, to_xlsx
from .extract import extract_page
from .fetch import Fetcher
from .models import OfficeRecord, PersonRecord

STATIC = Path(__file__).parent / "static"
OUT_DIR = Path.cwd() / "results"
app = FastAPI(title="CampusScraper", docs_url=None, redoc_url=None)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_STORE = None


def store():
    """The local database (results/campusscraper.db next to the Excel files)."""
    global _STORE
    from .store import Store
    path = Path(os.environ.get("CAMPUSSCRAPER_DB") or OUT_DIR / "campusscraper.db")
    if _STORE is None or _STORE.path != path:
        _STORE = Store(path)
    return _STORE


def _safe(fn, *a, **k):
    """Saving history must never break a crawl."""
    try:
        return fn(*a, **k)
    except Exception as exc:  # noqa: BLE001
        print(f"[history] could not save: {exc}")


def _host(u: str) -> str:
    return (urlsplit(u if "://" in u else "https://" + u).hostname or u).removeprefix("www.")


class JobIn(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20)
    max_pages: int = Field(200, ge=1, le=5000)
    max_depth: int = Field(4, ge=0, le=10)
    delay_seconds: float = Field(1.5, ge=0, le=30)
    render: str = "auto"
    all_people: bool = False
    use_sitemaps: bool = True
    include_subdomains: bool = False
    departments: str = Field("", max_length=300)
    include_offices: bool = True
    workers: int = Field(3, ge=1, le=8)
    patience: int = Field(80, ge=0, le=5000)


class PageIn(BaseModel):
    url: str
    render: str = "auto"


class Job:
    def __init__(self, body: JobIn):
        self.id = uuid.uuid4().hex[:10]
        self.body = body
        self.state = "running"
        self.log: deque[dict] = deque(maxlen=400)
        self.progress: dict = {"fetched": 0, "doctors_total": 0, "faculty": 0, "offices": 0, "queued": 0}
        self.result: CrawlResult | None = None
        self.error: str | None = None
        self.started = time.time()
        self.stop = threading.Event()
        self.pause = threading.Event()
        self.crawler: Crawler | None = None
        self.xlsx: Path | None = None
        self.site_name = _host(body.urls[0]) if body.urls else ""

    def save_history(self, res: CrawlResult) -> None:
        store().save_people(self.id, res.doctors, self.site_name)
        store().save_offices(self.id, res.offices, self.site_name)

    def on_event(self, e: dict) -> None:
        if e["event"] == "page":
            self.progress = {k: e.get(k, 0) for k in ("fetched", "doctors_total", "faculty", "offices", "queued")}
            if e["fetched"] % 25 == 0 and self.crawler:  # keep the history up to date during long crawls
                _safe(lambda: self.save_history(self.snapshot()))
            self.log.append({"url": e["url"], "type": e["type"], "status": e["status"],
                             "doctors": e["doctors_on_page"], "error": e.get("error")})
        elif e["event"] == "sitemap":
            self.log.append({"url": f"sitemap: {e['urls']} URLs", "type": "info", "status": "", "doctors": 0})

    def run(self) -> None:
        b = self.body
        try:
            cfg = ScrapeConfig(max_pages=b.max_pages, max_depth=b.max_depth, delay_seconds=b.delay_seconds,
                               render=b.render, relevant_only=not b.all_people, use_sitemaps=b.use_sitemaps,
                               include_subdomains=b.include_subdomains, departments=_depts(b.departments),
                               include_offices=b.include_offices, workers=b.workers, patience=b.patience)
            self.crawler = Crawler(cfg, self.on_event, self.stop, self.pause)
            self.result = self.crawler.run([u.strip() for u in b.urls if u.strip()])
            OUT_DIR.mkdir(exist_ok=True)
            self.xlsx = to_xlsx(self.result, OUT_DIR / f"faculty-{time.strftime('%Y%m%d-%H%M%S')}-{self.id}.xlsx")
            self.state = "stopped" if self.stop.is_set() else "done"
            _safe(self.save_history, self.result)
        except Exception as exc:  # surface any crash to the UI
            self.error = f"{type(exc).__name__}: {exc}"
            self.state = "failed"
        _safe(store().update_run, self.id, state=self.state, finished=time.time(), error=self.error,
              stats=(self.result.stats if self.result else {}), xlsx=str(self.xlsx) if self.xlsx else None)

    def snapshot(self) -> CrawlResult:
        """What has been found so far, while the crawl is still running (copies; the crawl is not touched)."""
        from . import relevance
        from .contacts import demote_shared, demote_sitewide
        from .models import OfficeRecord, PersonRecord
        from .profile import clean_fields
        c = self.crawler
        docs = [PersonRecord.from_full_dict(d.to_full_dict()) for d in list(c.merger.records)] if c else []
        relevance.set_targets(_depts(self.body.departments))
        for d in docs:
            clean_fields(d)
            relevance.rescore(d)
        if c:
            demote_sitewide(docs, {k: set(v) for k, v in list(c.value_pages.items())})
        demote_shared(docs)
        offices = [OfficeRecord.from_full_dict(o.to_full_dict()) for o in list(c.offices)] if c else []
        res = CrawlResult([u.strip() for u in self.body.urls if u.strip()], docs, list(c.result_pages) if c else [],
                          offices=offices)
        fac = [d for d in docs if d.is_relevant]
        res.stats = {"partial": "yes - downloaded while the crawl was running", "pages_fetched": self.progress.get("fetched", 0),
                     "people_found": len(docs), "faculty": len(fac), "offices": len(offices),
                     "seconds": round(time.time() - self.started, 1)}
        return res

    def doctors(self):
        if self.result:
            docs = self.result.doctors
        elif self.crawler:
            docs = list(self.crawler.merger.records)
        else:
            docs = []
        if not self.body.all_people:
            docs = [d for d in docs if d.is_relevant]
        return docs

    def offices(self):
        if self.result:
            return self.result.offices
        return list(self.crawler.offices) if self.crawler else []


def _depts(text: str) -> list[str]:
    return [d.strip() for d in (text or "").split(",") if d.strip()]


JOBS: dict[str, Job] = {}


ROW_KEYS = ("name", "designation", "department", "qualifications", "experience_years", "institution", "city",
            "phone", "email", "contact_phone", "contact_email", "research_areas", "google_scholar", "orcid",
            "profile_url", "source_url", "is_relevant", "page_type")


def _office_rows(offices, limit: int = 1000) -> list[dict]:
    return [o.to_dict() for o in list(offices)[:limit]]


def _rows(docs, limit: int = 3000) -> list[dict]:
    out = []
    for d in docs[:limit]:
        x = d.to_dict()
        out.append({k: x.get(k) for k in ROW_KEYS} | {"fields": len(d.filled_fields()),
                                                      "source_institution": d.source_institution})
    return out


def _state(job) -> str:
    if job.state == "running" and job.stop.is_set():
        return "stopping"  # Stop was pressed; pages already in flight are finishing
    return "paused" if job.state == "running" and job.pause.is_set() else job.state


def _pause(job, paused: bool) -> dict:
    if job.state != "running":
        raise HTTPException(409, f"cannot pause or resume: the run is {job.state}")
    (job.pause.set if paused else job.pause.clear)()
    _safe(store().update_run, job.id, state=_state(job))
    return {"ok": True, "state": _state(job)}


@app.get("/static/{name}.js")
def static_js(name: str):
    if name not in ("app", "portal"):
        raise HTTPException(404, "not found")
    return Response((STATIC / f"{name}.js").read_text(encoding="utf-8"), media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.post("/api/jobs")
def start(body: JobIn):
    if body.render not in ("never", "auto", "always"):
        raise HTTPException(400, "render must be never, auto or always")
    job = Job(body)
    JOBS[job.id] = job
    _safe(store().create_run, job.id, "crawl", ", ".join(_host(u) for u in body.urls[:3]), body.model_dump())
    threading.Thread(target=job.run, daemon=True).start()
    return {"id": job.id}


@app.get("/api/jobs/{job_id}")
def status(job_id: str, since: int = 0):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    rows = _rows(job.doctors())
    return {"id": job.id, "state": _state(job), "error": job.error, "progress": job.progress,
            "max_pages": job.body.max_pages, "elapsed": round(time.time() - job.started),
            "stats": job.result.stats if job.result else None, "log": list(job.log)[-60:], "doctors": rows,
            "offices": _office_rows(job.offices())}


@app.post("/api/jobs/{job_id}/stop")
def stop(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    job.stop.set()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/pause")
def pause_job(job_id: str):
    job = JOBS.get(job_id) or _missing("job")
    return _pause(job, True)


@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str):
    job = JOBS.get(job_id) or _missing("job")
    return _pause(job, False)


def _missing(what: str):
    raise HTTPException(404, f"{what} not found")


@app.get("/api/jobs/{job_id}/download.{fmt}")
def download(job_id: str, fmt: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if fmt not in ("xlsx", "csv", "json"):
        raise HTTPException(400, "format must be xlsx, csv or json")
    partial = job.result is None
    if partial and not job.crawler:
        raise HTTPException(404, "nothing found yet")
    try:
        result = job.snapshot() if partial else job.result
    except Exception as exc:  # the crawl changed under us; a second click works
        raise HTTPException(503, f"could not copy results, try again: {exc}") from None
    tag = "-partial-" + time.strftime("%H%M%S") if partial else ""
    if fmt == "xlsx":
        if not partial and job.xlsx:
            path = job.xlsx
        else:
            OUT_DIR.mkdir(exist_ok=True)
            path = to_xlsx(result, OUT_DIR / f"faculty-{job.id}{tag}.xlsx")
        return FileResponse(path, filename=path.name,
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if fmt == "csv":
        docs = result.doctors if job.body.all_people else [d for d in result.doctors if d.is_relevant]
        return Response(to_csv(docs).encode("utf-8-sig"), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="faculty-{job.id}{tag}.csv"'})
    return Response(to_json(result, not job.body.all_people), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="faculty-{job.id}{tag}.json"'})


@app.post("/api/page")
def test_page(body: PageIn):
    cfg = ScrapeConfig(render=body.render, delay_seconds=0)
    fetcher = Fetcher(cfg)
    try:
        page = fetcher.get(body.url)
    finally:
        fetcher.close()
    pr = extract_page(page)
    return {"status": page.status, "final_url": page.final_url, "error": page.error, "rendered": page.rendered,
            "page_type": pr.page_type, "signals": {k: v for k, v in pr.signals.items() if k != "page_contacts"},
            "doctors": [{k: v for k, v in d.to_dict().items() if v not in (None, [], {}, "")} for d in pr.doctors],
            "offices": [{k: v for k, v in o.to_dict().items() if v not in (None, [], {}, "", 0)} for o in pr.offices],
            "profile_links": pr.profile_links[:50], "pagination_links": pr.pagination_links}


# ---------------------------------------------------------------------------
# Batch: upload a college list (standard template) and crawl every college.
class UploadIn(BaseModel):
    filename: str = Field(max_length=200)
    content_base64: str = Field(max_length=20_000_000)


class BatchIn(UploadIn):
    pages_per_site: int = Field(150, ge=1, le=5000)
    max_depth: int = Field(4, ge=0, le=10)
    delay_seconds: float = Field(1.5, ge=0, le=30)
    render: str = "auto"
    all_people: bool = False
    use_sitemaps: bool = True
    departments: str = Field("", max_length=300)
    include_offices: bool = True
    workers: int = Field(3, ge=1, le=8)
    patience: int = Field(80, ge=0, le=5000)
    colleges_at_once: int = Field(3, ge=1, le=8)


def _load_upload(body: UploadIn):
    import base64
    import tempfile

    from .sources import HeaderError, read_sources
    suffix = Path(body.filename).suffix.lower()
    if suffix not in (".xlsx", ".xlsm", ".csv"):
        raise HTTPException(400, "Upload an .xlsx or .csv file made from the template")
    try:
        data = base64.b64decode(body.content_base64, validate=True)
    except ValueError:
        raise HTTPException(400, "File could not be decoded") from None
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(data)
        tmp = Path(fh.name)
    try:
        return read_sources(tmp)
    except HeaderError as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception as exc:
        raise HTTPException(400, f"Could not read the file. Save it as .xlsx or .csv from the template and try again ({exc})") from None
    finally:
        tmp.unlink(missing_ok=True)


class BatchJob:
    def __init__(self, body: BatchIn, sources, run_id: str | None = None, resume: bool = False):
        self.id = run_id or uuid.uuid4().hex[:10]
        self.resume = resume
        self.body = body
        self.sources = sources
        self.state = "running"
        self.current = ""
        self.index = 0
        self.sites: list[dict] = []
        self.log: deque[dict] = deque(maxlen=300)
        self.progress: dict = {}
        self.stats: dict | None = None
        self.error: str | None = None
        self.started = time.time()
        self.stop = threading.Event()
        self.pause = threading.Event()
        self.xlsx: Path | None = None
        self.live: dict = {}

    def on_event(self, e: dict) -> None:
        if e["event"] == "site_start":
            self.index = max(self.index, e["index"])
            running = [src.institution for _, src in list((self.live.get("active") or {}).values())]
            self.current = ", ".join(dict.fromkeys(running + [e["institution"]]))
            self.log.append({"url": f"=== {e['institution']}", "type": "info", "status": "", "doctors": 0})
        elif e["event"] == "site_done":
            site = {k: v for k, v in e.items() if k != "event"}
            self.sites.append(site)
            running = [src.institution for _, src in list((self.live.get("active") or {}).values())]
            self.current = ", ".join(running)
            _safe(store().save_site, self.id, site)
            _safe(self._save_college, site["institution"])
        elif e["event"] == "page":
            self.progress = {k: e.get(k, 0) for k in ("fetched", "doctors_total", "faculty", "offices", "queued")}
            self.log.append({"url": e["url"], "type": e["type"], "status": e["status"],
                             "doctors": e["doctors_on_page"], "error": e.get("error")})

    def run(self) -> None:
        from .batch import run_batch
        b = self.body
        try:
            base = ScrapeConfig(max_depth=b.max_depth, delay_seconds=b.delay_seconds, render=b.render,
                                relevant_only=not b.all_people, use_sitemaps=b.use_sitemaps,
                                departments=_depts(b.departments), include_offices=b.include_offices,
                                workers=b.workers, patience=b.patience)
            OUT_DIR.mkdir(exist_ok=True)
            out = OUT_DIR / f"batch-{self.id}.xlsx"  # fixed name: a resumed batch continues in the same files
            self.xlsx = run_batch(self.sources, out, base, b.pages_per_site, resume=self.resume,
                                  progress=self._capture, stop_event=self.stop, live=self.live,
                                  pause_event=self.pause, parallel_sites=b.colleges_at_once)
            self.state = "stopped" if self.stop.is_set() else "done"
            if self.live.get("merger") is not None:
                _safe(store().save_people, self.id, list(self.live["merger"].records))
                _safe(store().save_offices, self.id, list(self.live.get("offices") or []))
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.state = "failed"
        _safe(store().update_run, self.id, state=self.state, finished=time.time(), error=self.error,
              stats=self.stats or {}, xlsx=str(self.xlsx) if self.xlsx else None)

    def _save_college(self, college: str) -> None:
        """This college's people and offices go into the history as soon as it finishes."""
        merger = self.live.get("merger")
        if merger is not None:
            store().save_people(self.id, [d for d in list(merger.records) if d.source_institution == college])
        store().save_offices(self.id, [o for o in list(self.live.get("offices") or []) if o.source_institution == college])

    def _capture(self, e: dict) -> None:
        if e["event"] == "batch_done":
            self.stats = {k: v for k, v in e.items() if k != "event"}
        else:
            self.on_event(e)


BATCHES: dict[str, BatchJob] = {}


@app.get("/api/template.xlsx")
def template_download():
    import tempfile

    from .sources import write_template
    tmp = Path(tempfile.gettempdir()) / "campusscraper_college_list_template.xlsx"
    write_template(tmp)
    return FileResponse(tmp, filename="college_list_template.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/sources/check")
def sources_check(body: UploadIn):
    sources, problems = _load_upload(body)
    return {"usable": len(sources), "sources": [s.as_dict() for s in sources],
            "problems": [p.__dict__ for p in problems]}


@app.post("/api/batch")
def batch_start(body: BatchIn):
    if body.render not in ("never", "auto", "always"):
        raise HTTPException(400, "render must be never, auto or always")
    sources, problems = _load_upload(body)
    if not sources:
        raise HTTPException(400, "No usable colleges in the file: " + "; ".join(p.problem for p in problems[:5]))
    job = BatchJob(body, sources)
    BATCHES[job.id] = job
    import base64
    _safe(store().create_run, job.id, "batch", f"{body.filename} ({len(sources)} colleges)",
          body.model_dump(exclude={"content_base64"}), body.filename, base64.b64decode(body.content_base64))
    threading.Thread(target=job.run, daemon=True).start()
    return {"id": job.id, "colleges": len(sources), "problems": [p.__dict__ for p in problems]}


@app.get("/api/active")
def active():
    """The latest single crawl and batch, so a reloaded page can pick them up again."""
    def last(d):
        if not d:
            return None
        job = list(d.values())[-1]
        return {"id": job.id, "state": _state(job)}
    return {"job": last(JOBS), "batch": last(BATCHES)}


@app.get("/api/batch/{job_id}/doctors")
def batch_doctors(job_id: str):
    """People and offices found so far in a batch (finished colleges plus the one being crawled)."""
    job = BATCHES.get(job_id) or _missing("batch")
    live = job.live
    docs = list(live["merger"].records) if live.get("merger") else []
    running = list((live.get("active") or {}).values())
    offices = list(live.get("offices") or [])
    for crawler, src in running:
        for d in list(crawler.merger.records):
            d.source_institution = d.source_institution or src.institution
            docs.append(d)
        offices += list(crawler.offices)
    if not job.body.all_people:
        docs = [d for d in docs if d.is_relevant]
    return {"doctors": _rows(docs), "offices": _office_rows(offices)}


@app.get("/api/batch/{job_id}")
def batch_status(job_id: str):
    job = BATCHES.get(job_id)
    if not job:
        raise HTTPException(404, "batch not found")
    return {"id": job.id, "state": _state(job), "error": job.error, "current": job.current, "index": job.index,
            "total": len(job.sources), "elapsed": round(time.time() - job.started), "progress": job.progress,
            "sites": job.sites, "stats": job.stats, "log": list(job.log)[-60:]}


@app.post("/api/batch/{job_id}/stop")
def batch_stop(job_id: str):
    job = BATCHES.get(job_id)
    if not job:
        raise HTTPException(404, "batch not found")
    job.stop.set()
    return {"ok": True}


@app.post("/api/batch/{job_id}/pause")
def pause_batch(job_id: str):
    job = BATCHES.get(job_id) or _missing("batch")
    return _pause(job, True)


@app.post("/api/batch/{job_id}/resume")
def resume_batch(job_id: str):
    job = BATCHES.get(job_id) or _missing("batch")
    return _pause(job, False)


@app.get("/api/batch/{job_id}/download.xlsx")
def batch_download(job_id: str):
    job = BATCHES.get(job_id)
    if not job:
        raise HTTPException(404, "batch not found")
    if not job.xlsx:  # still running: write what has been found so far
        if not job.live.get("merger"):
            raise HTTPException(404, "nothing found yet")
        from .batch import snapshot_xlsx
        OUT_DIR.mkdir(exist_ok=True)
        part = OUT_DIR / f"batch-{job.id}-partial-{time.strftime('%H%M%S')}.xlsx"
        try:
            snapshot_xlsx(job.live, part)
        except Exception as exc:
            raise HTTPException(500, f"could not write partial Excel: {exc}") from None
        return FileResponse(part, filename=part.name,
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return FileResponse(job.xlsx, filename=job.xlsx.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------------
# Portal: run history, faculty directory, student-office directory, dashboard (all from the local database)
def _live_state(run_id: str) -> str | None:
    job = JOBS.get(run_id) or BATCHES.get(run_id)
    return _state(job) if job else None


@app.get("/api/runs")
def runs_list():
    runs = store().list_runs()
    for r in runs:
        r["state"] = _live_state(r["id"]) or r["state"]
        r["live"] = r["id"] in JOBS or r["id"] in BATCHES
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str):
    r = store().get_run(run_id) or _missing("run")
    r["state"] = _live_state(run_id) or r["state"]
    r["sites"] = store().sites(run_id)
    return r


@app.delete("/api/runs/{run_id}")
def run_delete(run_id: str):
    if _live_state(run_id) in ("running", "paused"):
        raise HTTPException(409, "Stop the run before deleting it")
    store().delete_run(run_id)
    return {"ok": True}


@app.get("/api/runs/{run_id}/download.{fmt}")
def run_download(run_id: str, fmt: str):
    if run_id in JOBS:
        return download(run_id, fmt)
    if run_id in BATCHES and fmt == "xlsx":
        return batch_download(run_id)
    r = store().get_run(run_id) or _missing("run")
    if fmt == "xlsx" and r.get("xlsx") and Path(r["xlsx"]).is_file():
        p = Path(r["xlsx"])
        return FileResponse(p, filename=p.name, media_type=XLSX)
    docs, offices = store().run_people(run_id), store().run_offices(run_id)
    if not docs and not offices:
        raise HTTPException(404, "nothing saved for this run")
    return _export(docs, offices, fmt, f"run-{run_id}", sites=store().sites(run_id) or None)


def _export(docs: list[PersonRecord], offices: list[OfficeRecord], fmt: str, name: str, sites=None,
            only_fac: bool = True):
    if fmt == "csv":
        return Response(to_csv([d for d in docs if d.is_relevant or not only_fac]).encode("utf-8-sig"),
                        media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    res = CrawlResult([], docs, [], offices=offices)
    fac = res.faculty
    res.stats = {"people_found": len(docs), "faculty": len(fac), "student_offices": len(offices),
                 "faculty_with_own_email": sum(1 for d in fac if d.get("email")),
                 "faculty_with_own_phone": sum(1 for d in fac if d.get("phone"))}
    if fmt == "json":
        return Response(to_json(res, only_fac), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
    if fmt != "xlsx":
        raise HTTPException(400, "format must be xlsx, csv or json")
    OUT_DIR.mkdir(exist_ok=True)
    path = to_xlsx(res, OUT_DIR / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.xlsx", sites=sites)
    return FileResponse(path, filename=path.name, media_type=XLSX)


@app.post("/api/runs/{run_id}/resume")
def run_resume(run_id: str):
    """Carry on a batch that was cut off when the app closed: finished colleges are not crawled again."""
    import base64
    if _live_state(run_id) in ("running", "paused"):
        raise HTTPException(409, "This run is still going")
    r = store().get_run(run_id) or _missing("run")
    if r["kind"] != "batch":
        raise HTTPException(400, "Only college-list batches can be resumed; use Run again for a single website")
    name, data = store().upload_of(run_id)
    if not data:
        raise HTTPException(400, "The college list of this run was not saved; start a new batch")
    settings = {k: v for k, v in r["settings"].items() if k not in ("filename", "content_base64")}
    body = BatchIn(filename=name or "list.xlsx", content_base64=base64.b64encode(data).decode(), **settings)
    sources, _ = _load_upload(body)
    job = BatchJob(body, sources, run_id=run_id, resume=True)
    BATCHES[run_id] = job
    store().update_run(run_id, state="running", finished=None, error=None)
    threading.Thread(target=job.run, daemon=True).start()
    return {"id": run_id, "colleges": len(sources)}


@app.post("/api/runs/{run_id}/rerun")
def run_again(run_id: str):
    r = store().get_run(run_id) or _missing("run")
    if r["kind"] != "crawl":
        raise HTTPException(400, "Use Resume for a batch")
    return start(JobIn(**r["settings"]))


def _dir_filters(q: str = "", city: str = "", college: str = "", department: str = "", has_email: bool = False,
                 has_phone: bool = False, has_contact: bool = False, has_profile: bool = False,
                 all_people: bool = False) -> dict:
    return dict(q=q.strip(), city=city, college=college, department=department, has_email=has_email,
                has_phone=has_phone, has_contact=has_contact, has_profile=has_profile, faculty_only=not all_people)


@app.get("/api/directory")
def directory(q: str = "", city: str = "", college: str = "", department: str = "", has_email: bool = False,
              has_phone: bool = False, has_contact: bool = False, has_profile: bool = False,
              all_people: bool = False, page: int = 1):
    page = max(1, page)
    f = _dir_filters(q, city, college, department, has_email, has_phone, has_contact, has_profile, all_people)
    total, rows = store().directory(**f, limit=100, offset=(page - 1) * 100)
    docs = [PersonRecord.from_full_dict(r) for r in rows]
    return {"total": total, "page": page, "pages": max(1, -(-total // 100)), "doctors": _rows(docs, 100),
            "facets": store().facets()}


@app.get("/api/directory/download.{fmt}")
def directory_download(fmt: str, q: str = "", city: str = "", college: str = "", department: str = "",
                       has_email: bool = False, has_phone: bool = False, has_contact: bool = False,
                       has_profile: bool = False, all_people: bool = False):
    f = _dir_filters(q, city, college, department, has_email, has_phone, has_contact, has_profile, all_people)
    docs = store().directory_records(**f)
    if not docs:
        raise HTTPException(404, "No faculty match these filters")
    return _export(docs, [], fmt, "faculty-directory", only_fac=not all_people)


def _office_filters(q: str = "", college: str = "", office_type: str = "", has_email: bool = False,
                    has_phone: bool = False, has_figures: bool = False) -> dict:
    return dict(q=q.strip(), college=college, office_type=office_type, has_email=has_email, has_phone=has_phone,
                has_figures=has_figures)


@app.get("/api/offices")
def office_directory(q: str = "", college: str = "", office_type: str = "", has_email: bool = False,
                     has_phone: bool = False, has_figures: bool = False):
    rows = store().office_directory(**_office_filters(q, college, office_type, has_email, has_phone, has_figures))
    return {"total": len(rows), "offices": rows[:1000], "facets": store().facets()}


@app.get("/api/offices/download.{fmt}")
def office_download(fmt: str, q: str = "", college: str = "", office_type: str = "", has_email: bool = False,
                    has_phone: bool = False, has_figures: bool = False):
    offices = store().office_records(**_office_filters(q, college, office_type, has_email, has_phone, has_figures))
    if not offices:
        raise HTTPException(404, "No student offices match these filters")
    if fmt == "csv":
        import csv
        import io
        from .export import OFFICE_COLUMNS, OFFICE_HEADERS, _csv_safe, office_row
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([OFFICE_HEADERS.get(c) or c for c in OFFICE_COLUMNS])
        for o in offices:
            w.writerow([_csv_safe(v) for v in office_row(o)])
        return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="student-offices.csv"'})
    return _export([], offices, fmt, "student-offices")


@app.get("/api/dashboard")
def dashboard():
    return store().dashboard()
