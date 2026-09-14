const state = { deviations: [], sites: [], capa: [], datasets: [], protocol: null, selectedSite: null, selectedDatasetId: null, selectedDeviationId: null, questionVariant: 0, severity: 'all', search: '', pendingImport: null };
const $ = (selector) => document.querySelector(selector);
const labelize = (value = '') => value.replaceAll('_', ' ');
const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;' }[character]));

async function request(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(typeof payload === 'string' ? payload : payload.detail || 'The request could not be completed.');
  return payload;
}

async function loadWorkspace(message) {
  const [summary, sites, deviations, protocol, capa, datasets] = await Promise.all([
    request('/api/summary'), request('/api/sites'), request('/api/deviations'), request('/api/protocol'), request('/api/capa'), request('/api/datasets'),
  ]);
  state.sites = sites; state.deviations = deviations; state.protocol = protocol; state.capa = capa; state.datasets = datasets;
  state.selectedSite = state.selectedSite && sites.find((site) => site.site_code === state.selectedSite.site_code) || sites[0] || null;
  renderSummary(summary); renderPriority(sites); renderDatasets(datasets); renderSites(sites); renderInbox(); renderProtocol(protocol); renderCapa(capa); renderBrief(state.selectedSite);
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  $('#last-run').textContent = `Updated ${time}`;
  if (message) toast(message);
}

function renderDatasets(datasets) {
  $('#dataset-count').textContent = `${datasets.length} dataset${datasets.length === 1 ? '' : 's'}`;
  $('#dataset-list').innerHTML = datasets.length ? datasets.map((dataset) => `<button class="dataset-card ${state.selectedDatasetId === dataset.id ? 'selected' : ''}" data-dataset="${dataset.id}"><span class="dataset-signal">●</span><span class="dataset-copy"><strong>${escapeHtml(dataset.name)}</strong><small>${escapeHtml(dataset.source_filename || 'Local JSON')}</small><em>${dataset.sites} site${dataset.sites === 1 ? '' : 's'} · ${dataset.patients} subject${dataset.patients === 1 ? '' : 's'} · ${dataset.deviations} finding${dataset.deviations === 1 ? '' : 's'}</em></span><span class="dataset-arrow">→</span><span class="dataset-delete" data-delete-dataset="${dataset.id}" title="Delete dataset">×</span></button>`).join('') : '<div class="shelf-empty">No datasets loaded. Import a JSON source to begin.</div>';
  document.querySelectorAll('[data-dataset]').forEach((card) => card.addEventListener('click', (event) => {
    if (event.target.closest('[data-delete-dataset]')) return;
    state.selectedDatasetId = Number(card.dataset.dataset);
    const datasetSites = state.sites.filter((site) => site.dataset_id === state.selectedDatasetId);
    state.selectedSite = datasetSites.sort((left, right) => right.risk_score - left.risk_score)[0] || null;
    renderDatasets(state.datasets); renderSites(state.sites); renderBrief(state.selectedSite);
    $('#site-risk').scrollIntoView({ behavior: 'smooth', block: 'start' });
    toast(`${card.querySelector('strong').textContent} selected.`);
  }));
  document.querySelectorAll('[data-delete-dataset]').forEach((button) => button.addEventListener('click', () => deleteDataset(Number(button.dataset.deleteDataset))));
}

function renderPriority(sites) {
  const priority = sites[0];
  if (!priority) {
    $('#priority-site').textContent = 'NO PRIORITY YET';
    $('#priority-score').textContent = '—';
    $('#priority-dataset').textContent = 'Waiting for active records';
    $('#priority-copy').textContent = 'Import multiple datasets to compare site risk across the full trial workspace.';
    return;
  }
  $('#priority-site').textContent = priority.site_code;
  $('#priority-score').textContent = `${Math.round(priority.risk_score)} / 100`;
  $('#priority-dataset').textContent = `${priority.dataset_name || 'Unassigned dataset'} · ${priority.deviation_count} finding${priority.deviation_count === 1 ? '' : 's'}`;
  $('#priority-copy').textContent = priority.risk_score > 0 ? `${priority.name} has the highest aggregate risk across all loaded datasets. Start inspection here.` : 'No active risk signals are present across the loaded datasets.';
}

