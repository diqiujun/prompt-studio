/* 提示词工作台 前端逻辑 */
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const S = {
  catalog: [],
  providers: [],
  active: null,
  fast: true,
  tpl: null,
  trTpl: null,
  images: [],
  tab: "prompt",
  last: null,
  history: [],
  specs: [],
  presets: [],
  utpl: [],
  busy: false,
};

const ROLES = {
  h3_video: ["人物身份图", "服装图", "场景图(weak_reference)", "首帧", "尾帧", "道具/武器图", "视频参考", "音频参考", "风格参考", "姿势参考（人体动态与构图）"],
  qwen_i2i: ["画布图·被编辑的底图", "人物身份来源", "服装来源", "场景来源", "风格来源", "道具来源", "构图参考", "姿势参考（人体动态与构图）"],
  moss_t2i: ["主体参考", "服装参考", "场景参考", "风格参考", "姿势参考（人体动态与构图）"],
  zi_i2i: ["底图·要改造的图", "风格参考图", "人物身份参考", "服装参考", "构图参考", "姿势参考（人体动态与构图）"],
  zt_t2i: ["风格参考", "构图参考", "姿势参考（人体动态与构图）"],
  default: ["参考图", "姿势参考（人体动态与构图）"],
};

const EXAMPLES = {
  h3_video: "例：沈不违提刀走进雪夜山门，镜头从他靴子慢慢上摇到脸，呼出白气，刀刃上有雪粒反光，最后一句台词「都让开」。时长 6 秒。",
  qwen_i2i: "例：把图1里的钟改成完整无缺的旧铜钟，只留一道从钟口向上的竖直长裂缝，其余保持不变；输出竖版 9:16。",
  moss_t2i: "例：仙侠剧里的女修站在丹殿废墟中，身后断裂的铜钟，手里捧着发光的丹炉残件，3D 仙侠渲染风。",
  zt_t2i: "例：新中式时尚人像，墨绿缎面长旗袍，站在月下回廊，手里提一盏纸灯笼，皮肤通透，胶片质感。",
  zi_i2i: "例：把这张分镜洗成电影感关键帧，构图与人物位置完全不动，只提升光影质感与颗粒，加冷青色调。",
  tr_general: "粘贴任意中文文案 / 英文文案。",
  tr_prompt: "粘贴一份 H3 六段式提示词、Qwen 的 JSON 输出，或中文图生图提示词。",
};

