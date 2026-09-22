// Investigations workspace: history, manual runs, RCA/evidence and optional LLM transcript.

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

function formatDuration(ms) {
  if (ms === null || ms === undefined) return '—';
  const value = Number(ms);
  if (!Number.isFinite(value)) return '—';
  if (value < 1000) return `${Math.round(value)} ms`;
  const seconds = value / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

function formatTokens(item) {
  if (!item?.llm_token_usage_available) return 'Unavailable';
  return Number(item.llm_total_tokens || 0).toLocaleString();
}

function aiLabel(item) {
  const providerType = item?.llm_provider_type;
  const providerMeta = providerType ? provider(providerType) : null;
  const name = providerMeta?.label || providerType || '—';
  return item?.llm_model ? `${name} · ${item.llm_model}` : name;
}

function renderInvestigations() {
  const root = qs('#investigations-list');
  if (!root) return;
  root.innerHTML = investigations.length ? `<div class="investigation-table-wrap"><table class="investigation-table"><thead><tr><th>ID</th><th>Application</th><th>Status</th><th>AI</th><th>Tokens</th><th>Duration</th><th>Created</th><th>Symptom</th><th></th></tr></thead><tbody>${investigations.map(item => `<tr><td>#${item.id}</td><td>${esc(applicationName(item.application_id))}</td><td><span class="badge ${investigationStatusClass(item.status)}">${esc(friendlyValue(item.status || 'unknown'))}</span></td><td class="investigation-ai">${esc(aiLabel(item))}</td><td>${esc(formatTokens(item))}</td><td>${esc(formatDuration(item.duration_ms))}</td><td>${esc(formatTimestamp(item.created_at))}</td><td class="investigation-query">${esc(item.query || '')}</td><td><button onclick="openInvestigation(${item.id})">Open</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty-state">No investigations yet.</div>';
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

function renderLLMHistoryItems(payload) {
  if (!payload.enabled) return '<div class="hint">LLM request/response history was disabled for this investigation.</div>';
  if (!payload.items?.length) return '<div class="hint">No LLM exchanges have been recorded yet.</div>';
  return `<div class="llm-history-list">${payload.items.map(item => {
    const tokenText = item.token_usage_available ? `${Number(item.total_tokens || 0).toLocaleString()} tokens` : 'tokens unavailable';
    return `<article class="llm-history-item"><div class="card-title-row"><div><strong>#${item.sequence} · ${esc(friendlyValue(item.phase || 'LLM'))}</strong><div class="hint">${esc(item.provider_type || 'LLM')}${item.model ? ` · ${esc(item.model)}` : ''} · ${esc(tokenText)} · ${esc(formatDuration(item.duration_ms))}</div></div>${item.error ? '<span class="badge error-badge">Error</span>' : '<span class="badge ok">Completed</span>'}</div><details><summary>Request</summary><pre>${esc(JSON.stringify(item.request || {}, null, 2))}</pre></details><details><summary>Response</summary><pre>${esc(JSON.stringify(item.response || {}, null, 2))}</pre></details>${item.error ? `<div class="investigation-error"><strong>LLM call failed</strong><p>${esc(item.error)}</p></div>` : ''}</article>`;
  }).join('')}</div>`;
}

async function loadLLMHistory(investigationId) {
  const root = qs('#llm-history-content');
  if (!root) return;
  try {
    const payload = await api(`/investigations/${investigationId}/llm-history`);
    root.innerHTML = renderLLMHistoryItems(payload);
  } catch (error) {
    root.innerHTML = `<div class="investigation-error"><strong>Unable to load LLM history</strong><p>${esc(error.message)}</p></div>`;
  }
}

async function openInvestigation(id) {
  const item = await api(`/investigations/${id}`);
  const detail = qs('#investigation-detail');
  closeManualInvestigation();
  detail.classList.remove('hidden');
  const pending = item.status === 'queued' || item.status === 'running';
  const tokenText = item.llm_token_usage_available ? Number(item.llm_total_tokens || 0).toLocaleString() : 'Unavailable';
  detail.innerHTML = `<div class="investigation-detail-header"><button class="back-button" id="close-investigation">← Back to investigations</button><div class="card-title-row"><div><div class="eyebrow">Investigation #${item.id}</div><h1>${esc(applicationName(item.application_id))}</h1><p>${esc(item.query || '')}</p></div><div class="actions compact-actions"><span class="badge ${investigationStatusClass(item.status)}">${esc(friendlyValue(item.status || 'unknown'))}</span>${pending ? '<button id="refresh-investigation-detail">Refresh result</button>' : ''}</div></div><div class="investigation-stats"><div><span>AI</span><strong>${esc(aiLabel(item))}</strong></div><div><span>Total tokens</span><strong>${esc(tokenText)}</strong></div><div><span>Investigation time</span><strong>${esc(formatDuration(item.duration_ms))}</strong></div><div><span>LLM history</span><strong>${item.llm_history_enabled ? 'Saved' : 'Not saved'}</strong></div></div><div class="investigation-meta"><span><strong>Trigger</strong> ${esc(friendlyValue(item.trigger_type || 'unknown'))}</span><span><strong>Created</strong> ${esc(formatTimestamp(item.created_at))}</span><span><strong>Started</strong> ${esc(formatTimestamp(item.started_at))}</span><span><strong>Finished</strong> ${esc(formatTimestamp(item.finished_at))}</span>${item.alert_id ? `<span><strong>Alert</strong> #${item.alert_id}</span>` : ''}</div></div>${item.error ? `<div class="investigation-error"><strong>Investigation failed</strong><p>${esc(item.error)}</p></div>` : ''}<div class="investigation-result">${renderRCA(item.rca)}</div><details class="raw-evidence"><summary>Technical evidence (${Array.isArray(item.evidence) ? item.evidence.length : 0} items)</summary><pre>${esc(JSON.stringify(item.evidence || [], null, 2))}</pre></details><details class="raw-evidence"><summary>Resolved scope / agent decisions</summary><pre>${esc(JSON.stringify(item.scope || {}, null, 2))}</pre></details><details class="raw-evidence llm-history-panel"><summary>LLM request / response history</summary><div id="llm-history-content" class="llm-history-content"><div class="hint">Loading…</div></div></details>`;
  qs('#investigations-list')?.classList.add('hidden');
  qs('#investigations-view .section-head')?.classList.add('hidden');
  qs('#close-investigation').onclick = () => {
    detail.classList.add('hidden');
    qs('#investigations-list')?.classList.remove('hidden');
    qs('#investigations-view .section-head')?.classList.remove('hidden');
  };
  const refreshButton = qs('#refresh-investigation-detail');
  if (refreshButton) refreshButton.onclick = () => openInvestigation(id).catch(error => toast(error.message));
  loadLLMHistory(id);
  detail.scrollIntoView({behavior:'smooth', block:'start'});
}

