// Investigations workspace: history, manual runs, RCA/evidence and optional LLM transcript.

let investigations = [];
let currentLLMHistoryPayload = null;

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

function canRunInvestigationActions() {
  return !authState?.enabled || ['admin','investigator'].includes(authState?.role);
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const fallback = document.createElement('textarea');
  fallback.value = text;
  fallback.setAttribute('readonly', '');
  fallback.style.position = 'fixed';
  fallback.style.opacity = '0';
  document.body.appendChild(fallback);
  fallback.select();
  const copied = document.execCommand('copy');
  fallback.remove();
  if (!copied) throw new Error('Clipboard copy is not available in this browser');
}

async function copyLLMHistoryPart(sequence, kind, button) {
  const item = currentLLMHistoryPayload?.items?.find(entry => Number(entry.sequence) === Number(sequence));
  if (!item) {
    toast('LLM history item is no longer available');
    return;
  }
  const value = kind === 'response' ? item.response : item.request;
  const text = JSON.stringify(value || {}, null, 2);
  const original = button?.textContent || 'Copy';
  try {
    await copyTextToClipboard(text);
    if (button) button.textContent = 'Copied';
    toast(kind === 'response' ? 'LLM response copied' : 'LLM request copied');
  } catch (error) {
    toast(error.message);
  } finally {
    if (button) setTimeout(() => { button.textContent = original; }, 1200);
  }
}

async function downloadInvestigationPdf(id) {
  const button = qs('#download-investigation-pdf');
  const original = button?.textContent || 'Download PDF';
  if (button) {
    button.disabled = true;
    button.textContent = 'Preparing PDF…';
  }
  try {
    const response = await fetch(`${API}/investigations/${id}/export.pdf`, {
      credentials: 'same-origin',
      headers: {'Accept': 'application/pdf'},
    });
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json();
        message = payload?.detail || message;
      } catch (_) {}
      throw new Error(message);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `rca-investigation-${id}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    toast(`PDF download failed: ${error.message}`);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

async function retryInvestigation(id) {
  if (!canRunInvestigationActions()) return;
  const button = qs('#retry-investigation');
  if (button) {
    button.disabled = true;
    button.textContent = 'Retrying…';
  }
  try {
    const result = await api(`/investigations/${id}/retry`, {method:'POST'});
    toast(`Investigation #${result.investigation_id} queued again`);
    await loadInvestigations();
    await openInvestigation(id);
  } catch (error) {
    toast(error.message);
    if (button) {
      button.disabled = false;
      button.textContent = 'Retry investigation';
    }
  }
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
  const rows = items.map(ref => `<div class="evidence-ref"><div class="evidence-ref-head"><strong>${esc(ref.service_name || 'service')}</strong><span>${esc(friendlyValue(ref.evidence_type || 'evidence'))}</span></div><p>${esc(ref.observation || '')}</p></div>`).join('');
  return `<details class="why-evidence"><summary>Evidence · ${items.length}</summary><div class="evidence-refs">${rows}</div></details>`;
}

