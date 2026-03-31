const API = '/api';
let qrSession = null, pollTimer = null, userCookie = null, userRoles = null;

// ── 登录弹窗控制 ────────────────────────────────────────
let qrRefreshTimer = null;
function openLoginModal() {
  $('login-modal').classList.add('show');
  $('login-modal-overlay').classList.add('show');
  // 打开弹窗时自动生成二维码
  setTimeout(() => generateQR(), 300);
  // 每 2 分钟自动刷新一次二维码
  if (qrRefreshTimer) clearInterval(qrRefreshTimer);
  qrRefreshTimer = setInterval(() => {
    if ($('login-modal').classList.contains('show')) {
      generateQR();
    }
  }, 120000);
}
function closeLoginModal() {
  $('login-modal').classList.remove('show');
  $('login-modal-overlay').classList.remove('show');
  stopPoll();
  if (qrRefreshTimer) clearInterval(qrRefreshTimer);
}

// ── 本地凭证持久化 ───────────────────────────────────────
const STORAGE_KEY = 'mys_credentials';

function saveCredentials(creds) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(creds)); } catch(e) {}
}
function loadCredentials() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)); } catch(e) { return null; }
}
function clearCredentials() {
  try { localStorage.removeItem(STORAGE_KEY); } catch(e) {}
}

function $(id) { return document.getElementById(id); }
function setStatus(s, t) { $('status-dot').className = 'dot ' + s; $('status-text').textContent = t; }
function toast(msg, ms = 2800) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), ms);
}

// ── 扫码登录 ────────────────────────────────────────────────
async function generateQR() {
  stopPoll();
  $('qr-img').style.display = 'none';
  $('qr-ph').style.display = 'none';
  $('qr-loading').classList.add('show');
  $('qr-confirmed').classList.remove('show');

  const hint = $('qr-hint');
  hint.className = 'qr-hint';
  hint.textContent = '';
  const hintLeft = $('qr-hint-left');
  if (hintLeft) hintLeft.textContent = '二维码生成中...';
  const pill = $('qr-state-pill');
  if (pill) pill.textContent = '生成中';
  setStatus('amber', '生成中...');

  try {
    const res = await fetch(API + '/login/qrcode/generate', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '二维码生成失败');

    qrSession = {
      ticket: data.ticket,
      device_id: data.device_id
    };

    const img = $('qr-img');
    img.src = 'data:image/png;base64,' + data.qr_image;
    img.style.display = 'block';

    $('qr-loading').classList.remove('show');
    hint.textContent = '';
    if (hintLeft) hintLeft.textContent = '二维码已生成';
    if (pill) pill.textContent = '等待扫码';
    setStatus('amber', '等待扫码');
    startPoll();
  } catch (e) {
    $('qr-loading').classList.remove('show');
    $('qr-ph').style.display = 'flex';
    hint.textContent = '生成失败，请重试';
    if (hintLeft) hintLeft.textContent = '生成失败';
    if (pill) pill.textContent = '生成失败';
    setStatus('', '未登录');
    toast('二维码生成失败：' + e.message);
  }
}

function startPoll() { pollTimer = setInterval(pollStatus, 3000); }
function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

async function pollStatus() {
  if (!qrSession) return;
  try {
    const url = `${API}/login/qrcode/status?ticket=${encodeURIComponent(qrSession.ticket)}&device_id=${encodeURIComponent(qrSession.device_id)}`;
    const res = await fetch(url, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '状态查询失败');

    const hint = $('qr-hint');

    if (data.status === 'confirmed') {
      stopPoll();
      $('qr-confirmed').classList.add('show');
      hint.className = 'qr-hint confirmed';
      hint.textContent = '登录成功！正在加载收藏夹...';
      const hintLeft = $('qr-hint-left');
      if (hintLeft) hintLeft.textContent = '登录成功，正在进入...';
      const pill = $('qr-state-pill');
      if (pill) pill.textContent = '登录成功';
      setStatus('golden', '已登录');
      userCookie = data.credentials;
      saveCredentials(data.credentials);
      await loadRoles();
      setTimeout(() => showPosts(), 800);
    } else {
      hint.className = 'qr-hint scanning';
      hint.textContent = '';
      const hintLeft = $('qr-hint-left');
      const pill = $('qr-state-pill');

      // 后端会返回 stat: Init / Scanned / Confirmed
      // 这里只在 Scanned 时显示“待确认”
      if (data.stat === 'Scanned') {
        if (hintLeft) hintLeft.textContent = '已扫码，等待 App 确认';
        if (pill) pill.textContent = '待确认';
        setStatus('amber', '等待确认');
      } else {
        // Init 或其他未确认状态
        if (hintLeft) hintLeft.textContent = '二维码已生成，等待扫码';
        if (pill) pill.textContent = '等待扫码';
        setStatus('amber', '等待扫码');
      }
    }
  } catch (e) {
    // 轮询静默失败，避免频繁弹窗
  }
}

