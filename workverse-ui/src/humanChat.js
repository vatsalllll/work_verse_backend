// Wires the human-to-human chat widget (People button + panel).
// Uses REST polling (no WebSockets). Started after the user logs in.
import ChatService from './services/ChatService';

let started = false;
let view = 'list';                 // 'list' | 'chat'
let otherUserId = null;
let otherName = '';
let convoTimer = null;
let lastRenderedCount = -1;

const $ = (id) => document.getElementById(id);

function show(el) { el && el.classList.remove('hc-hidden'); }
function hide(el) { el && el.classList.add('hc-hidden'); }

function openPanel() {
  hide($('hc-fab'));
  show($('hc-panel'));
  showList();
}

function closePanel() {
  hide($('hc-panel'));
  show($('hc-fab'));
  stopConvoPolling();
}

async function showList() {
  view = 'list';
  otherUserId = null;
  stopConvoPolling();
  $('hc-title').textContent = 'People';
  hide($('hc-back'));
  hide($('hc-chat'));
  hide($('hc-input-row'));
  show($('hc-list'));

  const list = $('hc-list');
  list.innerHTML = '<div class="hc-empty">Loading…</div>';
  let users = [];
  let unread = [];
  try {
    [users, unread] = await Promise.all([
      ChatService.getDirectory(),
      ChatService.getUnread()
    ]);
  } catch (e) {
    list.innerHTML = '<div class="hc-empty">Could not load people.</div>';
    return;
  }

  const unreadBy = {};
  unread.forEach((u) => { unreadBy[u.from_user_id] = u.count; });

  if (users.length === 0) {
    list.innerHTML = '<div class="hc-empty">No other people in the workspace yet.</div>';
    return;
  }

  list.innerHTML = '';
  users.forEach((u) => {
    const row = document.createElement('div');
    row.className = 'hc-user';
    const dotClass = u.online ? 'hc-dot' : 'hc-dot offline';
    const status = u.online ? '' : ' <span class="hc-status">offline</span>';
    const badge = unreadBy[u.id]
      ? ` <span class="hc-badge">${unreadBy[u.id]}</span>`
      : '';
    row.innerHTML = `<span class="${dotClass}"></span><span class="hc-uname">${escapeHtml(u.name)}</span>${status}${badge}`;
    row.addEventListener('click', () => openChat(u.id, u.name));
    list.appendChild(row);
  });
}

function openChat(userId, name) {
  view = 'chat';
  otherUserId = userId;
  otherName = name;
  lastRenderedCount = -1;
  $('hc-title').textContent = name;
  show($('hc-back'));
  hide($('hc-list'));
  show($('hc-chat'));
  show($('hc-input-row'));
  $('hc-messages').innerHTML = '<div class="hc-empty">Loading…</div>';
  refreshConversation();
  startConvoPolling();
  $('hc-input').focus();
}

async function refreshConversation() {
  if (!otherUserId) return;
  let messages = [];
  try {
    messages = await ChatService.getConversation(otherUserId);
  } catch (e) {
    return;
  }
  if (messages.length === lastRenderedCount) return; // nothing new
  lastRenderedCount = messages.length;

  const box = $('hc-messages');
  if (messages.length === 0) {
    box.innerHTML = '<div class="hc-empty">Say hi 👋</div>';
    return;
  }
  box.innerHTML = '';
  messages.forEach((m) => {
    const wrap = document.createElement('div');
    wrap.className = 'hc-msg' + (m.mine ? ' mine' : '');
    wrap.innerHTML = `<span class="hc-bubble">${escapeHtml(m.text)}</span>`;
    box.appendChild(wrap);
  });
  box.scrollTop = box.scrollHeight;
}

async function sendMessage() {
  const input = $('hc-input');
  const text = input.value.trim();
  if (!text || !otherUserId) return;
  input.value = '';
  try {
    await ChatService.send(otherUserId, text);
    await refreshConversation();
  } catch (e) {
    input.value = text; // restore so the user can retry
  }
}

function startConvoPolling() {
  stopConvoPolling();
  convoTimer = setInterval(refreshConversation, 1500);
}
function stopConvoPolling() {
  if (convoTimer) { clearInterval(convoTimer); convoTimer = null; }
}

async function pollUnreadBadge() {
  try {
    const unread = await ChatService.getUnread();
    const total = unread.reduce((sum, u) => sum + u.count, 0);
    const badge = $('hc-badge');
    if (total > 0) {
      badge.textContent = total;
      show(badge);
    } else {
      hide(badge);
    }
  } catch (e) { /* ignore */ }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

export function startHumanChat() {
  if (started) return;
  started = true;

  show($('hc-fab'));
  $('hc-fab').addEventListener('click', openPanel);
  $('hc-close').addEventListener('click', closePanel);
  $('hc-back').addEventListener('click', showList);
  $('hc-send').addEventListener('click', sendMessage);

  const input = $('hc-input');
  // Keep keystrokes from reaching the Phaser game (so the avatar doesn't move).
  input.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') sendMessage();
  });

  // Presence: tell the server we're online now and every 15s.
  ChatService.ping();
  setInterval(() => ChatService.ping(), 15000);

  // Unread badge: refresh every 5s.
  pollUnreadBadge();
  setInterval(pollUnreadBadge, 5000);
}