function renderRCA(rca) {
  if (!rca) return '<div class="empty-state">RCA result is not available yet.</div>';

  const whys = (rca.five_whys || []).map((step, index) => `<article class="why-step">
    <div class="why-marker" aria-hidden="true"><span>${esc(step.level || index + 1)}</span></div>
    <div class="why-content">
      <div class="why-step-head"><span class="why-level">Why ${esc(step.level || index + 1)}</span><span class="badge ${step.evidence_supported ? 'ok' : 'warn'}">${step.evidence_supported ? 'Supported' : 'Evidence gap'}</span></div>
      <h3>${esc(step.why || '')}</h3>
      <p>${esc(step.answer || '')}</p>
      ${evidenceRefs(step.evidence)}
    </div>
  </article>`).join('');

  const probable = (rca.probable_causes || []).map(cause => `<div class="cause-row"><div class="cause-row-head"><strong>${esc(cause.cause || '')}</strong><span class="confidence">${Math.round(Number(cause.confidence || 0) * 100)}% confidence</span></div>${evidenceRefs(cause.evidence)}</div>`).join('');

  return `
    <section class="rca-conclusion">
      <div class="rca-conclusion-head">
        <div>
          <div class="eyebrow">Conclusion</div>
          <h2>${esc(rca.summary || 'Root cause analysis')}</h2>
        </div>
        <span class="badge ${rca.insufficient_evidence ? 'warn' : 'ok'}">${rca.insufficient_evidence ? 'Evidence incomplete' : 'Evidence sufficient'}</span>
      </div>
      <div class="rca-facts">
        ${rca.root_cause ? `<div class="rca-fact"><span>Root cause</span><p>${esc(rca.root_cause)}</p></div>` : `<div class="rca-fact"><span>Root cause</span><p>Not established from the collected evidence.</p></div>`}
        ${rca.impact ? `<div class="rca-fact"><span>Impact</span><p>${esc(rca.impact)}</p></div>` : ''}
      </div>
    </section>

    <section class="rca-section why-section">
      <div class="section-title-row"><div><div class="eyebrow">Investigation chain</div><h2>5 Why</h2></div><span class="section-note">Only evidence-backed steps should be treated as confirmed.</span></div>
      <div class="why-timeline">${whys || '<div class="hint">No 5 Why steps returned.</div>'}</div>
    </section>

    <section class="rca-section">
      <div class="section-title-row"><div><div class="eyebrow">Findings</div><h2>What the investigation found</h2></div></div>
      <div class="rca-insight-grid">
        <div class="rca-panel"><h3>Probable causes</h3>${probable || '<div class="hint">None reported.</div>'}</div>
        <div class="rca-panel"><h3>Contributing factors</h3>${resultList(rca.contributing_factors)}</div>
      </div>
    </section>

    <section class="rca-section">
      <div class="section-title-row"><div><div class="eyebrow">Next steps</div><h2>Recommended response</h2></div></div>
      <div class="rca-insight-grid">
        <div class="rca-panel"><h3>Checks</h3>${resultList(rca.recommended_checks)}</div>
        <div class="rca-panel action-panel"><h3>Actions</h3>${resultList(rca.recommended_actions)}</div>
      </div>
    </section>

    ${rca.limitations?.length ? `<section class="rca-limitations"><div><div class="eyebrow">Limitations</div><h3>Evidence gaps and caveats</h3></div>${resultList(rca.limitations)}</section>` : ''}
  `;
}