async function loadRoles() {
  if (!userCookie) return;
  try {
    const res = await fetch(API + '/roles/list', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stuid: userCookie.stuid, stoken: userCookie.stoken, mid: userCookie.mid })
    });
    const data = await res.json();
    if (res.ok && data.retcode === 0) {
      userRoles = data.data.list || [];
    }
  } catch (e) { /* 静默失败，后续用默认值 */ }
}

function showPosts() {
  closeLoginModal();
  const ps = $('posts-section');
  ps.style.display = 'flex';
  ps.style.flex = '1';
  ps.style.minHeight = '0';
  ps.style.flexDirection = 'column';
  ps.style.overflow = 'hidden';
  const stuid = userCookie && userCookie.stuid ? userCookie.stuid : '—';
  if ($('sidebar-uid')) $('sidebar-uid').textContent = stuid;
  const su = $('sidebar-user'); if (su) su.classList.add('show');
  const sb = $('sidebar-bottom'); if (sb) sb.classList.add('show');
  const sg = $('stat-grid'); if (sg) sg.classList.add('show');
  const st = $('sidebar-status'); if (st) st.style.display = 'none';
  loadFavourites();
}

// ── 收藏帖 ──────────────────────────────────────────────────
async function loadFavourites(offset = '') {
  $('posts-list').innerHTML = '<div class="state-box"><div class="spinner"></div><p>加载中...</p></div>';
  $('count-badge').textContent = '加载中...';

  const c = userCookie || {};
  // 优先取已选角色，否则取 roles 列表第一个，再 fallback 空串
  const role = (userRoles && userRoles.length) ? userRoles[0] : null;
  const body = {
    stuid: c.stuid || '',
    stoken: c.stoken || '',
    mid: c.mid || '',
    game_uid: role ? role.game_uid : '',
    game_region: role ? role.region : 'cn_gf01',
    offset,
    size: 20
  };

  try {
    const res = await fetch(API + '/favourite/get', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'API 错误');
    renderPosts(data.data);
  } catch (e) {
    $('posts-list').innerHTML = '<div class="state-box"><div class="icon">⚠️</div><p>' + e.message + '</p></div>';
    $('count-badge').textContent = '加载失败';
    toast('加载收藏失败：' + e.message);
  }
}

function tryParseMid(raw) { try { return JSON.parse(raw).mid || ''; } catch (e) { return ''; } }

// ── 游戏 ID 映射表 ───────────────────────────────────────────
const GAME_MAP = {
  1: { name: '崩坏3',           emoji: '🌸' },
  2: { name: '原神',             emoji: '🌿' },
  3: { name: '崩坏学园2',       emoji: '🎓' },
  4: { name: '未定事件簿',       emoji: '🕵️' },
  5: { name: '大别野',           emoji: '🏡' },
  6: { name: '崩坏：星穹铁道',   emoji: '🚂' },
  8: { name: '绝区零',           emoji: '⚡' },
};
// 固定顺序展示
const GAME_ORDER = [0, 2, 6, 8, 1, 3, 4, 5];  // 0 = 全部，按热门度排列

let allItems = [];       // 全量收藏数据缓存
let activeGameId = 0;    // 0 = 全部
let ingestScopeChoice = null;
let ingestPendingGameIds = new Set();
let ingestedGames = loadIngestedGames();

function loadIngestedGames() {
  try {
    const raw = localStorage.getItem('mys_ingested_games');
    const data = raw ? JSON.parse(raw) : {};
    return data && typeof data === 'object' ? data : {};
  } catch (e) {
    return {};
  }
}

function saveIngestedGames() {
  try { localStorage.setItem('mys_ingested_games', JSON.stringify(ingestedGames)); } catch (e) {}
}

function getCurrentGameLabel() {
  if (activeGameId === 0) return '全部分区';
  if (activeGameId === -1) return '其他分区';
  return GAME_MAP[activeGameId] ? `${GAME_MAP[activeGameId].name}` : '当前分区';
}

