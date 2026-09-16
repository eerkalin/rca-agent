// Human-friendly labels and contextual help. Internal API/DB values remain stable;
// only presentation changes here.

const friendlyValues = {
  in_cluster: 'In-cluster',
  kubeconfig: 'Kubeconfig',
  collect_then_analyze: 'Collect then analyze',
  agentic: 'Agentic',
  openai_compatible: 'OpenAI-compatible',
  elastic_apm: 'Elastic APM',
  elasticsearch: 'Elasticsearch',
  prometheus: 'Prometheus',
  kubernetes: 'Kubernetes',
  metrics: 'Metrics',
  logs: 'Logs',
  traces: 'Traces',
  gemini: 'Google Gemini',
  openai: 'OpenAI',
  anthropic: 'Anthropic Claude',
};

function friendlyValue(value) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  if (friendlyValues[text]) return friendlyValues[text];
  return text.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
}

const fieldHelp = {
  base_url: 'HTTP(S) endpoint of the provider. Include scheme and port when required, for example http://prometheus:9090.',
  verify_ssl: 'Validate the remote TLS certificate. Keep enabled unless your lab uses a self-signed certificate.',
  timeout_seconds: 'Maximum time RCA Agent waits for one provider request, in seconds.',
  default_step: 'Default Prometheus range-query step. Examples: 15s, 30s, 1m.',
  bearer_token: 'Optional bearer token. It is encrypted before storage and never returned to the browser.',
  username: 'Optional username for providers using basic authentication.',
  password: 'Optional password. It is encrypted before storage and never returned to the browser.',
  api_key: 'Provider API key. It is encrypted before storage and never returned to the browser.',
  queries: 'JSON array of PromQL query definitions executed for this Application or dependency.',
  lookback_minutes: 'How far back RCA Agent searches from the investigation time.',
  index_pattern: 'Elasticsearch index or data-stream pattern to search, for example logs-* or traces-apm*.',
  time_field: 'Field containing the event timestamp, usually @timestamp.',
  service_field: 'Field used to filter evidence by resolved service name.',
  namespace_field: 'Field used to filter evidence by Kubernetes namespace.',
  size: 'Maximum number of matching documents returned by the initial search.',
  search_size: 'Maximum number of trace-search hits used to find candidate trace IDs.',
  max_traces: 'Maximum number of complete traces reconstructed for one investigation step.',
  max_documents_per_trace: 'Maximum spans/transactions/errors loaded for one trace.',
  trace_id_field: 'Field containing the distributed trace identifier, usually trace.id.',
  outcome_field: 'Field describing trace/transaction outcome, usually event.outcome.',
  filters: 'Optional JSON object with additional exact-match filters.',
  message_fields: 'Optional JSON array of fields searched for log message text.',
  source_fields: 'Optional JSON array limiting fields returned from Elasticsearch.',
  mode: 'How RCA Agent authenticates to Kubernetes. In-cluster uses its Kubernetes ServiceAccount; Kubeconfig uses encrypted kubeconfig content.',
  context: 'Optional kubeconfig context name to select when a kubeconfig contains multiple contexts.',
  kubeconfig: 'Full kubeconfig YAML. The value is encrypted and write-only.',
  namespace: 'Legacy single Kubernetes namespace retained for rollback compatibility.',
  namespaces: 'Kubernetes namespaces that belong to this Application. Enter comma-separated names, for example otel-demo, payments, shared-services.',
  tail_lines: 'Maximum number of recent log lines requested per container during evidence collection.',
  model: 'Model identifier sent to the selected LLM provider, for example gemini-3.6-flash.',
  temperature: 'LLM sampling temperature. Lower values make RCA output more deterministic.',
  max_output_tokens: 'Optional maximum number of tokens the LLM may return for one response.',
};

