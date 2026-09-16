// Provider-form enhancements layered on top of the base settings console.

function apiErrorMessage(detail, status, statusText) {
  if (!detail) return `${status} ${statusText}`.trim();
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => item?.msg || JSON.stringify(item)).join('; ');
  if (typeof detail === 'object') {
    const parts = [];
    if (detail.message) parts.push(detail.message);
    if (detail.provider) parts.push(`Provider: ${detail.provider}`);
    if (detail.error_type) parts.push(`Error: ${detail.error_type}`);
    if (detail.error) parts.push(String(detail.error));
    return parts.length ? parts.join(' · ') : JSON.stringify(detail);
  }
  return String(detail);
}

// Replace the base helper so structured FastAPI errors are shown as readable text
// instead of "[object Object]". Network/browser failures are preserved verbatim.
api = async function(path, options={}) {
  let response;
  try {
    response = await fetch(API + path, {
      headers: {'Content-Type':'application/json', ...(options.headers||{})},
      ...options,
    });
  } catch (error) {
    throw new Error(`Network error: ${error?.message || error}`);
  }
  if (!response.ok) {
    let payload;
    try { payload = await response.json(); } catch (_) {}
    throw new Error(apiErrorMessage(payload?.detail, response.status, response.statusText));
  }
  return response.status === 204 ? null : response.json();
};

const providerHelp = {
  gemini: 'Native Google Gemini connection. Enter the Gemini model and API key; no Base URL is required.',
  openai: 'Native OpenAI connection. Enter the model and API key.',
  anthropic: 'Native Anthropic Claude connection.',
  openai_compatible: 'For OpenAI-compatible APIs and local gateways only. For Google Gemini, choose “Google Gemini” instead.',
  kubernetes: 'Connect to Kubernetes using the RCA Agent service account in-cluster or an encrypted kubeconfig.',
  prometheus: 'Read-only Prometheus HTTP API connection used for Application and dependency metrics.',
  elasticsearch: 'Read-only Elasticsearch connection used for application logs.',
  elastic_apm: 'Read-only Elasticsearch-backed Elastic APM trace connection.',
};

fieldsHtml = function(fields=[], values={}, prefix='f') {
  return fields.map(f => {
    const v = values?.[f.name] ?? f.default ?? '';
    const hint = f.help ? `<span class="hint">${esc(f.help)}</span>` : '';
    if (f.type === 'boolean') return `<label class="switch"><input data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" type="checkbox" ${v?'checked':''}> ${esc(f.label)}${hint}</label>`;
    if (f.type === 'select') return `<label>${esc(f.label)}<select data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}">${(f.options||[]).map(o=>{const value=typeof o==='object'?o.value:o;const label=typeof o==='object'?o.label:o;return `<option value="${esc(value)}" ${String(v)===String(value)?'selected':''}>${esc(label)}</option>`}).join('')}</select>${hint}</label>`;
    if (f.type === 'json') return `<label class="full">${esc(f.label)}<textarea data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}">${esc(JSON.stringify(v||{},null,2))}</textarea>${hint}</label>`;
    if (f.type === 'textarea-password') return `<label class="full">${esc(f.label)}<textarea data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" class="secret-textarea" autocomplete="off" spellcheck="false" placeholder="${esc(f.placeholder||'')}"></textarea><span class="hint">Sensitive value is write-only: saved encrypted and never loaded back into this form.</span>${hint}</label>`;
    return `<label>${esc(f.label)}<input data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" type="${f.type==='password'?'password':f.type==='number'?'number':'text'}" value="${esc(v)}" placeholder="${esc(f.placeholder||'')}">${hint}</label>`;
  }).join('');
};

const isLLMProvider = type => provider(type)?.category === 'llm';

renderConnections = function() {
  const root = qs('#connections-list');
  root.innerHTML = connections.map(c => {
    const p = provider(c.provider_type);
    const canTest = ['prometheus','elasticsearch','elastic_apm','kubernetes','gemini','openai','anthropic','openai_compatible'].includes(c.provider_type);
    return `<div class="card"><h3>${esc(c.name)}</h3><div class="meta">${esc(p?.label||c.provider_type)} · ${c.enabled?'enabled':'disabled'}</div><p>${esc(c.config?.base_url||c.config?.context||c.config?.model||c.config?.mode||'Runtime connection')}</p><span class="badge ${c.has_credentials?'ok':''}">${c.has_credentials?'credentials saved':'no credentials'}</span><div class="actions"><button onclick="openConnectionEditor(${c.id})">Edit</button>${canTest?`<button onclick="testConnection(${c.id})">Test</button>`:''}<button class="danger" onclick="deleteConnection(${c.id})">Delete</button></div></div>`;
  }).join('') || '<p>No connections configured yet.</p>';
};