function getCurrentScopeGameIds() {
  if (activeGameId === 0) {
    return Array.from(new Set(allItems.map(item => item?.post?.game_id).filter(Boolean)));
  }
  if (activeGameId === -1) {
    return Array.from(new Set(allItems
      .map(item => item?.post?.game_id)
      .filter(gid => gid && !GAME_MAP[gid])));
  }
  return activeGameId > 0 ? [activeGameId] : [];
}

function getAllScopeGameIds() {
  return Array.from(new Set(allItems.map(item => item?.post?.game_id).filter(Boolean)));
}

function gameLabel(id) {
  const g = GAME_MAP[id];
  return g ? `${g.emoji} ${g.name}` : `🎮 其他`;
}

function buildGameTabs(items) {
  // 统计各游戏数量
  const counts = {};
  items.forEach(item => {
    const gid = item.post && item.post.game_id;
    if (gid) counts[gid] = (counts[gid] || 0) + 1;
  });

  // 检测是否有「其他」（不在 GAME_MAP 中的 id）
  let otherCount = 0;
  Object.keys(counts).forEach(gid => {
    if (!GAME_MAP[Number(gid)]) otherCount += counts[gid];
  });

  const container = $('game-tabs');
  if (!container) return;

  // 生成固定分类按钮（只显示有内容的 + 全部）
  const tabs = [];

  // 全部按钮
  tabs.push(makeTabBtn(0, '🎮 全部', items.length));

  // 按固定顺序遍历已知游戏
  GAME_ORDER.filter(id => id !== 0).forEach(gid => {
    const cnt = counts[gid] || 0;
    if (cnt > 0) {  // 只显示有收藏的游戏
      tabs.push(makeTabBtn(gid, gameLabel(gid), cnt));
    }
  });

  // 其他兜底
  if (otherCount > 0) {
    tabs.push(makeTabBtn(-1, '🎮 其他', otherCount));
  }

  container.innerHTML = tabs.join('');
}

function makeTabBtn(gid, label, count) {
  const isActive = activeGameId === gid;
  const pending = ingestPendingGameIds.has(gid);
  const ingested = !!ingestedGames[String(gid)];
  const statusBadge = pending
    ? `<span class="game-ingest-badge pending">入库中...</span>`
    : (ingested ? `<span class="game-ingest-badge done">已入库</span>` : '');
  return `<button class="game-tab-btn${isActive ? ' active' : ''}" onclick="filterGame(${gid})">${label}<span class="game-tab-count">${count}</span>${statusBadge}</button>`;
}

function filterGame(gid) {
  activeGameId = gid;
  buildGameTabs(allItems);
  let filtered;
  if (gid === 0) {
    filtered = allItems;
  } else if (gid === -1) {
    // 其他：所有不在 GAME_MAP 中的
    filtered = allItems.filter(item => item.post && !GAME_MAP[item.post.game_id]);
  } else {
    filtered = allItems.filter(item => item.post && item.post.game_id === gid);
  }
  renderPostCards(filtered);
}

function renderPosts(data) {
  allItems = (data && data.list) || [];
  activeGameId = 0;
  $('count-badge').textContent = allItems.length + ' 条收藏';
  if (!allItems.length) {
    const gt = $('game-tabs'); if (gt) gt.innerHTML = '';
    $('posts-list').innerHTML = '<div class="state-box"><div class="icon">📫</div><p>暂无收藏内容</p></div>';
    return;
  }
  buildGameTabs(allItems);
  renderPostCards(allItems);
}

function renderPostCards(items) {
  if (!items.length) {
    $('posts-list').innerHTML = '<div class="state-box"><div class="icon">📫</div><p>该分区暂无收藏</p></div>';
    return;
  }
  $('posts-list').innerHTML = items.map((item, i) => {
    const post = item.post || {}, stat = item.stat || {}, user = item.user || {};
    const imgs = item.image_list || [];
    const thumb = imgs.length ? imgs[0].url : null;
    const thumbHtml = thumb
      ? `<img class="post-thumb" src="${thumb}" loading="lazy"/>`
      : `<div class="post-thumb-ph">📄</div>`;
    const forum = item.forum || {};
    const topics = (item.topics || []).slice(0, 2);
    const gid = post.game_id;
    const gameBadge = gid
      ? `<span class="tag game-badge ${GAME_MAP[gid] ? 'game-' + gid : 'game-other'}">${GAME_MAP[gid] ? GAME_MAP[gid].emoji + ' ' + GAME_MAP[gid].name : '🎮 其他'}</span>`
      : '';
    const tags = [
      gameBadge,
      forum.name ? `<span class="tag blue">${forum.name}</span>` : '',
      ...topics.map(t => `<span class="tag">${esc(t.name)}</span>`)
    ].join('');
    return `<div class="post-card" style="animation-delay:${i * .04}s">
      ${thumbHtml}
      <div class="post-body">
        <div class="post-title">${esc(post.subject || '（无标题）')}</div>
        <div class="post-meta">
          <span>👁 ${fmt(stat.view_num)}</span>
          <span>❤️ ${fmt(stat.like_num)}</span>
          <span>⭐ ${fmt(stat.bookmark_num)}</span>
          <span>✍️ ${esc(user.nickname || '')}</span>
        </div>
        <div class="post-tags">${tags}</div>
      </div>
    </div>`;
  }).join('');
}