function renderLLMHistoryItems(payload) {
  if (!payload.enabled) return '<div class="hint">LLM request/response history was disabled for this investigation.</div>';
  if (!payload.items?.length) return '<div class="hint">No LLM exchanges have been recorded yet.</div>';
  return `<div class="llm-history-list">${payload.items.map(item => {
    const tokenText = item.token_usage_available ? `${Number(item.total_tokens || 0).toLocaleString()} tokens` : 'tokens unavailable';
    return `<article class="llm-history-item">
      <div class="card-title-row">
        <div><strong>#${item.sequence} · ${esc(friendlyValue(item.phase || 'LLM'))}</strong><div class="hint">${esc(item.provider_type || 'LLM')}${item.model ? ` · ${esc(item.model)}` : ''} · ${esc(tokenText)} · ${esc(formatDuration(item.duration_ms))}</div></div>
        ${item.error ? '<span class="badge error-badge">Error</span>' : '<span class="badge ok">Completed</span>'}
      </div>
      <details>
        <summary><span>Request</span><button type="button" class="copy-history-button" onclick="event.preventDefault();event.stopPropagation();copyLLMHistoryPart(${Number(item.sequence)}, 'request', this)">Copy request</button></summary>
        <pre>${esc(JSON.stringify(item.request || {}, null, 2))}</pre>
      </details>
      <details>
        <summary><span>Response</span><button type="button" class="copy-history-button" onclick="event.preventDefault();event.stopPropagation();copyLLMHistoryPart(${Number(item.sequence)}, 'response', this)">Copy response</button></summary>
        <pre>${esc(JSON.stringify(item.response || {}, null, 2))}</pre>
      </details>
      ${item.error ? `<div class="investigation-error"><strong>LLM call failed</strong><p>${esc(item.error)}</p></div>` : ''}
    </article>`;
  }).join('')}</div>`;
}
async function loadLLMHistory(investigationId) {
  const root = qs('#llm-history-content');
  if (!root) return;
  try {
    const payload = await api(`/investigations/${investigationId}/llm-history`);
    currentLLMHistoryPayload = payload;
    root.innerHTML = renderLLMHistoryItems(payload);
  } catch (error) {
    currentLLMHistoryPayload = null;
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
  detail.innerHTML = `
    <div class="investigation-detail-header">
      <div class="investigation-topline">
        <button class="back-button" id="close-investigation">← Investigations</button>
        <div class="actions compact-actions">
          <span class="badge ${investigationStatusClass(item.status)}">${esc(friendlyValue(item.status || 'unknown'))}</span>
          <button id="download-investigation-pdf" type="button">Download PDF</button>
          ${pending ? '<button id="refresh-investigation-detail">Refresh</button>' : ''}
          ${item.status === 'failed' && canRunInvestigationActions() ? '<button id="retry-investigation" class="primary">Retry</button>' : ''}
        </div>
      </div>
      <div class="investigation-title-block">
        <div class="eyebrow">Investigation #${item.id} · ${esc(applicationName(item.application_id))}</div>
        <h1>${esc(item.query || 'Investigation')}</h1>
      </div>
      <div class="investigation-stats compact">
        <div><span>AI</span><strong>${esc(aiLabel(item))}</strong></div>
        <div><span>Tokens</span><strong>${esc(tokenText)}</strong></div>
        <div><span>Duration</span><strong>${esc(formatDuration(item.duration_ms))}</strong></div>
        <div><span>History</span><strong>${item.llm_history_enabled ? 'Saved' : 'Not saved'}</strong></div>
      </div>
      <div class="investigation-meta">
        <span><strong>Trigger</strong> ${esc(friendlyValue(item.trigger_type || 'unknown'))}</span>
        <span><strong>Created</strong> ${esc(formatTimestamp(item.created_at))}</span>
        <span><strong>Started</strong> ${esc(formatTimestamp(item.started_at))}</span>
        <span><strong>Finished</strong> ${esc(formatTimestamp(item.finished_at))}</span>
        ${item.alert_id ? `<span><strong>Alert</strong> #${item.alert_id}</span>` : ''}
      </div>
    </div>
    ${item.error ? `<div class="investigation-error"><strong>Investigation failed</strong><p>${esc(item.error)}</p></div>` : ''}
    <div class="investigation-result">${renderRCA(item.rca)}</div>
    <section class="technical-details">
      <div class="section-title-row"><div><div class="eyebrow">Technical details</div><h2>Evidence and model trace</h2></div><span class="section-note">Collapsed by default to keep the RCA readable.</span></div>
      <details class="raw-evidence"><summary>Collected evidence <span>${Array.isArray(item.evidence) ? item.evidence.length : 0} items</span></summary><pre>${esc(JSON.stringify(item.evidence || [], null, 2))}</pre></details>
      <details class="raw-evidence"><summary>LLM tool decisions and resolved scope</summary><pre>${esc(JSON.stringify(item.scope || {}, null, 2))}</pre></details>
      <details class="raw-evidence llm-history-panel"><summary>LLM request / response history</summary><div id="llm-history-content" class="llm-history-content"><div class="hint">Loading…</div></div></details>
    </section>
  `;
  qs('#investigations-list')?.classList.add('hidden');
  qs('#investigations-view .section-head')?.classList.add('hidden');
  qs('#close-investigation').onclick = () => {
    detail.classList.add('hidden');
    qs('#investigations-list')?.classList.remove('hidden');
    qs('#investigations-view .section-head')?.classList.remove('hidden');
  };
  const downloadButton = qs('#download-investigation-pdf');
  if (downloadButton) downloadButton.onclick = () => downloadInvestigationPdf(id);
  const refreshButton = qs('#refresh-investigation-detail');
  if (refreshButton) refreshButton.onclick = () => openInvestigation(id).catch(error => toast(error.message));
  const retryButton = qs('#retry-investigation');
  if (retryButton) retryButton.onclick = () => retryInvestigation(id);
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
  root.innerHTML = `<div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="manual-investigation-title"><div class="modal-header"><div><div class="eyebrow">Manual RCA</div><h2 id="manual-investigation-title">Run investigation</h2><p>Describe the symptom. The configured LLM can choose among the Application's read-only tools and request additional evidence in multiple rounds.</p></div><button class="modal-close" id="cancel-manual-investigation" aria-label="Close">×</button></div><div class="grid"><label>Application<select id="manual-investigation-app">${enabledApps.map(item => `<option value="${item.id}">${esc(item.name)}</option>`).join('')}</select><span class="hint field-help">Only enabled Applications can start new investigations.</span></label><label class="full">Incident / symptom<textarea id="manual-investigation-text" placeholder="Example: payment pod is restarting with OOMKilled" required></textarea><span class="hint field-help">State the observed problem. The LLM will decide which enabled read-only observations to request.</span></label><label class="switch full"><span><input id="manual-save-llm-history" type="checkbox"> Save LLM request/response history</span><span class="hint field-help">Stores prompts, structured responses and per-call metadata in MySQL for this investigation. Leave disabled to reduce database usage. Aggregate AI/model/time/token metadata is still kept when available.</span></label></div><div class="actions modal-actions"><button class="primary" id="start-manual-investigation">Start investigation</button><button id="cancel-manual-investigation-secondary">Cancel</button></div></div>`;

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