const baseFieldValueFriendly = fieldValue;
fieldValue = function(input, field) {
  if (field.type === 'tags') {
    return input.value.split(',').map(value => value.trim()).filter((value, index, all) => value && all.indexOf(value) === index);
  }
  return baseFieldValueFriendly(input, field);
};

const baseCollectFieldsFriendly = collectFields;
collectFields = function(root, fields=[]) {
  const out = baseCollectFieldsFriendly(root, fields);
  if (Array.isArray(out.namespaces)) {
    // Mirror the first namespace to the legacy key so the previous release can
    // still read the configuration after a rollback.
    out.namespace = out.namespaces[0] || null;
  }
  return out;
};

fieldsHtml = function(fields=[], values={}, prefix='f') {
  return fields.map(f => {
    let v = values?.[f.name] ?? f.default ?? '';
    if (f.name === 'namespaces' && (!v || !v.length) && values?.namespace) v = [values.namespace];
    const help = f.help || fieldHelp[f.name] || '';
    const hint = help ? `<span class="hint field-help">${esc(help)}</span>` : '';
    const required = f.required ? '<span class="required-mark" title="Required"> *</span>' : '';
    if (f.type === 'boolean') return `<label class="switch field-with-help"><span><input data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" type="checkbox" ${v?'checked':''}> ${esc(f.label)}${required}</span>${hint}</label>`;
    if (f.type === 'select') return `<label class="field-with-help">${esc(f.label)}${required}<select data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}">${(f.options||[]).map(o=>{const value=typeof o==='object'?o.value:o;const label=typeof o==='object'?o.label:friendlyValue(o);return `<option value="${esc(value)}" ${String(v)===String(value)?'selected':''}>${esc(label)}</option>`}).join('')}</select>${hint}</label>`;
    if (f.type === 'json') return `<label class="full field-with-help">${esc(f.label)}${required}<textarea data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}">${esc(JSON.stringify(v||{},null,2))}</textarea>${hint}</label>`;
    if (f.type === 'tags') return `<label class="full field-with-help">${esc(f.label)}${required}<input data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" type="text" value="${esc(Array.isArray(v)?v.join(', '):v)}" placeholder="${esc(f.placeholder||'namespace-a, namespace-b')}">${hint}</label>`;
    if (f.type === 'textarea-password') return `<label class="full field-with-help">${esc(f.label)}${required}<textarea data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" class="secret-textarea" autocomplete="off" spellcheck="false" placeholder="${esc(f.placeholder||'')}"></textarea><span class="hint field-help">${esc(help || 'Sensitive value is write-only: saved encrypted and never loaded back into this form.')}</span></label>`;
    return `<label class="field-with-help">${esc(f.label)}${required}<input data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" type="${f.type==='password'?'password':f.type==='number'?'number':'text'}" value="${esc(v)}" placeholder="${esc(f.placeholder||'')}">${hint}</label>`;
  }).join('');
};

function addControlHelp(root, selector, text) {
  const control = root?.querySelector(selector);
  const label = control?.closest('label');
  if (!label || label.querySelector('.field-help')) return;
  const hint = document.createElement('span');
  hint.className = 'hint field-help';
  hint.textContent = text;
  label.appendChild(hint);
}

const friendlyConnectionEditor = openConnectionEditor;
openConnectionEditor = function(id=null) {
  friendlyConnectionEditor(id);
  const root = qs('#connection-editor');
  addControlHelp(root, '#conn-name', 'Display name used when binding this Connection to an Application, for example Production Prometheus.');
  addControlHelp(root, '#conn-provider', 'Provider implementation used by this Connection. Provider type cannot be changed after creation.');
  addControlHelp(root, '#conn-enabled', 'Disabled Connections remain stored but are not intended for active RCA use.');
};

