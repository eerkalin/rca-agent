// Authentication and RBAC presentation layer. Server-side middleware remains the
// authority; these controls only make the UI match the effective role.

let authState = {enabled:false, user:null, role:'admin'};
let managedUsers = [];

async function authFetch(path, options={}) {
  const response = await fetch(API + path, {
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {'Content-Type':'application/json', ...(options.headers||{})},
    ...options,
  });
  let payload = null;
  try { payload = await response.json(); } catch (_) {}
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : `${response.status} ${response.statusText}`));
  }
  return payload;
}

function showLogin(message='') {
  qs('#auth-gate').classList.remove('hidden');
  qs('#app-shell').classList.add('auth-locked');
  qs('.topbar').classList.add('auth-locked');
  const error = qs('#login-error');
  error.textContent = message;
  error.classList.toggle('hidden', !message);
  setTimeout(()=>qs('#login-username')?.focus(), 0);
}

function hideLogin() {
  qs('#auth-gate').classList.add('hidden');
  qs('#app-shell').classList.remove('auth-locked');
  qs('.topbar').classList.remove('auth-locked');
  qs('#login-error').classList.add('hidden');
}

function roleLabel(role) {
  return role === 'admin' ? 'Admin' : role === 'investigator' ? 'Investigator' : 'Read-only';
}

function setRoleDisabled(control, shouldDisable) {
  if (shouldDisable) {
    if (!control.disabled) control.dataset.rbacDisabled = 'role';
    control.disabled = true;
    return;
  }
  if (control.dataset.rbacDisabled === 'role') {
    control.disabled = false;
    delete control.dataset.rbacDisabled;
  }
}

function applyRoleControls() {
  const role = authState.role || 'readonly';
  document.body.dataset.role = role;
  const admin = role === 'admin';
  const investigator = role === 'investigator';

  qs('#new-application')?.classList.toggle('hidden', !admin);
  qs('#new-connection')?.classList.toggle('hidden', !admin);
  qs('#new-investigation')?.classList.toggle('hidden', !(admin || investigator));
  qs('#users-nav')?.classList.toggle('hidden', !admin || !authState.enabled);

  document.querySelectorAll('#applications-view button.danger,#connections-view button.danger')
    .forEach(button => button.classList.toggle('hidden', !admin));
  document.querySelectorAll('#applications-view .primary,#connections-view .primary')
    .forEach(button => button.classList.toggle('hidden', !admin));

  document.querySelectorAll('#applications-view button').forEach(button => {
    const text = button.textContent.trim().toLowerCase();
    const adminOnly = ['add tool','add dependency','save application','save llm settings','save tool','save dependency','save'].includes(text);
    if (adminOnly) button.classList.toggle('hidden', !admin);
  });

  document.querySelectorAll('#connections-view button').forEach(button => {
    const onclick = button.getAttribute('onclick') || '';
    const text = button.textContent.trim().toLowerCase();
    const adminOnly = ['save','delete'].some(word => text.includes(word));
    if (adminOnly) button.classList.toggle('hidden', !admin);
    if (onclick.includes('testConnection')) button.classList.toggle('hidden', !(admin || investigator));
  });

  // Role-based disabling must be reversible when another user signs in without
  // reloading the page. Preserve controls that were already disabled for a
  // functional reason (for example immutable provider type on an existing
  // Connection).
  document.querySelectorAll(
    '#application-editor input,#application-editor select,#application-editor textarea,' +
    '#connection-editor input,#connection-editor select,#connection-editor textarea'
  ).forEach(control => setRoleDisabled(control, !admin));
}

function resetWorkspaceAfterLogout() {
  managedUsers = [];
  catalog = [];
  connections = [];
  applications = [];
  if (typeof investigations !== 'undefined') investigations = [];
  document.querySelectorAll('[data-rbac-disabled="role"]').forEach(control => {
    control.disabled = false;
    delete control.dataset.rbacDisabled;
  });
  document.querySelectorAll('.view').forEach(view => view.classList.add('hidden'));
  qs('#applications-view')?.classList.remove('hidden');
  document.querySelectorAll(
    '#application-editor,#connection-editor,#user-editor,#investigation-editor,#investigation-detail'
  ).forEach(node => node?.classList.add('hidden'));
  qs('#login-password').value = '';
  qs('#login-error').textContent = '';
  qs('#login-error').classList.add('hidden');
}

async function establishAuthenticatedSession() {
  // Verify that the HttpOnly session cookie from /login is active before
  // rehydrating the workspace. This avoids carrying stale role/UI state across
  // logout -> login transitions.
  const current = await authFetch('/auth/me');
  authState = {
    enabled: true,
    user: current.user,
    role: current.effective_role,
  };
  hideLogin();
  renderSession();
  await refresh();
  applyRoleControls();

  if (!qs('#investigations-view')?.classList.contains('hidden') && typeof loadInvestigations === 'function') {
    await loadInvestigations();
  }
  if (!qs('#users-view')?.classList.contains('hidden') && authState.role === 'admin') {
    await loadUsers();
  }
}

function renderSession() {
  const controls = qs('#session-controls');
  if (!authState.enabled) {
    controls.classList.add('hidden');
    qs('#users-nav')?.classList.add('hidden');
    return;
  }
  controls.classList.remove('hidden');
  qs('#session-user').textContent = `${authState.user?.username || 'user'} · ${roleLabel(authState.role)}`;
  applyRoleControls();
}