function closeManualInvestigation() {
  const root = qs('#investigation-editor');
  if (!root) return;
  root.classList.add('hidden');
  root.classList.remove('modal-backdrop');
  root.innerHTML = '';
}

function openManualInvestigation() {
  const root = qs('#investigation-editor');
  const enabledApps = applications.filter(item => item.enabled);
  root.classList.remove('hidden');
  root.classList.add('modal-backdrop');
  root.innerHTML = `<div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="manual-investigation-title"><div class="modal-header"><div><div class="eyebrow">Manual RCA</div><h2 id="manual-investigation-title">Run investigation</h2><p>Describe the symptom. The configured LLM can choose among the Application's read-only tools and request additional evidence in multiple rounds.</p></div><button class="modal-close" id="cancel-manual-investigation" aria-label="Close">×</button></div><div class="grid"><label>Application<select id="manual-investigation-app">${enabledApps.map(item => `<option value="${item.id}">${esc(item.name)}</option>`).join('')}</select><span class="hint field-help">Only enabled Applications can start new investigations.</span></label><label class="full">Incident / symptom<textarea id="manual-investigation-text" placeholder="Example: payment pod is restarting with OOMKilled" required></textarea><span class="hint field-help">State the observed problem. The agent will decide which enabled read-only observations are useful.</span></label><label class="switch full"><span><input id="manual-save-llm-history" type="checkbox"> Save LLM request/response history</span><span class="hint field-help">Stores prompts, structured responses and per-call metadata in MySQL for this investigation. Leave disabled to reduce database usage. Aggregate AI/model/time/token metadata is still kept when available.</span></label></div><div class="actions modal-actions"><button class="primary" id="start-manual-investigation">Start investigation</button><button id="cancel-manual-investigation-secondary">Cancel</button></div></div>`;

  const appSelect = qs('#manual-investigation-app');
  const historyToggle = qs('#manual-save-llm-history');
  const applyDefaultHistory = () => {
    const app = applications.find(item => item.id === Number(appSelect?.value));
    historyToggle.checked = Boolean(app?.llm_history_enabled);
  };
  appSelect?.addEventListener('change', applyDefaultHistory);
  applyDefaultHistory();

  qs('#cancel-manual-investigation').onclick = closeManualInvestigation;
  qs('#cancel-manual-investigation-secondary').onclick = closeManualInvestigation;
  root.onclick = event => { if (event.target === root) closeManualInvestigation(); };

  qs('#start-manual-investigation').onclick = async () => {
    const startButton = qs('#start-manual-investigation');
    try {
      const applicationId = Number(appSelect.value);
      const text = qs('#manual-investigation-text').value.trim();
      if (!applicationId) throw new Error('Select an Application');
      if (text.length < 3) throw new Error('Describe the incident or symptom');
      startButton.disabled = true;
      startButton.textContent = 'Starting…';
      const result = await api('/investigations/manual', {
        method:'POST',
        body:JSON.stringify({
          application_id: applicationId,
          text,
          save_llm_history: Boolean(historyToggle.checked),
        }),
      });
      closeManualInvestigation();
      toast(`Investigation #${result.investigation_id} queued`);
      await loadInvestigations();
      await openInvestigation(result.investigation_id);
    } catch (error) {
      toast(error.message);
      startButton.disabled = false;
      startButton.textContent = 'Start investigation';
    }
  };
  if (!enabledApps.length) qs('#start-manual-investigation').disabled = true;
  setTimeout(() => qs('#manual-investigation-text')?.focus(), 0);
}

qs('#new-investigation').onclick = openManualInvestigation;
qs('#refresh-investigations').onclick = () => loadInvestigations().catch(error => toast(error.message));
qs('#investigations-nav').addEventListener('click', () => {
  closeManualInvestigation();
  qs('#investigation-detail')?.classList.add('hidden');
  qs('#investigations-list')?.classList.remove('hidden');
  qs('#investigations-view .section-head')?.classList.remove('hidden');
  loadInvestigations().catch(error => toast(error.message));
});