const baseOpenConnectionEditor = openConnectionEditor;
openConnectionEditor = function(id=null) {
  baseOpenConnectionEditor(id);
  const root = qs('#connection-editor');
  const select = qs('#conn-provider');
  const item = connections.find(x => x.id === id);

  const enhanceProviderPanel = () => {
    const type = select?.value;
    const p = provider(type);
    const panel = qs('#conn-provider-fields');
    if (!panel || !p) return;
    const heading = panel.querySelector('.full');
    if (heading) {
      heading.innerHTML = `<h3>Connection settings</h3><p class="hint">${esc(providerHelp[type] || 'Runtime settings for this provider. Stored in MySQL.')}</p>`;
    }
    const existingWarning = root.querySelector('.provider-warning');
    if (existingWarning) existingWarning.remove();
    const configuredUrl = item?.config?.base_url || '';
    if (type === 'openai_compatible' && configuredUrl.includes('generativelanguage.googleapis.com')) {
      const warning = document.createElement('div');
      warning.className = 'full hint provider-warning';
      warning.textContent = 'This connection points to Google Gemini. Use the native “Google Gemini” provider instead; it does not require a Base URL.';
      panel.prepend(warning);
    }
  };

  enhanceProviderPanel();
  if (select) select.addEventListener('change', () => setTimeout(enhanceProviderPanel, 0));
};

// Make connection tests actionable: success identifies provider/model; failures show
// the structured backend diagnostic returned by /connections/{id}/test.
testConnection = async function(id) {
  const connection = connections.find(c => c.id === id);
  try {
    const result = await api(`/connections/${id}/test`, {method:'POST'});
    const details = [provider(connection?.provider_type)?.label || connection?.provider_type];
    if (result.model) details.push(result.model);
    if (result.kubernetes_version) details.push(result.kubernetes_version);
    toast(`Connection test successful${details.filter(Boolean).length ? `: ${details.filter(Boolean).join(' · ')}` : ''}`);
  } catch (error) {
    toast(`Connection test failed: ${error.message}`);
  }
};

const baseOpenApplicationEditor = openApplicationEditor;
openApplicationEditor = async function(id=null) {
  await baseOpenApplicationEditor(id);
  if (!id) return;
  const app = await api(`/applications/${id}`);
  const root = qs('#application-editor');
  const llmConnections = connections.filter(c => isLLMProvider(c.provider_type) && c.enabled);
  const panel = document.createElement('div');
  panel.className = 'subpanel';
  panel.id = 'application-llm-panel';
  panel.innerHTML = `<h2>LLM</h2><p class="hint">Choose the LLM used for scope resolution and RCA for this Application. Connection/API credentials are encrypted in MySQL.</p><div class="grid"><label>LLM connection<select id="app-llm-connection"><option value="">Legacy default Gemini</option>${llmConnections.map(c=>`<option value="${c.id}" ${c.id===app.llm_connection_id?'selected':''}>${esc(c.name)} · ${esc(provider(c.provider_type)?.label||c.provider_type)}</option>`).join('')}</select></label></div><div id="app-llm-fields" class="grid"></div><div class="actions"><button class="primary" id="save-app-llm">Save LLM settings</button></div>`;
  const firstSubpanel = root.querySelector('.subpanel');
  if (firstSubpanel) root.insertBefore(panel, firstSubpanel); else root.appendChild(panel);
  const render = () => {
    const connectionId = Number(qs('#app-llm-connection').value || 0);
    const connection = connections.find(c => c.id === connectionId);
    const p = connection ? provider(connection.provider_type) : null;
    qs('#app-llm-fields').innerHTML = p ? fieldsHtml(p.application_fields||[], app.llm_config||{}, 'app-llm') : '<div class="full hint">Migrated Applications may temporarily use the global Gemini bootstrap settings. Select an LLM connection to move configuration fully into MySQL.</div>';
  };
  render();
  qs('#app-llm-connection').onchange = render;
  qs('#save-app-llm').onclick = async () => {
    try {
      const connectionId = Number(qs('#app-llm-connection').value || 0);
      const connection = connections.find(c => c.id === connectionId);
      const p = connection ? provider(connection.provider_type) : null;
      const config = p ? collectFields(qs('#app-llm-fields'), p.application_fields||[]) : {};
      await api(`/applications/${id}`, {method:'PATCH', body:JSON.stringify({llm_connection_id: connectionId || null, llm_config: config})});
      toast('Application LLM settings saved in MySQL');
      await refresh();
    } catch (e) { toast(e.message); }
  };
};

const baseToolForm = toolForm;
toolForm = function(app, existing=null) {
  baseToolForm(app, existing);
  const selects = document.querySelectorAll('.tool-provider');
  const select = selects[selects.length - 1];
  if (!select) return;
  [...select.options].forEach(o => { if (isLLMProvider(o.value)) o.remove(); });
};

const baseDependencyToolForm = dependencyToolForm;
dependencyToolForm = async function(appId, depId) {
  await baseDependencyToolForm(appId, depId);
  const select = document.querySelector('.dt-provider');
  if (!select) return;
  [...select.options].forEach(o => { if (isLLMProvider(o.value)) o.remove(); });
};

if (typeof connections !== 'undefined' && typeof qs === 'function') {
  try { renderConnections(); } catch (_) {}
}