async function deleteDataset(id) {
  const dataset = state.datasets.find((item) => item.id === id);
  if (!dataset || !window.confirm(`Delete “${dataset.name}” and all of its findings?`)) return;
  try { await request(`/api/datasets/${id}`, { method: 'DELETE' }); if (state.selectedDatasetId === id) state.selectedDatasetId = null; await loadWorkspace(`${dataset.name} deleted. Risk totals recalculated.`); } catch (error) { toast(error.message, 'error'); }
}

function renderSummary(summary) {
  const setText = (selector, value) => { const node = $(selector); if (node) node.textContent = value; };
  const critical = state.sites.filter((site) => site.risk_level === 'Critical').length;
  const major = state.deviations.filter((item) => item.severity === 'major').length;
  const coverage = summary.patients ? Math.max(0, Math.round(((summary.patients * 4 - major) / (summary.patients * 4)) * 100)) : 100;
  setText('#critical-sites', critical); setText('#open-deviations', summary.open_deviations); setText('#patients', summary.patients);
  setText('#site-count', `${summary.sites} trial site${summary.sites === 1 ? '' : 's'}`); setText('#site-count-label', `${summary.sites} sites`);
  setText('#nav-critical', critical); setText('#nav-deviations', summary.open_deviations); setText('#nav-capa', summary.capa_reports || 0);
  setText('#coverage', `${coverage}%`); setText('#coverage-note', summary.patients ? `${summary.sites} sites · ${summary.patients} subjects` : 'Ruleset ready');
  setText('#deviation-breakdown', state.deviations.length ? `${major} major · ${state.deviations.filter((item) => item.severity === 'minor').length} minor` : 'No active findings');
  ['all', 'major', 'minor', 'administrative'].forEach((severity) => { const id = severity === 'all' ? 'all' : severity; const count = severity === 'all' ? state.deviations.length : state.deviations.filter((item) => item.severity === severity).length; setText(`#${id}-count`, count); });
  setText('#signal-badge', critical ? `${critical} CRITICAL SITE${critical > 1 ? 'S' : ''}` : summary.sites ? 'MONITORING ACTIVE' : 'NO DATA');
  setText('#signal-title', critical ? `${critical} site${critical > 1 ? 's are' : ' is'} asking for attention.` : summary.sites ? 'The trial is under active surveillance.' : 'Load trial records to begin risk review.');
  setText('#signal-copy', critical ? 'Prioritize the critical worklist below. Every signal is linked to a subject record and protocol rule.' : summary.sites ? 'No critical site signal is currently open. Review the inbox for minor and administrative findings.' : 'Import an EDC export or the included test dataset. TrialGuard will compare every record with the active protocol.');
  setText('#signal-time', summary.sites ? 'Risk engine active' : 'Ready for import');
}

function renderSites(sites) {
  $('#site-list').innerHTML = sites.length ? sites.map((site) => { const selected = state.selectedSite?.site_code === site.site_code; return `<button class="site-row ${selected ? 'selected' : ''}" data-site="${escapeHtml(site.site_code)}"><span class="site-code"><strong>${escapeHtml(site.site_code)}</strong><small>${escapeHtml(site.name)}</small></span><span class="site-score"><strong>${Math.round(site.risk_score)}</strong><small>/ 100</small></span><span class="site-track"><i class="risk-fill ${site.risk_level.toLowerCase()}" style="width:${Math.max(site.risk_score, 2)}%"></i><small>${site.risk_level} risk</small></span><span class="risk-label ${site.risk_level.toLowerCase()}">${site.risk_level}</span><span class="row-arrow">→</span></button>`; }).join('') : `<div class="empty-state"><span>⌖</span><strong>No site risk yet</strong><p>Import patient records to build the site radar.</p></div>`;
  document.querySelectorAll('[data-site]').forEach((row) => row.addEventListener('click', () => { state.selectedSite = sites.find((site) => site.site_code === row.dataset.site); renderSites(sites); renderBrief(state.selectedSite); }));
}