/* ------------------------------------------------------------------ 通用 */
function toast(msg, kind) {
  const box = document.createElement("div");
  box.className = kind || "";
  box.textContent = msg;
  $("#toast").appendChild(box);
  setTimeout(() => box.remove(), kind === "e" ? 6500 : 3200);
}
function esc(t) {
  return String(t == null ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
/* ---- 桌面版桥（Qt 侧）：复制、主题都走它，绕开浏览器剪贴板权限 ------ */
let PSAPP = null;
function initBridge(after) {
  if (typeof window.qt === "undefined" || !window.qt.webChannelTransport) return;
  const s = document.createElement("script");
  s.src = "qrc:///qtwebchannel/qwebchannel.js";
  s.onload = function () {
    try {
      new QWebChannel(window.qt.webChannelTransport, function (ch) {
        PSAPP = ch.objects.psApp || null;
        if (after) after();
      });
    } catch (e) { /* 桥不可用时退回浏览器剪贴板 */ }
  };
  document.head.appendChild(s);
}
function copy(text) {
  if (PSAPP && PSAPP.copyText) {
    try { PSAPP.copyText(String(text == null ? "" : text)); toast("已复制"); return Promise.resolve(); } catch (e) {}
  }
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text).then(() => toast("已复制"), () => fallbackCopy(text));
  }
  fallbackCopy(text);
  return Promise.resolve();
}
function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed"; ta.style.top = "0"; ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.focus(); ta.select();
  try { ta.setSelectionRange(0, ta.value.length); } catch (e) {}
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  ta.remove();
  if (ok) toast("已复制");
  else toast("复制失败：请在结果区手动选中后 Ctrl+C", "e");
  return ok;
}
async function api(path, body, method) {
  const r = await fetch(path, {
    method: method || (body ? "POST" : "GET"),
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return await r.json();
}

/* ------------------------------------------------------------------ tab */
function showTab(name) {
  S.tab = name;
  $$("nav button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  ["prompt", "translate", "history", "settings"].forEach((t) => {
    $("#tab-" + t).style.display = t === name ? "" : "none";
  });
  if (name === "history") loadHistory();
  if (name === "settings") { renderProviders(); loadSpecMgr(); localRefresh(); loadPlugins(); loadRuntime(); }
}

/* ------------------------------------------------------------------ 模板选择 */
function renderTplPicker() {
  const prompt = S.catalog.filter((t) => t.group === "prompt");
  const tr = S.catalog.filter((t) => t.group === "translate");
  const html = prompt.map((t) =>
    `<div class="tpl${t.id === S.tpl ? " on" : ""}${t.plugin ? " plug" : ""}" data-id="${t.id}">
       <b>${esc(t.label)}${t.plugin ? ' <i class="pbadge">' + (t.custom ? "自定义" : "插件") + '</i>' : ""}</b>
       <span>${esc(t.tagline || "")}</span>
       ${t.custom ? `<span class="tplops"><i data-tpl-ed="${t.id}" title="编辑">编辑</i><i data-tpl-del="${t.id}" title="删除">删除</i></span>` : ""}
     </div>`).join("") +
    `<div class="tpl add" id="tplAdd"><b>＋ 添加模型</b><span>自己写规范：如 FLUX、SDXL、即梦……填好即可当作模板用</span></div>`;
  $("#tplPicker").innerHTML = html;
  $("#trPicker").innerHTML = tr.map((t) =>
    `<div class="tpl${t.id === S.trTpl ? " on" : ""}" data-id="${t.id}"><b>${esc(t.label)}</b><span>${esc(t.tagline)}</span></div>`).join("");
  $$("#tplPicker .tpl").forEach((el) => el.onclick = (ev) => {
    if (ev.target.closest("[data-tpl-ed]")) { openTplEditor(el.dataset.id); return; }
    if (ev.target.closest("[data-tpl-del]")) { delTpl(el.dataset.id); return; }
    if (el.id === "tplAdd") { openTplEditor(null); return; }
    pickTpl(el.dataset.id);
  });
  $$("#trPicker .tpl").forEach((el) => el.onclick = () => pickTrTpl(el.dataset.id));
}

/* ------------------------------------------------------------------ 自定义模型 */
/* 参数行格式：标签|类型|默认值|选项1,选项2 （只有标签时=普通文本输入） */
function parseTplParams(text) {
  const out = [];
  String(text || "").split("\n").forEach((line, i) => {
    const raw = line.trim();
    if (!raw) return;
    const parts = raw.split("|").map((s) => s.trim());
    const label = parts[0];
    if (!label) return;
    const p = { key: "p" + (i + 1), label, type: (parts[1] || "text").toLowerCase(), default: parts[2] || "" };
    if (p.type === "select") p.options = (parts[3] || "").split(",").map((s) => s.trim()).filter(Boolean);
    if (!["select", "number", "text", "textarea", "canvas"].includes(p.type)) p.type = "text";
    out.push(p);
  });
  return out;
}
function fmtTplParams(params) {
  return (params || []).map((p) => [p.label, p.type, p.default === undefined ? "" : p.default,
    (p.options || []).join(",")].join("|").replace(/\|+$/, "")).join("\n");
}
function openTplEditor(id) {
  const t = id ? (S.utpl || []).find((x) => x.id === id) : null;
  const box = $("#tplEd");
  box.classList.add("on");
  box.dataset.id = t ? t.id : "";
  box.querySelector("h3").textContent = t ? "编辑自定义模型" : "添加自定义模型";
  $("#teName").value = t ? t.name : "";
  $("#teTag").value = t ? t.tagline : "";
  $("#teIntro").value = t ? t.intro : "";
  $("#teSpec").value = t ? t.spec : "";
  $("#teParams").value = t ? fmtTplParams(t.params) : "";
  $("#teExamples").value = t ? (t.examples || []).join("\n") : "";
  $("#teJson").checked = t ? !!t.expect_json : false;
  $("#teMinImg").value = t ? t.min_images : 0;
  $("#teMaxImg").value = t ? t.max_images : 4;
  $("#teMsg").textContent = "";
  setTimeout(() => $("#teName").focus(), 50);
}
function closeTplEditor() { $("#tplEd").classList.remove("on"); }
async function loadUserTpl() {
  try {
    const j = await api("/api/templates");
    S.utpl = j.templates || [];
  } catch (e) { S.utpl = []; }
}
async function saveTplEditor() {
  const body = {
    template: {
      id: $("#tplEd").dataset.id || "",
      name: $("#teName").value.trim(),
      tagline: $("#teTag").value.trim(),
      intro: $("#teIntro").value.trim(),
      spec: $("#teSpec").value.trim(),
      params: parseTplParams($("#teParams").value),
      examples: $("#teExamples").value.split("\n").map((s) => s.trim()).filter(Boolean),
      expect_json: $("#teJson").checked,
      min_images: Number($("#teMinImg").value || 0),
      max_images: Number($("#teMaxImg").value || 4),
      enabled: true,
    },
  };
  if (!body.template.name) { $("#teMsg").textContent = "先填模型名称"; return; }
  if (!body.template.spec) { $("#teMsg").textContent = "规范正文不能为空——这里写清楚要模型怎么产出提示词"; return; }
  try {
    const j = await api("/api/templates/save", body);
    if (!j.ok) { $("#teMsg").textContent = j.error || "保存失败"; return; }
    S.utpl = j.templates || [];
    closeTplEditor();
    await loadState();
    renderTplPicker();
    toast("已保存自定义模型：" + body.template.name);
  } catch (e) { $("#teMsg").textContent = "保存失败：" + e.message; }
}
async function delTpl(id) {
  const t = (S.utpl || []).find((x) => x.id === id);
  if (!confirm("删除自定义模型「" + (t ? t.name : id) + "」？")) return;
  try {
    const j = await api("/api/templates/delete", { id });
    S.utpl = j.templates || [];
    await loadState();
    renderTplPicker();
    toast("已删除");
  } catch (e) { toast("删除失败：" + e.message, "e"); }
}
function tplDef(id) { return S.catalog.find((t) => t.id === id); }
function pickTpl(id) {
  S.tpl = id;
  $$("#tplPicker .tpl").forEach((el) => el.classList.toggle("on", el.dataset.id === id));
  const def = tplDef(id);
  $("#content").placeholder = EXAMPLES[id] || "";
  renderParams($("#paramRow"), def);
  renderImages();
  api("/api/provider/activate", { id: S.active, template: id, fast: S.fast });
}
function pickTrTpl(id) {
  S.trTpl = id;
  $$("#trPicker .tpl").forEach((el) => el.classList.toggle("on", el.dataset.id === id));
  $("#trText").placeholder = EXAMPLES[id] || "";
  renderParams($("#trParamRow"), tplDef(id), true);
}

/* 参数控件渲染 */
function renderParams(host, def, isTranslate) {
  if (!def) { host.innerHTML = ""; return; }
  host.innerHTML = "";
  (def.params || []).forEach((p) => {
    const col = document.createElement("div");
    col.className = p.type === "textarea" ? "col" : "col";
    if (p.type === "textarea") col.style.flex = "1 1 100%";
    const label = `<label>${esc(p.label)}</label>`;
    let ctl = "";
    if (p.type === "select") {
      const opts = (p.options || []).map((o) => `<option value="${esc(o)}"${o === p.default ? " selected" : ""}>${esc((p.labels && p.labels[o]) || o)}</option>`).join("");
      ctl = `<select data-k="${p.key}">${opts}</select>`;
    } else if (p.type === "number") {
      ctl = `<input type="number" data-k="${p.key}" value="${p.default}" min="${p.min ?? 1}" max="${p.max ?? 100}">`;
    } else if (p.type === "textarea") {
      ctl = `<textarea data-k="${p.key}" rows="3" placeholder="${esc(p.placeholder || "")}">${esc(p.default || "")}</textarea>`;
    } else if (p.type === "canvas") {
      const dl = `dl-${def.id}-${p.key}`;
      const items = (p.suggestions || []).map((s) => `<option value="${esc(s)}"></option>`).join("");
      ctl = `<input data-k="${p.key}" list="${dl}" value="${esc(p.default || "")}" placeholder="${esc(p.placeholder || "任意 WxH")}" style="text-transform:lowercase"><datalist id="${dl}">${items}</datalist>`;
    } else {
      ctl = `<input data-k="${p.key}" value="${esc(p.default || "")}" placeholder="${esc(p.placeholder || "")}">`;
    }
    col.innerHTML = label + ctl;
    host.appendChild(col);
  });
  if (!isTranslate && def.min_images > 0) {
    const c = document.createElement("div");
    c.className = "col"; c.style.flex = "1 1 100%";
    c.innerHTML = `<span class="hint">该模板要求至少 1 张参考图（${def.min_images}–${def.max_images} 张）。</span>`;
    host.appendChild(c);
  }
}
function collectParams(def) {
  const out = {};
  $$("#paramRow [data-k]").forEach((el) => {
    const v = el.type === "number" ? Number(el.value) : el.value;
    out[el.dataset.k] = v;
  });
  $$("#trParamRow [data-k]").forEach((el) => { out[el.dataset.k] = el.value; });
  if (!def) return out;
  (def.params || []).forEach((p) => { if (out[p.key] === undefined) out[p.key] = p.default; });
  return out;
}

/* ------------------------------------------------------------------ provider */
function renderProviderSelect() {
  $("#provider").innerHTML = S.providers.map((p) =>
    `<option value="${p.id}"${p.id === S.active ? " selected" : ""}>${esc(p.name)} · ${esc(p.model)}${p.vision ? " 👁" : ""}</option>`).join("");
}
async function loadState() {
  const st = await api("/api/state");
  S.catalog = st.templates; S.providers = st.providers; S.active = st.active_provider;
  S.fast = !!st.fast; S.tpl = st.template; S.specs = st.specs; S.presets = st.presets;
  if (st.version) { var _v = document.getElementById("appVer"); if (_v) _v.textContent = st.version; }
  $("#cfgPath").textContent = st.config_path;
  S.trTpl = (S.catalog.find((t) => t.group === "translate") || {}).id;
  renderProviderSelect();
  renderTplPicker();
  pickTpl(S.tpl && tplDef(S.tpl) ? S.tpl : S.catalog[0].id);
  const firstTr = S.catalog.find((t) => t.group === "translate");
  if (firstTr) pickTrTpl(S.catalog.some((t) => t.id === S.trTpl) ? S.trTpl : firstTr.id);
  $("#fastToggle").classList.toggle("on", S.fast);
  $("#presetBtns").innerHTML = S.presets.map((p, i) => `<button class="btn sm ghost" data-p="${i}">${esc(p.name)}</button>`).join(" ");
  $$("#presetBtns button").forEach((b) => b.onclick = () => addPreset(Number(b.dataset.p)));
  const def = tplDef(S.tpl);
  $("#content").placeholder = EXAMPLES[S.tpl] || "";
  $("#trText").placeholder = EXAMPLES[S.trTpl] || "";
}

/* ------------------------------------------------------------------ 图片 */
function renderImages() {
  const def = tplDef(S.tpl);
  const roles = ROLES[S.tpl] || ROLES.default;
  const max = def ? def.max_images : 4;
  $("#imgs").innerHTML = S.images.map((im, i) => `
    <div class="img">
      <button class="x" data-x="${i}" title="移除">✕</button>
      <img src="${im.data_url}" alt="">
      <select data-r="${i}">${roles.map((r) => `<option${r === im.role ? " selected" : ""}>${esc(r)}</option>`).join("")}</select>
    </div>`).join("");
  $$("#imgs .x").forEach((b) => b.onclick = () => { S.images.splice(Number(b.dataset.x), 1); renderImages(); renderImgChips(); });
  $$("#imgs select").forEach((s) => s.onchange = () => { S.images[Number(s.dataset.r)].role = s.value; renderImgChips(); });
  $("#drop").style.display = S.images.length >= max ? "none" : "";
  $("#drop").textContent = `点击选择图片，或把图片拖进来 · Ctrl+V 粘贴（最多 ${max} 张）`;
  renderImgChips();
}
function addFiles(files) {
  const def = tplDef(S.tpl);
  const max = def ? def.max_images : 4;
  Array.from(files).forEach(async (f) => {
    if (!f.type || !f.type.startsWith("image/")) return;
    if (S.images.length >= max) { toast(`该模板最多 ${max} 张参考图`, "e"); return; }
    try {
      const url = await shrink(f, 1568);
      const roles = ROLES[S.tpl] || ROLES.default;
      S.images.push({ data_url: url, role: roles[0], name: f.name });
      renderImages();
    } catch (e) { toast("图片读取失败：" + e.message, "e"); }
  });
}
function shrink(file, maxSide) {
  return new Promise((res, rej) => {
    const rd = new FileReader();
    rd.onload = () => {
      const raw = rd.result;
      if (file.size < 380 * 1024) return res(raw); // 小图原样传
      const img = new Image();
      img.onload = () => {
        const sc = Math.min(1, maxSide / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * sc));
        const h = Math.max(1, Math.round(img.height * sc));
        const c = document.createElement("canvas"); c.width = w; c.height = h;
        const ctx = c.getContext("2d");
        ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);
        res(c.toDataURL("image/jpeg", 0.86));
      };
      img.onerror = () => res(raw);
      img.src = raw;
    };
    rd.onerror = () => rej(new Error("FileReader"));
    rd.readAsDataURL(file);
  });
}

/* ------------------------------------------------------------------ 主题（深色 / 浅色） */
const THEME_KEY = "ps-theme";
function applyTheme(name, silent) {
  const t = name === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(THEME_KEY, t); } catch (e) {}
  $$("#themeSeg button").forEach((b) => b.classList.toggle("on", b.dataset.theme === t));
  if (PSAPP && PSAPP.setTheme) { try { PSAPP.setTheme(t); } catch (e) {} }   /* 桌面版：立即换菜单栏/状态栏 */
  if (!silent) { try { api("/api/ui/theme", { theme: t }); } catch (e) {} }  /* 落盘，供下次启动与其它窗口 */
}
function initTheme() {
  let t = "dark";
  try { t = localStorage.getItem(THEME_KEY) || "dark"; } catch (e) {}
  applyTheme(t);
  $$("#themeSeg button").forEach((b) => (b.onclick = () => applyTheme(b.dataset.theme)));
}

/* ------------------------------------------------------------------ @ 引用图片 */
const MENTION = { open: false, idx: 0, start: -1, items: [] };
function imageToken(i) { return "@图" + (i + 1); }

