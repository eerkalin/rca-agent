// Application detail navigation. Keeps the Applications landing page focused on
// the application catalog and moves configuration into a dedicated in-app view.

function closeApplicationDetail() {
  const view = qs('#applications-view');
  const head = view?.querySelector('.section-head');
  if (head) head.classList.remove('hidden');
  qs('#applications-list')?.classList.remove('hidden');
  const editor = qs('#application-editor');
  if (editor) editor.classList.add('hidden');
  if (location.hash.startsWith('#application/')) history.replaceState(null, '', '#applications');
}

renderApplications = function() {
  const root = qs('#applications-list');
  root.innerHTML = applications.map(a => `
    <article class="card application-card">
      <div class="card-title-row">
        <div>
          <h3>${esc(a.name)}</h3>
          <div class="meta">${esc(a.slug)}</div>
        </div>
        <span class="badge ${a.enabled?'ok':'warn'}">${a.enabled?'Enabled':'Disabled'}</span>
      </div>
      ${a.description ? `<p>${esc(a.description)}</p>` : '<p class="muted">No description</p>'}
      <div class="actions">
        <button class="primary" onclick="openApplicationEditor(${a.id})">Open</button>
        <button class="danger" onclick="deleteApplication(${a.id})">Delete</button>
      </div>
    </article>`).join('') || '<div class="empty-state">No applications configured yet.</div>';
};

const applicationEditorWithLlm = openApplicationEditor;
openApplicationEditor = async function(id=null) {
  await applicationEditorWithLlm(id);

  const view = qs('#applications-view');
  const list = qs('#applications-list');
  const head = view?.querySelector('.section-head');
  const root = qs('#application-editor');
  if (!root) return;

  if (head) head.classList.add('hidden');
  if (list) list.classList.add('hidden');
  root.classList.remove('hidden');
  root.classList.add('application-detail');

  const item = id ? await api(`/applications/${id}`) : null;
  if (id) history.replaceState(null, '', `#application/${id}`);

  const existingHeader = root.querySelector('.application-detail-header');
  if (existingHeader) existingHeader.remove();
  const existingTabs = root.querySelector('.application-tabs');
  if (existingTabs) existingTabs.remove();

  const header = document.createElement('div');
  header.className = 'application-detail-header';
  header.innerHTML = `
    <button class="back-button" type="button">← Applications</button>
    <div>
      <div class="eyebrow">Application</div>
      <h1>${esc(item?.name || 'New application')}</h1>
      ${item ? `<p>${esc(item.description || item.slug)}</p>` : '<p>Create the application first, then configure its LLM, tools and dependencies.</p>'}
    </div>`;
  root.prepend(header);
  header.querySelector('.back-button').onclick = closeApplicationDetail;

  const cancel = qs('#cancel-app', root);
  if (cancel) cancel.onclick = closeApplicationDetail;

  if (!id) return;

  // Wrap the base application form as Overview. The other sections are already
  // rendered as subpanels by the existing UI and LLM enhancement layer.
  let overview = root.querySelector('[data-app-tab="overview"]');
  if (!overview) {
    overview = document.createElement('section');
    overview.className = 'application-tab-panel';
    overview.dataset.appTab = 'overview';
    const firstSubpanel = [...root.children].find(el => el.classList?.contains('subpanel'));
    const movable = [...root.children].filter(el =>
      el !== header &&
      !el.classList?.contains('application-tabs') &&
      el !== firstSubpanel &&
      !el.classList?.contains('subpanel') &&
      !el.classList?.contains('application-detail-header')
    );
    movable.forEach(el => overview.appendChild(el));
    if (firstSubpanel) root.insertBefore(overview, firstSubpanel); else root.appendChild(overview);
  }

  overview.querySelector('h2')?.replaceChildren(document.createTextNode('Overview'));

  const llmPanel = qs('#application-llm-panel', root);
  if (llmPanel) {
    llmPanel.classList.add('application-tab-panel');
    llmPanel.dataset.appTab = 'llm';
  }

  [...root.querySelectorAll('.subpanel')].forEach(panel => {
    if (panel === llmPanel) return;
    const title = panel.querySelector('h2')?.textContent?.toLowerCase() || '';
    panel.classList.add('application-tab-panel');
    if (title.includes('tool')) panel.dataset.appTab = 'tools';
    if (title.includes('dependenc')) panel.dataset.appTab = 'dependencies';
  });

  const tabs = document.createElement('nav');
  tabs.className = 'application-tabs';
  tabs.innerHTML = `
    <button type="button" data-target="overview">Overview</button>
    <button type="button" data-target="llm">LLM</button>
    <button type="button" data-target="tools">Tools</button>
    <button type="button" data-target="dependencies">Dependencies</button>`;
  header.after(tabs);

  const activate = name => {
    tabs.querySelectorAll('button').forEach(button => button.classList.toggle('active', button.dataset.target === name));
    root.querySelectorAll('.application-tab-panel').forEach(panel => panel.classList.toggle('hidden', panel.dataset.appTab !== name));
  };
  tabs.querySelectorAll('button').forEach(button => button.onclick = () => activate(button.dataset.target));
  activate('overview');
};

// If the base script refreshed before this enhancement loaded, repaint with the
// detail-aware card renderer.
try { renderApplications(); } catch (_) {}
