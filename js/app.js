(function () {
  "use strict";

  var LS = {
    cfg: "aiAssistant.config.v1",
    ui: "aiAssistant.ui.v1",
    roles: "aiAssistant.customRoles.v1"
    // 聊天记录与角色提示词不再进 localStorage，改由后端存成
    // history/<用户>.json 与 prompts/<角色>.md，换浏览器也能拿回来
  };

  var ICONS = {
    chat: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
    teacher: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 10L12 5 2 10l10 5 10-5z"></path><path d="M6 12v5c0 1 3 3 6 3s6-2 6-3v-5"></path></svg>',
    doctor: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 6v12M6 12h12"></path><circle cx="12" cy="12" r="9"></circle></svg>',
    dream: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path></svg>',
    name: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20l6.5-6.5M14 4l6 6-9.5 9.5H4.5V14z"></path></svg>',
    fairy: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 3l1.9 4.6L17.5 9.5l-4.6 1.9L11 16 9.1 11.4 4.5 9.5l4.6-1.9z"></path><path d="M18 14.5l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8z"></path></svg>',
    image: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><path d="M21 15l-5-5L5 21"></path></svg>',
    book: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path><path d="M9 7h7"></path></svg>',
    settings: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.2A1.6 1.6 0 0 0 7 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 15a1.6 1.6 0 0 0-1.5-1H1a2 2 0 1 1 0-4h.2A1.6 1.6 0 0 0 3 9a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 9 3.6V3a2 2 0 1 1 4 0v.2A1.6 1.6 0 0 0 15 3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 .6 2.2h.1a1.6 1.6 0 0 0 1.4.9h.2a2 2 0 1 1 0 4h-.2a1.6 1.6 0 0 0-1.5 1z" transform="translate(1.5 1.5) scale(0.88)"></path></svg>',
    caret: '<svg class="caret" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"></path></svg>'
  };

  var VIEWS = ["chat", "image", "t2i", "i2i", "kb", "prompt", "settings"];
  var VIEW_TITLE = {
    image: "对话 - 图片理解",
    t2i: "图片处理 - 文生图",
    i2i: "图片处理 - 图生图",
    kb: "知识库 - 资料管理",
    prompt: "配置 - 角色提示词",
    settings: "配置 - 参数配置"
  };

  /* ---------------- 存取 ---------------- */
  function read(key, def) {
    try {
      var v = localStorage.getItem(key);
      return v ? JSON.parse(v) : def;
    } catch (e) { return def; }
  }
  function write(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* 隐私模式下忽略 */ }
  }
  function $(id) { return document.getElementById(id); }
  function escape(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function fmtTime(ts) {
    var d = new Date(ts), p = function (n) { return n < 10 ? "0" + n : n; };
    return d.getFullYear() + "/" + p(d.getMonth() + 1) + "/" + p(d.getDate()) +
      " " + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }

  var defaults = Object.assign({
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
    chatModels: ["qwen-plus", "qwen3-vl-plus"],
    visionModel: "qwen3-vl-plus",
    temperature: 0, seed: 20261104,
    maxTokens: 0, historyLimit: 20, stream: true, timeout: 120000,
    imageSizes: ["1024*1024"], imageModels: [], imageModel: "", imageMaxCount: 4
  }, window.AI_CONFIG || {});

  var savedCfg = read(LS.cfg, {});
  // 浏览器里存过的老配置带着 temperature:0.7，会把「同题同答」的新默认值悄悄盖掉；
  // 没有 seed 这个键就说明是老的，采样参数一律按 config.js 重来一遍。
  if (savedCfg && Object.keys(savedCfg).length && !("seed" in savedCfg)) {
    delete savedCfg.temperature;
  }

  var state = {
    user: "",
    config: Object.assign({}, defaults, savedCfg),
    convos: {},
    prompts: {},
    ui: Object.assign({ collapsed: window.innerWidth < 860, openGroups: { chat: true },
                        view: "chat", roleId: "normal", promptId: "teacher" }, read(LS.ui, {})),
    customRoles: read(LS.roles, []),
    backend: { online: false, hasKey: false, keyTail: "", model: "", rag: null,
               imageSizes: [], imageModels: [], imageModel: "", imageMaxCount: 0 },
    authTab: "login",
    busy: false,
    controller: null,
    imageData: "",
    i2iImage: "",
    gen: { t2i: false, i2i: false }
  };
  if (VIEWS.indexOf(state.ui.view) < 0) state.ui.view = "chat";

  // 提示词和历史都以后端文件为准：prompts/<角色>.md 与 history/<用户>.json
  async function loadUserData() {
    state.convos = {};
    state.prompts = {};
    try {
      var pr = await getJSON("api/prompts");
      state.prompts = pr.prompts || {};
    } catch (e) { /* 拿不到就退回 config.js 的默认设定 */ }
    try {
      var hi = await getJSON("api/history/all");
      state.convos = hi.conversations || {};
    } catch (e) { /* 历史拉不到时按空会话处理 */ }
  }

  function saveHistory(roleId) {
    var msgs = state.convos[roleId] || [];
    return postJSON("api/history", { role: roleId, messages: msgs }).catch(function () {});
  }

  function allRoles() {
    return (window.AI_ROLES || []).concat(state.customRoles.map(function (r) {
      return { id: r.id, title: r.title, short: r.title, icon: "chat", system: r.system, custom: true };
    }));
  }
  function roleById(id) {
    var list = allRoles();
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return list[0];
  }
  // 提示词编辑页保存过的内容优先于 config.js 里的默认设定
  function systemOf(role) {
    if (!role) return "";
    var ov = state.prompts[role.id];
    return (ov === undefined || ov === null) ? (role.system || "") : ov;
  }
  function currentMessages() {
    if (!state.convos[state.ui.roleId]) state.convos[state.ui.roleId] = [];
    return state.convos[state.ui.roleId];
  }

  function openedByFile() { return location.protocol === "file:"; }
  function configed() { return !!state.user && state.backend.online && state.backend.hasKey; }
  function backendHint() {
    if (openedByFile()) return "你是双击 index.html 打开的，这样连不上后端。请改用浏览器地址栏访问 http://127.0.0.1:8000";
    if (!state.backend.online) return "后端未启动：请在项目目录执行 python api.py 后刷新页面";
    if (!state.backend.hasKey) return "后端已启动，但 config.py 里的 API_KEY 还是空的";
    if (!state.user) return "请先登录";
    return "";
  }

  /* ---------------- 后端请求 ---------------- */
  async function postJSON(path, payload, opts) {
    opts = opts || {};
    var res;
    try {
      res = await fetch(path, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}), signal: opts.signal
      });
    } catch (err) {
      if (err.name === "AbortError") throw new Error("请求已取消或超时");
      throw new Error("无法连接后端：" + err.message + "（请确认 python api.py 正在运行）");
    }
    var data = {};
    try { data = await res.json(); } catch (e) { try { data = { error: await res.text() }; } catch (e2) {} }
    var msg = data.error || (typeof data.detail === "string" ? data.detail : "") || ("HTTP " + res.status);
    if (res.status === 401 && !opts.allow401) expired();
    if (!res.ok) { var err = new Error(msg); err.status = res.status; err.data = data; throw err; }
    return data;
  }
  async function getJSON(path) {
    var res;
    try { res = await fetch(path, { cache: "no-store" }); }
    catch (err) { throw new Error("无法连接后端：" + err.message); }
    var data = {};
    try { data = await res.json(); } catch (e) {}
    if (res.status === 401) { expired(); throw new Error(data.detail || "请先登录"); }
    if (!res.ok) throw new Error(data.error || data.detail || ("HTTP " + res.status));
    return data;
  }
  // 任何一个业务接口返回 401，都说明 Cookie 里的会话没了对应用退回登录页
  function expired() {
    if (!state.user) return;
    state.user = "";
    showGate("登录已过期，请重新登录");
  }

  /* ---------------- 登录 / 注册 ---------------- */
  function setAuthMsg(text, kind) {
    var el = $("authMsg");
    el.textContent = text || "";
    el.className = "auth-msg" + (kind ? " " + kind : "");
  }
  function showGate(msg) {
    $("app").hidden = true;
    $("authGate").hidden = false;
    setAuthMsg(msg, msg ? "err" : "");
    $("authSubmit").disabled = false;
    $("authSubmit").textContent = state.authTab === "login" ? "登 录" : "注 册";
    setTimeout(function () { $(state.authTab === "login" ? "authPass" : "authUser").focus(); }, 30);
  }
  async function enterApp(username) {
    state.user = username;
    $("authGate").hidden = true;
    $("app").hidden = false;
    $("userName").textContent = username;
    $("userAvatar").textContent = username.slice(0, 1).toUpperCase();
    await loadUserData();
    renderMenu();
    fillImagePickers();
    switchView(state.ui.view || "chat");
    renderMenu();
    updateStatus();
    if (state.ui.view === "settings") fillForm();
    $("input").focus();
  }
  function switchAuthTab(tab) {
    state.authTab = tab;
    Array.prototype.forEach.call(document.querySelectorAll(".auth-tab"), function (b) {
      b.classList.toggle("on", b.dataset.tab === tab);
    });
    $("authPass2Field").hidden = tab !== "register";
    $("authPass").autocomplete = tab === "login" ? "current-password" : "new-password";
    $("authSubmit").textContent = tab === "login" ? "登 录" : "注 册";
    setAuthMsg("");
  }
  Array.prototype.forEach.call(document.querySelectorAll(".auth-tab"), function (b) {
    b.addEventListener("click", function () { switchAuthTab(b.dataset.tab); });
  });
  $("authSubmit").addEventListener("click", submitAuth);
  ["authUser", "authPass", "authPass2"].forEach(function (id) {
    $(id).addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.isComposing) submitAuth();
    });
  });
  async function submitAuth() {
    var u = $("authUser").value.trim(), p = $("authPass").value;
    if (!u || !p) { setAuthMsg("请填写用户名和密码", "err"); return; }
    if (state.authTab === "register" && p !== $("authPass2").value) {
      setAuthMsg("两次输入的密码不一致", "err"); return;
    }
    if (openedByFile() || !state.backend.online) { setAuthMsg(backendHint(), "err"); return; }
    $("authSubmit").disabled = true;
    $("authSubmit").textContent = "处理中…";
    try {
      var r = await postJSON(state.authTab === "register" ? "api/register" : "api/login",
        { username: u, password: p }, { allow401: true });
      $("authPass").value = ""; $("authPass2").value = "";
      enterApp(r.username);
    } catch (e) {
      setAuthMsg(e.message, "err");
      $("authSubmit").disabled = false;
      $("authSubmit").textContent = state.authTab === "login" ? "登 录" : "注 册";
    }
  }
  $("logoutBtn").addEventListener("click", async function () {
    try { await postJSON("api/logout", {}, { allow401: true }); } catch (e) { /* 本地照样退出 */ }
    state.user = "";
    $("userName").textContent = "";
    showGate("已退出登录");
  });

  /* ---------------- 侧边菜单 ---------------- */
  function menuGroups() {
    var chatItems = allRoles().map(function (r) {
      return { label: r.short || r.title, view: "chat", roleId: r.id };
    });
    chatItems.push({ label: "图片理解", view: "image" });
    var promptItems = allRoles().filter(function (r) {
      return r.promptLabel && (r.promptLabel || r.system);
    }).map(function (r) {
      return { label: r.promptLabel, view: "prompt", roleId: r.id };
    });
    return [
      { key: "chat", label: "对话", icon: "chat", items: chatItems },
      { key: "pic", label: "图片处理", icon: "image",
        items: [{ label: "文生图", view: "t2i" }, { label: "图生图", view: "i2i" }] },
      { key: "kb", label: "知识库", icon: "book",
        items: [{ label: "资料管理", view: "kb" }] },
      { key: "cfg", label: "配置", icon: "settings",
        items: [{ label: "参数配置", view: "settings" }].concat(promptItems) }
    ];
  }

  function itemActive(it) {
    if (it.view === "chat") return state.ui.view === "chat" && state.ui.roleId === it.roleId;
    if (it.view === "prompt") return state.ui.view === "prompt" && state.ui.promptId === it.roleId;
    return state.ui.view === it.view;
  }

  function renderMenu() {
    $("menu").innerHTML = menuGroups().map(function (g) {
      var open = !!state.ui.openGroups[g.key];
      var items = g.items.map(function (it) {
        return '<div class="submenu-item' + (itemActive(it) ? " active" : "") +
          '" data-view="' + it.view + '" data-group="' + g.key + '" data-role="' +
          (it.roleId || "") + '">' + escape(it.label) + "</div>";
      }).join("");
      return '<div class="menu-group' + (open ? " open" : "") + '" data-group="' + g.key + '">' +
        '<div class="menu-item' + (open && state.ui.view && g.key === groupOfView(state.ui.view) ? " active" : "") +
        '" data-toggle="' + g.key + '">' + ICONS[g.icon] +
        '<span class="menu-label">' + g.label + "</span>" + ICONS.caret + "</div>" +
        '<div class="submenu">' + items + "</div></div>";
    }).join("");
  }
  var GROUP_OF_VIEW = { chat: "chat", image: "chat", t2i: "pic", i2i: "pic",
                        kb: "kb", settings: "cfg", prompt: "cfg" };
  function groupOfView(v) { return GROUP_OF_VIEW[v] || "chat"; }

  $("menu").addEventListener("click", function (e) {
    var toggle = e.target.closest("[data-toggle]");
    if (toggle) {
      var g = toggle.dataset.toggle;
      var wasOpen = !!state.ui.openGroups[g];
      state.ui.openGroups[g] = !wasOpen;
      if (state.ui.collapsed) { state.ui.collapsed = false; applyCollapsed(); }
      if (!wasOpen) {
        var group = menuGroups().filter(function (x) { return x.key === g; })[0];
        if (group && group.items.length) pickItem(group.items[0]);
      }
      renderMenu(); saveUi();
      return;
    }
    var sub = e.target.closest(".submenu-item");
    if (sub) {
      pickItem({ view: sub.dataset.view, roleId: sub.dataset.role || null, label: sub.textContent });
      renderMenu(); saveUi();
    }
  });

  function pickItem(it) {
    if (it.view === "chat" && it.roleId) {
      state.ui.roleId = it.roleId;
      // 「知识库问答」离开检索就没意义，选中它时顺手把开关拨上；关得掉，状态也看得见
      if (it.roleId === "kb" && !state.config.rag) {
        state.config.rag = true;
        write(LS.cfg, state.config);
        $("ragKb").checked = true;
      }
      refreshHint();
    }
    if (it.view === "prompt" && it.roleId) state.ui.promptId = it.roleId;
    state.ui.openGroups[groupOfView(it.view)] = true;
    switchView(it.view);
  }

  function saveUi() { write(LS.ui, state.ui); }

  function switchView(view) {
    state.ui.view = view;
    VIEWS.forEach(function (v) { $("view-" + v).classList.toggle("active", v === view); });
    $("chatActions").style.display = view === "chat" ? "flex" : "none";
    $("viewTitle").textContent = view === "chat" ? roleById(state.ui.roleId).title
      : view === "prompt" ? "配置 - " + (roleById(state.ui.promptId).promptLabel || "角色提示词")
      : (VIEW_TITLE[view] || "AI助手");
    if (view === "chat") { renderChat(); autoGrow(); refreshHint(); }
    if (view === "kb") loadKb();
    if (view === "prompt") renderPromptEditor();
    if (view === "settings") fillForm();
    if (view === "t2i" || view === "i2i") fillImagePickers();
    saveUi();
  }

  function applyCollapsed() {
    $("sidebar").classList.toggle("collapsed", !!state.ui.collapsed);
  }
  $("collapseBtn").addEventListener("click", function () {
    state.ui.collapsed = !state.ui.collapsed;
    applyCollapsed(); saveUi();
  });

  /* ---------------- 聊天渲染 ---------------- */
  function renderChat() {
    var role = roleById(state.ui.roleId);
    var list = currentMessages();
    $("viewTitle").textContent = role.title;
    $("modelTag").textContent = state.config.model;

    if (!list.length) {
      $("msgList").innerHTML = '<div class="empty"><b>' + escape(role.title) + "</b>" +
        (systemOf(role) ? "已加载角色设定，直接提问即可" : "有什么可以帮你的？") + "</div>";
      return;
    }
    var frag = document.createDocumentFragment();
    list.forEach(function (m, idx) { frag.appendChild(msgNode(m, idx)); });
    $("msgList").innerHTML = "";
    $("msgList").appendChild(frag);
    scrollBottom();
  }

  function toolNote(tools) {
    var s = tools.map(function (t) {
      var city = t.args && t.args.city;
      return t.name + (city ? "(" + city + ")" : "");
    }).join("、");
    return " · MCP：" + s;
  }

  // RAG 的引用来自后端响应头，形如 [{"name":"第3章.md","i":7,"score":0.612}]
  function ragNote(hits) {
    var s = hits.map(function (h) {
      return "《" + h.name + "》" + (h.i != null ? "第 " + h.i + " 段" : "")
        + (h.score != null ? " " + Number(h.score).toFixed(2) : "");
    }).join("、");
    return " · 知识库引用 " + hits.length + " 段：" + s;
  }

  function msgNode(m, idx) {
    var wrap = document.createElement("div");
    wrap.className = "msg " + (m.role === "user" ? "user" : "ai");
    var bubble = document.createElement("div");
    bubble.className = "bubble" + (m.error ? " err" : "");
    if (m.role === "user") bubble.textContent = m.content;
    else bubble.innerHTML = window.renderMarkdown(m.content);
    var time = document.createElement("div");
    time.className = "msg-time";
    time.textContent = fmtTime(m.ts) + (m.search ? " · 联网搜索" : "") +
      (m.tools && m.tools.length ? toolNote(m.tools) : "");
    if (m.rag && m.rag.length) {
      // 段名和相似度放 title 里，鼠标悬停看得到，时间行不至于被撑成三行
      time.textContent += " · 知识库 " + m.rag.length + " 段";
      time.title = ragNote(m.rag);
    }
    if (m.cache && m.cache.hit) {
      // 命中缓存这条根本没调模型，得说清是"复用"而不是"答得快"
      var tag = document.createElement("span");
      tag.className = "cache-tag";
      tag.textContent = "缓存命中 " + Number(m.cache.score || 0).toFixed(2) + " · 0 token";
      tag.title = "复用了「" + (m.cache.question || "") + "」的答案\n"
        + "没调大模型，答案直接来自 kb/collections/qa.json";
      time.appendChild(tag);
    }
    wrap.appendChild(bubble);
    wrap.appendChild(time);
    if (m.role !== "user") {
      var tools = document.createElement("div");
      tools.className = "msg-tools";
      tools.innerHTML = "<button data-act=copy>复制</button>" +
        (idx === currentMessages().length - 1 && !state.busy ? "<button data-act=regen>重新生成</button>" : "");
      tools.addEventListener("click", function (e) {
        var b = e.target.closest("button"); if (!b) return;
        if (b.dataset.act === "copy") copyText(m.content, b);
        if (b.dataset.act === "regen") regenerate(idx);
      });
      wrap.appendChild(tools);
    }
    return wrap;
  }

  function scrollBottom() {
    var el = $("msgList");
    el.scrollTop = el.scrollHeight;
  }

  // 剪贴板 API 在非聚焦窗口 / 未授权时会被拒，退回到 execCommand 再不行就明说
  function copyText(text, btn) {
    function legacy() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;top:-9999px;left:0";
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      return ok;
    }
    var p = (navigator.clipboard && navigator.clipboard.writeText)
      ? navigator.clipboard.writeText(text).then(function () { return true; }, legacy)
      : Promise.resolve(legacy());
    p.then(function (ok) {
      btn.textContent = ok ? "已复制" : "复制失败";
      setTimeout(function () { btn.textContent = "复制"; }, 1600);
    });
  }

  /* ---------------- 调用大模型 ---------------- */
  function buildMessages(history) {
    var role = roleById(state.ui.roleId);
    var sys = systemOf(role);
    var msgs = [];
    if (sys) msgs.push({ role: "system", content: sys });
    var limit = Number(state.config.historyLimit) || 0;
    var h = limit > 0 ? history.slice(-limit * 2) : history;
    h.forEach(function (m) { msgs.push({ role: m.role, content: m.content }); });
    return msgs;
  }

  // 唯一开关就是 composer 上那个勾；选「知识库问答」角色时会自动拨上（见 pickItem）
  function ragEnabled() { return !!state.config.rag; }

  function chatBody(messages, stream, model) {
    var mcp = !!state.config.mcp;
    var ragOn = ragEnabled();
    var role = roleById(state.ui.roleId);
    // 角色自带 temp 就用它（答题类锁 0、创意类留 0.8~0.9），否则用配置页的全局温度
    var temp = role && typeof role.temp === "number" ? role.temp : Number(state.config.temperature);
    var b = {
      model: model || state.config.model,
      baseUrl: state.config.baseUrl,
      messages: messages,
      temperature: temp
    };
    var seed = Number(state.config.seed);
    if (seed > 0) b.seed = seed;
    // 温度为 0（这个角色要的是同题同答）或勾了知识库，就先过一遍问答缓存；
    // 温度调上去说明想要变化，不再拿旧答案拦它。MCP 和识图在后端本来就不缓存。
    b.cache = ragOn || temp === 0;
    if (Number(state.config.maxTokens) > 0) b.max_tokens = Number(state.config.maxTokens);
    // MCP 这条路要在服务端来回问模型好几轮，只能整体返回，带不了流式
    if (mcp) b.mcp = true;
    else if (stream) b.stream = true;
    if (ragOn) b.rag = true;
    // 百炼的联网搜索开关：qwen 系列在 compatible-mode 下直接吃这个字段。
    // 知识库已经给了依据，再联网搜只会盖住本地资料，所以这两样不叠加。
    if (state.config.search && !mcp && !ragOn) b.enable_search = true;
    return JSON.stringify(b);
  }

  async function request(messages, onDelta, signal, model, meta) {
    var ctrl = signal || (function () {
      var c = new AbortController();
      setTimeout(function () { c.abort(); }, state.config.timeout || 120000);
      return c;
    })();
    var res;
    try {
      res = await fetch("api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: chatBody(messages, !!state.config.stream, model), signal: ctrl.signal
      });
    } catch (err) {
      if (err.name === "AbortError") throw new Error("请求超时或已取消：" + (backendHint() || "请检查网络"));
      throw new Error("无法连接后端：" + err.message + "（请确认已用 python api.py 启动，并通过 http://127.0.0.1:8000 访问）");
    }
    if (res.status === 401) { expired(); throw new Error("登录已过期，请重新登录"); }
    if (!res.ok) {
      var detail = "";
      try {
        var j = await res.json();
        detail = j.error || (typeof j.detail === "string" ? j.detail : JSON.stringify(j));
      } catch (e) {
        try { detail = await res.text(); } catch (e2) {}
      }
      throw new Error("HTTP " + res.status + " " + (detail || "").slice(0, 400));
    }
    // 引用清单走响应头，流式与非流式两条路都在这里一次性取到
    if (meta) {
      var src = res.headers.get("x-rag-sources");
      meta.rag = [];
      if (src) { try { meta.rag = JSON.parse(src) || []; } catch (e) { /* 头坏了就当没引用 */ } }
      var ch = res.headers.get("x-rag-cache");
      if (ch) { try { meta.cache = JSON.parse(ch) || null; } catch (e) { /* 同上 */ } }
    }
    // MCP 那一路返回的是普通 JSON 而不是 SSE，按 content-type 判断比看开关更可靠
    var ctype = res.headers.get("content-type") || "";
    if (!state.config.stream || !res.body || ctype.indexOf("text/event-stream") < 0) {
      var json = await res.json();
      var txt = json && json.choices && json.choices[0] && json.choices[0].message ? json.choices[0].message.content : "";
      if (meta) meta.calls = json.mcpCalls || [];
      if (onDelta && txt) onDelta(txt);
      return txt;
    }

    var reader = res.body.getReader();
    var decoder = new TextDecoder("utf-8");
    var buf = "", full = "";
    while (true) {
      var r = await reader.read();
      if (r.done) break;
      buf += decoder.decode(r.value, { stream: true });
      var parts = buf.split("\n\n");
      buf = parts.pop();
      for (var i = 0; i < parts.length; i++) {
        var dataLines = parts[i].split("\n").filter(function (l) { return l.indexOf("data:") === 0; });
        if (!dataLines.length) continue;
        var payload = dataLines.map(function (l) { return l.slice(5).trim(); }).join("");
        if (!payload || payload === "[DONE]") continue;
        try {
          var obj = JSON.parse(payload);
          var d = obj.choices && obj.choices[0] && (obj.choices[0].delta || obj.choices[0].message);
          var piece = d && d.content ? d.content : "";
          if (piece) { full += piece; if (onDelta) onDelta(piece); }
        } catch (e) { /* 忽略心跳/不完整分片 */ }
      }
    }
    return full;
  }

  /* ---------------- 发送 ---------------- */
  async function send(text) {
    text = (text || "").trim();
    if (!text || state.busy) return;
    if (!configed()) { notifyNotReady(); return; }
    var list = currentMessages();
    list.push({ role: "user", content: text, ts: Date.now() });
    var reply = { role: "assistant", content: "", ts: Date.now(),
                  search: !!state.config.search && !state.config.mcp && !ragEnabled() };
    list.push(reply);
    renderChat();

    state.busy = true;
    $("sendBtn").disabled = true;
    $("stopBtn").hidden = false;
    $("tokenHint").textContent = "正在思考…";
    var aiEl = $("msgList").lastElementChild.querySelector(".bubble");
    if (aiEl) aiEl.classList.add("cursor");
    state.controller = new AbortController();
    var meta = {};

    try {
      await request(buildMessages(list.slice(0, -1)), function (piece) {
        reply.content += piece;
        if (aiEl && aiEl.isConnected) {
          aiEl.innerHTML = window.renderMarkdown(reply.content);
          aiEl.classList.add("cursor");
          var last = $("msgList").lastElementChild;
          if (last && last.querySelector(".bubble") === aiEl) scrollBottom();
        }
      }, state.controller.signal, null, meta);
      if (!reply.content) reply.content = "(模型未返回内容)";
    } catch (err) {
      reply.content = String(err && err.message || err);
      reply.error = true;
    } finally {
      if (meta.calls && meta.calls.length) reply.tools = meta.calls;
      if (meta.rag && meta.rag.length) reply.rag = meta.rag;
      if (meta.cache && meta.cache.hit) reply.cache = meta.cache;
      reply.ts = Date.now();
      state.busy = false;
      state.controller = null;
      $("sendBtn").disabled = false;
      $("stopBtn").hidden = true;
      refreshHint();
      saveHistory(state.ui.roleId);
      renderChat();
      updateStatus();
    }
  }

  function regenerate(idx) {
    if (!configed()) { notifyNotReady(); return; }
    var list = currentMessages();
    while (list.length > idx) list.pop();
    var last = list[list.length - 1];
    if (!last || last.role !== "user") { saveHistory(state.ui.roleId); renderChat(); return; }
    var reply = { role: "assistant", content: "", ts: Date.now(),
                  search: !!state.config.search && !state.config.mcp && !ragEnabled() };
    list.push(reply);
    state.busy = true;
    renderChat();
    var aiEl = $("msgList").lastElementChild.querySelector(".bubble");
    if (aiEl) aiEl.classList.add("cursor");
    $("sendBtn").disabled = true; $("stopBtn").hidden = false;
    state.controller = new AbortController();
    var meta = {};
    request(buildMessages(list.slice(0, -1)), function (p) {
      reply.content += p;
      if (aiEl && aiEl.isConnected) { aiEl.innerHTML = window.renderMarkdown(reply.content); aiEl.classList.add("cursor"); scrollBottom(); }
    }, state.controller.signal, null, meta).catch(function (e) {
      reply.content = String(e.message || e); reply.error = true;
    }).then(function () {
      if (meta.calls && meta.calls.length) reply.tools = meta.calls;
      if (meta.rag && meta.rag.length) reply.rag = meta.rag;
      if (meta.cache && meta.cache.hit) reply.cache = meta.cache;
      reply.ts = Date.now();
    }).finally(function () {
      state.busy = false; state.controller = null;
      $("sendBtn").disabled = false; $("stopBtn").hidden = true;
      saveHistory(state.ui.roleId);
      renderChat();
    });
  }

  function notifyNotReady() {
    var msg = backendHint() || "暂不可用";
    if (state.ui.view === "settings") { $("cfgHint").textContent = msg; return; }
    pickItem({ view: "settings" });
    renderMenu();
    $("cfgHint").textContent = msg;
  }

  $("sendBtn").addEventListener("click", function () {
    send($("input").value); $("input").value = ""; autoGrow();
  });
  $("stopBtn").addEventListener("click", function () {
    if (state.controller) state.controller.abort();
  });
  function dropConversation() {
    var roleId = state.ui.roleId;
    state.convos[roleId] = [];
    postJSON("api/history/clear", { role: roleId }).catch(function () {});
    renderChat();
    return roleId;
  }
  $("clearBtn").addEventListener("click", function () {
    if (!currentMessages().length) return;
    if (!confirm("确定清空当前会话的全部消息？")) return;
    dropConversation();
  });
  $("newChatBtn").addEventListener("click", function () {
    if (currentMessages().length) {
      if (!confirm("开始新会话将清空当前角色的聊天记录，继续？")) return;
    }
    dropConversation();
    $("input").focus();
  });
  function composerHint() {
    if (state.config.rag) return "知识库问答已开启：先查问答缓存，意思问过的直接复用答案（0 token）；没命中再检索片段、拼进提示词问模型";
    if (state.config.mcp) return "MCP 天气已开启：模型会自行调用 get_weather 查实时天气，耗时略长";
    if (state.config.search) return "联网搜索已开启：回答前先检索，耗时会略长";
    var hintRole = roleById(state.ui.roleId);
    var hintTemp = hintRole && typeof hintRole.temp === "number" ? hintRole.temp : Number(state.config.temperature);
    if (hintTemp === 0) return "这个角色温度锁在 0：同一道题每次给同一个答案（先查问答缓存，命中 0 token）";
    return IDLE_HINT;
  }
  // 回答结束、切换角色、开机进来都要重新算一次，否则「温度锁在 0」这句会被默认的 Enter 提示盖掉
  function refreshHint() { $("tokenHint").textContent = composerHint(); }
  function bindToggle(id, field) {
    $(id).addEventListener("change", function () {
      state.config[field] = $(id).checked;
      write(LS.cfg, state.config);
      refreshHint();
    });
  }
  bindToggle("ragKb", "rag");
  bindToggle("webSearch", "search");
  bindToggle("mcpWeather", "mcp");

  var input = $("input");
  var IDLE_HINT = "Enter 发送 · Shift+Enter 换行";
  function autoGrow() {
    if (!input.offsetParent) return;
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 180) + "px";
  }
  input.addEventListener("input", autoGrow);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      send(input.value); input.value = ""; autoGrow();
    }
  });

  /* ---------------- 图片理解（对话分组） ---------------- */
  function showPicked(f, dataUrl, dims) {
    state.imageData = dataUrl;
    $("previewImg").src = dataUrl;
    $("preview").hidden = false;
    $("drop").style.display = "none";
    $("imgHint").textContent = f.name + " · " + dims.w + "×" + dims.h + " · " + (f.size / 1024).toFixed(0) + " KB";
  }
  function pickImage(file, onOk, onErr) {
    if (!file || !/^image\//.test(file.type)) { onErr("请选择图片文件"); return; }
    if (file.size > 4 * 1024 * 1024) { onErr("图片超过 4MB，请先压缩"); return; }
    var fr = new FileReader();
    fr.onload = function () {
      var url = String(fr.result);
      var probe = new Image();
      probe.onload = function () { onOk(file, url, { w: probe.naturalWidth, h: probe.naturalHeight }); };
      probe.onerror = function () { onErr("这张图片读不出来，换一张试试"); };
      probe.src = url;
    };
    fr.onerror = function () { onErr("读取文件失败"); };
    fr.readAsDataURL(file);
  }
  $("drop").addEventListener("click", function () { $("file").click(); });
  $("file").addEventListener("change", function (e) {
    pickImage(e.target.files[0], showPicked, function (m) { $("imgHint").textContent = m; });
  });
  ["dragover", "dragenter"].forEach(function (t) {
    $("drop").addEventListener(t, function (e) { e.preventDefault(); $("drop").classList.add("over"); });
  });
  $("drop").addEventListener("dragleave", function () { $("drop").classList.remove("over"); });
  $("drop").addEventListener("drop", function (e) {
    e.preventDefault(); $("drop").classList.remove("over");
    pickImage(e.dataTransfer.files[0], showPicked, function (m) { $("imgHint").textContent = m; });
  });
  $("removeImg").addEventListener("click", function () {
    state.imageData = ""; $("file").value = "";
    $("preview").hidden = true; $("drop").style.display = "";
    $("imgHint").textContent = "";
  });
  $("imgClear").addEventListener("click", function () {
    $("imgResult").innerHTML = '<span class="placeholder">暂无结果</span>';
  });
  $("imgRun").addEventListener("click", function () {
    if (!configed()) { notifyNotReady(); return; }
    if (!state.imageData) { $("imgHint").textContent = "请先选择图片"; return; }
    var prompt = $("imgPrompt").value.trim() || "请详细描述这张图片的内容。";
    var box = $("imgResult");
    box.innerHTML = "";
    $("imgRun").disabled = true;
    $("imgHint").textContent = "处理中…";
    var msgs = [{
      role: "user",
      content: [{ type: "text", text: prompt }, { type: "image_url", image_url: { url: state.imageData } }]
    }];
    var acc = "";
    request(msgs, function (p) {
      acc += p;
      box.innerHTML = window.renderMarkdown(acc);
    }, null, state.config.visionModel || "qwen3-vl-plus").then(function (txt) {
      if (!acc) box.innerHTML = window.renderMarkdown(txt || "模型未返回内容");
    }).catch(function (e) {
      box.innerHTML = '<span style="color:#c0392b">' + escape(String(e.message || e)) + "</span>";
    }).finally(function () {
      $("imgRun").disabled = false;
      $("imgHint").textContent = "完成 " + fmtTime(Date.now());
    });
  });

  /* ---------------- 文生图 / 图生图 ---------------- */
  var SIZES = null;
  function fillImagePickers() {
    var sizes = state.backend.imageSizes.length ? state.backend.imageSizes : defaults.imageSizes;
    var models = state.backend.imageModels.length ? state.backend.imageModels : defaults.imageModels;
    var max = state.backend.imageMaxCount || defaults.imageMaxCount;
    if (JSON.stringify(sizes) !== JSON.stringify(SIZES)) {
      SIZES = sizes;
      ["t2iSize", "i2iSize"].forEach(function (id) {
        var sel = $(id), keep = sel.value;
        sel.innerHTML = sizes.map(function (s) { return '<option value="' + s + '">' + s + "</option>"; }).join("");
        if (sizes.indexOf(keep) >= 0) sel.value = keep;
      });
    }
    ["t2iN", "i2iN"].forEach(function (id) {
      var sel = $(id), keep = sel.value;
      sel.innerHTML = "";
      for (var i = 1; i <= max; i++) {
        var o = document.createElement("option");
        o.value = String(i); o.textContent = i + " 张";
        sel.appendChild(o);
      }
      sel.value = keep && +keep <= max ? keep : "1";
    });
    if (models.length) {
      ["t2iModel", "i2iModel"].forEach(function (id) {
        if (!$(id)) return;
        var sel = $(id), keep = sel.value;
        sel.innerHTML = models.map(function (m) { return '<option value="' + escape(m) + '">' + escape(m) + "</option>"; }).join("");
        if (models.indexOf(keep) >= 0) sel.value = keep;
      });
    }
  }

  function galleryPending(kind, n) {
    $(kind + "Result").innerHTML = '<div class="shot pending"><span class="spinner"></span>' +
      "正在生成 " + n + " 张，请稍候…</div>";
  }
  function galleryFailed(kind, msg) {
    $(kind + "Result").innerHTML = '<div class="shot failed">' + escape(msg) + "</div>";
    $(kind + "Hint").textContent = "失败 " + fmtTime(Date.now());
  }
  function galleryDone(kind, images, meta) {
    var box = $(kind + "Result");
    box.innerHTML = "";
    images.forEach(function (src, i) {
      var shot = document.createElement("div");
      shot.className = "shot";
      var img = document.createElement("img");
      img.src = src;
      img.alt = "第 " + (i + 1) + " 张生成结果";
      var bar = document.createElement("div");
      bar.className = "bar";
      bar.innerHTML = "<span>" + (i + 1) + " / " + images.length + "</span>";
      var a = document.createElement("a");
      a.href = src;
      a.download = kind + "-" + Date.now() + "-" + (i + 1) + ".png";
      a.textContent = "下载";
      bar.appendChild(a);
      shot.appendChild(img);
      shot.appendChild(bar);
      box.appendChild(shot);
    });
    $(kind + "Hint").textContent = meta + " · 完成 " + fmtTime(Date.now());
  }

  async function runGeneration(kind) {
    if (state.gen[kind]) return;
    if (!configed()) { notifyNotReady(); return; }
    var prompt = $(kind + "Prompt").value.trim();
    if (!prompt) { $(kind + "Hint").textContent = "请先写提示词"; return; }
    var payload = {
      kind: kind, prompt: prompt,
      size: $(kind + "Size").value, n: Number($(kind + "N").value)
    };
    var modelSel = $(kind + "Model");
    if (modelSel && modelSel.value) payload.model = modelSel.value;
    if (kind === "t2i") {
      payload.negativePrompt = $("t2iNegative").value.trim();
    } else {
      if (!state.i2iImage) { $("i2iHint").textContent = "请先选择参考图"; return; }
      payload.images = [state.i2iImage];
    }
    state.gen[kind] = true;
    var btn = $(kind + "Run");
    btn.disabled = true;
    $(kind + "Hint").textContent = "提交中…";
    galleryPending(kind, payload.n);
    try {
      var r = await postJSON("api/image", payload);
      galleryDone(kind, r.images, r.model + " · " + r.size + " · " + r.seconds + " 秒");
    } catch (e) {
      galleryFailed(kind, String(e.message || e));
    } finally {
      state.gen[kind] = false;
      btn.disabled = false;
    }
  }

  $("t2iRun").addEventListener("click", function () { runGeneration("t2i"); });
  $("i2iRun").addEventListener("click", function () { runGeneration("i2i"); });
  $("t2iClear").addEventListener("click", function () {
    $("t2iResult").innerHTML = '<span class="placeholder">暂无结果</span>';
  });
  $("i2iClear").addEventListener("click", function () {
    $("i2iResult").innerHTML = '<span class="placeholder">暂无结果</span>';
  });

  function showRef(file, dataUrl, dims) {
    state.i2iImage = dataUrl;
    $("i2iImg").src = dataUrl;
    $("i2iPreview").hidden = false;
    $("i2iDrop").style.display = "none";
    $("i2iHint").textContent = file.name + " · " + dims.w + "×" + dims.h;
  }
  function bindDrop(dropId, fileId, handler) {
    $(dropId).addEventListener("click", function () { $(fileId).click(); });
    $(fileId).addEventListener("change", function (e) { handler(e.target.files[0]); });
    ["dragover", "dragenter"].forEach(function (t) {
      $(dropId).addEventListener(t, function (e) { e.preventDefault(); $(dropId).classList.add("over"); });
    });
    $(dropId).addEventListener("dragleave", function () { $(dropId).classList.remove("over"); });
    $(dropId).addEventListener("drop", function (e) {
      e.preventDefault(); $(dropId).classList.remove("over");
      handler(e.dataTransfer.files[0]);
    });
  }
  bindDrop("i2iDrop", "i2iFile", function (f) {
    pickImage(f, showRef, function (m) { $("i2iHint").textContent = m; });
  });
  $("i2iRemove").addEventListener("click", function () {
    state.i2iImage = ""; $("i2iFile").value = "";
    $("i2iPreview").hidden = true; $("i2iDrop").style.display = "";
    $("i2iHint").textContent = "";
  });

  /* ---------------- 知识库（RAG） ---------------- */
  var kbBusy = false;

  // 学生机上的 txt 常常是 GBK，先用 fatal 严格解 UTF-8，解不动再退 GBK
  function readTextFile(file) {
    return new Promise(function (resolve, reject) {
      var fr = new FileReader();
      fr.onerror = function () { reject(new Error("读取文件失败")); };
      fr.onload = function () {
        var buf = new Uint8Array(fr.result);
        var text = null;
        try { text = new TextDecoder("utf-8", { fatal: true }).decode(buf); }
        catch (e) {
          try { text = new TextDecoder("gbk").decode(buf); }
          catch (e2) { reject(new Error("这份文件既不是 UTF-8 也不是 GBK，请另存为纯文本")); }
        }
        if (text !== null) resolve(text.replace(/^/, ""));
      };
      fr.readAsArrayBuffer(file);
    });
  }

  function renderKbStatus(s) {
    var bits = ["文档 " + s.docs.length + " 份", "片段 " + s.totalChunks + " 个",
      "正文 " + s.totalChars + " 字", "向量模型 " + s.model + " · " + s.dim + " 维",
      "切片 " + s.chunkChars + " 字/片", "取 top-" + s.topK + " · 阈值 " + s.minScore,
      "单份上限 " + s.maxDocChars + " 字"];
    $("kbStats").innerHTML = bits.map(function (b) { return "<span>" + escape(b) + "</span>"; }).join("");
  }

  function renderKbDocs(docs) {
    var box = $("kbDocs");
    if (!docs.length) {
      box.innerHTML = '<span class="placeholder">还没有文档。上传一份 md 或 txt，' +
        '等它切片、向量化落盘到 kb 目录，就能在「对话 → 知识库问答」里提问了。</span>';
      return;
    }
    box.innerHTML = docs.map(function (d) {
      return '<div class="kb-doc' + (d.current ? "" : " stale") + '">' +
        '<span class="nm">' + escape(d.name) + "</span>" +
        '<span class="meta">' + d.chars + " 字 · " + d.chunks + " 片 · " +
        fmtTime(d.createdAt * 1000) +
        (d.current ? "" : " · 向量模型或维度已改，这份需要重新上传") + "</span>" +
        '<button class="ghost-btn sm" data-del="' + escape(d.id) + '">删除</button></div>';
    }).join("");
  }

  async function loadKb() {
    if (!state.user) return;
    try {
      var s = await getJSON("api/rag/status");
      renderKbStatus(s);
      renderKbDocs(s.docs);
    } catch (e) {
      $("kbStats").textContent = "读不到知识库状态：" + e.message;
    }
    loadKbCache();
  }

  async function ingestFiles(files) {
    if (kbBusy) return;
    var list = Array.prototype.slice.call(files || []).filter(function (f) {
      return /\.(md|markdown|txt|text)$/i.test(f.name) || f.type === "text/plain";
    });
    if (!list.length) { $("kbHint").textContent = "只收 md / txt 文本文件"; return; }
    kbBusy = true;
    var failed = [];
    for (var i = 0; i < list.length; i++) {
      var f = list[i];
      if (f.size > 800 * 1024) { failed.push(f.name + "：超过 800KB"); continue; }
      $("kbHint").textContent = "正在切片并向量化 " + (i + 1) + "/" + list.length + "：" + f.name + "…";
      try {
        var text = await readTextFile(f);
        var r = await postJSON("api/rag/doc", { name: f.name, text: text });
        $("kbHint").textContent = f.name + " 已入库：" + r.doc.chars + " 字切成 " + r.doc.chunks +
          " 片，向量化用了 " + r.doc.seconds + " 秒";
      } catch (e) {
        failed.push(f.name + "：" + (e.message || e));
      }
      await loadKb();  // 每份入库就刷新列表，批量上传时能看到进度
    }
    if (failed.length) $("kbHint").textContent = "失败 " + failed.length + " 份：" + failed.join("；");
    kbBusy = false;
  }

  function renderKbHits(r) {
    var box = $("kbHits");
    if (!r.hits.length) {
      box.innerHTML = '<span class="placeholder">候选 ' + (r.diag.candidates || 0) +
        " 段，但没有一段过阈值 " + r.diag.minScore + "。要么库里确实没相关内容，" +
        "要么在 config.py 里把 RAG_MIN_SCORE 调低、RAG_TOP_K 调高再试。</span>";
      return;
    }
    box.innerHTML = r.hits.map(function (h) {
      return '<div class="kb-hit' + (h.score < 0.5 ? " cold" : "") + '">' +
        '<div class="top"><span class="sc">' + h.score.toFixed(4) + "</span>" +
        "<span>《" + escape(h.name) + "》第 " + h.i + " 段</span></div>" +
        '<div class="body">' + escape(h.text) + "</div></div>";
    }).join("");
  }

  async function runKbSearch() {
    var q = $("kbQuery").value.trim();
    if (!q) { $("kbHint").textContent = "先写一句要检索的话"; return; }
    $("kbSearchBtn").disabled = true;
    $("kbHits").innerHTML = '<span class="placeholder">检索中…（问题也要向量化一次）</span>';
    try {
      var r = await postJSON("api/rag/search", { query: q });
      renderKbHits(r);
      $("kbHint").textContent = "候选 " + (r.diag.candidates || 0) + " 段 · 命中 " + r.hits.length +
        " 段 · 耗时 " + r.seconds + " 秒";
    } catch (e) {
      $("kbHits").innerHTML = '<span class="placeholder">检索失败：' + escape(String(e.message || e)) + "</span>";
    } finally {
      $("kbSearchBtn").disabled = false;
    }
  }

  function renderKbCache(c) {
    var s = c.stats;
    var bits = ["已存 " + s.items + " 条 · 累计复用 " + s.totalHits + " 次",
      "命中阈值 " + c.minScore, "上限 " + c.maxEntries + " 条，超了淘汰最久没用过的",
      "kb/collections/" + c.collection + ".json · " + (s.bytes / 1024).toFixed(1) + " KB"];
    bits.push(c.enabled ? "开启中：温度 0 的角色或勾了知识库就自动查" : "已关闭（config.py 的 CACHE_ENABLED = False）");
    if (c.ttl > 0) bits.push(c.ttl + " 秒没再问到就过期");
    $("kbCacheStats").innerHTML = bits.map(function (b) { return "<span>" + escape(b) + "</span>"; }).join("");
    var box = $("kbCacheList");
    if (!c.items.length) {
      box.innerHTML = '<span class="placeholder">还没有缓存。在「对话 → 知识库问答」里问过、' +
        "而且模型确实引用了资料的答案，会自动存进这里。</span>";
      return;
    }
    box.innerHTML = c.items.map(function (it) {
      return '<div class="kb-doc' + (it.current ? "" : " stale") + '" title="' +
        escape(String(it.answer || "").slice(0, 200)) + '">' +
        '<span class="nm">' + escape(it.question) + "</span>" +
        '<span class="meta">复用 ' + it.hits + " 次 · 引用 " + (it.sources || []).length +
        " 段 · 作用域 " + escape(String(it.scope || "").slice(0, 8)) +
        " · " + fmtTime(it.updatedAt * 1000) +
        (it.current ? "" : " · 参数或资料已变更，这条不再复用") + "</span>" +
        '<button class="ghost-btn sm" data-cdel="' + escape(it.id) + '">删除</button></div>';
    }).join("");
  }

  async function loadKbCache() {
    if (!state.user) return;
    try {
      renderKbCache(await getJSON("api/rag/cache"));
    } catch (e) {
      $("kbCacheStats").textContent = "读不到缓存：" + (e.message || e);
    }
  }

  async function probeCache() {
    var q = $("kbCacheQuery").value.trim();
    if (!q) { $("kbCacheHint").textContent = "先写一句要探测的问题"; return; }
    $("kbCacheBtn").disabled = true;
    $("kbCacheHint").textContent = "正在把这句问题向量化并查缓存…";
    try {
      // 作用域要按「知识库问答人设 + 当前检索开关 + 这个角色的温度」算，才和真实对话那条路一致
      var role = roleById("kb");
      var temp = typeof role.temp === "number" ? role.temp : Number(state.config.temperature);
      var modeNote = "（作用域：知识库问答人设 + " + (state.config.rag ? "开检索" : "不开检索") +
        " + 温度 " + temp + "）";
      var r = await postJSON("api/rag/cache/lookup", {
        query: q, model: state.config.model, rag: !!state.config.rag, temperature: temp,
        messages: [{ role: "system", content: systemOf(role) }, { role: "user", content: q }]
      });
      var d = r.diag || {};
      if (r.hit) {
        $("kbCacheHint").textContent = "会命中：相似度 " + r.score + "（阈值 " + d.minScore +
          "）· 命中的是「" + r.question + "」· 耗时 " + r.seconds + " 秒，不调模型、0 token" + modeNote;
      } else {
        var why = d.best == null
          ? (d.filtered ? "（库里 " + d.filtered + " 条是别人设 / 别的温度 / 别的检索开关存的，作用域不同、不参与匹配）"
                        : "（这句问题库里没有可比的）")
          : "：库里最像的只有 " + d.best + "，没到阈值 " + d.minScore + "，会正常检索并重新生成";
        $("kbCacheHint").textContent = "不会命中" + why +
          " · 候选 " + (d.candidates || 0) + " 条 · 耗时 " + r.seconds + " 秒" + modeNote;
      }
    } catch (e) {
      $("kbCacheHint").textContent = "探测失败：" + (e.message || e);
    } finally {
      $("kbCacheBtn").disabled = false;
    }
  }

  $("kbCacheBtn").addEventListener("click", probeCache);
  $("kbCacheQuery").addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.isComposing) probeCache();
  });
  $("kbCacheClear").addEventListener("click", async function () {
    if (!confirm("清空后所有问题都要重新问模型一次。继续？")) return;
    try {
      var r = await postJSON("api/rag/cache/clear", {});
      $("kbCacheHint").textContent = "已清空 " + r.removed + " 条缓存";
      await loadKbCache();
    } catch (e) {
      $("kbCacheHint").textContent = "清空失败：" + (e.message || e);
    }
  });
  $("kbCacheList").addEventListener("click", async function (e) {
    var btn = e.target.closest("[data-cdel]");
    if (!btn) return;
    btn.disabled = true;
    try {
      await postJSON("api/rag/cache/clear", { ids: [btn.dataset.cdel] });
      await loadKbCache();
    } catch (err) {
      $("kbCacheHint").textContent = "删除失败：" + (err.message || err);
      btn.disabled = false;
    }
  });

  $("kbDrop").addEventListener("click", function () { $("kbFile").click(); });
  $("kbFile").addEventListener("change", function (e) {
    ingestFiles(e.target.files);
    e.target.value = "";  // 允许连续上传同名文件
  });
  ["dragover", "dragenter"].forEach(function (t) {
    $("kbDrop").addEventListener(t, function (e) { e.preventDefault(); $("kbDrop").classList.add("over"); });
  });
  $("kbDrop").addEventListener("dragleave", function () { $("kbDrop").classList.remove("over"); });
  $("kbDrop").addEventListener("drop", function (e) {
    e.preventDefault(); $("kbDrop").classList.remove("over");
    ingestFiles(e.dataTransfer.files);
  });
  $("kbSearchBtn").addEventListener("click", runKbSearch);
  $("kbQuery").addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.isComposing) runKbSearch();
  });
  $("kbDocs").addEventListener("click", async function (e) {
    var btn = e.target.closest("[data-del]");
    if (!btn) return;
    if (!confirm("删除后这份资料的向量索引就没了，要重新上传才能用。继续？")) return;
    btn.disabled = true;
    try {
      await postJSON("api/rag/doc/remove", { id: btn.dataset.del });
      $("kbHint").textContent = "已删除该文档的 kb 索引文件";
      await loadKb();
    } catch (err) {
      $("kbHint").textContent = "删除失败：" + (err.message || err);
      btn.disabled = false;
    }
  });

  /* ---------------- 角色提示词编辑 ---------------- */
  function promptChoices() {
    return allRoles().filter(function (r) { return r.id !== "normal"; });
  }
  function renderPromptEditor() {
    var list = promptChoices();
    if (!list.some(function (r) { return r.id === state.ui.promptId; })) state.ui.promptId = list[0].id;
    var sel = $("promptRole");
    sel.innerHTML = list.map(function (r) {
      return '<option value="' + r.id + '">' + escape(r.short || r.title) + "</option>";
    }).join("");
    sel.value = state.ui.promptId;
    var role = roleById(state.ui.promptId);
    $("promptText").value = systemOf(role);
    promptHint(role);
  }
  function promptHint(role) {
    var custom = state.prompts[role.id] !== undefined;
    $("promptHint").innerHTML = (custom ? "已自定义（覆盖 config.js 默认）" : "当前用的是 config.js 里的默认设定") +
      " · " + ($("promptText").value.length) + " 字";
  }
  $("promptRole").addEventListener("change", function () {
    state.ui.promptId = $("promptRole").value;
    renderPromptEditor(); renderMenu(); saveUi();
  });
  $("promptText").addEventListener("input", function () {
    promptHint(roleById(state.ui.promptId));
  });
  $("savePrompt").addEventListener("click", function () {
    var role = roleById(state.ui.promptId);
    var text = $("promptText").value;
    var btn = $("savePrompt");
    btn.disabled = true;
    postJSON("api/prompt", { role: role.id, content: text }).then(function () {
      if (text.trim()) state.prompts[role.id] = text; else delete state.prompts[role.id];
      $("promptHint").textContent = "已写入 prompts/" + role.id + ".md · " + fmtTime(Date.now());
      renderChat();
    }).catch(function (e) {
      $("promptHint").textContent = "保存失败：" + e.message;
    }).finally(function () {
      btn.disabled = false;
    });
  });
  $("resetPrompt").addEventListener("click", function () {
    var role = roleById(state.ui.promptId);
    postJSON("api/prompt", { role: role.id, content: "" }).then(function () {
      delete state.prompts[role.id];
      $("promptText").value = role.system || "";
      promptHint(role);
      $("promptHint").textContent = "已删除 prompts/" + role.id + ".md，回到 config.js 默认设定";
      renderChat();
    }).catch(function (e) {
      $("promptHint").textContent = "恢复失败：" + e.message;
    });
  });
  $("gotoChat").addEventListener("click", function () {
    pickItem({ view: "chat", roleId: state.ui.promptId });
    renderMenu();
  });

  /* ---------------- 配置页 ---------------- */
  function fillForm() {
    var c = state.config;
    $("cfgBaseUrl").value = c.baseUrl || "";
    fillModelSelect();
    $("cfgModel").value = c.model || "";
    $("cfgTemp").value = c.temperature;
    $("cfgSeed").value = c.seed == null ? 0 : c.seed;
    $("cfgMax").value = c.maxTokens || 0;
    $("cfgLimit").value = c.historyLimit == null ? 20 : c.historyLimit;
    $("cfgStream").checked = !!c.stream;
    $("ragKb").checked = !!c.rag;
    $("webSearch").checked = !!c.search;
    $("mcpWeather").checked = !!c.mcp;
    renderKeyMask();
    renderPresets(); renderRoles();
  }
  function fillModelSelect() {
    var sel = $("cfgModel"), want = state.config.model;
    var base = (state.backend.model ? [state.backend.model] : []).
      concat(state.config.chatModels || defaults.chatModels).
      concat(window.AI_CHAT_MODELS || []);
    var uniq = [];
    base.concat([want]).forEach(function (m) { if (m && uniq.indexOf(m) < 0) uniq.push(m); });
    sel.innerHTML = uniq.map(function (m) {
      return '<option value="' + escape(m) + '">' + escape(m) + "</option>";
    }).join("");
  }
  function renderKeyMask() {
    var el = $("keyMask"); if (!el) return;
    var b = state.backend;
    if (openedByFile()) { el.textContent = "当前是用 file:// 打开的，页面连不到后端。请在地址栏输入 http://127.0.0.1:8000 重新访问。"; return; }
    if (!b.online) { el.textContent = "未检测到后端服务。请在项目目录执行 python api.py，再用 http://127.0.0.1:8000 打开本页。"; return; }
    if (!b.hasKey) { el.textContent = "后端已启动，但 config.py 中的 API_KEY 仍为空，对话功能不可用。填写后需重启后端。"; return; }
    el.textContent = "密钥由后端保管，浏览器中不存在明文。当前已加载末 4 位为 " + b.keyTail + " 的 Key。更换请编辑 config.py 后重启 python api.py。";
  }
  function renderPresets() {
    $("presets").innerHTML = (window.AI_PRESETS || []).map(function (p, i) {
      var on = p.baseUrl === state.config.baseUrl;
      return '<span class="chip' + (on ? " on" : "") + '" data-i="' + i + '">' + escape(p.name) + "</span>";
    }).join("");
  }
  $("presets").addEventListener("click", function (e) {
    var chip = e.target.closest(".chip"); if (!chip) return;
    var p = window.AI_PRESETS[+chip.dataset.i];
    $("cfgBaseUrl").value = p.baseUrl;
    if (p.models && p.models.length) {
      (p.models || []).forEach(function (m) {
        if ((state.config.chatModels || []).indexOf(m) < 0) state.config.chatModels.push(m);
      });
    }
    if (p.model) $("cfgModel").value = p.model;
    saveConfig();
    $("cfgHint").innerHTML = '已切换：' + escape(p.name) +
      (p.keyUrl ? '　<a href="' + p.keyUrl + '" target="_blank" rel="noopener">去申请 API Key</a>' : "");
  });
  function renderRoles() {
    $("roleList").innerHTML = state.customRoles.length ? state.customRoles.map(function (r, i) {
      return '<div class="role-row"><span class="nm">' + escape(r.title) + '</span>' +
        '<span class="sy">' + escape(r.system || "") + '</span>' +
        '<button class="ghost-btn sm" data-i="' + i + '">删除</button></div>';
    }).join("") : '<span class="hint">暂无自定义角色</span>';
  }
  $("roleList").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-i]"); if (!b) return;
    var i = +b.dataset.i;
    var id = state.customRoles[i].id;
    if (!confirm("删除角色「" + state.customRoles[i].title + "」？")) return;
    state.customRoles.splice(i, 1);
    delete state.convos[id];
    write(LS.roles, state.customRoles);
    postJSON("api/history/clear", { role: id }).catch(function () {});
    if (state.ui.roleId === id) state.ui.roleId = "normal";
    renderRoles(); renderMenu(); switchView(state.ui.view);
  });
  $("addRole").addEventListener("click", function () {
    var name = $("newRoleName").value.trim();
    var sys = $("newRoleSystem").value.trim();
    if (!name) { $("cfgHint").textContent = "请填写角色名称"; return; }
    state.customRoles.push({ id: "c" + Date.now(), title: "角色对话 - " + name, system: sys });
    write(LS.roles, state.customRoles);
    $("newRoleName").value = ""; $("newRoleSystem").value = "";
    renderRoles(); renderMenu();
    $("cfgHint").textContent = "已添加角色「" + name + "」，在左侧「对话」中使用";
  });
  function saveConfig() {
    state.config = Object.assign({}, state.config, {
      baseUrl: $("cfgBaseUrl").value.trim(),
      model: $("cfgModel").value.trim(),
      temperature: $("cfgTemp").value === "" ? defaults.temperature : Number($("cfgTemp").value),
      seed: Number($("cfgSeed").value) || 0,
      maxTokens: Number($("cfgMax").value) || 0,
      historyLimit: Number($("cfgLimit").value) || 0,
      stream: $("cfgStream").checked
    });
    delete state.config.apiKey;
    write(LS.cfg, state.config);
    updateStatus(); $("modelTag").textContent = state.config.model;
    renderPresets();
  }
  $("saveCfg").addEventListener("click", function () {
    saveConfig();
    $("cfgHint").textContent = "已保存到浏览器本地 " + fmtTime(Date.now());
  });
  $("resetCfg").addEventListener("click", function () {
    localStorage.removeItem(LS.cfg);
    state.config = Object.assign({}, defaults);
    fillForm(); updateStatus();
    $("cfgHint").textContent = "已恢复 config.js 中的默认值";
  });
  $("testCfg").addEventListener("click", async function () {
    saveConfig();
    $("cfgHint").textContent = "正在测试连接…";
    try {
      var txt = await request([{ role: "user", content: "回复“连接正常”四个字" }], null);
      $("cfgHint").textContent = "连接成功：" + String(txt || "").slice(0, 60);
    } catch (e) {
      $("cfgHint").textContent = "连接失败：" + String(e.message || e).slice(0, 160);
    }
  });

  /* ---------------- 修改密码 ---------------- */
  $("savePwd").addEventListener("click", async function () {
    var o = $("pwdOld").value, n = $("pwdNew").value, n2 = $("pwdNew2").value;
    if (!o || !n) { $("pwdHint").textContent = "请填写原密码和新密码"; return; }
    if (n !== n2) { $("pwdHint").textContent = "两次输入的新密码不一致"; return; }
    $("savePwd").disabled = true;
    $("pwdHint").textContent = "提交中…";
    try {
      await postJSON("api/password", { oldPassword: o, newPassword: n }, { allow401: true });
      $("pwdOld").value = $("pwdNew").value = $("pwdNew2").value = "";
      $("pwdHint").textContent = "密码已修改，请用新密码重新登录。";
      state.user = "";
      showGate("密码已修改，请用新密码重新登录");
    } catch (e) {
      $("pwdHint").textContent = e.message;
    } finally {
      $("savePwd").disabled = false;
    }
  });

  /* ---------------- 状态与启动 ---------------- */
  function updateStatus() {
    var ok = configed();
    $("statusDot").classList.toggle("ok", ok);
    $("statusText").textContent = ok ? state.config.model
      : openedByFile() ? "请用 http://127.0.0.1:8000"
      : !state.backend.online ? "后端未启动"
      : !state.backend.hasKey ? "Key 未配置" : "未登录";
  }

  async function checkBackend() {
    try {
      var h = await getJSON("api/health");
      state.backend = Object.assign(state.backend, {
        online: true, hasKey: !!h.hasKey, mcp: !!h.mcp, rag: h.rag || null,
        imageSizes: h.imageSizes || [], imageModels: h.imageModels || [],
        imageModel: h.imageModel || "", imageMaxCount: h.imageMaxCount || 0
      });
      if (h.model && !state.config.model) state.config.model = h.model;
    } catch (e) {
      state.backend = { online: false, hasKey: false, keyTail: "", mcp: false, rag: null,
                        model: "", imageSizes: [], imageModels: [], imageModel: "", imageMaxCount: 0 };
    }
    // 后端没装 mcp 包就别把开关摆出来，勾了只会收到一句报错；RAG 同理
    $("mcpWeather").parentNode.hidden = !state.backend.mcp;
    $("ragKb").parentNode.hidden = !state.backend.rag;
    if (state.user) await refreshMe();
    fillImagePickers();
    if (state.ui.view === "kb") loadKb();
    updateStatus();
    renderKeyMask();
  }

  async function refreshMe() {
    try {
      var me = await getJSON("api/me");
      state.backend.hasKey = !!me.hasKey;
      state.backend.keyTail = me.keyTail || "";
    } catch (e) { /* 401 已由 getJSON 退回登录页 */ }
  }

  async function boot() {
    renderMenu();
    applyCollapsed();
    fillForm();
    updateStatus();
    await checkBackend();
    if (!state.backend.online) { showGate(backendHint()); setInterval(checkBackend, 15000); return; }
    try {
      var me = await getJSON("api/me");
      state.user = me.username;
      state.backend.hasKey = !!me.hasKey;
      state.backend.keyTail = me.keyTail || "";
      enterApp(me.username);
    } catch (e) {
      state.user = "";
      showGate("");
    }
    setInterval(checkBackend, 15000);
  }
  boot();
})();