function renderImgChips() {
  const host = $("#imgChips");
  if (!host) return;
  if (!S.images.length) { host.innerHTML = ""; return; }
  host.innerHTML = `<span class="lbl">可 @ 引用：</span>` +
    S.images.map((im, i) => `<span class="chip" data-ins="${i}">${imageToken(i)} · ${esc(im.role || "参考图")}</span>`).join("") +
    `<span class="lbl">生成时自动写成 &lt;imageN&gt; 引用</span>`;
  $$("#imgChips .chip").forEach((c) => (c.onclick = () => insertText($("#content"), imageToken(Number(c.dataset.ins)) + " ")));
}
/* ------------------------------------------------------- 插件界面宿主（PSPlugin）
   代码插件可以在 plugin.json 的 web 里声明 js/css，宿主会把它们加载进来，
   并给插件一个 addPanel({id,title,mount,render(el, api)}) 的挂载点。
   插件进度：
     api.insertImage(src, role)  取图（URL 或 dataURL）→ 加入参考图
     api.insertText(text)        往输入框追加文本
     api.toast(msg,tone)         提示
     api.setting(key, def)       读插件设置项当前值
     api.value(key)              同 setting
     api.template()              当前模板 id
     api.images()                当前参考图数组（只读）
*/
const PSPlugin = {
  _panels: [],
  _loaded: {},
  _settings: {},
  _order: 0,
  _sbarCur: "",
  addPanel: function (opt) {
    if (!opt || !opt.id || typeof opt.render !== "function") { console.warn("[PSPlugin] addPanel 参数不完整", opt); return; }
    PSPlugin._panels.push(opt);
    PSPlugin.mountAll();
  },
  setting: function (key, def) {
    const v = PSPlugin._settings[key];
    return v === undefined || v === null || v === "" ? def : v;
  },
  toast: function (msg, tone) { toast(msg, tone); },
  insertText: function (text) { insertText($("#content"), text); },
  images: function () { return S.images.slice(); },
  template: function () { return S.tpl; },
  insertImage: async function (src, role) {
    const def = (S.catalog || []).find((t) => t.id === S.tpl) || {};
    const max = def.max_images || 8;
    if (S.images.length >= max) { throw new Error("该模板最多 " + max + " 张参考图"); }
    let dataUrl = src;
    if (!/^data:/i.test(src)) {
      const resp = await fetch(src, { cache: "force-cache" });
      if (!resp.ok) { throw new Error("取图失败 HTTP " + resp.status); }
      const blob = await resp.blob();
      dataUrl = await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result);
        fr.onerror = () => rej(new Error("读取图片失败"));
        fr.readAsDataURL(blob);
      });
    }
    S.images.push({ data_url: dataUrl, role: role || "参考图" });
    renderImages();
    return dataUrl;
  },
  mountAll: function () {
    const hosts = { prompt: $("#pluginPanels"), settings: $("#pluginPanelsCfg") };
    PSPlugin._panels.forEach(function (p) {
      const mount = p.mount || "prompt";
      if (mount === "sidebar") { PSPlugin.mountSbar(p); return; }
      const host = hosts[mount] || hosts.prompt;
      if (!host) { return; }
      let el = host.querySelector('[data-ppanel="' + p.id + '"]');
      if (el && el.dataset.mounted === "1") { return; }
      if (!el) {
        el = document.createElement("div");
        el.className = "pp-panel";
        el.dataset.ppanel = p.id;
        if (p.title) {
          const h = document.createElement("div");
          h.className = "pp-title";
          h.textContent = p.title;
          el.appendChild(h);
        }
        const body = document.createElement("div");
        el.appendChild(body);
        host.appendChild(el);
        try {
          p.render(body, PSPlugin);
          el.dataset.mounted = "1";
        } catch (e) {
          body.innerHTML = '<p class="mini err">插件面板出错：' + esc(e.message) + "</p>";
        }
      }
    });
    PSPlugin.sbarRefresh();
  },
  /* ---- 右侧工具栏：mount="sidebar" 的插件挂在这里，页签切换 ---- */
  mountSbar: function (p) {
    const host = $("#sbarBody");
    if (!host) { return; }
    let el = host.querySelector('[data-ppanel="' + p.id + '"]');
    if (el && el.dataset.mounted === "1") { return; }
    if (!el) {
      el = document.createElement("div");
      el.className = "pp-panel";
      el.dataset.ppanel = p.id;
      el.dataset.ptitle = p.title || p.id;
      el.hidden = true;
      host.appendChild(el);
      try {
        p.render(el, PSPlugin);
        el.dataset.mounted = "1";
      } catch (e) {
        el.innerHTML = '<p class="mini err">插件面板出错：' + esc(e.message) + "</p>";
      }
    }
  },
  sbarPick: function (id) {
    PSPlugin._sbarCur = id;
    try { localStorage.setItem("ps-sbar-cur", id); } catch (e) {}
    PSPlugin.sbarRefresh();
  },
  sbarRefresh: function () {
    const tabs = $("#sbarTabs"), host = $("#sbarBody");
    if (!tabs || !host) { return; }
    const els = Array.prototype.slice.call(host.querySelectorAll("[data-ppanel]"));
    if (!els.length) {
      document.body.classList.add("sbar-nopanel");
      tabs.innerHTML = "";
      tabs.dataset.sig = "";
      return;
    }
    document.body.classList.remove("sbar-nopanel");
    const ids = els.map((el) => el.dataset.ppanel);
    if (ids.indexOf(PSPlugin._sbarCur) < 0) {
      let saved = "";
      try { saved = localStorage.getItem("ps-sbar-cur") || ""; } catch (e) {}
      PSPlugin._sbarCur = (saved && ids.indexOf(saved) >= 0) ? saved : ids[0];
    }
    const sig = ids.join(",") + "|" + ids.map((id) => {
      const p = PSPlugin._panels.filter((x) => x.id === id)[0];
      return (p && p.title) || id;
    }).join(",");
    if (tabs.dataset.sig !== sig) {
      tabs.dataset.sig = sig;
      tabs.innerHTML = "";
      ids.forEach(function (id) {
        const p = PSPlugin._panels.filter((x) => x.id === id)[0] || {};
        const b = document.createElement("button");
        b.className = "sbarTab";
        b.dataset.sbtab = id;
        b.type = "button";
        b.textContent = p.title || id;
        b.onclick = function () { PSPlugin.sbarPick(id); };
        tabs.appendChild(b);
      });
    }
    Array.prototype.forEach.call(tabs.children, function (b) {
      b.classList.toggle("on", b.dataset.sbtab === PSPlugin._sbarCur);
    });
    els.forEach(function (el) { el.hidden = el.dataset.ppanel !== PSPlugin._sbarCur; });
  },
  sbarOn: function (on) {
    document.body.classList.toggle("sbar-on", !!on);
    try { localStorage.setItem("ps-sbar", on ? "1" : "0"); } catch (e) {}
    PSPlugin.sbarRefresh();
  },
  load: async function (list) {
    const items = (list || []).filter((p) => p.web && (p.web.js || p.web.css));
    const settings = {};
    items.forEach((p) => { settings[p.id] = p.values || {}; });
    PSPlugin._settings = Object.assign(PSPlugin._settings, Object.assign({}, ...Object.values(settings)));
    for (const p of items) {
      const web = p.web;
      if (web.css && !PSPlugin._loaded["css:" + p.id]) {
        const l = document.createElement("link");
        l.rel = "stylesheet";
        l.href = web.css;
        document.head.appendChild(l);
        PSPlugin._loaded["css:" + p.id] = 1;
      }
      if (web.js && !PSPlugin._loaded["js:" + p.id]) {
        PSPlugin._loaded["js:" + p.id] = 1;
        await new Promise(function (res) {
          const s = document.createElement("script");
          s.src = web.js;
          s.onload = res;
          s.onerror = function () { console.warn("[PSPlugin] 脚本加载失败", web.js); res(); };
          document.body.appendChild(s);
        });
      }
    }
    PSPlugin.mountAll();
  },
};
window.PSPlugin = PSPlugin;