function renderBrief(site) {
  state.questionVariant = 0;
  $('#ask-bob').innerHTML = 'Generate questions <span>→</span>';
  if (!site) { $('#brief-title').textContent = 'Select a site'; $('#brief').innerHTML = '<div class="empty-state compact"><span>◈</span><strong>Risk explanation</strong><p>Select a site to inspect the evidence driving its score.</p></div>'; return; }
  const findings = state.deviations.filter((item) => item.site_code === site.site_code);
  $('#brief-title').textContent = `${site.site_code} investigation`;
  $('#brief').innerHTML = `<div class="brief-score"><div><span>Risk score</span><strong>${Math.round(site.risk_score)}<small>/100</small></strong></div><span class="risk-label ${site.risk_level.toLowerCase()}">${site.risk_level}</span></div><p class="brief-lead">${findings.length ? `${findings.length} evidence-backed finding${findings.length === 1 ? '' : 's'} are contributing to this site's priority.` : 'No deviations are currently linked to this site.'}</p><div class="finding-stack">${findings.slice(0, 4).map((item) => `<button class="finding-line" data-finding="${item.id}"><span class="severity-dot ${item.severity}"></span><span><strong>${labelize(item.deviation_type)}</strong><small>${evidenceSummary(item.evidence)}</small></span><b>→</b></button>`).join('')}</div><div id="investigation-questions" class="questions"></div>`;
  document.querySelectorAll('[data-finding]').forEach((button) => button.addEventListener('click', () => focusDeviation(Number(button.dataset.finding))));
}

function renderInbox() {
  const visible = state.deviations.filter((item) => (state.severity === 'all' || item.severity === state.severity) && `${item.site_code} ${item.patient_code} ${item.deviation_type} ${item.description}`.toLowerCase().includes(state.search));
  const emptyMessage = state.deviations.length === 0 && state.sites.length > 0 ? 'No deviations detected. The loaded dataset is currently within the active protocol rules.' : 'No findings match the current view.';
  $('#deviation-list').innerHTML = visible.length ? visible.map((item) => `<tr data-row="${item.id}"><td><span class="deviation-name">${labelize(item.deviation_type)}</span><span class="deviation-sub">${escapeHtml(item.description)}</span></td><td><strong>${escapeHtml(item.site_code)}</strong><span class="deviation-sub">${escapeHtml(item.patient_code || 'Site-level')}</span></td><td><span class="severity severity-${item.severity}">${item.severity}</span></td><td>${evidenceSummary(item.evidence)}</td><td><select class="status-select" data-status="${item.id}"><option value="open" ${item.status === 'open' ? 'selected' : ''}>Open</option><option value="under_investigation" ${item.status === 'under_investigation' ? 'selected' : ''}>Investigating</option><option value="capa_required" ${item.status === 'capa_required' ? 'selected' : ''}>CAPA required</option><option value="resolved" ${item.status === 'resolved' ? 'selected' : ''}>Resolved</option><option value="closed" ${item.status === 'closed' ? 'selected' : ''}>Closed</option></select></td><td><button class="table-action" data-capa="${item.id}">CAPA</button></td></tr>`).join('') : `<tr><td colspan="6" class="loading">${emptyMessage}</td></tr>`;
  document.querySelectorAll('[data-capa]').forEach((button) => button.addEventListener('click', () => openCapa(Number(button.dataset.capa))));
  document.querySelectorAll('[data-status]').forEach((select) => select.addEventListener('change', () => updateStatus(Number(select.dataset.status), select.value)));
}

function renderProtocol(protocol) {
  if (!protocol) return;
  $('#protocol-version').textContent = `v${protocol.version}`;
  const windows = Object.entries(protocol.visit_windows).map(([visit, range]) => `V${visit} ${range[0]}–${range[1]}`).join(' · ');
  $('#protocol-list').innerHTML = `<div class="protocol-row"><span>Visit windows</span><strong>${windows}</strong></div><div class="protocol-row"><span>Target dose</span><strong>${protocol.dose_mg} mg · ${labelize(protocol.dose_frequency)}</strong></div><div class="protocol-row"><span>Restricted medication</span><strong>${protocol.prohibited_medications.join(', ')}</strong></div><div class="protocol-row"><span>Required checks</span><strong>${protocol.required_assessments.map(labelize).join(', ')}</strong></div><div class="protocol-row"><span>Entry deadline</span><strong>${protocol.data_entry_deadline_days} days</strong></div>`;
}

