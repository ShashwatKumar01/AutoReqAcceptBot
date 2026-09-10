const TOKEN_KEY = 'rab_admin_token';

const state = {
  tab: 'dashboard',
  tables: {
    users: { page: 1, q: '', status: '', sort: 'created_at', order: 'desc' },
    chats: { page: 1, q: '', status: '', type: '', sort: 'created_at', order: 'desc' },
    requests: { page: 1, q: '', status: '', chat_id: '', sort: 'created_at', order: 'desc' },
    broadcasts: { page: 1, status: '', owner_id: '', sort: 'created_at', order: 'desc' },
  },
};

function $(sel) { return document.querySelector(sel); }
function $all(sel) { return [...document.querySelectorAll(sel)]; }

function token() { return localStorage.getItem(TOKEN_KEY) || ''; }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}), Authorization: `Bearer ${token()}` };
  if (opts.body) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    showLogin();
    throw new Error('Unauthorized');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function showLogin() {
  $('#login-screen').classList.remove('hidden');
  $('#app').classList.add('hidden');
}

function showApp() {
  $('#login-screen').classList.add('hidden');
  $('#app').classList.remove('hidden');
}

function switchTab(name) {
  state.tab = name;
  $all('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $all('.tab').forEach(t => t.classList.remove('active'));
  const panel = $(`#tab-${name}`);
  if (panel) panel.classList.add('active');
  const titles = {
    dashboard: 'Dashboard',
    bot: 'Bot',
    users: 'Users',
    chats: 'Chats & settings',
    requests: 'Join Requests',
    broadcasts: 'Broadcasts',
    'create-broadcast': 'New Broadcast',
  };
  $('#page-title').textContent = titles[name] || name;
  loadCurrentTab();
}

async function loadCurrentTab() {
  try {
    if (state.tab === 'dashboard') await loadDashboard();
    else if (state.tab === 'bot') await loadBot();
    else if (state.tab === 'users') await loadUsers();
    else if (state.tab === 'chats') await loadChats();
    else if (state.tab === 'requests') await loadRequests();
    else if (state.tab === 'broadcasts') await loadBroadcasts();
  } catch (e) {
    console.error(e);
  }
}

function renderCards(stats) {
  const el = $('#stats-cards');
  el.innerHTML = `
    <div class="card"><h3>Users</h3><div class="value">${stats.users.total}</div>
      <div class="sub">${stats.users.active} active · +${stats.users.new_today} today</div></div>
    <div class="card"><h3>Chats</h3><div class="value">${stats.chats.total}</div>
      <div class="sub">${stats.chats.connected} connected · ${stats.chats.channels} channels</div></div>
    <div class="card"><h3>Join Requests</h3><div class="value">${stats.join_requests.total}</div>
      <div class="sub">${stats.join_requests.approved} approved · ${stats.join_requests.pending} pending</div></div>
    <div class="card"><h3>Broadcasts</h3><div class="value">${stats.broadcasts.total}</div>
      <div class="sub">${stats.broadcasts.running} running · ${stats.broadcasts.paused} paused</div></div>
  `;
}

async function loadDashboard() {
  const [stats, bot] = await Promise.all([
    api('/api/admin/stats'),
    api('/api/admin/bot').catch(() => null),
  ]);
  renderCards(stats);
  renderBotStrip(bot);
}

function renderBotStrip(bot) {
  const el = $('#dashboard-bot-strip');
  if (!el) return;
  if (!bot) {
    el.innerHTML = '';
    return;
  }
  const tg = bot.telegram || {};
  const name = tg.first_name || 'Bot';
  const user = tg.username ? `@${tg.username}` : '—';
  el.innerHTML = `
    <strong>${esc(name)}</strong> (${esc(user)}) · ID <code>${tg.id || '—'}</code>
    · Token: <code>${esc(bot.token_masked || '—')}</code>
    <button type="button" class="btn sm" id="dash-bot-more">Full bot info</button>
  `;
  $('#dash-bot-more')?.addEventListener('click', () => switchTab('bot'));
}

function renderBotDetail(bot) {
  const el = $('#bot-detail');
  if (!el) return;
  const tg = bot.telegram || {};
  const dep = bot.deployment || {};
  el.innerHTML = `
    <h3>🤖 ${esc(tg.first_name || 'Bot')} ${tg.username ? `(@${esc(tg.username)})` : ''}</h3>
    <div class="settings-grid">
      <div class="kv"><b>Telegram bot ID</b>${tg.id ?? '—'}</div>
      <div class="kv"><b>Username</b>${tg.username ? `@${esc(tg.username)}` : '—'}</div>
      <div class="kv"><b>Environment</b>${esc(dep.environment || '—')}</div>
      <div class="kv"><b>Webhook URL</b>${esc(dep.webhook_url || '—')}</div>
      <div class="kv"><b>Admin panel</b>${esc(dep.admin_web_url || '—')}</div>
      <div class="kv"><b>Super admin IDs</b>${(bot.super_admin_ids || []).join(', ') || '—'}</div>
    </div>
    <h4>BOT_TOKEN</h4>
    <div class="token-row">
      <code id="bot-token-value">${esc(bot.bot_token || bot.token_masked || 'not set')}</code>
      ${bot.bot_token ? '<button type="button" class="btn sm" id="copy-bot-token">Copy</button>' : ''}
    </div>
    <p style="color:var(--muted);font-size:.85rem">Keep this secret — only share with trusted admins.</p>
  `;
  $('#copy-bot-token')?.addEventListener('click', () => {
    navigator.clipboard?.writeText(bot.bot_token);
  });
}

async function loadBot() {
  const bot = await api('/api/admin/bot');
  renderBotDetail(bot);
}

function renderButtonsList(buttons) {
  if (!buttons || !buttons.length) return '<em style="color:var(--muted)">No buttons</em>';
  return `<ul class="btn-list">${buttons.map((b, i) =>
    `<li>${i + 1}. <strong>${esc(b.text || '?')}</strong> → ${esc(b.url || b.callback_data || '—')}</li>`
  ).join('')}</ul>`;
}

function renderChatDetail(data) {
  const c = data.chat || {};
  const w = data.welcome || {};
  const g = data.goodbye || {};
  const a = data.approval || {};
  const panel = $('#chat-detail');
  panel.classList.remove('hidden');
  panel.innerHTML = `
    <h3>💬 ${esc(c.title || 'Chat')} <code>${c.chat_id}</code></h3>
    <button type="button" class="btn sm" id="chat-detail-close">Close</button>
    <div class="settings-grid">
      <div class="kv"><b>Chat ID</b><code>${c.chat_id}</code></div>
      <div class="kv"><b>Type</b>${esc(c.type || '—')}</div>
      <div class="kv"><b>Status</b>${statusPill(c.status || 'unknown')}</div>
      <div class="kv"><b>Owner admin ID</b>${c.admin_id ?? '—'}</div>
      <div class="kv"><b>Linked admin IDs</b>${(data.admin_user_ids || []).join(', ') || '—'}</div>
      <div class="kv"><b>Approved members</b>${c.total_approved ?? 0}</div>
      <div class="kv"><b>Join requests</b>${c.total_join_requests ?? 0}</div>
      <div class="kv"><b>Welcome sent</b>${c.total_welcome_sent ?? 0}</div>
    </div>

    <h4>Auto-approve</h4>
    <div class="settings-grid">
      <div class="kv"><b>Enabled</b>${a.enabled ? '✅ ON' : '❌ OFF'}</div>
      <div class="kv"><b>Delay (sec)</b>${a.delay ?? 0}</div>
      <div class="kv"><b>Captcha</b>${a.captcha_enabled ? 'ON' : 'OFF'}</div>
    </div>

    <h4>Welcome message</h4>
    <div class="settings-grid">
      <div class="kv"><b>Enabled</b>${w.enabled ? '✅ ON' : '❌ OFF'}</div>
      <div class="kv"><b>Trigger</b>${esc(w.trigger)}</div>
      <div class="kv"><b>Delay (sec)</b>${w.delay_seconds ?? 0}</div>
      <div class="kv"><b>Frequency</b>${esc(w.frequency)}</div>
      <div class="kv"><b>Media</b>${w.media_file_id ? `${esc(w.media_type)} (file_id set)` : '—'}</div>
    </div>
    <p><b>Text</b></p>
    <pre class="settings-pre">${esc(w.text || '(empty)')}</pre>
    <p><b>Buttons (${(w.buttons || []).length})</b></p>
    ${renderButtonsList(w.buttons)}

    <h4>Goodbye message</h4>
    <div class="settings-grid">
      <div class="kv"><b>Enabled</b>${g.enabled ? '✅ ON' : '❌ OFF'}</div>
      <div class="kv"><b>Frequency</b>${esc(g.frequency)}</div>
      <div class="kv"><b>Media</b>${g.media_file_id ? `${esc(g.media_type)} (file_id set)` : '—'}</div>
    </div>
    <p><b>Text</b></p>
    <pre class="settings-pre">${esc(g.text || '(empty)')}</pre>
    <p><b>Buttons (${(g.buttons || []).length})</b></p>
    ${renderButtonsList(g.buttons)}

    <h4>All stored settings (raw)</h4>
    <pre class="settings-pre">${esc(JSON.stringify(data.settings_raw, null, 2))}</pre>
  `;
  $('#chat-detail-close')?.addEventListener('click', () => panel.classList.add('hidden'));
}

async function showChatDetail(chatId) {
  const data = await api(`/api/admin/chats/${chatId}`);
  renderChatDetail(data);
  switchTab('chats');
}

function buildQuery(table) {
  const s = state.tables[table];
  const p = new URLSearchParams();
  p.set('page', s.page);
  p.set('limit', '25');
  p.set('sort', s.sort);
  p.set('order', s.order);
  if (s.q) p.set('q', s.q);
  if (s.status) p.set('status', s.status);
  if (s.type) p.set('type', s.type);
  if (s.chat_id) p.set('chat_id', s.chat_id);
  if (s.owner_id) p.set('owner_id', s.owner_id);
  return p.toString();
}

function renderTable(tableId, headers, rows) {
  const table = $(`#${tableId}`);
  table.querySelector('thead').innerHTML = `<tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>`;
  table.querySelector('tbody').innerHTML = rows.length
    ? rows.join('')
    : '<tr><td colspan="99" style="text-align:center;color:var(--muted)">No results</td></tr>';
}

function renderPager(table, data) {
  const el = $(`.pager[data-table="${table}"]`);
  if (!el) return;
  el.innerHTML = `
    <button class="btn sm" data-page="prev" ${data.page <= 1 ? 'disabled' : ''}>‹</button>
    <span>Page ${data.page} / ${data.pages} (${data.total} total)</span>
    <button class="btn sm" data-page="next" ${data.page >= data.pages ? 'disabled' : ''}>›</button>
  `;
  el.querySelector('[data-page="prev"]')?.addEventListener('click', () => {
    state.tables[table].page = Math.max(1, data.page - 1);
    loadCurrentTab();
  });
  el.querySelector('[data-page="next"]')?.addEventListener('click', () => {
    state.tables[table].page = Math.min(data.pages, data.page + 1);
    loadCurrentTab();
  });
}

function statusPill(s) {
  return `<span class="status-pill status-${s}">${s}</span>`;
}

function progressBar(p) {
  const pct = p?.percent || 0;
  return `<div class="progress-bar" title="${p?.sent || 0}/${p?.total || 0}"><span style="width:${pct}%"></span></div>
    <small>${pct}% (${p?.sent || 0} sent, ${p?.failed || 0} failed)</small>`;
}

async function loadUsers() {
  const data = await api(`/api/admin/users?${buildQuery('users')}`);
  const rows = data.items.map(u => `<tr>
    <td>${u.telegram_id}</td>
    <td>@${u.username || '—'}</td>
    <td>${u.first_name || ''} ${u.last_name || ''}</td>
    <td>${statusPill(u.status || 'active')}</td>
    <td>${(u.chat_ids || []).length}</td>
    <td>${fmtDate(u.created_at)}</td>
  </tr>`);
  renderTable('users-table', ['ID', 'Username', 'Name', 'Status', 'Chats', 'Created'], rows);
  renderPager('users', data);
}

async function loadChats() {
  const data = await api(`/api/admin/chats?${buildQuery('chats')}`);
  const rows = data.items.map(c => {
    const s = c.settings_summary || {};
    return `<tr class="clickable-row" data-chat-id="${c.chat_id}">
    <td><code>${c.chat_id}</code></td>
    <td>${esc(c.title || '—')}</td>
    <td>${c.type || '—'}</td>
    <td>${statusPill(c.status || 'unknown')}</td>
    <td>${s.auto_approval ? '✅' : '❌'} ${s.approval_delay_seconds ? `(${s.approval_delay_seconds}s)` : ''}</td>
    <td>${s.welcome_enabled ? '✅' : '❌'} · ${s.welcome_buttons_count || 0} btn</td>
    <td>${s.goodbye_enabled ? '✅' : '❌'}</td>
    <td>${c.total_approved || 0}</td>
    <td><button type="button" class="btn sm" data-chat-view="${c.chat_id}">View</button></td>
  </tr>`;
  });
  renderTable('chats-table',
    ['Chat ID', 'Title', 'Type', 'Status', 'Auto-approve', 'Welcome', 'Goodbye', 'Approved', ''],
    rows);
  $all('[data-chat-view]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      showChatDetail(btn.dataset.chatView);
    });
  });
  $all('tr[data-chat-id]').forEach(tr => {
    tr.addEventListener('click', () => showChatDetail(tr.dataset.chatId));
  });
  renderPager('chats', data);
}

