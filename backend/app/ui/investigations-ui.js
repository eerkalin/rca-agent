// Investigations workspace: history, manual runs and RCA/evidence drill-down.

let investigations = [];

function applicationName(id) {
  const app = applications.find(item => item.id === id);
  return app ? app.name : `Application #${id ?? '—'}`;
}

function investigationStatusClass(status) {
  if (status === 'completed') return 'ok';
  if (status === 'failed') return 'error-badge';
  if (status === 'running' || status === 'queued') return 'warn';
  return '';
}

function formatTimestamp(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function renderInvestigations() {
  const root = qs('#investigations-list');
  if (!root) return;
  root.innerHTML = investigations.length ? `<div class="investigation-table-wrap"><table class="investigation-table"><thead><tr><th>ID</th><th>Application</th><th>Trigger</th><th>Status</th><th>Created</th><th>Symptom</th><th></th></tr></thead><tbody>${investigations.map(item => `<tr><td>#${item.id}</td><td>${esc(applicationName(item.application_id))}</td><td>${esc(friendlyValue(item.trigger_type || 'unknown'))}</td><td><span class="badge ${investigationStatusClass(item.status)}">${esc(friendlyValue(item.status || 'unknown'))}</span></td><td>${esc(formatTimestamp(item.created_at))}</td><td class="investigation-query">${esc(item.query || '')}</td><td><button onclick="openInvestigation(${item.id})">Open</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty-state">No investigations yet.</div>';
}

async function loadInvestigations() {
  const result = await api('/investigations?limit=100');
  investigations = result.items || [];
  renderInvestigations();
  if (typeof applyRoleControls === 'function') applyRoleControls();
}

function resultList(items) {
  if (!items?.length) return '<div class="hint">None reported.</div>';
  return `<ul>${items.map(item => `<li>${esc(typeof item === 'string' ? item : JSON.stringify(item))}</li>`).join('')}</ul>`;
}

function evidenceRefs(items) {
  if (!items?.length) return '';
  return `<div class="evidence-refs">${items.map(ref => `<div><strong>${esc(ref.service_name || 'service')}</strong> · ${esc(friendlyValue(ref.evidence_type || 'evidence'))}<br>${esc(ref.observation || '')}</div>`).join('')}</div>`;
}

function renderRCA(rca) {
  if (!rca) return '<div class="empty-state">RCA result is not available yet.</div>';
  const whys = (rca.five_whys || []).map(step => `<div class="why-step"><div class="why-level">Why ${esc(step.level)}</div><h3>${esc(step.why || '')}</h3><p>${esc(step.answer || '')}</p><span class="badge ${step.evidence_supported ? 'ok' : 'warn'}">${step.evidence_supported ? 'Evidence supported' : 'Insufficient direct evidence'}</span>${evidenceRefs(step.evidence)}</div>`).join('');
  const probable = (rca.probable_causes || []).map(cause => `<div class="cause-row"><div><strong>${esc(cause.cause || '')}</strong><div class="hint">Confidence: ${Math.round(Number(cause.confidence || 0) * 100)}%</div></div>${evidenceRefs(cause.evidence)}</div>`).join('');
  return `<div class="rca-summary"><div class="card-title-row"><div><div class="eyebrow">RCA summary</div><h2>${esc(rca.summary || 'Root cause analysis')}</h2></div><span class="badge ${rca.insufficient_evidence ? 'warn' : 'ok'}">${rca.insufficient_evidence ? 'Evidence incomplete' : 'Evidence sufficient'}</span></div>${rca.impact ? `<p><strong>Impact:</strong> ${esc(rca.impact)}</p>` : ''}${rca.root_cause ? `<div class="root-cause"><strong>Root cause</strong><p>${esc(rca.root_cause)}</p></div>` : ''}</div><div class="rca-section"><h2>5 Why</h2>${whys || '<div class="hint">No 5 Why steps returned.</div>'}</div><div class="rca-grid"><section class="card"><h3>Probable causes</h3>${probable || '<div class="hint">None.</div>'}</section><section class="card"><h3>Contributing factors</h3>${resultList(rca.contributing_factors)}</section><section class="card"><h3>Recommended checks</h3>${resultList(rca.recommended_checks)}</section><section class="card"><h3>Recommended actions</h3>${resultList(rca.recommended_actions)}</section></div>${rca.limitations?.length ? `<section class="card limitations"><h3>Limitations</h3>${resultList(rca.limitations)}</section>` : ''}`;
}

async function openInvestigation(id) {
  const item = await api(`/investigations/${id}`);
  const detail = qs('#investigation-detail');
  const editor = qs('#investigation-editor');
  editor?.classList.add('hidden');
  detail.classList.remove('hidden');
  const pending = item.status === 'queued' || item.status === 'running';
  detail.innerHTML = `<div class="investigation-detail-header"><button class="back-button" id="close-investigation">← Back to investigations</button><div class="card-title-row"><div><div class="eyebrow">Investigation #${item.id}</div><h1>${esc(applicationName(item.application_id))}</h1><p>${esc(item.query || '')}</p></div><div class="actions compact-actions"><span class="badge ${investigationStatusClass(item.status)}">${esc(friendlyValue(item.status || 'unknown'))}</span>${pending ? '<button id="refresh-investigation-detail">Refresh result</button>' : ''}</div></div><div class="investigation-meta"><span><strong>Trigger</strong> ${esc(friendlyValue(item.trigger_type || 'unknown'))}</span><span><strong>Created</strong> ${esc(formatTimestamp(item.created_at))}</span><span><strong>Started</strong> ${esc(formatTimestamp(item.started_at))}</span><span><strong>Finished</strong> ${esc(formatTimestamp(item.finished_at))}</span>${item.alert_id ? `<span><strong>Alert</strong> #${item.alert_id}</span>` : ''}</div></div>${item.error ? `<div class="investigation-error"><strong>Investigation failed</strong><p>${esc(item.error)}</p></div>` : ''}<div class="investigation-result">${renderRCA(item.rca)}</div><details class="raw-evidence"><summary>Technical evidence (${Array.isArray(item.evidence) ? item.evidence.length : 0} items)</summary><pre>${esc(JSON.stringify(item.evidence || [], null, 2))}</pre></details><details class="raw-evidence"><summary>Resolved scope</summary><pre>${esc(JSON.stringify(item.scope || {}, null, 2))}</pre></details>`;
  qs('#investigations-list')?.classList.add('hidden');
  qs('#investigations-view .section-head')?.classList.add('hidden');
  qs('#close-investigation').onclick = () => {
    detail.classList.add('hidden');
    qs('#investigations-list')?.classList.remove('hidden');
    qs('#investigations-view .section-head')?.classList.remove('hidden');
  };
  const refreshButton = qs('#refresh-investigation-detail');
  if (refreshButton) refreshButton.onclick = () => openInvestigation(id).catch(error => toast(error.message));
  detail.scrollIntoView({behavior:'smooth', block:'start'});
}

function openManualInvestigation() {
  const root = qs('#investigation-editor');
  qs('#investigation-detail')?.classList.add('hidden');
  root.classList.remove('hidden');
  const enabledApps = applications.filter(item => item.enabled);
  root.innerHTML = `<h2>Run manual investigation</h2><p>Describe the observed symptom or incident. RCA Agent will use the selected Application context, enabled tools and dependencies.</p><div class="grid"><label>Application<select id="manual-investigation-app">${enabledApps.map(item => `<option value="${item.id}">${esc(item.name)}</option>`).join('')}</select><span class="hint field-help">Only enabled Applications can start new investigations.</span></label><label class="full">Incident / symptom<textarea id="manual-investigation-text" placeholder="Example: Checkout latency increased and users are seeing HTTP 500 errors" required></textarea><span class="hint field-help">Include what is failing, approximate time window, affected service/user journey, and any known alert details.</span></label></div><div class="actions"><button class="primary" id="start-manual-investigation">Start investigation</button><button id="cancel-manual-investigation">Cancel</button></div>`;
  qs('#cancel-manual-investigation').onclick = () => root.classList.add('hidden');
  qs('#start-manual-investigation').onclick = async () => {
    try {
      const applicationId = Number(qs('#manual-investigation-app').value);
      const text = qs('#manual-investigation-text').value.trim();
      if (!applicationId) throw new Error('Select an Application');
      if (text.length < 3) throw new Error('Describe the incident or symptom');
      const result = await api('/investigations/manual', {method:'POST', body:JSON.stringify({application_id: applicationId, text})});
      root.classList.add('hidden');
      toast(`Investigation #${result.investigation_id} queued`);
      await loadInvestigations();
      await openInvestigation(result.investigation_id);
    } catch (error) {
      toast(error.message);
    }
  };
  if (!enabledApps.length) qs('#start-manual-investigation').disabled = true;
  root.scrollIntoView({behavior:'smooth'});
}

qs('#new-investigation').onclick = openManualInvestigation;
qs('#refresh-investigations').onclick = () => loadInvestigations().catch(error => toast(error.message));
qs('#investigations-nav').addEventListener('click', () => {
  qs('#investigation-detail')?.classList.add('hidden');
  qs('#investigation-editor')?.classList.add('hidden');
  qs('#investigations-list')?.classList.remove('hidden');
  qs('#investigations-view .section-head')?.classList.remove('hidden');
  loadInvestigations().catch(error => toast(error.message));
});