const friendlyApplicationEditor = openApplicationEditor;
openApplicationEditor = async function(id=null) {
  await friendlyApplicationEditor(id);
  const root = qs('#application-editor');
  addControlHelp(root, '#app-name', 'Human-readable Application name shown in the RCA Agent UI.');
  addControlHelp(root, '#app-slug', 'Stable technical identifier. Use lowercase letters, digits and hyphens, for example payment-platform.');
  addControlHelp(root, '#app-strategy', 'Collect then analyze gathers enabled evidence first and then asks the LLM once. Agentic analyzes incrementally and may stop when evidence becomes sufficient.');
  addControlHelp(root, '#app-enabled', 'Disabled Applications remain stored but should not receive new investigations.');
  addControlHelp(root, '#app-description', 'Describe the Application’s business/technical purpose so RCA has useful context.');

  const strategy = root?.querySelector('#app-strategy');
  if (strategy) [...strategy.options].forEach(option => option.textContent = friendlyValue(option.value));
};

renderTools = function(app) {
  const root = qs('#app-tools');
  root.innerHTML = (app.tools||[]).map(t => `
    <div class="tool-row">
      <div class="row">
        <strong>${esc(friendlyValue(t.tool_type))}</strong>
        <span class="badge">${esc(provider(t.provider_type)?.label || friendlyValue(t.provider_type))}</span>
        <span class="meta">Priority ${t.priority}</span>
      </div>
      <pre>${esc(JSON.stringify(t.config||{},null,2))}</pre>
      <div class="actions"><button onclick="editTool(${app.id},${t.id})">Edit</button><button class="danger" onclick="deleteTool(${app.id},${t.id})">Delete</button></div>
    </div>`).join('') || '<p>No tools bound to this application.</p>';
};

const friendlyToolForm = toolForm;
toolForm = function(app, existing=null) {
  friendlyToolForm(app, existing);
  const forms = document.querySelectorAll('#app-tools .tool-row');
  const root = forms[forms.length - 1];
  if (!root) return;
  addControlHelp(root, '.tool-provider', 'Observability provider that will supply evidence for this tool.');
  addControlHelp(root, '.tool-type', 'Evidence type exposed by the selected provider.');
  addControlHelp(root, '.tool-connection', 'Reusable Connection containing endpoint and encrypted credentials.');
  addControlHelp(root, '.tool-priority', 'Execution order for Application tools. Lower numbers run first; tools with the same priority keep their creation order.');
  addControlHelp(root, '.tool-enabled', 'Disabled tools stay configured but are excluded from investigations.');
  const typeSelect = root.querySelector('.tool-type');
  if (typeSelect) [...typeSelect.options].forEach(option => option.textContent = friendlyValue(option.value));
};

const friendlyDependencyForm = dependencyForm;
dependencyForm = function(app) {
  friendlyDependencyForm(app);
  const forms = document.querySelectorAll('#dependencies .dep-row');
  const root = forms[forms.length - 1];
  if (!root) return;
  addControlHelp(root, '.dep-name', 'Dependency name RCA should recognize, for example Redis Session Cache or Orders Database.');
  addControlHelp(root, '.dep-type', 'Short dependency category such as Redis, Kafka, RabbitMQ, Database, External API, or Internal service.');
  addControlHelp(root, '.dep-description', 'Explain why the Application depends on it and what impact its degradation can cause.');
};

const friendlyDependencyToolForm = dependencyToolForm;
dependencyToolForm = async function(appId, depId) {
  await friendlyDependencyToolForm(appId, depId);
  const root = document.querySelector('#dependencies .tool-row');
  if (!root) return;
  addControlHelp(root, '.dt-provider', 'Provider used to observe this dependency. Current dependency diagnostics should normally use Prometheus metrics.');
  addControlHelp(root, '.dt-type', 'Evidence type supplied by the provider.');
  addControlHelp(root, '.dt-connection', 'Reusable Connection used for this dependency diagnostic tool.');
  const typeSelect = root.querySelector('.dt-type');
  if (typeSelect) [...typeSelect.options].forEach(option => option.textContent = friendlyValue(option.value));
};
