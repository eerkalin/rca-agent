// Keep the UI aligned with the tool bindings the backend can actually execute.
// The API performs the authoritative validation; this layer prevents invalid
// configuration from being offered in normal UI flows.

function removeUnsupportedConnectionProviders(select, existingProvider=null) {
  if (!select) return;
  [...select.options].forEach(option => {
    const item = provider(option.value);
    if (!item?.implemented && option.value !== existingProvider) option.remove();
  });
}

function enforceApplicationToolOptions(root) {
  if (!root) return;
  const providerSelect = root.querySelector('.tool-provider');
  const connectionSelect = root.querySelector('.tool-connection');
  if (providerSelect) {
    [...providerSelect.options].forEach(option => {
      const item = provider(option.value);
      if (!item?.implemented || item?.category === 'llm') option.remove();
    });
  }
  if (connectionSelect) {
    [...connectionSelect.options].forEach(option => {
      if (!option.value) option.remove();
    });
    connectionSelect.required = true;
  }
}

function enforceDependencyToolOptions(root) {
  if (!root) return;
  const providerSelect = root.querySelector('.dt-provider');
  if (providerSelect) {
    [...providerSelect.options].forEach(option => {
      if (option.value !== 'prometheus') option.remove();
    });
  }
  const connectionSelect = root.querySelector('.dt-connection');
  if (connectionSelect) {
    [...connectionSelect.options].forEach(option => {
      if (!option.value) option.remove();
    });
    connectionSelect.required = true;
  }
}

const hardenedOpenConnectionEditor = openConnectionEditor;
openConnectionEditor = function(id=null) {
  hardenedOpenConnectionEditor(id);
  const existing = connections.find(item => item.id === id);
  removeUnsupportedConnectionProviders(qs('#conn-provider'), existing?.provider_type || null);
};

const hardenedToolForm = toolForm;
toolForm = function(app, existing=null) {
  hardenedToolForm(app, existing);
  const forms = document.querySelectorAll('#app-tools .tool-row');
  const root = forms[forms.length - 1];
  enforceApplicationToolOptions(root);
  const select = root?.querySelector('.tool-provider');
  if (select) select.addEventListener('change', () => setTimeout(() => enforceApplicationToolOptions(root), 0));
};

const hardenedDependencyToolForm = dependencyToolForm;
dependencyToolForm = async function(appId, depId) {
  await hardenedDependencyToolForm(appId, depId);
  const root = document.querySelector('#dependencies .tool-row');
  enforceDependencyToolOptions(root);
  const select = root?.querySelector('.dt-provider');
  if (select) select.addEventListener('change', () => setTimeout(() => enforceDependencyToolOptions(root), 0));
};