function insertText(ta, text) {
  const caret = ta.selectionStart || ta.value.length;
  ta.value = ta.value.slice(0, caret) + text + ta.value.slice(caret);
  const pos = caret + text.length;
  ta.focus(); ta.setSelectionRange(pos, pos);
  ta.dispatchEvent(new Event("input"));
}
function mentionCandidates() {
  return S.images.map((im, i) => ({ token: imageToken(i), label: "第 " + (i + 1) + " 张",
    role: im.role || "参考图", thumb: im.data_url || "" }));
}
function openMention(prefix) {
  const q = String(prefix || "").trim();
  MENTION.items = mentionCandidates().filter((c) => !q || c.token.slice(1).indexOf(q) >= 0 || c.role.indexOf(q) >= 0);
  if (!MENTION.items.length) return closeMention();
  MENTION.open = true; MENTION.idx = 0;
  const box = $("#mention");
  box.innerHTML = MENTION.items.map((c, i) =>
    `<div data-i="${i}" class="${i === 0 ? "on" : ""}">` +
    (c.thumb ? `<img class="mthumb" src="${c.thumb}" alt="">` : `<img class="mthumb" alt="">`) +
    `<i>${esc(c.token)}</i><span>${esc(c.label)} · ${esc(c.role)}</span></div>`).join("") +
    `<div class="tip">↑↓ 选择 · Enter 插入 · Esc 关闭</div>`;
  box.classList.add("on");
  $$("#mention div[data-i]").forEach((d) => (d.onclick = () => chooseMention(Number(d.dataset.i))));
}
function closeMention() { MENTION.open = false; const b = $("#mention"); if (b) b.classList.remove("on"); }
function chooseMention(i) {
  const c = MENTION.items[i]; if (!c) return;
  const ta = $("#content");
  const caret = ta.selectionStart || 0;
  const before = ta.value.slice(0, MENTION.start);
  const after = ta.value.slice(caret);
  ta.value = before + c.token + " " + after;
  const pos = (before + c.token + " ").length;
  ta.focus(); ta.setSelectionRange(pos, pos);
  closeMention();
  renderImgChips();
}
function wireMention() {
  const ta = $("#content");
  if (!ta) return;
  ta.addEventListener("input", () => {
    if (!S.images.length) return closeMention();
    const caret = ta.selectionStart || 0;
    const m = /@([^\s@]{0,10})$/.exec(ta.value.slice(0, caret));
    if (!m) return closeMention();
    MENTION.start = caret - m[0].length;
    openMention(m[1]);
  });
  ta.addEventListener("keydown", (e) => {
    if (!MENTION.open) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const n = MENTION.items.length;
      MENTION.idx = (MENTION.idx + (e.key === "ArrowDown" ? 1 : -1) + n) % n;
      $$("#mention div[data-i]").forEach((d) => d.classList.toggle("on", Number(d.dataset.i) === MENTION.idx));
    } else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); chooseMention(MENTION.idx); }
    else if (e.key === "Escape") closeMention();
  });
  ta.addEventListener("blur", () => setTimeout(closeMention, 140));
}
/* 把「@图1 / @图片2 / @第3张」解析成模型看的 <imageN>（越界原样保留） */
function resolveMentions(text) {
  const n = S.images.length;
  return String(text).replace(/@(?:图片|图|第)(\d{1,2})(?:张)?/g, (all, d) => {
    const i = Number(d) - 1;
    return i >= 0 && i < n ? "<image" + (i + 1) + ">" : all;
  });
}

/* ------------------------------------------------------------------ 生成 */
async function generate(feedback) {
  if (S.busy) return;
  const raw = $("#content").value.trim();
  const def = tplDef(S.tpl);
  if (!raw) { toast("先写内容描述", "e"); return; }
  const content = resolveMentions(raw);
  const params = collectParams(def);
  if (feedback) params.feedback = feedback;
  S.busy = true; $("#go").disabled = true; $("#bar").classList.add("on");
  $("#meta").innerHTML = "<span>生成中…</span><span>" + esc(def.label) + "</span>";
  try {
    const r = await api("/api/generate", {
      template: S.tpl, content, params, images: S.images,
      provider: S.active, fast: S.fast,
    });
    if (!r.ok) {
      $("#bar").classList.remove("on");
      $("#meta").innerHTML = "<span style='color:var(--err)'>失败</span>";
      $("#result").innerHTML = `<pre class="body">${esc(r.error || "未知错误")}</pre>`;
      toast("生成失败", "e");
      return;
    }
    S.last = r;
    $("#meta").innerHTML = [
      `<span>${esc(r.label)}</span>`,
      `<span>${esc(r.provider_name)} · ${esc(r.model)}</span>`,
      `<span>${r.elapsed}s</span>`,
      r.usage && r.usage.total_tokens ? `<span>tokens ${r.usage.prompt_tokens}+${r.usage.completion_tokens}</span>` : "",
      `<span>注入 ${r.system_chars} 字符</span>`,
      `<span style="flex:1"></span>`,
      `<span><button class="btn sm" id="cpAll">复制全部</button></span>`,
      `<span><button class="btn sm" id="expMd">导出 .md</button></span>`,
    ].filter(Boolean).join("");
    renderResult(r);
    $("#cpAll").onclick = () => copy(r.content);
    $("#expMd").onclick = () => exportMd(r);
    toast("已生成");
  } catch (e) {
    $("#meta").innerHTML = "<span style='color:var(--err)'>请求失败</span>";
    $("#result").innerHTML = `<pre class="body">${esc(e.message)}</pre>`;
    toast("请求失败：" + e.message, "e");
  } finally {
    S.busy = false; $("#go").disabled = false; $("#bar").classList.remove("on");
  }
}

