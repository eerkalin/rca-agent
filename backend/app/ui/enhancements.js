// Provider-form enhancements layered on top of the base settings console.
// Kept separate so provider-specific UX can evolve without coupling app.js to
// individual integrations.

fieldsHtml = function(fields=[], values={}, prefix='f') {
  return fields.map(f => {
    const v = values?.[f.name] ?? f.default ?? '';
    if (f.type === 'boolean') {
      return `<label class="switch"><input data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" type="checkbox" ${v?'checked':''}> ${esc(f.label)}</label>`;
    }
    if (f.type === 'select') {
      return `<label>${esc(f.label)}<select data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}">${(f.options||[]).map(o=>`<option ${String(v)===String(o)?'selected':''}>${esc(o)}</option>`).join('')}</select></label>`;
    }
    if (f.type === 'json') {
      return `<label class="full">${esc(f.label)}<textarea data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}">${esc(JSON.stringify(v||{},null,2))}</textarea></label>`;
    }
    if (f.type === 'textarea-password') {
      return `<label class="full">${esc(f.label)}<textarea data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" class="secret-textarea" autocomplete="off" spellcheck="false" placeholder="${esc(f.placeholder||'')}"></textarea><span class="hint">Sensitive value is write-only: saved encrypted and never loaded back into this form.</span></label>`;
    }
    return `<label>${esc(f.label)}<input data-field="${esc(f.name)}" id="${prefix}-${esc(f.name)}" type="${f.type==='password'?'password':f.type==='number'?'number':'text'}" value="${esc(v)}" placeholder="${esc(f.placeholder||'')}"></label>`;
  }).join('');
};

renderConnections = function() {
  const root = qs('#connections-list');
  root.innerHTML = connections.map(c => {
    const p = provider(c.provider_type);
    const canTest = ['prometheus','elasticsearch','kubernetes'].includes(c.provider_type);
    return `<div class="card"><h3>${esc(c.name)}</h3><div class="meta">${esc(p?.label||c.provider_type)} · ${c.enabled?'enabled':'disabled'}</div><p>${esc(c.config?.base_url||c.config?.context||c.config?.mode||'Runtime connection')}</p><span class="badge ${c.has_credentials?'ok':''}">${c.has_credentials?'credentials saved':'no credentials'}</span><div class="actions"><button onclick="openConnectionEditor(${c.id})">Edit</button>${canTest?`<button onclick="testConnection(${c.id})">Test</button>`:''}<button class="danger" onclick="deleteConnection(${c.id})">Delete</button></div></div>`;
  }).join('') || '<p>No connections configured yet.</p>';
};

// Re-render once after overriding the base renderer.
if (typeof connections !== 'undefined' && typeof qs === 'function') {
  try { renderConnections(); } catch (_) {}
}
