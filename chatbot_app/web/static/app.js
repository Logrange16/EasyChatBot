"use strict";

const $ = (id) => document.getElementById(id);
const state = { conversations: [], active: null, busy: false, controller: null, mode: localStorage.getItem("chatbot-mode") === "assistant" ? "assistant" : "companion", navigation: 0 };
const modes = {
  companion: {
    label: "陪伴模式", description: "日常分享，轻松陪伴", eyebrow: "A LITTLE SPACE, JUST FOR YOU",
    title: "今天，想聊些什么？", welcome: "生活里的小事，突然冒出的想法，或只是简单地说声「你好」。",
    placeholder: "慢慢说，我在听…",
    suggestions: [["☀", "分享今天的小开心", "想和你分享一下今天的小开心。"], ["♡", "陪我聊聊天", "现在有空吗？陪我聊聊天吧。"], ["✧", "一起想个好主意", "我有个想法，想和你一起讨论一下。"]],
  },
  assistant: {
    label: "助手模式", description: "知微 · 检索资料，梳理问题", eyebrow: "EXPLORE WITH EVIDENCE",
    title: "今天，想了解什么？", welcome: "查找资料、核实信息，或把一个问题慢慢研究清楚。",
    placeholder: "告诉知微你想研究的问题…",
    suggestions: [["⌕", "查找最新进展", "请联网检索最近一个月人工智能领域的三项进展，列出日期和来源。"], ["◇", "核实一条信息", "我想核实一条信息，请先问我需要查证的内容。"], ["✧", "梳理研究思路", "我想研究一个问题，请帮助我明确范围并整理检索思路。"]],
  },
};
const mobileLayout = window.matchMedia("(max-width: 680px)");
const defaultAppearance = { companion_name: "你的聊天伙伴", companion_prompt: "", theme: "lavender", background_opacity: 30, background_url: null };
let sidebarCollapsed = localStorage.getItem("chatbot-sidebar-collapsed") === "true";
let appearance = { ...defaultAppearance };
let settingsTheme = "lavender";
let settingsBackground;
let settingsPreviewURL = null;
let settingsSaving = false;
let toastTimer;

function agentName(values = appearance) {
  return state.mode === "assistant" ? "知微" : values.companion_name;
}

function renderMode() {
  const mode = modes[state.mode];
  document.querySelectorAll("[data-mode]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.mode === state.mode));
    button.disabled = state.busy;
  });
  $("mode-description").textContent = mode.description;
  $("welcome-eyebrow").textContent = mode.eyebrow;
  $("welcome-title").textContent = mode.title;
  $("welcome-description").textContent = mode.welcome;
  $("message-input").placeholder = mode.placeholder;
  document.querySelectorAll("[data-prompt]").forEach((button, index) => {
    const [symbol, label, prompt] = mode.suggestions[index];
    const icon = document.createElement("span");
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = symbol;
    button.dataset.prompt = prompt;
    button.replaceChildren(icon, document.createTextNode(` ${label}`));
  });
  applyAppearance(appearance);
}

async function switchMode(mode) {
  if (state.busy || state.mode === mode) return;
  state.navigation++;
  state.mode = mode;
  state.active = null;
  localStorage.setItem("chatbot-mode", mode);
  $("messages").replaceChildren();
  $("empty-state").hidden = false;
  renderMode();
  renderConversations();
  const previous = localStorage.getItem(`chatbot-last-conversation-${mode}`);
  if (state.conversations.some(row => row.id === previous && row.mode === mode)) await openConversation(previous);
  closeSidebar();
  updateComposer();
}

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
  closeSettingsMenu();
  if ($("settings-dialog").open) $("settings-dialog").close();
  appearance = { ...defaultAppearance };
  $("companion-prompt-input").value = "";
  applyAppearance(appearance);
  state.conversations = [];
  state.active = null;
  state.navigation++;
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
  document.querySelectorAll("[data-mode]").forEach(button => { button.disabled = busy; });
  $("mode-description").textContent = busy ? "正在思考…" : modes[state.mode].description;
  document.querySelectorAll(".conversation-select, .conversation-delete").forEach(button => { button.disabled = busy; });
  $("send-button").classList.toggle("is-stop", busy);
  $("send-button").innerHTML = busy ? '<span aria-hidden="true">■</span>' : '<span aria-hidden="true">↑</span>';
  $("send-button").setAttribute("aria-label", busy ? "停止生成" : "发送消息");
  $("messages").setAttribute("aria-busy", String(busy));
  updateComposer();
}