/* 富文本渲染：【区块】高亮 + 代码块带复制 */
function renderRich(text) {
  const parts = String(text).split(/```/);
  let out = "";
  parts.forEach((seg, i) => {
    if (i % 2 === 1) {
      const body = seg.replace(/^\s*(text|json|markdown|)\n/, "").replace(/\s$/, "");
      out += `<pre class="code"><button class="btn sm cp" data-code="${encodeURIComponent(body)}">复制</button>${esc(body)}</pre>`;
    } else {
      out += `<pre class="body">` + esc(seg).replace(/(【[^】]{2,14}】)/g, `<span class="sec">$1</span>`) + `</pre>`;
    }
  });
  return out;
}
function wireCopy(root) {
  $$("[data-code]", root).forEach((b) => b.onclick = () => copy(decodeURIComponent(b.dataset.code)));
  root.querySelectorAll("[data-code]").forEach((b) => b.onclick = () => copy(decodeURIComponent(b.dataset.code)));
}

function renderResult(r) {
  const host = $("#result");
  if (r.json && Object.keys(r.json).length) {
    host.innerHTML = renderJson(r.json) + renderRich(r.content.replace(/```json[\s\S]*?```/, ""));
  } else {
    host.innerHTML = renderRich(r.content);
  }
  host.querySelectorAll("[data-code]").forEach((b) => b.onclick = () => copy(decodeURIComponent(b.dataset.code)));
}
function renderJson(j) {
  const tags = (arr, cls) => (arr && arr.length) ? arr.map((x) => `<span class="tag${cls ? " " + cls : ""}">${esc(x)}</span>`).join("") : "";
  let h = "";
  const pick = (k) => j[k];
  if (pick("positive_prompt")) h += `<pre class="code"><button class="btn sm cp" data-code="${encodeURIComponent(pick("positive_prompt"))}">复制正向</button>${esc(pick("positive_prompt"))}</pre>`;
  if (pick("rewritten_prompt")) h += `<pre class="code"><button class="btn sm cp" data-code="${encodeURIComponent(pick("rewritten_prompt"))}">复制改写指令</button>${esc(pick("rewritten_prompt"))}</pre>`;
  if (pick("negative_prompt")) h += `<pre class="code"><button class="btn sm cp" data-code="${encodeURIComponent(pick("negative_prompt"))}">复制负向</button>${esc(pick("negative_prompt"))}</pre>`;
  const ratio = [];
  if (j.wh_ratio) ratio.push("wh_ratio=" + j.wh_ratio);
  if (j.ratio_follow) ratio.push("ratio_follow=" + j.ratio_follow);
  if (ratio.length) h += `<div>${tags(ratio, "ok")}</div>`;
  if (j.slots) {
    h += `<table class="kv">` + Object.entries(j.slots).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("") + `</table>`;
  }
  if (j.scene_specific_negatives) h += `<div>${tags(j.scene_specific_negatives.map((x) => "场景负向 " + x))}</div>`;
  if (j.canvas_size) h += `<div>${tags(["canvas " + (j.canvas_size.width || "?") + "x" + (j.canvas_size.height || "?")])}</div>`;
  if (j.sampling_profile) h += `<div>${tags(Object.entries(j.sampling_profile).map(([k, v]) => k + "=" + v))}</div>`;
  if (j.warnings && j.warnings.length) h += `<div>${tags(j.warnings.map((x) => "⚠ " + x), "warn")}</div>`;
  return h ? `<div class="card" style="margin-bottom:12px"><h3>结构化输出</h3>${h}</div>` : "";
}
function exportMd(r) {
  const head = `# ${r.label} · ${new Date().toLocaleString("zh-CN")}\n\n> 服务：${r.provider_name} · ${r.model} ｜ 注入规范 ${r.system_chars} 字符 ｜ ${r.elapsed}s\n\n`;
  const body = r.json ? "```json\n" + JSON.stringify(r.json, null, 2) + "\n```\n" : r.content;
  const blob = new Blob([head + body], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${r.label}-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
  toast("已导出 .md");
}

/* ------------------------------------------------------------------ 翻译 */
async function translate() {
  if (S.busy) return;
  const text = $("#trText").value.trim();
  if (!text) { toast("先粘贴原文", "e"); return; }
  const def = tplDef(S.trTpl);
  const params = collectParams(def);
  const gl = $("#trGlossary").value.trim();
  if (gl) params.glossary = gl;
  S.busy = true; $("#trGo").disabled = true; $("#trBar").classList.add("on");
  $("#trMeta").innerHTML = "<span>翻译中…</span>";
  try {
    const r = await api("/api/generate", {
      template: S.trTpl, content: text, params, images: [],
      provider: S.active, fast: S.fast,
    });
    if (!r.ok) { $("#trResult").innerHTML = `<pre class="body">${esc(r.error)}</pre>`; toast("翻译失败", "e"); }
    else {
      const clean = String(r.content).replace(/^```[a-z]*\n?/i, "").replace(/\n?```$/, "");
      $("#trResult").innerHTML = `<pre class="code"><button class="btn sm cp" data-code="${encodeURIComponent(clean)}">复制译文</button>${esc(clean)}</pre>`;
      $("#trMeta").innerHTML = `<span>${esc(r.label)}</span><span>${esc(r.model)}</span><span>${r.elapsed}s</span>` +
        (r.usage && r.usage.total_tokens ? `<span>tokens ${r.usage.total_tokens}</span>` : "");
      $("#trResult").querySelectorAll("[data-code]").forEach((b) => b.onclick = () => copy(decodeURIComponent(b.dataset.code)));
    }
  } catch (e) { $("#trResult").innerHTML = `<pre class="body">${esc(e.message)}</pre>`; }
  finally { S.busy = false; $("#trGo").disabled = false; $("#trBar").classList.remove("on"); }
}

/* ------------------------------------------------------------------ 历史 */
async function loadHistory() {
  const r = await api("/api/history");
  S.history = r.history || [];
  $("#histList").innerHTML = S.history.length ? S.history.map((it, i) => `
    <div class="hitem">
      <div class="hd">
        <b>${esc(it.label)}</b>
        <span class="t">${esc(it.ts || "")}</span>
        <span class="tag">${esc(it.model || "")}</span>
        ${it.images ? `<span class="tag">图 ${it.images}</span>` : ""}
        <span style="flex:1"></span>
        <button class="btn sm" data-load="${i}">载入</button>
      </div>
      <div class="prev">${esc(String(it.input || "").slice(0, 120))}</div>
      <details style="margin-top:6px"><summary class="mini">查看输出</summary>
        <pre class="body">${esc(it.output || "")}</pre>
        <button class="btn sm" data-cph="${i}" style="margin-top:6px">复制这份输出</button>
      </details>
    </div>`).join("") : `<p class="hint">暂无记录。</p>`;
  $$("#histList [data-load]").forEach((b) => b.onclick = () => {
    const it = S.history[Number(b.dataset.load)];
    showTab("prompt");
    pickTpl(it.template);
    $("#content").value = it.input || "";
    toast("已载入描述与模板");
  });
  $$("#histList [data-cph]").forEach((b) => b.onclick = () => copy(S.history[Number(b.dataset.cph)].output || ""));
}

/* ------------------------------------------------------------------ 设置 */
/* ---------------------------------------------------------------- 本地模型 */
var LOC = null;
var LOC_PAINTED = false;

function locVal(id) { const el = $("#" + id); return el ? (el.value || "") : ""; }

function fillLocalForm(c) {
  if (LOC_PAINTED) return;
  $("#locDir").value = c.llama_dir || "";
  $("#locPort").value = c.port || 8910;
  $("#locCtx").value = c.ctx || 32768;
  $("#locNgl").value = c.ngl || 99;
  $("#locModel").value = c.model || "";
  $("#locMmproj").value = c.mmproj || "";
  $("#locMtp").value = c.mtp || "";
  $("#locAuto").checked = !!c.auto;
  $("#locAutoUnload").checked = c.auto_unload !== false;
  $("#locMtpOn").checked = !!c.use_mtp;
  $("#locEnabled").checked = c.enabled !== false;
  LOC_PAINTED = true;
}

/* 选路径：桌面版走 Qt 对话框（桥），网页版走后端弹框（有些环境弹不出来就手填） */
  function pickPath(mode, title, filt, cb) {
    var b = (typeof PSAPP !== "undefined" && PSAPP) ? PSAPP : null;
    if (b && typeof b.pickPath === "function") {
      try {
        b.pickPath(mode || "file", title || "选择", filt || "", function (p) { if (p) cb(p); });
        return;
      } catch (e) { /* 掉到后端 */ }
    }
    api("/api/local/browse", { mode: mode || "file", title: title || "选择", filter: filt || "" })
      .then(function (j) {
        if (j && j.path) cb(j.path);
        else if (j && j.error) toast(j.error, "e");
      })
      .catch(function (e) { toast("打不开选择框：" + e.message + "（可以直接把路径粘进来）", "e"); });
  }

  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest(".locpick");
    if (!el) return;
    e.preventDefault();
    var inp = document.getElementById(el.dataset.for);
    if (!inp) return;
    pickPath(el.dataset.mode, el.title, el.dataset.filter, function (p) {
      inp.value = p;
      inp.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });

function localBody() {
  return {
    llama_dir: locVal("locDir"),
    port: +locVal("locPort") || 8910,
    ctx: +locVal("locCtx") || 32768,
    ngl: +locVal("locNgl") || 99,
    model: locVal("locModel"),
    mmproj: locVal("locMmproj"),
    mtp: locVal("locMtp"),
    auto: $("#locAuto").checked,
    auto_unload: $("#locAutoUnload").checked,
    use_mtp: $("#locMtpOn").checked,
    enabled: $("#locEnabled").checked,
  };
}

function renderLocal(j) {
  fillLocalForm(j.config || {});
  const files = j.files || {};
  $("#locState").textContent = (j.running ? "● 运行中" : (j.enabled === false ? "× 已关闭" : "○ 未启动"))
    + "｜端口 " + j.port + (j.running && j.pid ? "｜pid " + j.pid : "")
    + ((j.config || {}).auto_unload !== false ? "｜按需加载" : "");
  const miss = [];
  if (!files.model) miss.push("主模型");
  if (!files.mmproj) miss.push("视觉投影");
  if (!files.mtp) miss.push("MTP 草稿");
  const mid = (j.models && j.models[0] && (j.models[0].id || j.models[0].name)) || "";
  $("#locHint").innerHTML = (miss.length ? "⚠ 找不到文件：" + esc(miss.join("、")) + "。" : "文件齐全。")
    + (j.running ? " 当前对外模型名：<code>" + esc(mid) + "</code>；在「模型服务」里选「本机模型 · gemma-4-e2b（内置）」即可调用。" : "");
}

async function localRefresh() {
  if (!$("#locState")) return;
  try {
    const j = await api("/api/local/status");
    LOC = j;
    renderLocal(j);
  } catch (e) {
    $("#locState").textContent = "状态读取失败：" + e.message;
  }
}

/* ---- 运行环境（llama.cpp 预编译包，按硬件自动适配） */
let RT = null;

function rtSay(msg) { const el = $("#rtState"); if (el) el.textContent = msg; }

async function loadRuntime() {
  rtSay("读取中…");
  try {
    const j = await api("/api/runtime/status");
    RT = j;
    renderRuntime(j);
  } catch (e) { rtSay("读取失败：" + e.message); }
}

function renderRuntime(j) {
  const det = j.detect || {};
  const nv = det.nvidia || {};
  const amd = det.amd || {};
  const gpu = nv.present
    ? ("NVIDIA " + (nv.name || "") + " · " + Math.round((nv.vram_mb || 0) / 1024) + " GB 显存 · CUDA " + (nv.cuda || "?"))
    : (amd.present ? ("AMD " + (amd.name || "") + (amd.rocm ? " · ROCm 已装" : " · 未见 ROCm")) : "未检测到独立显卡");
  const st = $("#rtState");
  if (st) {
    st.textContent = j.supported
      ? ("系统 " + (det.os || "?") + " · 架构 " + (det.arch || "?") + " · 已装 " + (j.installed || []).length + " 套")
      : ("不支持：" + (j.message || "该平台没有运行环境"));
  }
  const dEl = $("#rtDetect");
  if (dEl) {
    dEl.innerHTML = "检测：" + esc(gpu) + " · " + (det.cpus || 0) + " 线程"
      + (j.preferred ? ("　推荐：<b>" + esc(j.preferred) + "</b>") : "")
      + "<br>运行环境目录：" + esc(j.dir || "");
  }
  const host = $("#rtList");
  if (!host) return;
  const packs = (j.packs || []).filter(p => !p.hidden || p.installed);
  host.innerHTML = packs.map(p => `
    <div class="prov"><div class="ft">
      <span class="mini">${esc(p.label)}</span>
      <span class="tag ${p.installed ? "ok" : ""}">${p.installed ? "已安装" : (p.zip_ok ? "未安装" : "缺包文件")}</span>
      ${p.id === j.preferred ? '<span class="tag">推荐</span>' : ""}
      <span class="mini">${(p.bytes / 1048576).toFixed(0)} MB</span>
      <span class="spacer"></span>
      <button class="btn sm" data-rt="${esc(p.id)}">${p.installed ? "重装" : "安装"}</button>
    </div>
    <div class="mini" style="margin-top:4px">${esc(p.note || "")}</div></div>`).join("");
}

async function installRuntime(id) {
  rtSay(id ? ("正在安装 " + id + "…") : "正在按硬件安装…");
  try {
    const j = await api("/api/runtime/install", id ? { id } : {});
    if (j.ok) {
      const v = j.verify || {};
      toast("运行环境就绪：" + (j.pack || id) + (v.ok ? "（自检通过）" : "（自检未通过，见 data\\llama.log）"));
    } else {
      toast("安装失败：" + (j.error || "未知原因"));
    }
  } catch (e) { toast("安装失败：" + e.message); }
  loadRuntime();
}

function runtimeInit() {
  const r = $("#rtRefresh"); if (r) r.onclick = loadRuntime;
  const i = $("#rtInstall"); if (i) i.onclick = () => installRuntime("");
  const host = $("#rtList");
  if (host) host.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-rt]");
    if (b) installRuntime(b.getAttribute("data-rt"));
  });
}

function localInit() {
  $("#locRefresh").onclick = () => localRefresh();
  $("#locSave").onclick = async () => {
    try {
      await api("/api/local/save", { local: localBody() });
      toast("本地模型设置已保存");
      LOC_PAINTED = false;
      await localRefresh();
    } catch (e) { toast("保存失败：" + e.message); }
  };
  $("#locStart").onclick = async () => {
    $("#locState").textContent = "启动中…（首次加载模型约 5–20 秒，请稍候）";
    try {
      const r = await api("/api/local/start", { local: localBody() });
      toast(r.ok ? ("已启动" + (r.note ? "：" + r.note : "")) : (r.error || "启动失败"));
    } catch (e) { toast("启动失败：" + e.message); }
    LOC_PAINTED = false;
    await loadState();
    await localRefresh();
  };
  $("#locStop").onclick = async () => {
    try {
      const r = await api("/api/local/stop", {});
      toast(r.ok ? "已停止本地模型" : (r.error || "本地模型没有在运行"));
    } catch (e) { toast("停止失败：" + e.message); }
    await localRefresh();
  };
}