function renderCapa(reports) { $('#capa-list').innerHTML = reports.length ? reports.slice(0, 5).map((report) => `<div class="capa-row"><button class="capa-open" data-capa-open="${report.id}"><span><strong>CAPA-${report.id}</strong><small>${escapeHtml(report.site_code)} · ${escapeHtml(report.owner || 'Unassigned')} · ${labelize(report.status)}</small></span><time>${report.due_date || 'No target date'}</time></button><a class="capa-download" href="/api/capa/${report.id}/download" download title="Download CAPA">↓</a></div>`).join('') : '<div class="empty-state compact"><span>↗</span><strong>Queue is clear</strong><p>CAPA reports will appear here after triage.</p></div>'; $('#capa-count').textContent = `${reports.length} report${reports.length === 1 ? '' : 's'}`; document.querySelectorAll('[data-capa-open]').forEach((button) => button.addEventListener('click', () => openCapaReview(Number(button.dataset.capaOpen)))); }
function evidenceSummary(evidence) { if (evidence.actual_day !== undefined) return `Day ${evidence.actual_day} / allowed ${evidence.allowed_window.join('–')}`; if (evidence.medication) return evidence.medication; if (evidence.assessment) return evidence.assessment; if (evidence.observed) return `${evidence.observed.dose_mg} mg recorded`; if (evidence.delay_days) return `${evidence.delay_days} days late`; return 'Record mismatch detected'; }
function focusDeviation(id) { const row = $(`[data-row="${id}"]`); if (row) { row.scrollIntoView({ behavior: 'smooth', block: 'center' }); row.classList.add('focused'); setTimeout(() => row.classList.remove('focused'), 1800); } }
function toast(message, type = 'success') { const item = document.createElement('div'); item.className = `toast toast-${type}`; item.innerHTML = `<span class="toast-icon">${type === 'error' ? '!' : type === 'info' ? 'i' : '✓'}</span><span>${escapeHtml(message)}</span>`; $('#toast-region').append(item); requestAnimationFrame(() => item.classList.add('visible')); setTimeout(() => { item.classList.remove('visible'); setTimeout(() => item.remove(), 250); }, 3600); }

async function updateStatus(id, status) { try { await request(`/api/deviations/${id}/status`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) }); await loadWorkspace(); toast(`Finding moved to ${labelize(status)}.`); } catch (error) { toast(error.message, 'error'); } }
function openCapa(id) { const item = state.deviations.find((deviation) => deviation.id === id); if (!item) return; state.selectedDeviationId = id; $('#capa-deviation-context').textContent = `${labelize(item.deviation_type)} · ${item.site_code} · ${item.description}`; $('#capa-dialog').showModal(); }
async function saveCapa(event) { event.preventDefault(); try { const report = await request('/api/capa', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ deviation_id: state.selectedDeviationId, owner: $('#capa-owner').value, due_date: $('#capa-due-date').value || null }) }); $('#capa-dialog').close(); await loadWorkspace(); toast(`CAPA-${report.id} assigned to ${report.owner}.`); $('#actions').scrollIntoView({ behavior: 'smooth' }); } catch (error) { toast(error.message, 'error'); } }
async function openCapaReview(id) {
  try {
    const report = await request(`/api/capa/${id}`);
    $('#capa-review-title').textContent = `CAPA-${report.id} · ${report.site_code}`;
    $('#capa-review-content').innerHTML = `<div class="report-meta"><span>${labelize(report.status)}</span><span>${escapeHtml(report.owner || 'Unassigned')}</span><span>${report.due_date || 'No target date'}</span></div><section class="report-identity"><div><small>DATASET</small><strong>${escapeHtml(report.dataset_name || 'Unknown')}</strong></div><div><small>SITE</small><strong>${escapeHtml(report.site_code)} · ${escapeHtml(report.site_name)}</strong></div><div><small>SUBJECT</small><strong>${escapeHtml(report.patient_code || 'Site-level')}</strong></div><div><small>SEVERITY</small><strong class="report-severity ${report.severity}">${escapeHtml(report.severity)}</strong></div></section><section><h4>Selected deviation</h4><p><strong>${labelize(report.deviation_type)}</strong> · ${escapeHtml(report.description)}</p><pre>${escapeHtml(JSON.stringify(report.evidence, null, 2))}</pre></section><section><h4>Impact assessment</h4><p>${escapeHtml(report.impact_assessment)}</p></section><section><h4>Root-cause hypothesis</h4><p>${escapeHtml(report.root_cause)}</p></section><section><h4>Corrective action</h4><p>${escapeHtml(report.corrective_action)}</p></section><section><h4>Preventive action</h4><p>${escapeHtml(report.preventive_action)}</p></section><section><h4>Effectiveness verification</h4><p>${escapeHtml(report.verification_plan)}</p></section>`;
    $('#capa-download').href = `/api/capa/${id}/download`;
    $('#capa-review-dialog').showModal();
  } catch (error) { toast(error.message, 'error'); }
}

