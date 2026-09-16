// Connection catalog/detail navigation. Connection cards intentionally expose only
// the connection name and actions; runtime configuration stays inside the detail view.

function closeConnectionDetail() {
  const view = qs('#connections-view');
  const head = view?.querySelector('.section-head');
  if (head) head.classList.remove('hidden');
  qs('#connections-list')?.classList.remove('hidden');
  const editor = qs('#connection-editor');
  if (editor) editor.classList.add('hidden');
  if (location.hash.startsWith('#connection/')) history.replaceState(null, '', '#connections');
}

renderConnections = function() {
  const root = qs('#connections-list');
  root.innerHTML = connections.map(c => {
    const canTest = ['prometheus','elasticsearch','elastic_apm','kubernetes','gemini','openai','anthropic','openai_compatible'].includes(c.provider_type);
    return `
      <article class="card connection-card">
        <h3>${esc(c.name)}</h3>
        <div class="actions">
          <button class="primary" onclick="openConnectionEditor(${c.id})">Open</button>
          ${canTest ? `<button onclick="testConnection(${c.id})">Test</button>` : ''}
          <button class="danger" onclick="deleteConnection(${c.id})">Delete</button>
        </div>
      </article>`;
  }).join('') || '<div class="empty-state">No connections configured yet.</div>';
};

const connectionEditorEnhanced = openConnectionEditor;
openConnectionEditor = function(id=null) {
  connectionEditorEnhanced(id);

  const view = qs('#connections-view');
  const list = qs('#connections-list');
  const head = view?.querySelector('.section-head');
  const root = qs('#connection-editor');
  if (!root) return;

  if (head) head.classList.add('hidden');
  if (list) list.classList.add('hidden');
  root.classList.remove('hidden');
  root.classList.add('connection-detail');

  const item = connections.find(x => x.id === id);
  const p = item ? provider(item.provider_type) : null;
  if (id) history.replaceState(null, '', `#connection/${id}`);

  const oldHeader = root.querySelector('.connection-detail-header');
  if (oldHeader) oldHeader.remove();
  const header = document.createElement('div');
  header.className = 'connection-detail-header';
  header.innerHTML = `
    <button class="back-button" type="button">← Connections</button>
    <div class="eyebrow">Connection</div>
    <h1>${esc(item?.name || 'New connection')}</h1>
    <p>${esc(p?.label || (item ? item.provider_type : 'Configure a reusable provider connection'))}</p>`;
  root.prepend(header);
  header.querySelector('.back-button').onclick = closeConnectionDetail;

  const cancel = qs('#cancel-conn', root);
  if (cancel) cancel.onclick = closeConnectionDetail;
};

try { renderConnections(); } catch (_) {}