async function loadRequests() {
  const data = await api(`/api/admin/join-requests?${buildQuery('requests')}`);
  const rows = data.items.map(r => `<tr>
    <td>${r.user_id}</td>
    <td>@${r.username || '—'}</td>
    <td>${r.chat_id}</td>
    <td>${statusPill(r.status)}</td>
    <td>${r.welcome_status || '—'}</td>
    <td>${fmtDate(r.created_at)}</td>
  </tr>`);
  renderTable('requests-table', ['User', 'Username', 'Chat', 'Status', 'Welcome', 'Created'], rows);
  renderPager('requests', data);
}

async function loadBroadcasts() {
  const data = await api(`/api/admin/broadcasts?${buildQuery('broadcasts')}`);
  const rows = data.items.map(b => `<tr data-job="${b.id}">
    <td><code>${(b.id || '').slice(0, 8)}…</code></td>
    <td>${b.owner_id}</td>
    <td>${b.target}${b.target_id ? ` (${b.target_id})` : ''}</td>
    <td>${statusPill(b.status)}</td>
    <td>${progressBar(b.progress)}</td>
    <td>${fmtDate(b.created_at)}</td>
    <td class="actions">
      ${b.status === 'running' ? `<button class="btn sm" data-act="pause" data-id="${b.id}">Pause</button>` : ''}
      ${b.status === 'paused' ? `<button class="btn sm" data-act="resume" data-id="${b.id}">Resume</button>` : ''}
      ${['running','paused'].includes(b.status) ? `<button class="btn sm danger" data-act="cancel" data-id="${b.id}">Cancel</button>` : ''}
      <button class="btn sm" data-act="detail" data-id="${b.id}">Detail</button>
    </td>
  </tr>`);
  renderTable('broadcasts-table',
    ['Job', 'Owner', 'Target', 'Status', 'Progress', 'Created', 'Actions'], rows);

  $all('[data-act]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      const act = btn.dataset.act;
      if (act === 'detail') return showBroadcastDetail(id);
      await api(`/api/admin/broadcasts/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ action: act }),
      });
      await loadBroadcasts();
    });
  });
  renderPager('broadcasts', data);
}

async function showBroadcastDetail(jobId) {
  const job = await api(`/api/admin/broadcasts/${jobId}`);
  const panel = $('#broadcast-detail');
  panel.classList.remove('hidden');
  panel.innerHTML = `
    <h3>Broadcast ${job.id}</h3>
    <p>Status: ${statusPill(job.status)} · Target: <b>${job.target}</b></p>
    <p>${progressBar(job.progress)}</p>
    <p>Recipients: pending ${job.recipients?.pending || 0},
       sent ${job.recipients?.sent || 0}, failed ${job.recipients?.failed || 0}</p>
    <pre style="white-space:pre-wrap;background:var(--surface2);padding:.75rem;border-radius:8px;max-height:200px;overflow:auto">${esc(JSON.stringify(job.payload, null, 2))}</pre>
  `;
}

function fmtDate(v) {
  if (!v) return '—';
  try { return new Date(v).toLocaleString(); } catch { return v; }
}
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function bindFilters() {
  $all('.search').forEach(inp => {
    let t;
    inp.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => {
        const table = inp.dataset.table;
        state.tables[table].q = inp.value.trim();
        state.tables[table].page = 1;
        if (state.tab === table || (table === 'requests' && state.tab === 'requests')) loadCurrentTab();
      }, 350);
    });
  });

  $all('.filter').forEach(sel => {
    sel.addEventListener('change', () => {
      const table = sel.dataset.table;
      const field = sel.dataset.field;
      state.tables[table][field] = sel.value;
      state.tables[table].page = 1;
      loadCurrentTab();
    });
  });

  $all('.filter-text').forEach(inp => {
    let t;
    inp.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => {
        const table = inp.dataset.table;
        const field = inp.dataset.field;
        state.tables[table][field] = inp.value.trim();
        state.tables[table].page = 1;
        loadCurrentTab();
      }, 350);
    });
  });

  $all('.sort').forEach(sel => {
    sel.addEventListener('change', () => {
      const table = sel.dataset.table;
      state.tables[table].sort = sel.value;
      state.tables[table].page = 1;
      loadCurrentTab();
    });
  });
}

async function init() {
  $('#login-btn').addEventListener('click', async () => {
    const t = $('#token-input').value.trim();
    if (!t) return;
    setToken(t);
    try {
      await api('/api/admin/stats');
      showApp();
      switchTab('dashboard');
      $('#login-error').classList.add('hidden');
    } catch {
      clearToken();
      $('#login-error').textContent = 'Invalid secret';
      $('#login-error').classList.remove('hidden');
    }
  });

  $('#logout-btn').addEventListener('click', () => {
    clearToken();
    showLogin();
  });

  $all('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  $('#refresh-btn').addEventListener('click', () => loadCurrentTab());

  $('#broadcast-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      target: fd.get('target'),
      text: fd.get('text'),
    };
    if (fd.get('target_id')) body.target_id = parseInt(fd.get('target_id'), 10);
    if (fd.get('owner_id')) body.owner_id = parseInt(fd.get('owner_id'), 10);
    const msg = $('#broadcast-form-msg');
    try {
      const job = await api('/api/admin/broadcasts', { method: 'POST', body: JSON.stringify(body) });
      msg.textContent = `Broadcast started: ${job.id}`;
      msg.className = 'msg ok';
      msg.classList.remove('hidden');
      e.target.reset();
      switchTab('broadcasts');
    } catch (err) {
      msg.textContent = err.message;
      msg.className = 'msg err';
      msg.classList.remove('hidden');
    }
  });

  bindFilters();

  if (token()) {
    try {
      await api('/api/admin/stats');
      showApp();
      switchTab('dashboard');
    } catch {
      showLogin();
    }
  } else {
    showLogin();
  }

  // Auto-refresh broadcasts tab every 10s
  setInterval(() => {
    if (state.tab === 'broadcasts' || state.tab === 'dashboard') loadCurrentTab();
  }, 10000);
}

init();
