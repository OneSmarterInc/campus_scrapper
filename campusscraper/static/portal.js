// Portal pages: Dashboard, Runs history, Faculty directory and Student offices. Uses helpers from app.js.
const VIEWS = ['dashboard', 'new', 'runs', 'directory', 'offices'];
let viewTimer = null;

function fmtTime(t) { if (!t) return ''; const d = new Date(t * 1000); return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
function fmtDur(a, b) {
  if (!a) return ''; const s = Math.max(0, Math.round(((b || Date.now() / 1000) - a)));
  return s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}m`;
}
const STATE_CLASS = { done: 'ok', running: 'ok', paused: 'warn', pausing: 'warn', waiting: 'warn', partial: 'warn', clarify: 'warn', stopping: 'warn', interrupted: 'warn', stopped: 'warn', failed: 'bad' };
function stateCell(s) { return `<span class="${STATE_CLASS[s] || ''}"><b>${esc(s)}</b></span>`; }

function show(view) {
  if (!VIEWS.includes(view)) view = 'dashboard';
  for (const v of VIEWS) $('view-' + v).hidden = v !== view;
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + view));
  clearInterval(viewTimer);
  if (view === 'dashboard') { loadDashboard(); viewTimer = setInterval(loadDashboard, 5000); }
  if (view === 'runs') { loadRuns(); viewTimer = setInterval(loadRuns, 4000); }
  if (view === 'directory') loadDirectory();
  if (view === 'offices') loadOffices();
}
window.addEventListener('hashchange', () => show(location.hash.slice(1)));

// ---- dashboard ----------------------------------------------------------------
async function loadDashboard() {
  const [d, r] = await Promise.all([api('/api/dashboard'), api('/api/runs')]);
  if (!d.ok) { $('d-totals').innerHTML = `<p class="msg bad">${esc(d.error)}</p>`; return; }
  const t = d.data.totals;
  const pct = n => t.faculty ? ` <small>(${Math.round(100 * n / t.faculty)}%)</small>` : '';
  $('d-totals').innerHTML = [
    ['Faculty', t.faculty], ['Colleges', t.colleges], ['Departments', t.departments],
    ['With own email', t.with_email + pct(t.with_email)], ['With any contact', t.with_contact + pct(t.with_contact)],
    ['With Scholar / ORCID', t.with_profile + pct(t.with_profile)],
    ['Student offices', t.offices + (t.offices ? ` <small>(${t.offices_with_email} with email)</small>` : '')],
    ['Placement cells', t.placement_cells], ['Higher-studies cells', t.higher_studies_cells],
    ['Runs', t.runs + (t.active_runs ? ` <small>(${t.active_runs} active)</small>` : '')],
  ].map(([k, v]) => `<div class="stat"><span>${k}</span><b>${v}</b></div>`).join('');
  const cs = d.data.colleges;
  $('d-coll').innerHTML = cs.length ? cs.map(c => {
    const n = Math.max(1, c.fac), e = 100 * c.email / n, p = 100 * Math.max(0, c.phone - c.email) / n, o = 100 * Math.max(0, c.contact - Math.max(c.email, c.phone)) / n;
    const types = (c.office_types || []).map(x => OFFICE_NAMES[x] || x).join(', ');
    return `<tr><td><a href="#directory" data-coll="${esc(c.c)}">${esc(c.c)}</a></td><td>${c.fac}</td><td>${c.email}</td><td>${c.phone}</td><td>${c.contact}</td><td>${c.profile}</td>
      <td>${c.offices ? `<a href="#offices" data-ocoll="${esc(c.c)}">${c.offices}</a> <span class="muted">${esc(types)}</span>` : '0'}</td>
      <td><div class="cov" title="${Math.round(100 * c.contact / n)}% have some contact"><i class="e" style="width:${e}%"></i><i class="p" style="width:${p}%"></i><i class="o" style="width:${o}%"></i></div></td></tr>`;
  }).join('') + `<tr><td colspan="8" class="legend">Coverage:<b style="background:#1d7a3c"></b>own email<b style="background:#3f8fd6"></b>own phone<b style="background:#9bb7bd"></b>department / office contact only</td></tr>`
    : `<tr><td colspan="8" class="empty">Nothing saved yet. Start a run under <a href="#new">New run</a>.</td></tr>`;
  document.querySelectorAll('#d-coll a[data-coll]').forEach(a => a.onclick = () => { $('x-coll').dataset.want = a.dataset.coll; });
  document.querySelectorAll('#d-coll a[data-ocoll]').forEach(a => a.onclick = () => { $('o-coll').dataset.want = a.dataset.ocoll; });
  if (r.ok) $('d-runs').innerHTML = r.data.runs.slice(0, 8).map(x => `<tr><td>${fmtTime(x.started)}</td><td>${esc(x.title)}</td><td>${stateCell(x.state)}</td><td>${x.faculty_saved}</td><td>${x.offices_saved}</td></tr>`).join('')
    || `<tr><td colspan="5" class="empty">No runs yet.</td></tr>`;
}

// ---- runs history -----------------------------------------------------------------
const armed = new Set();
async function loadRuns() {
  const r = await api('/api/runs');
  if (!r.ok) { say($('r-msg'), r.error, 'bad'); return; }
  $('r-rows').innerHTML = r.data.runs.map(x => {
    const live = ['queued','running','paused','pausing','waiting','stopping'].includes(x.state);
    const acts = [];
    if (live || x.kind === 'prompt') acts.push(`<button data-act="open" data-id="${x.id}" data-kind="${x.kind}">Open</button>`);
    acts.push(`<button class="secondary" data-act="dl" data-id="${x.id}">Excel</button>`);
    if (!live && x.kind === 'batch' && x.has_upload && x.state !== 'done') acts.push(`<button data-act="resume" data-id="${x.id}">Resume</button>`);
    if (x.kind === 'prompt' && ['paused','stopped','interrupted','failed'].includes(x.state)) acts.push(`<button data-act="resume" data-id="${x.id}" data-kind="prompt">Resume</button>`);
    if (!live && x.kind === 'crawl') acts.push(`<button class="secondary" data-act="rerun" data-id="${x.id}">Run again</button>`);
    if (!live) acts.push(`<button class="secondary" data-act="del" data-id="${x.id}">${armed.has(x.id) ? 'Click again to delete' : 'Delete'}</button>`);
    return `<tr><td>${fmtTime(x.started)}</td><td>${x.kind === 'prompt' ? 'Prompt' : x.kind === 'batch' ? 'College list' : 'One website'}</td><td>${esc(x.title)}</td>
      <td>${stateCell(x.state)}${x.error ? `<div class="muted">${esc(x.error)}</div>` : ''}</td><td>${fmtDur(x.started, live ? null : x.finished)}</td>
      <td>${x.faculty_saved}</td><td>${x.offices_saved}</td><td class="actions">${acts.join('')}</td></tr>`;
  }).join('') || `<tr><td colspan="8" class="empty">No runs yet. Start one under <a href="#new">New run</a>.</td></tr>`;
}
$('r-rows').onclick = async e => {
  const b = e.target.closest('button[data-act]'); if (!b) return;
  const id = b.dataset.id, act = b.dataset.act;
  if (act === 'open') { location.hash = '#new'; if (b.dataset.kind === 'prompt') { attachPrompt(id); $('prompt-card').scrollIntoView(); } else b.dataset.kind === 'batch' ? attachBatch(id) : attachJob(id); return; }
  if (act === 'dl') { download(`/api/runs/${id}/download.xlsx`, $('r-msg'), b); return; }
  if (act === 'del') {
    if (!armed.has(id)) { armed.add(id); b.textContent = 'Click again to delete'; setTimeout(() => armed.delete(id), 5000); return; }
    const r = await api(`/api/runs/${id}`, { method: 'DELETE' });
    say($('r-msg'), r.ok ? 'Run deleted.' : r.error, r.ok ? 'ok' : 'bad'); armed.delete(id); loadRuns(); return;
  }
  b.disabled = true;
  const r = await postJSON(`/api/runs/${id}/${act}`);
  b.disabled = false;
  if (!r.ok) { say($('r-msg'), r.error, 'bad'); return; }
  location.hash = '#new';
  if (r.data.kind === 'prompt') { attachPrompt(r.data.id); return; }
  if (act === 'resume') { say($('b-msg'), `Resumed: finished colleges are kept, ${r.data.colleges} in the list.`, 'ok'); attachBatch(r.data.id); }
  else { showRows([], 'this website crawl', []); attachJob(r.data.id); }
};

function fillSelect(sel, values, label, names) {
  const want = sel.dataset.want || sel.value;
  sel.innerHTML = `<option value="">${label}</option>` + values.map(v => `<option value="${esc(v)}"${v === want ? ' selected' : ''}>${esc((names && names[v]) || v)}</option>`).join('');
  delete sel.dataset.want;
}

// ---- faculty directory ------------------------------------------------------------------
const dirState = { page: 1 };
function dirQuery() {
  const p = new URLSearchParams();
  const v = { q: $('x-q').value, college: $('x-coll').dataset.want || $('x-coll').value, department: $('x-dept').value, city: $('x-city').value };
  for (const [k, x] of Object.entries(v)) if (x) p.set(k, x);
  for (const [k, id] of [['has_email', 'x-email'], ['has_phone', 'x-phone'], ['has_contact', 'x-contact'], ['has_profile', 'x-profile'], ['all_people', 'x-all']])
    if ($(id).checked) p.set(k, 'true');
  return p;
}
async function loadDirectory() {
  const p = dirQuery(); p.set('page', dirState.page);
  const r = await api('/api/directory?' + p);
  if (!r.ok) { say($('x-msg'), r.error, 'bad'); return; }
  const j = r.data; say($('x-msg'), '');
  fillSelect($('x-coll'), j.facets.colleges, 'All colleges');
  fillSelect($('x-dept'), j.facets.departments, 'All departments');
  fillSelect($('x-city'), j.facets.cities, 'All cities');
  $('x-count').textContent = `${j.total} ${j.total === 1 ? 'person' : 'people'}`;
  $('x-page').textContent = `Page ${j.page} of ${j.pages}`;
  $('x-prev').disabled = j.page <= 1; $('x-next').disabled = j.page >= j.pages;
  $('x-rows').innerHTML = j.doctors.map(d => `<tr><td><b>${esc(d.name)}</b></td><td>${esc(d.designation)}</td><td>${esc(d.department)}</td>
    <td class="contact">${esc(d.email)}</td><td class="contact">${esc(d.phone)}</td><td class="muted">${esc([d.contact_email, d.contact_phone].filter(Boolean).join('; '))}</td>
    <td>${esc(d.source_institution || d.institution)}</td><td>${esc(list(d.qualifications))}</td><td>${esc(list(d.research_areas))}</td>
    <td>${d.google_scholar ? `<a href="${esc(safeUrl(d.google_scholar))}" target="_blank" rel="noopener">Scholar</a>` : ''}${d.orcid ? ` ORCID ${esc(d.orcid)}` : ''}</td>
    <td><a href="${esc(safeUrl(d.profile_url || d.source_url))}" target="_blank" rel="noopener">open</a></td></tr>`).join('')
    || `<tr><td colspan="11" class="empty">${j.total ? '' : 'Nobody matches. Clear the filters or run a crawl first.'}</td></tr>`;
}
let dirDebounce = null;
const dirChanged = () => { dirState.page = 1; clearTimeout(dirDebounce); dirDebounce = setTimeout(loadDirectory, 300); };
$('x-q').oninput = dirChanged;
for (const id of ['x-coll', 'x-dept', 'x-city', 'x-email', 'x-phone', 'x-contact', 'x-profile', 'x-all']) $(id).onchange = dirChanged;
$('x-prev').onclick = () => { dirState.page--; loadDirectory(); };
$('x-next').onclick = () => { dirState.page++; loadDirectory(); };
$('x-reset').onclick = () => {
  for (const id of ['x-q', 'x-coll', 'x-dept', 'x-city']) $(id).value = '';
  for (const id of ['x-email', 'x-phone', 'x-contact', 'x-profile', 'x-all']) $(id).checked = false;
  dirChanged();
};
$('x-xlsx').onclick = () => download('/api/directory/download.xlsx?' + dirQuery(), $('x-msg'), $('x-xlsx'));
$('x-csv').onclick = () => download('/api/directory/download.csv?' + dirQuery(), $('x-msg'), $('x-csv'));

// ---- student offices ------------------------------------------------------------------
function officeQuery() {
  const p = new URLSearchParams();
  const v = { q: $('o-q').value, college: $('o-coll').dataset.want || $('o-coll').value, office_type: $('o-type').value };
  for (const [k, x] of Object.entries(v)) if (x) p.set(k, x);
  for (const [k, id] of [['has_email', 'o-email'], ['has_phone', 'o-phone'], ['has_figures', 'o-figures']])
    if ($(id).checked) p.set(k, 'true');
  return p;
}
async function loadOffices() {
  const r = await api('/api/offices?' + officeQuery());
  if (!r.ok) { say($('o-msg'), r.error, 'bad'); return; }
  const j = r.data; say($('o-msg'), '');
  fillSelect($('o-coll'), j.facets.colleges, 'All colleges');
  fillSelect($('o-type'), j.facets.office_types, 'All types', OFFICE_NAMES);
  $('o-count').textContent = `${j.total} office${j.total === 1 ? '' : 's'}`;
  $('o-rows').innerHTML = j.offices.map(o => `<tr><td><span class="pill">${esc(OFFICE_NAMES[o.office_type] || o.office_type)}</span></td>
    <td><b>${esc(o.office_name)}</b></td><td>${esc(o.college || o.source_institution || o.institution)}</td>
    <td class="contact">${esc(list(o.emails))}</td><td class="contact">${esc(list(o.phones))}</td>
    <td>${esc((o.coordinators || []).join('; '))}</td><td class="muted">${esc((o.higher_studies_lines || []).join(' | '))}</td>
    <td><a href="${esc(safeUrl(o.page_url))}" target="_blank" rel="noopener">open</a></td></tr>`).join('')
    || `<tr><td colspan="8" class="empty">No student offices match. Clear the filters or run a crawl first.</td></tr>`;
}
let offDebounce = null;
const offChanged = () => { clearTimeout(offDebounce); offDebounce = setTimeout(loadOffices, 300); };
$('o-q').oninput = offChanged;
for (const id of ['o-coll', 'o-type', 'o-email', 'o-phone', 'o-figures']) $(id).onchange = offChanged;
$('o-reset').onclick = () => {
  for (const id of ['o-q', 'o-coll', 'o-type']) $(id).value = '';
  for (const id of ['o-email', 'o-phone', 'o-figures']) $(id).checked = false;
  offChanged();
};
$('o-xlsx').onclick = () => download('/api/offices/download.xlsx?' + officeQuery(), $('o-msg'), $('o-xlsx'));
$('o-csv').onclick = () => download('/api/offices/download.csv?' + officeQuery(), $('o-msg'), $('o-csv'));

show(location.hash.slice(1) || 'dashboard');