function fmt(n) { if (!n) return '0'; if (n >= 10000) return (n / 10000).toFixed(1) + 'w'; return String(n); }
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

function logout() {
  stopPoll();
  qrSession = null;
  userCookie = null;
  userRoles = null;
  clearCredentials();
  $('posts-section').style.display = 'none';
  const su = $('sidebar-user'); if (su) su.classList.remove('show');
  const sb = $('sidebar-bottom'); if (sb) sb.classList.remove('show');
  const sg = $('stat-grid'); if (sg) sg.classList.remove('show');
  const st = $('sidebar-status'); if (st) st.style.display = 'flex';
  $('qr-img').style.display = 'none';
  $('qr-img').src = '';
  $('qr-ph').style.display = 'flex';
  $('qr-confirmed').classList.remove('show');
  $('qr-hint').className = 'qr-hint';
  $('qr-hint').textContent = '';
  const hintLeft = $('qr-hint-left');
  if (hintLeft) hintLeft.textContent = '等待二维码生成...';
  const pill = $('qr-state-pill');
  if (pill) pill.textContent = '准备中';
  setStatus('', '未登录');
  openLoginModal();
}

// ── Tab / View 切换 ────────────────────────────────────────
function switchTab(paneId, btn) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  $(paneId).classList.add('active');
  btn.classList.add('active');
  if (paneId === 'tab-rag') loadRAGStats();
}

function openIngestScopeModal() {
  const overlay = $('ingest-scope-overlay');
  const modal = $('ingest-scope-modal');
  if (!overlay || !modal) return;

  ingestScopeChoice = null;
  overlay.classList.add('show');
  modal.classList.add('show');

  const currentBtn = $('ingest-opt-current');
  const allBtn = $('ingest-opt-all');
  const currentLabel = getCurrentGameLabel();
  if (currentBtn) currentBtn.textContent = `当前分区（${currentLabel}）`;
  if (allBtn) allBtn.textContent = '全部分区';

  // 当当前是“全部”时，默认高亮“全部分区”
  if (activeGameId === 0) {
    selectIngestScope('all');
  } else {
    selectIngestScope('current');
  }
}

function closeIngestScopeModal() {
  const overlay = $('ingest-scope-overlay');
  const modal = $('ingest-scope-modal');
  if (overlay) overlay.classList.remove('show');
  if (modal) modal.classList.remove('show');
}

function selectIngestScope(scope) {
  ingestScopeChoice = scope;
  const currentBtn = $('ingest-opt-current');
  const allBtn = $('ingest-opt-all');
  if (currentBtn) currentBtn.classList.toggle('active', scope === 'current');
  if (allBtn) allBtn.classList.toggle('active', scope === 'all');
}

async function confirmIngestScope() {
  if (!ingestScopeChoice) return;
  closeIngestScopeModal();
  await ingestFavourites(ingestScopeChoice);
}