function updateComposer() {
  const input = $("message-input");
  input.style.height = "auto";
  const height = input.scrollHeight;
  input.style.height = `${Math.min(height + 2, 160)}px`;
  input.style.overflowY = height > 160 ? "auto" : "hidden";
  $("send-button").disabled = !state.busy && !input.value.trim();
  updateScrollButton();
}

function scrollBottom(force = false) {
  const area = $("scroll-area");
  if (force || area.scrollHeight - area.scrollTop - area.clientHeight < 180) area.scrollTop = area.scrollHeight;
  updateScrollButton();
}

function updateScrollButton() {
  const area = $("scroll-area");
  $("scroll-latest").hidden = !$("messages").childElementCount || area.scrollHeight - area.scrollTop - area.clientHeight < 180;
}

function renderMessageContent(element, content) {
  if (window.ChatRenderer) window.ChatRenderer.render(element, content);
  else element.textContent = content;
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
  label.textContent = role === "user" ? "我" : agentName();
  const bubble = document.createElement("div");
  bubble.className = "message-content";
  renderMessageContent(bubble, content);
  body.append(label, bubble);
  item.append(body);
  $("messages").append(item);
  return { item, bubble };
}

function renderConversations() {
  const list = $("conversation-list");
  list.replaceChildren();
  const conversations = state.conversations.filter(row => row.mode === state.mode);
  $("conversation-count").textContent = String(conversations.length);
  if (!conversations.length) {
    const empty = document.createElement("p");
    empty.className = "no-conversations";
    empty.textContent = state.mode === "assistant" ? "还没有助手对话。\n从一个问题开始吧。" : "还没有对话。\n从一句你好开始吧。";
    list.append(empty);
  }
  for (const conversation of conversations) {
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
  const navigation = ++state.navigation;
  const data = await (await api(`/api/conversations/${id}`)).json();
  if (navigation !== state.navigation || state.busy) return;
  state.mode = data.mode;
  state.active = id;
  localStorage.setItem("chatbot-mode", state.mode);
  localStorage.setItem("chatbot-last-conversation", id);
  localStorage.setItem(`chatbot-last-conversation-${state.mode}`, id);
  renderMode();
  $("messages").replaceChildren();
  $("empty-state").hidden = data.messages.length > 0;
  for (const message of data.messages) addMessage(message.role, message.content);
  renderConversations();
  closeSidebar();
  scrollBottom(true);
}

async function newConversation() {
  if (state.busy) return;
  state.navigation++;
  const data = await (await api("/api/conversations", { method: "POST", body: JSON.stringify({ mode: state.mode }) })).json();
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
      localStorage.removeItem(`chatbot-last-conversation-${state.mode}`);
      $("messages").replaceChildren();
      $("empty-state").hidden = false;
      updateScrollButton();
    }
    await refreshConversations();
    toast("对话已删除。");
  } catch (error) { toast(error.message); }
}

