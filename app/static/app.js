/* NOT — main app logic. No AI API key lives here; ever. */
(() => {
  "use strict";

  // ---------- Auth keys (MUST match login.js) ----------
  const LS_TOKEN = "not.token";
  const LS_USER  = "not.user";

  // ---------- Guard: must be logged in ----------
  // Note: this redirects to /login only if there is NO token.
  // If the token exists but is expired, the first API call will 401
  // and api() will handle the redirect — no loop.
  if (!localStorage.getItem(LS_TOKEN)) {
    window.location.replace("/login");
    return;
  }

  // ---------- State ----------
  const state = {
    conversationId: null,
    conversations: [],
    sending: false,
    abortController: null,
    listening: false,
    recognition: null,
    voiceOut: false,
    voiceConv: false,
    rate: 1.0,
    voiceName: "",
    language: "auto",
    autoSendTranscript: false,
  };

  const LS = {
    theme: "not.theme",
    lang: "not.lang",
    voiceOut: "not.voiceOut",
    voiceConv: "not.voiceConv",
    rate: "not.rate",
    voice: "not.voice",
    autoSend: "not.autoSendTranscript",
  };

  const $ = (id) => document.getElementById(id);
  const chatEl = $("chat");
  const inputEl = $("input");
  const composerEl = $("composer");
  const sendBtn = $("sendBtn");
  const micBtn = $("micBtn");
  const stopSpeakBtn = $("stopSpeakBtn");
  const convosEl = $("convos");
  const topbarTitle = $("topbarTitle");
  const statusDot = $("statusDot");
  const appEl = $("app");

  // ---------- Utilities ----------
  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function showToast(msg, ms = 3200) {
    const t = $("toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { t.hidden = true; }, ms);
  }

  function detectDir(text, lang) {
    if (lang === "ur") return "rtl";
    if (lang === "roman-ur" || lang === "hi") return "ltr";
    return /[\u0600-\u06FF\u0750-\u077F]/.test(text) ? "rtl" : "ltr";
  }

  // ---------- Minimal safe Markdown renderer ----------
  function renderMarkdown(src) {
    let text = escapeHtml(src);

    const codeBlocks = [];
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) => {
      const idx = codeBlocks.length;
      codeBlocks.push(`<div class="code-block"><button class="code-copy" type="button" data-idx="${idx}">Copy</button><pre><code>${code}</code></pre></div>`);
      return `\u0000CODE${idx}\u0000`;
    });

    text = text.replace(/`([^`\n]+)`/g, (_, c) => `<code>${c}</code>`);
    text = text.replace(/^### (.*)$/gm, "<h3>$1</h3>");
    text = text.replace(/^## (.*)$/gm, "<h2>$1</h2>");
    text = text.replace(/^# (.*)$/gm, "<h1>$1</h1>");
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    text = text.replace(/^&gt; (.*)$/gm, "<blockquote>$1</blockquote>");

    text = text.replace(/(?:^|\n)((?:[-*] .*(?:\n|$))+)/g, (m) => {
      const items = m.trim().split("\n").map(l => `<li>${l.replace(/^[-*]\s+/, "")}</li>`).join("");
      return `\n<ul>${items}</ul>\n`;
    });
    text = text.replace(/(?:^|\n)((?:\d+\. .*(?:\n|$))+)/g, (m) => {
      const items = m.trim().split("\n").map(l => `<li>${l.replace(/^\d+\.\s+/, "")}</li>`).join("");
      return `\n<ol>${items}</ol>\n`;
    });

    const lines = text.split(/\n{2,}/);
    text = lines.map((block) => {
      if (/^\s*<(h[1-3]|ul|ol|blockquote|pre|div)/.test(block)) return block;
      return `<p>${block.replace(/\n/g, "<br>")}</p>`;
    }).join("\n");

    text = text.replace(/\u0000CODE(\d+)\u0000/g, (_, i) => codeBlocks[Number(i)]);
    return text;
  }

  // ---------- API ----------
  function authHeaders() {
    const h = { "Content-Type": "application/json" };
    const jwt = localStorage.getItem(LS_TOKEN);
    if (jwt) h["Authorization"] = "Bearer " + jwt;
    return h;
  }

  async function api(path, options = {}) {
    const res = await fetch(path, { headers: authHeaders(), ...options });

    if (res.status === 401) {
      localStorage.removeItem(LS_TOKEN);
      localStorage.removeItem(LS_USER);
      window.location.replace("/login");
      throw new Error("Not authenticated.");
    }
    if (res.status === 204) return null;

    let data = null;
    try { data = await res.json(); } catch { /* ignore */ }

    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }

  // ---------- Rendering ----------
  function clearWelcome() {
    const w = $("welcome");
    if (w) w.remove();
  }

  function appendMessage(role, content, { id = null } = {}) {
    clearWelcome();
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    if (id) wrap.dataset.id = id;

    const avatar = document.createElement("div");
    avatar.className = "msg__avatar";
    avatar.textContent = role === "user" ? "You".slice(0, 1) : "N";

    const body = document.createElement("div");
    body.className = "msg__body";

    const roleLabel = document.createElement("div");
    roleLabel.className = "msg__role";
    roleLabel.textContent = role === "user" ? "You" : "NOT";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    const dir = detectDir(content, state.language);
    bubble.setAttribute("dir", dir);
    bubble.innerHTML = renderMarkdown(content);

    body.appendChild(roleLabel);
    body.appendChild(bubble);
    body.appendChild(buildMessageActions(role, content, bubble));
    wrap.appendChild(avatar);
    wrap.appendChild(body);
    chatEl.appendChild(wrap);
    wireCodeCopy(bubble);
    maybeAutoScroll();
    return wrap;
  }

  function buildMessageActions(role, content, bubble) {
    const actions = document.createElement("div");
    actions.className = "msg__actions";

    const copyBtn = document.createElement("button");
    copyBtn.className = "icon-btn";
    copyBtn.title = "Copy";
    copyBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>`;
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(content);
        showToast("Copied");
      } catch { showToast("Copy failed"); }
    });
    actions.appendChild(copyBtn);

    if (role === "assistant") {
      const regenBtn = document.createElement("button");
      regenBtn.className = "icon-btn";
      regenBtn.title = "Regenerate";
      regenBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7M3 3v6h6"/></svg>`;
      regenBtn.addEventListener("click", () => regenerate(bubble));
      actions.appendChild(regenBtn);
    }
    return actions;
  }

  function wireCodeCopy(root) {
    root.querySelectorAll(".code-copy").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const block = btn.closest(".code-block");
        const code = block?.querySelector("code");
        if (!code) return;
        try {
          await navigator.clipboard.writeText(code.textContent);
          btn.textContent = "Copied";
          setTimeout(() => (btn.textContent = "Copy"), 1200);
        } catch { showToast("Copy failed"); }
      });
    });
  }

  function maybeAutoScroll() {
    const nearBottom = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 150;
    if (nearBottom) chatEl.scrollTop = chatEl.scrollHeight;
  }

  function showTyping() {
    clearWelcome();
    const wrap = document.createElement("div");
    wrap.className = "msg assistant";
    wrap.id = "typingIndicator";
    wrap.innerHTML = `
      <div class="msg__avatar">N</div>
      <div class="msg__body">
        <div class="msg__role">NOT</div>
        <div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>
      </div>`;
    chatEl.appendChild(wrap);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function hideTyping() {
    const el = $("typingIndicator");
    if (el) el.remove();
  }

  // ---------- Conversation list ----------
  async function refreshConversations() {
    try {
      state.conversations = await api("/api/conversations");
      renderConversations();
    } catch (e) {
      console.warn("Failed to load conversations", e);
    }
  }

  function renderConversations() {
    convosEl.innerHTML = "";
    if (!state.conversations.length) {
      const empty = document.createElement("div");
      empty.className = "muted";
      empty.style.padding = "10px";
      empty.style.fontSize = "13px";
      empty.textContent = "No conversations yet.";
      convosEl.appendChild(empty);
      return;
    }
    for (const c of state.conversations) {
      const item = document.createElement("div");
      item.className = "convo-item" + (c.id === state.conversationId ? " active" : "");
      item.dataset.id = c.id;

      const title = document.createElement("div");
      title.className = "convo-item__title";
      title.textContent = c.title || "Untitled";
      title.title = c.title || "";

      const actions = document.createElement("div");
      actions.className = "convo-item__actions";

      const renameBtn = document.createElement("button");
      renameBtn.className = "icon-btn";
      renameBtn.title = "Rename";
      renameBtn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>`;
      renameBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        renameConversation(c);
      });

      const delBtn = document.createElement("button");
      delBtn.className = "icon-btn";
      delBtn.title = "Delete";
      delBtn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M6 6l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14"/></svg>`;
      delBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        confirmModal("Delete conversation?", `"${c.title}" will be permanently removed.`, async () => {
          try {
            await api(`/api/conversations/${c.id}`, { method: "DELETE" });
            if (state.conversationId === c.id) newChat();
            await refreshConversations();
            showToast("Deleted");
          } catch (err) { showToast(err.message); }
        });
      });

      actions.appendChild(renameBtn);
      actions.appendChild(delBtn);

      item.appendChild(title);
      item.appendChild(actions);
      item.addEventListener("click", () => openConversation(c.id));
      convosEl.appendChild(item);
    }
  }

  async function openConversation(id) {
    try {
      const detail = await api(`/api/conversations/${id}`);
      state.conversationId = detail.id;
      topbarTitle.textContent = detail.title || "NOT";
      chatEl.innerHTML = "";
      for (const m of detail.messages) {
        appendMessage(m.role, m.content, { id: m.id });
      }
      chatEl.scrollTop = chatEl.scrollHeight;
      renderConversations();
      if (window.innerWidth <= 820) appEl.classList.remove("sidebar-open");
    } catch (e) {
      showToast(e.message);
    }
  }

  function newChat() {
    state.conversationId = null;
    topbarTitle.textContent = "NOT";
    chatEl.innerHTML = `
      <div class="welcome" id="welcome">
        <div class="welcome__mark">N</div>
        <h1>How can I help?</h1>
        <p class="muted">Ask anything. Type, or use the microphone to talk.</p>
      </div>`;
    renderConversations();
    inputEl.focus();
  }

  async function renameConversation(c) {
    const next = prompt("Rename conversation:", c.title);
    if (!next || !next.trim() || next.trim() === c.title) return;
    try {
      await api(`/api/conversations/${c.id}`, {
        method: "PATCH",
        body: JSON.stringify({ title: next.trim() }),
      });
      await refreshConversations();
      if (state.conversationId === c.id) topbarTitle.textContent = next.trim();
    } catch (e) { showToast(e.message); }
  }

  // ---------- Sending ----------
  async function sendMessage(text) {
    if (state.sending) return;
    const msg = (text ?? inputEl.value).trim();
    if (!msg) return;

    state.sending = true;
    sendBtn.disabled = true;

    appendMessage("user", msg);
    inputEl.value = "";
    autoGrow();

    showTyping();
    state.abortController = new AbortController();

    try {
      const payload = {
        conversation_id: state.conversationId,
        message: msg,
        language: state.language,
      };
      const data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify(payload),
        signal: state.abortController.signal,
      });
      hideTyping();
      state.conversationId = data.conversation_id;
      appendMessage("assistant", data.reply);
      await refreshConversations();
      const current = state.conversations.find(c => c.id === state.conversationId);
      if (current) topbarTitle.textContent = current.title;

      if (state.voiceOut || state.voiceConv) {
        speak(data.reply);
      }
      if (state.voiceConv) {
        onSpeechEnd(() => { if (state.voiceConv) startListening(); });
      }
    } catch (e) {
      hideTyping();
      if (e.name === "AbortError") {
        showToast("Generation stopped");
      } else {
        appendMessage("assistant", `**Error:** ${e.message}`);
        showToast("Something went wrong");
      }
    } finally {
      state.sending = false;
      sendBtn.disabled = false;
      state.abortController = null;
    }
  }

  async function regenerate(bubble) {
    const msgEl = bubble.closest(".msg");
    const prev = msgEl?.previousElementSibling;
    const userText = prev?.classList.contains("user")
      ? prev.querySelector(".bubble")?.textContent
      : null;
    if (!userText) return;
    await sendMessage(userText);
  }

  // ---------- Composer ----------
  function autoGrow() {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + "px";
  }

  inputEl.addEventListener("input", autoGrow);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      composerEl.requestSubmit();
    }
  });

  composerEl.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage();
  });

  // ---------- Voice input ----------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

  function setupRecognition() {
    if (!SR) return null;
    const r = new SR();
    r.continuous = false;
    r.interimResults = true;
    r.lang = langToBCP47(state.language);
    return r;
  }

  function langToBCP47(lang) {
    return ({
      "auto": navigator.language || "en-US",
      "en": "en-US",
      "ur": "ur-PK",
      "roman-ur": "en-IN",
      "hi": "hi-IN",
    })[lang] || "en-US";
  }

  function startListening() {
    if (!SR) {
      showToast("Voice input isn't supported in this browser. Try Chrome or Edge.");
      return;
    }
    if (state.listening) { stopListening(); return; }

    const r = setupRecognition();
    state.recognition = r;
    state.listening = true;
    micBtn.classList.add("recording");
    micBtn.title = "Stop listening";
    inputEl.placeholder = "Listening…";

    let interimBuffer = "";
    r.onresult = (event) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i];
        if (res.isFinal) finalText += res[0].transcript;
        else interimText += res[0].transcript;
      }
      if (finalText) {
        interimBuffer += finalText;
        inputEl.value = (inputEl.value + " " + finalText).trim();
      } else if (interimText) {
        inputEl.value = (interimBuffer + " " + interimText).trim();
      }
      autoGrow();
    };
    r.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        showToast("Microphone permission denied. Enable it in your browser settings.");
      } else if (e.error === "no-speech") {
        // silent
      } else {
        showToast("Voice error: " + e.error);
      }
      stopListening();
    };
    r.onend = () => {
      stopListening();
      if (state.voiceConv && inputEl.value.trim()) {
        sendMessage();
      }
    };
    try {
      r.start();
    } catch (e) {
      showToast("Could not start listening: " + e.message);
      stopListening();
    }
  }

  function stopListening() {
    state.listening = false;
    micBtn.classList.remove("recording");
    micBtn.title = "Voice input";
    inputEl.placeholder = "Message NOT…";
    try { state.recognition?.stop(); } catch { /* ignore */ }
  }

  micBtn.addEventListener("click", startListening);

  // ---------- Speech output ----------
  const synth = window.speechSynthesis;
  let speechEndHandlers = [];

  function onSpeechEnd(fn) {
    speechEndHandlers.push(fn);
  }

  function populateVoices() {
    if (!synth) return;
    const voices = synth.getVoices();
    const sel = $("setVoice");
    const current = sel.value;
    sel.innerHTML = `<option value="">System default</option>`;
    voices.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.name;
      opt.textContent = `${v.name} (${v.lang})`;
      sel.appendChild(opt);
    });
    sel.value = current || state.voiceName || "";
  }

  if (synth) {
    synth.onvoiceschanged = populateVoices;
    populateVoices();
  }

  function speak(text) {
    if (!synth || !text) return;
    synth.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = state.rate;
    utter.lang = langToBCP47(state.language);
    if (state.voiceName) {
      const match = synth.getVoices().find(v => v.name === state.voiceName);
      if (match) utter.voice = match;
    }
    utter.onstart = () => { stopSpeakBtn.hidden = false; };
    utter.onend = () => {
      stopSpeakBtn.hidden = true;
      const handlers = speechEndHandlers;
      speechEndHandlers = [];
      handlers.forEach((h) => { try { h(); } catch {} });
    };
    utter.onerror = () => { stopSpeakBtn.hidden = true; };
    synth.speak(utter);
  }

  stopSpeakBtn.addEventListener("click", () => {
    synth?.cancel();
    stopSpeakBtn.hidden = true;
  });

  // ---------- Settings ----------
  function loadPrefs() {
    const theme = localStorage.getItem(LS.theme) || "dark";
    const lang = localStorage.getItem(LS.lang) || "auto";
    state.voiceOut = localStorage.getItem(LS.voiceOut) === "1";
    state.voiceConv = localStorage.getItem(LS.voiceConv) === "1";
    state.rate = parseFloat(localStorage.getItem(LS.rate) || "1");
    state.voiceName = localStorage.getItem(LS.voice) || "";
    state.autoSendTranscript = localStorage.getItem(LS.autoSend) === "1";

    document.documentElement.dataset.theme = theme;
    state.language = lang;

    $("setTheme").value = theme;
    $("setLang").value = lang;
    $("setVoiceOut").checked = state.voiceOut;
    $("setVoiceConv").checked = state.voiceConv;
    $("setRate").value = String(state.rate);
    $("rateVal").textContent = state.rate.toFixed(1);
  }

  function savePref(key, value) { localStorage.setItem(key, value); }

  $("setTheme").addEventListener("change", (e) => {
    document.documentElement.dataset.theme = e.target.value;
    savePref(LS.theme, e.target.value);
  });
  $("setLang").addEventListener("change", (e) => {
    state.language = e.target.value;
    savePref(LS.lang, e.target.value);
  });
  $("setVoiceOut").addEventListener("change", (e) => {
    state.voiceOut = e.target.checked;
    savePref(LS.voiceOut, state.voiceOut ? "1" : "0");
    if (!state.voiceOut) synth?.cancel();
  });
  $("setVoiceConv").addEventListener("change", (e) => {
    state.voiceConv = e.target.checked;
    savePref(LS.voiceConv, state.voiceConv ? "1" : "0");
    if (state.voiceConv) {
      state.voiceOut = true;
      $("setVoiceOut").checked = true;
      savePref(LS.voiceOut, "1");
      showToast("Voice conversation mode on. Tap the mic to start.");
    }
  });
  $("setRate").addEventListener("input", (e) => {
    state.rate = parseFloat(e.target.value);
    $("rateVal").textContent = state.rate.toFixed(1);
    savePref(LS.rate, String(state.rate));
  });
  $("setVoice").addEventListener("change", (e) => {
    state.voiceName = e.target.value;
    savePref(LS.voice, state.voiceName);
  });

  // ---------- Drawer / modal ----------
  function openDrawer() {
    $("drawer").hidden = false;
    $("drawerBackdrop").hidden = false;
  }
  function closeDrawer() {
    $("drawer").hidden = true;
    $("drawerBackdrop").hidden = true;
  }
  $("settingsBtn").addEventListener("click", openDrawer);
  $("closeDrawer").addEventListener("click", closeDrawer);
  $("drawerBackdrop").addEventListener("click", closeDrawer);

  function confirmModal(title, body, onConfirm) {
    const backdrop = $("modalBackdrop");
    $("modalTitle").textContent = title;
    $("modalBody").textContent = body;
    backdrop.hidden = false;

    $("modalCancel").onclick = null;
    $("modalConfirm").onclick = null;
    backdrop.onclick = null;

    const cleanup = () => {
      backdrop.hidden = true;
      $("modalCancel").onclick = null;
      $("modalConfirm").onclick = null;
      backdrop.onclick = null;
    };

    $("modalCancel").onclick = cleanup;
    $("modalConfirm").onclick = () => {
      cleanup();
      try { onConfirm(); }
      catch (e) { console.error(e); showToast(e.message || "Action failed"); }
    };
    backdrop.onclick = (e) => {
      if (e.target === backdrop) cleanup();
    };
  }

  function clearAllConfirm() {
    confirmModal(
      "Clear all conversations?",
      "Every conversation and message will be permanently deleted.",
      async () => {
        try {
          await api("/api/conversations", { method: "DELETE" });
          newChat();
          await refreshConversations();
          showToast("History cleared");
        } catch (e) { showToast(e.message); }
      }
    );
  }
  $("clearAllBtn").addEventListener("click", clearAllConfirm);
  $("drawerClearBtn").addEventListener("click", clearAllConfirm);

  // ---------- Sidebar / mobile ----------
  $("menuBtn").addEventListener("click", () => appEl.classList.toggle("sidebar-open"));
  $("collapseBtn").addEventListener("click", () => appEl.classList.toggle("sidebar-collapsed"));
  $("newChatBtn").addEventListener("click", () => {
    newChat();
    if (window.innerWidth <= 820) appEl.classList.remove("sidebar-open");
  });

  // ---------- User menu ----------
  function loadUser() {
    let user = null;
    try { user = JSON.parse(localStorage.getItem(LS_USER) || "null"); }
    catch { user = null; }
    if (!user) return;
    const name = user.display_name || user.email || "You";
    const initial = name.slice(0, 1).toUpperCase();
    $("userAvatar").textContent = initial;
    $("userName").textContent = name;
    $("userDropdownName").textContent = name;
    $("userDropdownRole").textContent = user.is_admin ? "Administrator" : "Member";
  }

  function bindUserMenu() {
    const btn = $("userBtn");
    const dd = $("userDropdown");
    if (!btn || !dd) return;

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = dd.hidden;
      dd.hidden = !willOpen;
      btn.setAttribute("aria-expanded", String(willOpen));
    });

    document.addEventListener("click", () => {
      if (!dd.hidden) {
        dd.hidden = true;
        btn.setAttribute("aria-expanded", "false");
      }
    });
    dd.addEventListener("click", (e) => e.stopPropagation());

    $("logoutBtn").addEventListener("click", () => {
      localStorage.removeItem(LS_TOKEN);
      localStorage.removeItem(LS_USER);
      window.location.replace("/login");
    });
  }

  // ---------- Health check ----------
  async function checkHealth() {
    try {
      const h = await api("/api/health");
      statusDot.classList.remove("err");
      statusDot.classList.add(h.api_key_configured ? "ok" : "err");
      statusDot.title = h.api_key_configured
        ? `Connected · model: ${h.model}`
        : "Server has no AI key configured";
      const statusEl = $("apiStatus");
      if (statusEl) {
        statusEl.textContent = h.api_key_configured
          ? `OK — model: ${h.model}`
          : "Server is missing the AI API key";
        statusEl.className = "api-status " + (h.api_key_configured ? "ok" : "err");
      }
    } catch (e) {
      statusDot.classList.remove("ok");
      statusDot.classList.add("err");
      statusDot.title = "Cannot reach the server";
      const statusEl = $("apiStatus");
      if (statusEl) {
        statusEl.textContent = "Cannot reach the server";
        statusEl.className = "api-status err";
      }
    }
  }

  // ---------- Init ----------
  loadPrefs();
  loadUser();
  bindUserMenu();
  checkHealth();
  refreshConversations();
  autoGrow();
  inputEl.focus();

  if (!SR) {
    micBtn.title = "Voice input not supported in this browser";
  }
})();