function renderProviders() {
  $("#provList").innerHTML = S.providers.map((p) => `
    <div class="prov${p.id === S.active ? " on" : ""}" data-id="${p.id}">
      <div class="hd"><b data-name>${esc(p.name)}</b><span class="id">${esc(p.id)}</span>
        ${p.id === S.active ? '<span class="tag ok">当前</span>' : ""}
        <span style="flex:1"></span>
        <button class="btn sm" data-act="${p.id}">设为当前</button></div>
      <div class="gr">
        <div><label class="hint">显示名</label><input data-f="name" value="${esc(p.name)}"></div>
        <div><label class="hint">base_url</label><input data-f="base_url" value="${esc(p.base_url)}"></div>
        <div><label class="hint">model</label><input data-f="model" value="${esc(p.model)}"></div>
        <div><label class="hint">api_key（留空＝不改）</label><input data-f="api_key" placeholder="${esc(p.api_key_masked)}"></div>
        <div><label class="hint">max_tokens</label><input data-f="max_tokens" type="number" value="${p.max_tokens}"></div>
        <div><label class="hint">temperature</label><input data-f="temperature" type="number" step="0.1" value="${p.temperature}"></div>
        <div style="grid-column:1 / -1"><label class="hint">备注</label><input data-f="note" value="${esc(p.note || "")}"></div>
        <div style="grid-column:1 / -1"><label class="hint">额外请求参数（JSON，透传给 API，如 {"reasoning_effort":"low"}）</label><textarea data-f="extra_json" rows="2">${esc(p.extra_json || "")}</textarea></div>
      </div>
      <div class="ft">
        <label class="chk"><input type="checkbox" data-f="vision" ${p.vision ? "checked" : ""}>支持看图（可传参考图给模型阅读）</label>
        <span style="flex:1"></span>
        <button class="btn sm" data-test="${p.id}">测试连接</button>
        <button class="btn sm" data-save="${p.id}">保存</button>
        <button class="btn sm danger" data-del="${p.id}">删除</button>
      </div>
    </div>`).join("");

  $$("#provList [data-act]").forEach((b) => b.onclick = async () => {
    S.active = b.dataset.act;
    await api("/api/provider/activate", { id: S.active, fast: S.fast });
    renderProviderSelect(); renderProviders(); toast("已切换服务");
  });
  $$("#provList [data-save]").forEach((b) => b.onclick = async () => {
    const box = b.closest(".prov");
    const provider = { id: b.dataset.save };
    box.querySelectorAll("[data-f]").forEach((el) => {
      provider[el.dataset.f] = el.type === "checkbox" ? el.checked : el.value;
    });
    if (provider.api_key === "") delete provider.api_key;
    const r = await api("/api/provider/save", { provider });
    S.providers = r.providers; renderProviderSelect(); renderProviders();
    toast("已保存", "s");
  });
  $$("#provList [data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("删除这个服务配置？")) return;
    const r = await api("/api/provider/delete", { id: b.dataset.del });
    S.providers = r.providers; S.active = r.providers[0] ? r.providers[0].id : null;
    renderProviderSelect(); renderProviders(); toast("已删除");
  });
  $$("#provList [data-test]").forEach((b) => b.onclick = async () => {
    const box = b.closest(".prov");
    const g = (f) => { const el = box.querySelector(`[data-f="${f}"]`); return el ? el.value : ""; };
    b.textContent = "测试中…"; b.disabled = true;
    try {
      const r = await api("/api/provider/test", { id: b.dataset.test, base_url: g("base_url"), model: g("model"), api_key: g("api_key") });
      b.textContent = r.ok ? "测试通过 ✓" : "失败 ✕";
      if (r.ok) toast(r.content.slice(0, 60) || "连接正常", "s");
      else { toast("连接失败", "e"); box.insertAdjacentHTML("afterbegin", `<pre class="body" style="margin-bottom:10px">${esc(r.error)}</pre>`); }
    } catch (e) { b.textContent = "失败 ✕"; toast(e.message, "e"); }
    setTimeout(() => { b.textContent = "测试连接"; b.disabled = false; }, 4000);
  });
}
async function addPreset(i) {
  const p = S.presets[i];
  const r = await api("/api/provider/save", {
    provider: { id: null, name: p.name, base_url: p.base_url, model: p.model, vision: p.vision, note: p.note, api_key: p.base_url.includes("127.0.0.1") ? "local" : "" },
  });
  S.providers = r.providers; renderProviderSelect(); renderProviders();
  toast("已添加：" + p.name + "（记得填 key 和模型名）");
}

/* ------------------------------------------------------------------ 规范管理 */
/* ------------------------------------------------------------------ 插件 */
let PLUG = null;

async function loadPlugins() {
  try {
    PLUG = await api("/api/plugins");
    renderPlugins();
    renderPluginTools();
    if (window.PSPlugin) await PSPlugin.load((PLUG && PLUG.plugins) || []);
  } catch (e) {
    const box = $("#pluginList");
    if (box) box.innerHTML = `<p class="hint">插件列表读取失败：${esc(String(e.message || e))}</p>`;
  }
}

function plugStatusTag(p) {
  const M = {
    template: ['模板', ""],
    loaded: ['代码 · 已加载', "ok"],
    error: ['出错', "err"],
    untrusted: ['未信任', "warn"],
    disabled: ['已停用', "off"],
    pending: ['待加载', "off"],
  };
  const v = M[p.status] || [p.status || "", ""];
  return `<span class="tag ${v[1]}">${esc(v[0])}</span>`;
}

function renderPlugins() {
  const box = $("#pluginList");
  if (!box || !PLUG) return;
  const dir = $("#pluginDir");
  if (dir) dir.textContent = PLUG.dir || "";
  const plugs = PLUG.plugins || [];
  if (!plugs.length && !(PLUG.errors || []).length) {
    box.innerHTML = `<p class="hint">插件目录还是空的。按 README 建一个文件夹放进来（或点「安装插件」上传 zip），
      也可以复制自带的 <code>sample_generic</code> 改成自己的。</p>`;
    return;
  }
  const rows = plugs.map((p) => {
    if (p.error && p.status === "error") {
      return `<div class="prov"><div class="ft"><span class="tag err">出错</span>
        <span class="mini"><b>${esc(p.name || p.id)}</b>：${esc(p.error)}</span>
        ${p.kind === "code" ? `<button class="btn sm" data-pg-reload="${esc(p.id)}">重试</button>` : ""}
      </div></div>`;
    }
    const nParam = Array.isArray(p.params) ? p.params.length : (typeof p.params === "number" ? p.params : 0);
    const meta = [p.version ? "v" + p.version : "", p.author || "",
                  p.kind === "code" ? "代码插件" : "提示词模板",
                  nParam ? nParam + " 个参数" : ""].filter(Boolean).join(" · ");
    const toolBtns = (p.tools || []).map((t) =>
      `<button class="btn sm" data-pg-tool="${esc(p.id)}" data-tool="${esc(t.name)}" title="${esc(t.hint || "")}">${esc(t.label || t.name)}</button>`).join(" ");
    const setRows = (p.settings || []).map((s) => {
      const val = p.values && Object.prototype.hasOwnProperty.call(p.values, s.key) ? p.values[s.key] : (s.default !== undefined ? s.default : "");
      const ctl = s.type === "select" && (s.options || []).length
        ? `<select data-ps-key="${esc(s.key)}">${s.options.map((o) => {
            const ov = typeof o === "string" ? o : (o.value !== undefined ? o.value : o);
            const ol = typeof o === "string" ? o : (o.label !== undefined ? o.label : ov);
            return `<option value="${esc(ov)}"${String(ov) === String(val) ? " selected" : ""}>${esc(ol)}</option>`;
          }).join("")}</select>`
        : s.type === "checkbox"
          ? `<label class="chk"><input type="checkbox" data-ps-key="${esc(s.key)}"${val ? " checked" : ""}>${esc(s.label || s.key)}</label>`
          : `<input data-ps-key="${esc(s.key)}" value="${esc(val)}" placeholder="${esc(s.placeholder || "")}">`;
      if (s.type === "checkbox") return `<div class="ft">${ctl}</div>`;
      return `<div class="ft"><span class="mini" style="min-width:120px">${esc(s.label || s.key)}</span>${ctl}</div>`;
    }).join("");
    return `<div class="prov" data-pgbox="${esc(p.id)}">
      <div class="ft">
        <label class="chk"><input type="checkbox" data-pg-id="${esc(p.id)}"${p.enabled ? " checked" : ""}>启用</label>
        <span class="mini"><b>${esc(p.name)}</b></span>
        ${plugStatusTag(p)}
        <span class="tag">${esc(meta)}</span>
        <span class="spacer"></span>
        ${p.kind === "code" && !p.trusted ? `<button class="btn sm primary" data-pg-trust="${esc(p.id)}">信任并加载</button>` : ""}
        ${p.kind === "code" && p.trusted ? `<button class="btn sm" data-pg-untrust="${esc(p.id)}">取消信任</button>` : ""}
        <button class="btn sm" data-pg-del="${esc(p.id)}">删除</button>
      </div>
      ${p.description ? `<div class="mini" style="margin-top:2px">${esc(p.description)}</div>` : ""}
      ${toolBtns ? `<div class="ft" style="margin-top:6px"><span class="mini">工具</span>${toolBtns}</div>` : ""}
      ${setRows ? `<div class="pgset">${setRows}
        <button class="btn sm" data-pg-save="${esc(p.id)}">保存设置</button></div>` : ""}
      <div class="mini" style="margin-top:4px;opacity:.6">${esc(p.dir || "")}${(p.routes || []).length ? " · 接口 " + p.routes.map((r) => "/api/plugin/" + p.id + "/" + r.path).join("、") : ""}</div>
    </div>`;
  }).join("");
  const errs = (PLUG.errors || []).length
    ? `<div class="mini" style="color:var(--err);margin-top:6px">${PLUG.errors.map(esc).join("<br>")}</div>` : "";
  box.innerHTML = rows + errs;
}