async function enterChat() {
  appearance = await (await api("/api/preferences")).json();
  applyAppearance(appearance);
  renderMode();
  await refreshConversations();
  $("loading-screen").hidden = true;
  $("login-screen").hidden = true;
  $("chat-screen").hidden = false;
  const previous = localStorage.getItem(`chatbot-last-conversation-${state.mode}`) || localStorage.getItem("chatbot-last-conversation");
  if (state.conversations.some(row => row.id === previous && row.mode === state.mode)) await openConversation(previous);
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
  state.navigation++;
  setBusy(true);
  try {
    if (!state.active) {
      const data = await (await api("/api/conversations", { method: "POST", body: JSON.stringify({ mode: state.mode }) })).json();
      state.active = data.id;
      localStorage.setItem("chatbot-last-conversation", data.id);
      localStorage.setItem(`chatbot-last-conversation-${state.mode}`, data.id);
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
  let streamedText = "";
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
        reply.bubble.classList.remove("rendered");
        streamedText += data.text;
        reply.bubble.textContent = streamedText;
        scrollBottom();
      } else if (type === "done") {
        renderMessageContent(reply.bubble, data.content);
        scrollBottom();
        receivedDone = true;
      } else if (type === "status") {
        $("mode-description").textContent = data.text;
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
  closeSettingsMenu();
  $("sidebar").classList.remove("is-open");
  $("sidebar").inert = mobileLayout.matches;
  $("sidebar-backdrop").hidden = true;
  $("open-sidebar").setAttribute("aria-expanded", "false");
  applySidebarLayout();
}

function applySidebarLayout() {
  const collapsed = !mobileLayout.matches && sidebarCollapsed;
  $("chat-screen").dataset.sidebarCollapsed = String(collapsed);
  $("toggle-sidebar").setAttribute("aria-expanded", String(!collapsed));
  const label = collapsed ? "展开侧边栏" : "收起侧边栏";
  $("toggle-sidebar").setAttribute("aria-label", label);
  $("toggle-sidebar").title = label;
}

function closeSettingsMenu({ restoreFocus = false } = {}) {
  $("settings-menu").hidden = true;
  $("open-settings").setAttribute("aria-expanded", "false");
  if (restoreFocus) $("open-settings").focus({ preventScroll: true });
}

function toggleSettingsMenu() {
  if (!$("settings-menu").hidden) { closeSettingsMenu(); return; }
  $("settings-menu").hidden = false;
  $("open-settings").setAttribute("aria-expanded", "true");
  $("settings-menu").querySelector("button:not(:disabled)").focus({ preventScroll: true });
}

function applyAppearance(values) {
  document.documentElement.dataset.theme = values.theme;
  document.documentElement.style.setProperty("--background-opacity", String(values.background_opacity / 100));
  $("sidebar-companion-name").textContent = agentName(values);
  $("sidebar-companion-name").title = agentName(values);
  document.title = `${agentName(values)} · ${modes[state.mode].label}`;
  $("theme-color").content = { lavender: "#f7f5fc", pink: "#fff5f8", sky: "#f0f8ff" }[values.theme];
  document.querySelectorAll(".message.assistant .message-label").forEach(label => { label.textContent = agentName(values); });
  $("background-layer").style.backgroundImage = values.background_url ? `url("${values.background_url}")` : "none";
}

function previewSettings() {
  const background = settingsBackground === null ? null : settingsPreviewURL || appearance.background_url;
  const values = {
    ...appearance,
    companion_name: $("companion-name-input").value.trim() || appearance.companion_name,
    theme: settingsTheme,
    background_opacity: Number($("background-opacity").value),
    background_url: background,
  };
  applyAppearance(values);
  $("background-preview").style.backgroundImage = background ? `url("${background}")` : "none";
  $("background-placeholder").hidden = Boolean(background);
  $("remove-background").disabled = !background || settingsSaving;
  $("background-opacity-value").textContent = `${values.background_opacity}%`;
  document.querySelectorAll("[data-theme-option]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.themeOption === settingsTheme));
  });
}

function openSettings(section = "names") {
  closeSettingsMenu();
  $("companion-name-input").value = appearance.companion_name;
  $("companion-prompt-input").value = appearance.companion_prompt || "";
  $("background-opacity").value = appearance.background_opacity;
  $("background-file").value = "";
  $("background-file-label").textContent = appearance.background_url ? "已设置背景，可重新选择" : "PNG / JPG，最大 8 MB";
  $("settings-error").textContent = "";
  settingsTheme = appearance.theme;
  settingsBackground = undefined;
  previewSettings();
  $("settings-dialog").showModal();
  $("settings-dialog").scrollTop = 0;
  const focusTarget = {
    names: $("companion-name-input"),
    colors: document.querySelector(`[data-theme-option="${settingsTheme}"]`),
    background: $("background-file"),
  }[section];
  const sectionTarget = { names: $("name-settings"), colors: $("color-settings"), background: $("background-settings") }[section];
  if (section !== "names") sectionTarget.scrollIntoView({ block: "nearest" });
  focusTarget.focus({ preventScroll: true });
}

function readImage(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("图片读取失败，请重新选择。"));
    reader.readAsDataURL(file);
  });
}

