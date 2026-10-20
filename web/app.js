"use strict";

const $ = (id) => document.getElementById(id);
const state = { conversations: [], active: null, busy: false, controller: null };
const mobileLayout = window.matchMedia("(max-width: 680px)");
let toastTimer;

function toast(text) {
  $("toast").textContent = text;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4000);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== "/api/login") showLogin();
    throw new Error(data.detail || "暂时没有连接上，请稍后再试。");
  }
  return response;
}

function showLogin() {
  state.conversations = [];
  state.active = null;
  $("messages").replaceChildren();
  $("conversation-list").replaceChildren();
  $("chat-screen").hidden = true;
  $("login-screen").hidden = false;
  $("loading-screen").hidden = true;
  $("password").value = "";
  closeSidebar();
}

function setBusy(busy) {
  state.busy = busy;
  $("new-chat").disabled = busy;
  $("logout").disabled = busy;
  document.querySelectorAll(".conversation-select, .conversation-delete").forEach(button => { button.disabled = busy; });
  $("send-button").classList.toggle("is-stop", busy);
  $("send-button").innerHTML = busy ? '<span aria-hidden="true">■</span>' : '<span aria-hidden="true">↑</span>';
  $("send-button").setAttribute("aria-label", busy ? "停止生成" : "发送消息");
  $("chat-status").replaceChildren();
  const dot = document.createElement("span");
  dot.className = "status-dot";
  $("chat-status").append(dot, document.createTextNode(busy ? " 正在认真回复…" : " 随时听你说"));
  updateComposer();
}

function updateComposer() {
  const input = $("message-input");
  input.style.height = "auto";
  const height = input.scrollHeight;
  input.style.height = `${Math.min(height + 2, 160)}px`;
  input.style.overflowY = height > 160 ? "auto" : "hidden";
  $("send-button").disabled = !state.busy && !input.value.trim();
}

function scrollBottom(force = false) {
  const area = $("scroll-area");
  if (force || area.scrollHeight - area.scrollTop - area.clientHeight < 180) area.scrollTop = area.scrollHeight;
}

function addMessage(role, content, pending = false) {
  $("empty-state").hidden = true;
  const item = document.createElement("article");
  item.className = `message ${role}${pending ? " pending streaming" : ""}`;
  if (role === "assistant") {
    const avatar = document.createElement("span");
    avatar.className = "message-avatar";
    avatar.textContent = "✦";
    avatar.setAttribute("aria-hidden", "true");
    item.append(avatar);
  }
  const body = document.createElement("div");
  body.className = "message-body";
  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "我" : "聊天伙伴";
  const bubble = document.createElement("div");
  bubble.className = "message-content";
  // Model and user messages are always rendered as text, never executable HTML.
  bubble.textContent = content;
  body.append(label, bubble);
  item.append(body);
  $("messages").append(item);
  return { item, bubble };
}

function renderConversations() {
  const list = $("conversation-list");
  list.replaceChildren();
  $("conversation-count").textContent = String(state.conversations.length);
  if (!state.conversations.length) {
    const empty = document.createElement("p");
    empty.className = "no-conversations";
    empty.textContent = "还没有对话。\n从一句你好开始吧。";
    list.append(empty);
  }
  for (const conversation of state.conversations) {
    const row = document.createElement("div");
    row.className = `conversation-item${conversation.id === state.active ? " active" : ""}`;
    const button = document.createElement("button");
    button.className = "conversation-select";
    button.disabled = state.busy;
    button.setAttribute("aria-current", conversation.id === state.active ? "true" : "false");
    const icon = document.createElement("span");
    icon.className = "conversation-icon";
    icon.textContent = "♧";
    icon.setAttribute("aria-hidden", "true");
    const info = document.createElement("span");
    const title = document.createElement("span");
    title.className = "conversation-title";
    title.textContent = conversation.title;
    const date = document.createElement("span");
    date.className = "conversation-date";
    date.textContent = new Date(conversation.updated_at * 1000).toLocaleDateString("zh-CN", { month: "long", day: "numeric" });
    info.append(title, date);
    button.append(icon, info);
    button.addEventListener("click", () => openConversation(conversation.id).catch(error => toast(error.message)));
    const remove = document.createElement("button");
    remove.className = "conversation-delete";
    remove.disabled = state.busy;
    remove.textContent = "×";
    remove.setAttribute("aria-label", `删除对话：${conversation.title}`);
    remove.addEventListener("click", () => deleteConversation(conversation.id));
    row.append(button, remove);
    list.append(row);
  }
}

async function refreshConversations() {
  state.conversations = await (await api("/api/conversations")).json();
  renderConversations();
}

async function openConversation(id) {
  if (state.busy) return;
  const data = await (await api(`/api/conversations/${id}`)).json();
  state.active = id;
  localStorage.setItem("chatbot-last-conversation", id);
  $("messages").replaceChildren();
  $("empty-state").hidden = data.messages.length > 0;
  for (const message of data.messages) addMessage(message.role, message.content);
  renderConversations();
  closeSidebar();
  scrollBottom(true);
}