/* 撰写页工具条：插件注册的工具按钮，作用于当前结果（没有结果时作用于输入） */
function renderPluginTools() {
  const host = $("#pluginTools");
  if (!host) return;
  const btns = [];
  (PLUG && PLUG.plugins || []).forEach((p) => {
    if (!p.enabled || (p.kind === "code" && !p.trusted)) return;
    (p.tools || []).forEach((t) => {
      btns.push(`<button class="btn sm" data-ptool="${esc(p.id)}" data-tool="${esc(t.name)}" title="${esc(t.hint || "")}">${esc(t.label || t.name)}</button>`);
    });
  });
  if (!btns.length) { host.innerHTML = ""; return; }
  host.innerHTML = `<span class="mini" style="margin-right:6px">插件工具</span>` + btns.join(" ");
}

/* 把插件工具的输出放进结果区（同时更新 S.last，让复制/导出可用） */
function placeResult(text, label, note) {
  const r = {
    content: text,
    json: null,
    label: label || "插件输出",
    provider_name: "插件",
    model: "plugin",
    system_chars: 0,
    user_chars: 0,
    elapsed: 0,
    note: note || "",
  };
  S.last = r;
  const host = $("#result");
  if (host) host.innerHTML = renderRich(text);
  const meta = $("#meta");
  if (meta) meta.textContent = (label || "插件输出") + (note ? " · " + note : "");
  const bar = $("#bar");
  if (bar) bar.textContent = "";
  if (typeof bindResultButtons === "function") bindResultButtons();
}

async function runPluginTool(pid, tool) {
  const src = ($("#result") && $("#result").textContent || "").trim();
  const text = src || $("#content").value.trim();
  if (!text) { toast("先写点内容（或先出一版结果）再用工具", "e"); return; }
  toast("正在运行插件工具…");
  try {
    const j = await api("/api/plugins/tool", { id: pid, tool, text, params: collectParams(), template: S.tpl });
    if (!j.ok) { toast("工具执行失败：" + (j.error || ""), "e"); return; }
    placeResult(j.text || "", "插件 · " + tool, j.note || "");
  } catch (e) { toast("工具执行失败：" + (e.message || e), "e"); }
}

function pluginInit() {
  const bt = $("#pluginReload");
  if (bt) bt.onclick = async () => {
    try {
      PLUG = await api("/api/plugins/reload", {});
      renderPlugins(); renderPluginTools();
      await loadState();
      renderTplPicker();
      toast("已重新加载插件（共 " + (PLUG.count || 0) + " 个可用）");
    } catch (e) { toast("重新加载失败：" + (e.message || e), "e"); }
  };
  const op = $("#pluginOpen");
  if (op) op.onclick = async () => {
    try {
      const j = await api("/api/plugins/reveal", {});
      toast(j.opened ? "已打开插件文件夹" : "请在资源管理器里手动打开：" + (j.dir || ""), j.opened ? "" : "e");
    } catch (e) { toast("打开失败：" + (e.message || e), "e"); }
  };
  const ins = $("#pluginInstall");
  if (ins) ins.onclick = () => { const f = $("#pluginZip"); if (f) f.click(); };
  const zip = $("#pluginZip");
  if (zip) zip.onchange = async () => {
    const f = zip.files && zip.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    toast("正在安装 " + f.name + "…");
    try {
      const r = await fetch("/api/plugins/install", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok || !j.ok) { toast("安装失败：" + (j.error || ("HTTP " + r.status)), "e"); return; }
      PLUG = j; renderPlugins(); renderPluginTools();
      const it = j.installed || {};
      toast(it.ok ? "已安装插件：" + (it.id || "") : ("安装失败：" + (it.error || "")), it.ok ? "" : "e");
      await loadState(); renderTplPicker();
    } catch (e) { toast("安装失败：" + (e.message || e), "e"); }
    zip.value = "";
  };

  const box = $("#pluginList");
  if (box) {
    box.addEventListener("change", async (ev) => {
      const el = ev.target;
      if (!el || !el.dataset) return;
      const tid = el.dataset.pgId;
      if (!tid) return;
      try {
        PLUG = await api("/api/plugins/toggle", { id: tid, enabled: !!el.checked });
        renderPlugins(); renderPluginTools();
        await loadState(); renderTplPicker();
        toast(el.checked ? "已启用插件" : "已停用插件");
      } catch (e) { toast("切换失败：" + (e.message || e), "e"); }
    });
    box.addEventListener("click", async (ev) => {
      const el = ev.target.closest ? ev.target.closest("button") : null;
      if (!el || !el.dataset) return;
      const d = el.dataset;
      const call = async (path, body, okMsg) => {
        try {
          PLUG = await api(path, body);
          renderPlugins(); renderPluginTools();
          await loadState(); renderTplPicker();
          if (okMsg) toast(okMsg);
        } catch (e) { toast((okMsg || "操作") + "失败：" + (e.message || e), "e"); }
      };
      if (d.pgTrust) return call("/api/plugins/trust", { id: d.pgTrust, trusted: true }, "已信任并加载插件");
      if (d.pgUntrust) return call("/api/plugins/trust", { id: d.pgUntrust, trusted: false }, "已取消信任");
      if (d.pgDel) {
        if (!confirm("删除插件目录？这会删掉插件文件夹本身。")) return;
        return call("/api/plugins/delete", { id: d.pgDel }, "已删除插件");
      }
      if (d.pgReload) return call("/api/plugins/reload", {}, "已重新加载");
      if (d.pgTool) return runPluginTool(d.pgTool, d.tool);
      if (d.pgSave) {
        const box2 = box.querySelector('[data-pgbox="' + d.pgSave + '"]');
        const values = {};
        (box2 ? box2.querySelectorAll("[data-ps-key]") : []).forEach((c) => {
          values[c.dataset.psKey] = c.type === "checkbox" ? !!c.checked : c.value;
        });
        return call("/api/plugins/settings", { id: d.pgSave, values }, "已保存插件设置");
      }
    });
  }

  const tools = $("#pluginTools");
  if (tools) tools.addEventListener("click", (ev) => {
    const el = ev.target.closest ? ev.target.closest("button") : null;
    if (!el || !el.dataset || !el.dataset.ptool) return;
    runPluginTool(el.dataset.ptool, el.dataset.tool);
  });
}

let SPEC = null;

async function loadSpecMgr() {
  try {
    SPEC = await api("/api/spec");
    renderSpecMgr();
  } catch (e) { toast("读取规范清单失败：" + e.message, "e"); }
}

function renderSpecMgr() {
  const host = $("#specMgr");
  if (!host || !SPEC) return;
  const tpls = SPEC.templates || [];
  let nComp = 0, nExtra = 0;
  tpls.forEach((t) => { nComp += (t.components || []).length; nExtra += (t.extra || []).length; });
  const cnt = $("#specCount");
  if (cnt) cnt.textContent = `　共 ${tpls.length} 个模板 / ${nComp} 个内置组件 / ${nExtra} 条自定义规范`;
  host.innerHTML = tpls.map((t) => {
    const rows = (t.components || []).map((c) => {
      const tag = c.replaced
        ? `<span class="tag ok">已替换 ${c.replace_chars} 字</span>`
        : (c.enabled ? '<span class="tag">内置</span>' : '<span class="tag off">已关闭</span>');
      return `<div class="prov"><div class="ft">
        <label class="chk"><input type="checkbox" data-sp-tg-name="${esc(c.name)}"${c.enabled ? " checked" : ""}>注入</label>
        <span class="mini">${esc(c.name)}</span>${tag}
        <span class="mini">${Math.round(c.bytes / 1024)} KB</span>
        <span style="flex:1"></span>
        <button class="btn sm" data-sp-ed-name="${esc(c.name)}">编辑替换</button>
        ${c.replaced ? `<button class="btn sm" data-sp-rs-name="${esc(c.name)}">恢复内置</button>` : ""}
      </div></div>`;
    }).join("");
    const ex = (t.extra || []).map((e) => `<div class="prov"><div class="ft">
        <label class="chk"><input type="checkbox" data-sp-tg-id="${esc(e.id)}"${e.enabled ? " checked" : ""}>启用</label>
        <span class="mini">${esc(e.name)}</span><span class="tag ok">自定义</span>
        <span class="mini">${e.chars || 0} 字</span><span style="flex:1"></span>
        <button class="btn sm" data-sp-edx-id="${esc(e.id)}">编辑</button>
        <button class="btn sm danger" data-sp-del-id="${esc(e.id)}">删除</button>
      </div></div>`).join("");
    return `<div style="margin-bottom:12px">
      <label class="hint">${esc(t.label)}${t.id === S.tpl ? "（当前模板）" : ""}</label>
      ${rows || '<div class="mini">该模板无内置规范组件。</div>'}${ex}
      <div style="margin-top:6px"><button class="btn sm" data-sp-add="${esc(t.id)}">＋ 添加规范</button></div>
    </div>`;
  }).join("");
}