// ── RAG 归档 ────────────────────────────────────────────────
async function ingestFavourites(scope = 'current') {
  const c = userCookie || {};
  const role = (userRoles && userRoles.length) ? userRoles[0] : null;
  const statusEl = $('ingest-status');
  const btn = $('btn-ingest');

  const currentScopeIds = getCurrentScopeGameIds();
  const allScopeIds = getAllScopeGameIds();
  const targetGameIds = (scope === 'all' ? allScopeIds : currentScopeIds).filter(Boolean);

  // 全部分区时不传 selected_game_id（后端全量）
  const selectedGameId = (scope === 'current' && activeGameId > 0) ? activeGameId : null;

  targetGameIds.forEach(gid => ingestPendingGameIds.add(gid));
  buildGameTabs(allItems);

  btn.disabled = true;
  statusEl.innerHTML = '<div class="spinner" style="width:14px;height:14px;border-width:2px"></div> <span>提交中...</span>';
  try {
    const res = await fetch(API + '/rag/ingest/favourites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        stuid:       c.stuid || '',
        stoken:      c.stoken || '',
        mid:         c.mid || '',
        game_uid:    role ? role.game_uid : '',
        game_region: role ? role.region : 'cn_gf01',
        size:        20,
        selected_game_id: selectedGameId
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '归档失败');

    targetGameIds.forEach(gid => {
      ingestedGames[String(gid)] = {
        ingested: true,
        at: Date.now()
      };
      ingestPendingGameIds.delete(gid);
    });
    saveIngestedGames();
    buildGameTabs(allItems);

    statusEl.innerHTML = `<span style="color:var(--success)">✓ ${data.message}</span>`;
    toast(data.message);
    setTimeout(loadRAGStats, 3000);
  } catch (e) {
    targetGameIds.forEach(gid => ingestPendingGameIds.delete(gid));
    buildGameTabs(allItems);
    statusEl.innerHTML = `<span style="color:#e05">✗ ${e.message}</span>`;
    toast('归档失败：' + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function loadRAGStats() {
  try {
    const res = await fetch(API + '/rag/stats');
    const data = await res.json();
    const byType = data.by_type || {};
    $('stat-posts').textContent = data.posts ?? '0';
    $('stat-docs').textContent = data.docs ?? '0';
    const vectorsEl = $('stat-vectors');
    if (vectorsEl) vectorsEl.textContent = data.vectors ?? '0';
    $('stat-image').textContent = byType['image'] ?? '0';
    $('stat-audio').textContent = byType['audio'] ?? '0';
  } catch (e) { }
}

// ── Chat ─────────────────────────────────────────────────────
function clearChat() {
  $('chat-messages').innerHTML =
    '<div class="chat-empty" id="chat-empty"><div class="chat-empty-icon">🤖</div><span>归档收藏帖后，在此提问</span></div>';
}

function appendMsg(role, text) {
  const empty = $('chat-empty');
  if (empty) empty.remove();
  const wrap = document.createElement('div');
  wrap.className = 'chat-msg ' + role;
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  bubble.textContent = text;
  wrap.appendChild(bubble);
  const msgs = $('chat-messages');
  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
  return bubble;
}

document.addEventListener('DOMContentLoaded', () => {
  // 自动恢复上次登录
  const saved = loadCredentials();
  if (saved && saved.stuid && saved.stoken) {
    userCookie = saved;
    setStatus('golden', '已登录');
    loadRoles().then(() => showPosts());
  }

  const ta = $('chat-input');
  if (!ta) return;
  ta.addEventListener('input', () => {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  });
  ta.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
});

async function sendChat() {
  const ta = $('chat-input');
  const q = ta.value.trim();
  if (!q) return;
  const btn = $('btn-send');
  ta.value = ''; ta.style.height = 'auto';
  btn.disabled = true;
  appendMsg('user', q);
  const thinkBubble = appendMsg('assistant', '思考中...');
  thinkBubble.classList.add('thinking');
  try {
    const res = await fetch(API + '/rag/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '查询失败');
    thinkBubble.classList.remove('thinking');
    // Markdown 渲染
    const mdText = data.answer || '暂无回答';
    thinkBubble.innerHTML = typeof marked !== 'undefined'
      ? marked.parse(mdText)
      : mdText.replace(/\n/g, '<br>');
    if (data.sources && data.sources.length) {
      const srcDiv = document.createElement('div');
      srcDiv.className = 'chat-sources';
      srcDiv.innerHTML = data.sources.map(s =>
        `<a class="chat-src-tag" href="${s.url || '#'}" target="_blank" title="${s.post_id || ''}">${s.summary || s.type}</a>`
      ).join('');
      // 插入到 .chat-msg 行之后（聊天框容器下方）
      const msgRow = thinkBubble.parentElement;
      msgRow.insertAdjacentElement('afterend', srcDiv);
    }
    $('chat-messages').scrollTop = $('chat-messages').scrollHeight;
  } catch (e) {
    thinkBubble.classList.remove('thinking');
    thinkBubble.textContent = '查询失败：' + e.message;
    toast('问答失败：' + e.message);
  } finally {
    btn.disabled = false;
    $('chat-input').focus();
  }
}