async function newConversation() {
  if (state.busy) return;
  const data = await (await api("/api/conversations", { method: "POST" })).json();
  await refreshConversations();
  await openConversation(data.id);
  return data.id;
}

async function deleteConversation(id) {
  if (state.busy || !confirm("要删除这段对话吗？删除后无法恢复。")) return;
  try {
    await api(`/api/conversations/${id}`, { method: "DELETE" });
    if (state.active === id) {
      state.active = null;
      localStorage.removeItem("chatbot-last-conversation");
      $("messages").replaceChildren();
      $("empty-state").hidden = false;
    }
    await refreshConversations();
    toast("对话已删除。");
  } catch (error) { toast(error.message); }
}

async function enterChat() {
  await refreshConversations();
  $("loading-screen").hidden = true;
  $("login-screen").hidden = true;
  $("chat-screen").hidden = false;
  const previous = localStorage.getItem("chatbot-last-conversation");
  if (state.conversations.some(row => row.id === previous)) await openConversation(previous);
  else {
    state.active = null;
    $("messages").replaceChildren();
    $("empty-state").hidden = false;
  }
  updateComposer();
}

async function sendMessage() {
  if (state.busy) { state.controller?.abort(); return; }
  const content = $("message-input").value.trim();
  if (!content) return;
  setBusy(true);
  try {
    if (!state.active) {
      const data = await (await api("/api/conversations", { method: "POST" })).json();
      state.active = data.id;
      localStorage.setItem("chatbot-last-conversation", data.id);
      await refreshConversations();
    }
  } catch (error) { setBusy(false); toast(error.message); return; }
  $("message-input").value = "";
  updateComposer();
  addMessage("user", content);
  const reply = addMessage("assistant", "", true);
  scrollBottom(true);
  state.controller = new AbortController();
  let receivedDone = false;
  try {
    const response = await api(`/api/conversations/${state.active}/messages`, {
      method: "POST", body: JSON.stringify({ content }), signal: state.controller.signal,
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const consume = (frame) => {
      const type = frame.split("\n").find(line => line.startsWith("event: "))?.slice(7);
      const dataLine = frame.split("\n").find(line => line.startsWith("data: "));
      if (!dataLine) return;
      const data = JSON.parse(dataLine.slice(6));
      if (type === "delta") {
        reply.item.classList.remove("pending");
        reply.bubble.textContent += data.text;
        scrollBottom();
      } else if (type === "done") {
        reply.bubble.textContent = data.content;
        receivedDone = true;
      } else if (type === "error") throw new Error(data.detail);
    };
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        consume(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
      }
      if (done) break;
    }
    if (!receivedDone) throw new Error("连接中断了，请稍后再试。");
  } catch (error) {
    toast(error.name === "AbortError" ? "已停止生成。" : error.message);
  } finally {
    reply.item.classList.remove("pending", "streaming");
    state.controller = null;
    setBusy(false);
    try {
      await refreshConversations();
      if (state.active) await openConversation(state.active);
    } catch (error) { toast(error.message); }
  }
}

function closeSidebar() {
  $("sidebar").classList.remove("is-open");
  $("sidebar").inert = mobileLayout.matches;
  $("sidebar-backdrop").hidden = true;
  $("open-sidebar").setAttribute("aria-expanded", "false");
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("login-button").disabled = true;
  $("login-error").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify({ password: $("password").value }) });
    await enterChat();
  } catch (error) { $("login-error").textContent = error.message; }
  finally { $("login-button").disabled = false; }
});
$("show-password").addEventListener("click", () => {
  const hidden = $("password").type === "password";
  $("password").type = hidden ? "text" : "password";
  $("show-password").textContent = hidden ? "隐藏" : "显示";
  $("show-password").setAttribute("aria-label", hidden ? "隐藏密码" : "显示密码");
});
$("message-form").addEventListener("submit", event => { event.preventDefault(); sendMessage(); });
$("message-input").addEventListener("input", updateComposer);
$("message-input").addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!state.busy) sendMessage();
  }
});
$("new-chat").addEventListener("click", () => newConversation().catch(error => toast(error.message)));
$("logout").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST" }); showLogin(); }
  catch (error) { toast(error.message); }
});
$("open-sidebar").addEventListener("click", () => {
  $("sidebar").inert = false;
  $("sidebar").classList.add("is-open");
  $("sidebar-backdrop").hidden = false;
  $("open-sidebar").setAttribute("aria-expanded", "true");
});
$("close-sidebar").addEventListener("click", closeSidebar);
$("sidebar-backdrop").addEventListener("click", closeSidebar);
mobileLayout.addEventListener("change", closeSidebar);
closeSidebar();
document.addEventListener("keydown", event => { if (event.key === "Escape") closeSidebar(); });
document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => {
  $("message-input").value = button.dataset.prompt;
  updateComposer();
  $("message-input").focus();
}));

(async () => {
  try {
    const data = await (await api("/api/session")).json();
    if (data.authenticated) await enterChat(); else showLogin();
  } catch (error) { showLogin(); $("login-error").textContent = error.message; }
})();