$('#capa-form').addEventListener('submit', saveCapa);
$('#reanalyze').addEventListener('click', async (event) => { const button = event.currentTarget; button.disabled = true; try { await request('/api/analyze', { method: 'POST' }); await loadWorkspace('Analysis complete. Risk signals are current.'); } catch (error) { toast(error.message, 'error'); } finally { button.disabled = false; } });
$('#refresh-sites').addEventListener('click', () => loadWorkspace('Site risk radar refreshed.').catch((error) => toast(error.message, 'error')));
$('#open-priority').addEventListener('click', () => {
  if (!state.sites.length) return toast('Import a dataset before opening an inspection priority.', 'info');
  state.selectedDatasetId = state.sites[0].dataset_id;
  state.selectedSite = state.sites[0];
  renderDatasets(state.datasets); renderSites(state.sites); renderBrief(state.selectedSite);
  $('#site-risk').scrollIntoView({ behavior: 'smooth', block: 'start' });
});
$('#ask-bob').addEventListener('click', async (event) => { if (!state.selectedSite) return toast('Select a site before generating questions.', 'info'); const button = event.currentTarget; button.disabled = true; try { const brief = await request(`/api/investigation/${state.selectedSite.site_code}?variant=${state.questionVariant}`); $('#investigation-questions').innerHTML = `<strong>Questions for ${escapeHtml(state.selectedSite.site_code)}</strong><ul>${brief.questions.map((question) => `<li>${escapeHtml(question)}</li>`).join('')}</ul>`; state.questionVariant += 1; button.innerHTML = 'Regenerate questions <span>↻</span>'; toast(state.questionVariant === 1 ? 'Questions generated from current risk evidence.' : 'Questions regenerated with an alternate evidence lens.'); } catch (error) { toast(error.message, 'error'); } finally { button.disabled = false; } });
$('#import-file').addEventListener('change', async (event) => {
  const [file] = event.target.files;
  if (!file) return;
  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    state.pendingImport = { file, text };
    $('#import-file-name').textContent = file.name;
    $('#import-file-size').textContent = `${(file.size / 1024).toFixed(1)} KB · JSON parsed successfully`;
    $('#dataset-name').value = file.name.replace(/\.json$/i, '');
    const stats = [
      ['sites', payload.sites?.length || 0],
      ['patients', payload.patients?.length || 0],
      ['visits', payload.visits?.length || 0],
      ['doses', payload.doses?.length || 0],
      ['medications', payload.medications?.length || 0],
      ['assessments', payload.assessments?.length || 0],
    ];
    $('#import-preview').innerHTML = stats.map(([label, value]) => `<div class="preview-stat"><strong>${value}</strong><span>${label}</span></div>`).join('');
    $('#import-dialog').showModal();
  } catch (error) { toast(`This file is not valid JSON: ${error.message}`, 'error'); event.target.value = ''; }
});

$('#import-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!state.pendingImport) return;
  const button = $('#confirm-import');
  button.disabled = true;
  try {
    const datasetName = $('#dataset-name').value.trim();
    if (!datasetName) { toast('Add a name for this dataset before importing.', 'info'); button.disabled = false; return; }
    const payload = JSON.parse(state.pendingImport.text);
    payload.dataset_name = datasetName.trim() || state.pendingImport.file.name;
    payload.source_filename = state.pendingImport.file.name;
    const result = await request('/api/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const fileName = state.pendingImport.file.name;
    $('#import-dialog').close();
    state.pendingImport = null;
    await loadWorkspace(`${fileName} imported. ${result.total} finding${result.total === 1 ? '' : 's'} detected.`);
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; $('#import-file').value = ''; }
});
$('#deviation-search').addEventListener('input', (event) => { state.search = event.target.value.toLowerCase(); renderInbox(); });
document.querySelectorAll('.filter').forEach((button) => button.addEventListener('click', () => { document.querySelectorAll('.filter').forEach((item) => item.classList.remove('active')); button.classList.add('active'); state.severity = button.dataset.severity; renderInbox(); }));
loadWorkspace().catch((error) => { $('#signal-title').textContent = 'Workspace unavailable.'; toast(error.message, 'error'); });