$("open-settings").addEventListener("click", toggleSettingsMenu);
document.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => switchMode(button.dataset.mode).catch(error => toast(error.message))));
$("open-settings").addEventListener("keydown", event => {
  if (event.key === "ArrowDown" && $("settings-menu").hidden) { event.preventDefault(); toggleSettingsMenu(); }
});
document.querySelectorAll("[data-settings-section]").forEach(button => button.addEventListener("click", () => openSettings(button.dataset.settingsSection)));
$("settings-menu").addEventListener("keydown", event => {
  if (event.key === "Escape") { event.preventDefault(); closeSettingsMenu({ restoreFocus: true }); return; }
  const buttons = Array.from($("settings-menu").querySelectorAll("button:not(:disabled)"));
  const index = buttons.indexOf(document.activeElement);
  let next;
  if (event.key === "ArrowDown") next = (index + 1) % buttons.length;
  if (event.key === "ArrowUp") next = (index - 1 + buttons.length) % buttons.length;
  if (event.key === "Home") next = 0;
  if (event.key === "End") next = buttons.length - 1;
  if (next !== undefined) { event.preventDefault(); buttons[next].focus(); }
});
document.addEventListener("click", event => { if (!$("settings-area").contains(event.target)) closeSettingsMenu(); });
$("settings-area").addEventListener("focusout", event => {
  if (event.relatedTarget && !$("settings-area").contains(event.relatedTarget)) closeSettingsMenu();
});
$("close-settings").addEventListener("click", () => $("settings-dialog").close());
$("cancel-settings").addEventListener("click", () => $("settings-dialog").close());
$("settings-dialog").addEventListener("cancel", event => { if (settingsSaving) event.preventDefault(); });
$("settings-dialog").addEventListener("close", () => {
  applyAppearance(appearance);
  if (settingsPreviewURL) URL.revokeObjectURL(settingsPreviewURL);
  settingsPreviewURL = null;
  settingsBackground = undefined;
  if (!$("chat-screen").hidden) $("open-settings").focus({ preventScroll: true });
});
document.querySelectorAll("[data-theme-option]").forEach(button => button.addEventListener("click", () => {
  settingsTheme = button.dataset.themeOption;
  previewSettings();
}));
$("companion-name-input").addEventListener("input", previewSettings);
$("background-opacity").addEventListener("input", previewSettings);
$("background-file").addEventListener("change", () => {
  const file = $("background-file").files[0];
  if (!file) return;
  $("settings-error").textContent = "";
  if (file.size > 8 * 1024 * 1024 || !(/\.(png|jpe?g)$/i.test(file.name) && (!file.type || ["image/png", "image/jpeg"].includes(file.type)))) {
    $("settings-error").textContent = "请选择不超过 8 MB 的 PNG 或 JPG 图片。";
    $("background-file").value = "";
    return;
  }
  if (settingsPreviewURL) URL.revokeObjectURL(settingsPreviewURL);
  settingsBackground = file;
  settingsPreviewURL = URL.createObjectURL(file);
  $("background-file-label").textContent = file.name;
  previewSettings();
});
$("remove-background").addEventListener("click", () => {
  if (settingsPreviewURL) URL.revokeObjectURL(settingsPreviewURL);
  settingsPreviewURL = null;
  settingsBackground = null;
  $("background-file").value = "";
  $("background-file-label").textContent = "PNG / JPG，最大 8 MB";
  previewSettings();
});
$("settings-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (settingsSaving) return;
  settingsSaving = true;
  $("settings-error").textContent = "";
  const values = {
    companion_name: $("companion-name-input").value.trim(),
    companion_prompt: $("companion-prompt-input").value.trim(),
    theme: settingsTheme,
    background_opacity: Number($("background-opacity").value),
  };
  $("settings-dialog").querySelectorAll("input, textarea, button").forEach(control => { control.disabled = true; });
  $("save-settings").textContent = "正在保存…";
  try {
    if (settingsBackground !== undefined) values.background_image = settingsBackground === null ? null : await readImage(settingsBackground);
    appearance = await (await api("/api/preferences", { method: "PUT", body: JSON.stringify(values) })).json();
    applyAppearance(appearance);
    $("settings-dialog").close();
    toast("已经换成你喜欢的样子啦。");
  } catch (error) { $("settings-error").textContent = error.message; }
  finally {
    settingsSaving = false;
    $("settings-dialog").querySelectorAll("input, textarea, button").forEach(control => { control.disabled = false; });
    $("save-settings").textContent = "保存设置";
    if ($("settings-dialog").open) previewSettings();
  }
});

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
  closeSettingsMenu();
  try { await api("/api/logout", { method: "POST" }); showLogin(); }
  catch (error) { toast(error.message); }
});
$("scroll-area").addEventListener("scroll", updateScrollButton, { passive: true });
$("scroll-latest").addEventListener("click", () => scrollBottom(true));
window.addEventListener("resize", updateScrollButton);
$("toggle-sidebar").addEventListener("click", () => {
  const area = $("scroll-area");
  const atBottom = area.scrollHeight - area.scrollTop - area.clientHeight < 180;
  closeSettingsMenu();
  sidebarCollapsed = !sidebarCollapsed;
  localStorage.setItem("chatbot-sidebar-collapsed", String(sidebarCollapsed));
  applySidebarLayout();
  if (atBottom) scrollBottom(true); else updateScrollButton();
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