function closeSpecEditor() {
  const box = $("#specEdBox");
  if (box) box.remove();
}

function openSpecEditor(o) {
  closeSpecEditor();
  const host = $("#specMgr");
  const box = document.createElement("div");
  box.id = "specEdBox";
  box.className = "card";
  box.style.marginBottom = "12px";
  const title = o.kind === "extra"
    ? `编辑自定义规范：${o.name || "未命名"}`
    : `替换内置组件：${o.name}`;
  box.innerHTML = `<div style="padding:12px">
    <h3>${esc(title)}</h3>
    <textarea id="specEd" rows="12">${esc(o.text || "")}</textarea>
    <div style="margin-top:8px">
      <button class="btn pri" id="specEdSave">保存</button>
      <button class="btn" id="specEdCancel">取消</button>
    </div>
    <div class="mini" style="margin-top:8px">${o.kind === "extra"
      ? "内容注入到该模板系统提示词末尾，并声明「优先级高于上方内置规范，冲突时以本节为准」。"
      : "保存后该内置组件的原文被这段内容顶掉；点列表里的「恢复内置」可还原官方原文。保存空内容＝该组件不再注入。"}</div>
  </div>`;
  host.parentNode.insertBefore(box, host);
  $("#specEdCancel").onclick = closeSpecEditor;
  $("#specEdSave").onclick = async () => {
    const text = $("#specEd").value;
    try {
      if (o.kind === "extra") {
        await api("/api/spec/save", { spec: { id: o.id || null, template: o.template, name: o.name || "我的规范", text, enabled: true } });
      } else {
        await api("/api/spec/replace", { name: o.name, replace: text });
        if (!text.trim()) toast("已保存空内容：该组件不会注入", "w");
      }
      toast("规范已保存", "s");
      closeSpecEditor();
      await loadSpecMgr();
    } catch (e) { toast("保存失败：" + e.message, "e"); }
  };
  $("#specEd").focus();
}

function specMgrInit() {
  const reset = $("#specResetAll");
  if (reset) reset.onclick = async () => {
    if (!confirm("把所有内置规范恢复官方原文，并删除全部自定义规范？")) return;
    try {
      await api("/api/spec/reset", {});
      toast("已恢复默认", "s");
      await loadSpecMgr();
    } catch (e) { toast("失败：" + e.message, "e"); }
  };
  const host = $("#specMgr");
  if (!host) return;
  host.addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-sp-add],[data-sp-rs-name],[data-sp-del-id],[data-sp-ed-name],[data-sp-edx-id]");
    if (!b) return;
    const d = b.dataset;
    try {
      if (d.spAdd) {
        const nm = prompt("给这条规范起个名字", "我的规范");
        if (nm === null) return;
        openSpecEditor({ kind: "extra", template: d.spAdd, name: (nm || "我的规范").trim(), text: "" });
      } else if (d.spRsName) {
        await api("/api/spec/replace", { name: d.spRsName, replace: "" });
        toast("已恢复内置原文", "s"); await loadSpecMgr();
      } else if (d.spDelId) {
        if (!confirm("删除这条自定义规范？")) return;
        await api("/api/spec/delete", { id: d.spDelId });
        toast("已删除", "s"); await loadSpecMgr();
      } else if (d.spEdName) {
        const j = await api("/api/spec/content?name=" + encodeURIComponent(d.spEdName));
        openSpecEditor({ kind: "built-in", name: d.spEdName, text: j.text || "" });
      } else if (d.spEdxId) {
        let found = null;
        (SPEC.templates || []).forEach((t) => (t.extra || []).forEach((e) => {
          if (e.id === d.spEdxId) found = { template: t.id, name: e.name, text: e.text, id: e.id };
        }));
        if (!found) { toast("找不到这条规范", "e"); return; }
        openSpecEditor({ kind: "extra", ...found });
      }
    } catch (e) { toast("操作失败：" + e.message, "e"); }
  });
  host.addEventListener("change", async (ev) => {
    const el = ev.target;
    try {
      if (el.dataset.spTgName) {
        await api("/api/spec/toggle", { name: el.dataset.spTgName, enabled: !!el.checked });
        await loadSpecMgr();
      } else if (el.dataset.spTgId) {
        await api("/api/spec/toggle", { id: el.dataset.spTgId, enabled: !!el.checked });
        await loadSpecMgr();
      }
    } catch (e) { toast("切换失败：" + e.message, "e"); }
  });
}

/* ------------------------------------------------------------------ 事件 */
function sbarInit() {
  const fold = $("#sbarFold"), open = $("#sbarOpen");
  if (fold) fold.onclick = () => PSPlugin.sbarOn(false);
  if (open) open.onclick = () => PSPlugin.sbarOn(true);
  let saved = "1";
  try { saved = localStorage.getItem("ps-sbar") || "1"; } catch (e) {}
  document.body.classList.toggle("sbar-on", saved !== "0");
  document.addEventListener("keydown", function (ev) {
    if (ev.ctrlKey && ev.shiftKey && String(ev.key).toLowerCase() === "b") {
      ev.preventDefault();
      PSPlugin.sbarOn(!document.body.classList.contains("sbar-on"));
    }
  });
}
async function boot() {
  initBridge(function () { applyTheme(document.documentElement.getAttribute("data-theme") || "dark", true); });
  initTheme();
  sbarInit();
  wireMention();
  await loadState();
  await loadUserTpl();
  specMgrInit();
  pluginInit();
  runtimeInit();
  localInit();
  localRefresh();
  loadPlugins();          /* 插件工具按钮在「提示词撰写」页也要显示；同时把插件自带面板挂上去 */
  /* 自定义模型编辑器 */
  $("#teSave").onclick = saveTplEditor;
  $("#teCancel").onclick = closeTplEditor;
  $("#tplEd").onclick = (ev) => { if (ev.target.id === "tplEd") closeTplEditor(); };
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && $("#tplEd").classList.contains("on")) closeTplEditor();
  });
  const _tab = /[?&]tab=(\w+)/.exec(location.search);   /* 支持 ?tab=settings 直达 */
  if (_tab) showTab(_tab[1]);
  const _sb = /[?&]sbar=([\w\-]+)/.exec(location.search); /* 支持 ?sbar=插件id 直达侧栏页签 */
  if (_sb) PSPlugin._sbarCur = _sb[1];
  $$("nav button").forEach((b) => b.onclick = () => showTab(b.dataset.tab));
  $("#provider").onchange = async () => {
    S.active = $("#provider").value;
    await api("/api/provider/activate", { id: S.active, fast: S.fast, template: S.tpl });
    renderProviderSelect(); toast("已切换：" + $("#provider").selectedOptions[0].text);
  };
  $("#fastWrap").onclick = async () => {
    S.fast = !S.fast;
    $("#fastToggle").classList.toggle("on", S.fast);
    await api("/api/provider/activate", { id: S.active, fast: S.fast, template: S.tpl });
    toast(S.fast ? "快速模式：精简规范注入" : "完整模式：注入全部实测规范（更慢更贵，质量更高）");
  };
  $("#go").onclick = () => generate("");
  $("#iterate").onclick = () => {
    const fb = $("#feedback").value.trim();
    if (!fb) { toast("写下对上一版的要求", "e"); return; }
    generate(fb);
  };
  $("#clear").onclick = () => {
    $("#content").value = ""; $("#feedback").value = "";
    S.images = []; renderImages();
    $("#result").innerHTML = `<p class="hint">已清空。</p>`;
  };
  $("#drop").onclick = () => $("#file").click();
  $("#file").onchange = (e) => addFiles(e.target.files);
  const drop = $("#drop");
  ["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("hot"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("hot"); }));
  drop.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files); });
  document.addEventListener("paste", (e) => {
    if (S.tab !== "prompt") return;
    const items = (e.clipboardData || {}).items || [];
    const files = [];
    for (const it of items) if (it.kind === "file" && it.type.startsWith("image/")) files.push(it.getAsFile());
    if (files.length) { e.preventDefault(); addFiles(files); }
  });
  $("#trGo").onclick = translate;
  $("#trSwap").onclick = () => {
    const box = $("#trResult").querySelector("[data-code]");
    if (!box) { toast("还没有译文", "e"); return; }
    $("#trText").value = decodeURIComponent(box.dataset.code);
    toast("译文已搬到原文框");
  };
  $("#histReload").onclick = loadHistory;
  $("#histClear").onclick = async () => {
    if (!confirm("清空全部历史记录？")) return;
    await api("/api/history/clear", {}); loadHistory(); toast("已清空");
  };
  $("#addProv").onclick = async () => {
    const r = await api("/api/provider/save", {
      provider: { name: "新服务 " + (S.providers.length + 1), base_url: "https://api.openai.com/v1", model: "gpt-4.1-mini", vision: true, api_key: "", note: "填写 base_url / model / key 后保存" },
    });
    S.providers = r.providers; renderProviderSelect(); renderProviders();
    toast("已添加，填完字段后点「保存」");
  };
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && S.tab === "prompt") { e.preventDefault(); generate($("#feedback").value.trim()); }
  });
}
boot().catch((e) => {
  document.body.insertAdjacentHTML("afterbegin", `<pre class="body" style="margin:12px;color:#f85149">前端初始化失败：${esc(e.message)}\n刷新页面试试。</pre>`);
});