async function loadAuthState() {
  const health = await fetch(`${API}/health`, {credentials:'same-origin', cache:'no-store'}).then(response => response.json());
  if (!health.auth_enabled) {
    authState = {enabled:false, user:null, role:'admin'};
    hideLogin();
    renderSession();
    return true;
  }
  try {
    const current = await authFetch('/auth/me');
    authState = {enabled:true, user:current.user, role:current.effective_role};
    hideLogin();
    renderSession();
    return true;
  } catch (error) {
    authState = {enabled:true, user:null, role:'readonly'};
    showLogin();
    return false;
  }
}

qs('#login-form').onsubmit = async event => {
  event.preventDefault();
  const submit = qs('#login-form button[type="submit"]');
  if (submit) { submit.disabled = true; submit.textContent = 'Signing in…'; }
  try {
    await authFetch('/auth/login', {
      method:'POST',
      body:JSON.stringify({username:qs('#login-username').value.trim(), password:qs('#login-password').value}),
    });
    qs('#login-password').value = '';
    await establishAuthenticatedSession();
  } catch (error) {
    authState = {enabled:true, user:null, role:'readonly'};
    showLogin(error.message);
  } finally {
    if (submit) { submit.disabled = false; submit.textContent = 'Sign in'; }
  }
};

qs('#logout-button').onclick = async () => {
  try { await authFetch('/auth/logout', {method:'POST'}); } catch (_) {}
  authState = {enabled:true, user:null, role:'readonly'};
  resetWorkspaceAfterLogout();
  renderSession();
  showLogin();
};

const rbacRenderApplications = renderApplications;
renderApplications = function() {
  rbacRenderApplications();
  applyRoleControls();
};

const rbacRenderConnections = renderConnections;
renderConnections = function() {
  rbacRenderConnections();
  applyRoleControls();
};

const rbacOpenApplicationEditor = openApplicationEditor;
openApplicationEditor = async function(id=null) {
  await rbacOpenApplicationEditor(id);
  applyRoleControls();
};

const rbacOpenConnectionEditor = openConnectionEditor;
openConnectionEditor = function(id=null) {
  rbacOpenConnectionEditor(id);
  setTimeout(applyRoleControls, 0);
};

function renderUsers() {
  const root = qs('#users-list');
  root.innerHTML = managedUsers.map(user => `<div class="card user-card"><div class="card-title-row"><h3>${esc(user.username)}</h3><span class="badge ${user.enabled?'ok':'warn'}">${user.enabled?'enabled':'disabled'}</span></div><p>${esc(roleLabel(user.role))}</p><div class="actions"><button onclick="openUserEditor(${user.id})">Edit</button><button class="danger" onclick="deleteManagedUser(${user.id})">Delete</button></div></div>`).join('') || '<div class="empty-state">No users.</div>';
}

async function loadUsers() {
  if (authState.role !== 'admin') return;
  const result = await authFetch('/auth/users');
  managedUsers = result.items || [];
  renderUsers();
}

function openUserEditor(id=null) {
  const item = managedUsers.find(user => user.id === id);
  const root = qs('#user-editor');
  root.classList.remove('hidden');
  root.innerHTML = `<h2>${item?'Edit user':'New user'}</h2><div class="grid"><label>Username<input id="user-name" value="${esc(item?.username||'')}" required></label><label>Role<select id="user-role"><option value="admin" ${item?.role==='admin'?'selected':''}>Admin</option><option value="investigator" ${item?.role==='investigator'?'selected':''}>Investigator</option><option value="readonly" ${!item||item?.role==='readonly'?'selected':''}>Read-only</option></select></label><label>Password${item?' (leave blank to keep current)':''}<input id="user-password" type="password" autocomplete="new-password"></label><label class="switch"><input id="user-enabled" type="checkbox" ${item?.enabled===false?'':'checked'}> Enabled</label></div><div class="actions"><button class="primary" id="save-user">Save user</button><button id="cancel-user">Cancel</button></div>`;
  qs('#cancel-user').onclick = () => root.classList.add('hidden');
  qs('#save-user').onclick = async () => {
    try {
      const payload = {username:qs('#user-name').value.trim(), role:qs('#user-role').value, enabled:qs('#user-enabled').checked};
      const password = qs('#user-password').value;
      if (password) payload.password = password;
      if (!item && !password) throw new Error('Password is required for a new user');
      if (item) await authFetch(`/auth/users/${item.id}`, {method:'PATCH', body:JSON.stringify(payload)});
      else await authFetch('/auth/users', {method:'POST', body:JSON.stringify(payload)});
      root.classList.add('hidden');
      await loadUsers();
      toast('User saved');
    } catch (error) { toast(error.message); }
  };
}

async function deleteManagedUser(id) {
  if (!confirm('Delete this user?')) return;
  try {
    await authFetch(`/auth/users/${id}`, {method:'DELETE'});
    await loadUsers();
    toast('User deleted');
  } catch (error) { toast(error.message); }
}

qs('#new-user').onclick = () => openUserEditor();
const usersNav = qs('#users-nav');
if (usersNav) usersNav.addEventListener('click', () => loadUsers().catch(error => toast(error.message)));

loadAuthState().then(authenticated => {
  if (authenticated) {
    refresh().then(applyRoleControls).catch(error => {
      if (authState.enabled && String(error.message).includes('Authentication')) showLogin();
    });
  }
}).catch(error => showLogin(error.message));
