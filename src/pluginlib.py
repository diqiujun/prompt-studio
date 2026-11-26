"""插件系统（两级，仿 DSH 的插件形态）。

第一级 · 模板插件（纯声明式，只读 JSON/文本，不执行代码）
=========================================================
    plugins/
      my-plugin/
        plugin.json     # 必须：id / name，其余可选
        spec.md         # 可选：提示词规范正文（也可在 plugin.json 里用 "spec" 内联）

第二级 · 代码插件（plugin.json + plugin.py，可注册工具按钮 / 后端接口 / 生成后钩子 / 设置项）
=========================================================================================
    plugins/
      my-tools/
        plugin.json     # 必须：id / name；"entry": "plugin.py" 可省（默认 plugin.py）
        plugin.py       # 必须：定义 register(ctx)

plugin.py 的写法（ctx 由程序注入，不要自己 import 程序内部模块）：

    def register(ctx):
        ctx.log("插件已加载")

        @ctx.tool("to_english", label="改写成英文", where="result")
        def to_english(text, params):
            # text   = 结果区当前文本（where="result"）或输入框文本（where="prompt"）
            # params = {"settings": {...插件设置...}, "params": {...界面上的生成参数...},
            #           "template": "h3_video", "images": 2, "note": ""}
            return {"text": "改写后的文本", "note": "已改写成英文"}

        @ctx.route("/stats", methods=["POST"])
        def stats(body, query):
            return {"ok": True, "chars": len(body.get("text") or "")}

        @ctx.on("generate.after")
        def after(payload):
            # payload: {"template","content","output","json"}
            return payload["output"].rstrip()   # 返回字符串 = 用新文本替换结果

插件清单字段（plugin.json，全部可选，除 id、name）：

    id / name / description（或 tagline）/ author / version
    entry         代码插件入口文件名（缺省 plugin.py）
    intro         给模型的开场角色句（模板插件用，缺省用内置通用句）
    spec          规范正文（字符串），或 "spec_file" 指定文件名
                  （缺省按 spec.md / spec.txt / prompt.md / 规范.md 顺序找）
    min_images / max_images / need_roles / expect_json   同内置模板
    params        模板参数定义数组：{key,label,type,default,options,min,max,placeholder}
                  type 取值：select / number / text / textarea / canvas
    examples      输入示例（字符串数组）
    settings      插件设置项定义数组，元素同 params（值存进 data\\config.json 的 plugin_settings）
    enabled       是否启用（缺省 true；程序里的开关不会改你的文件）

安全模型：代码插件**首次加载必须在界面上点「信任并加载」**，信任名单存
data\\config.json 的 plugin_trust；不信任则只登记信息、不执行任何代码。
"""
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import zipfile

import settings

MANIFEST_NAMES = ("plugin.json", "manifest.json")
SPEC_FALLBACK = ("spec.md", "spec.txt", "prompt.md", "规范.md")
DEFAULT_ENTRY = "plugin.py"
ID_RE = re.compile(r"[^0-9a-zA-Z_\-]+")

DEFAULT_INTRO = (
    "你是运行在「提示词工作台」里的提示词引擎，正在执行插件「{name}」。"
    "输入 = 用户的口语化内容描述 + 生成参数 + 可选的参考图清单。"
)

OUTPUT_RULES = """【输出纪律】
1. 只输出最终可用的提示词正文，不要寒暄、不要解释你做了什么、不要复述我的要求。
2. 不要用 markdown 代码块包裹答案，不要加「提示词：」之类的前缀。
3. 参数区只影响提示词内容本身，不要把参数抄成列表塞进正文。
4. 插件规范里若要求 JSON，就严格按 JSON 输出，不要夹带解释文字。
5. 我的描述模糊时按最合理的方案补全，不要反问我。"""

CODE_HINT = "此插件会执行 Python 代码（plugin.py），首次加载需要你点「信任并加载」。"

_LOCK = threading.RLock()
_LOADED = {}      # pid -> {"ok":bool, "error":str, "ctx":Ctx|None, "meta":dict}


# ---------------------------------------------------------------- 目录与读取
def plugins_dir():
    """插件目录：<程序目录>/plugins（绿色版就在 exe 旁边）。"""
    return settings.app_root() / "plugins"


def ensure_dir():
    d = plugins_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_dir_for(pid):
    d = settings.data_dir() / "plugins" / _slug(pid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path():
    return settings.data_dir() / "plugins.log"


def _log(pid, msg):
    try:
        line = "[%s] [%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), pid, msg)
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def _slug(s):
    s = ID_RE.sub("_", str(s or "").strip()) or "plugin"
    return s.strip("_").lower() or "plugin"


def _norm_fields(raw, kind="param"):
    """参数 / 设置项定义规范化。"""
    out = []
    if not isinstance(raw, list):
        return out
    for it in raw:
        if not isinstance(it, dict):
            continue
        key = str(it.get("key") or it.get("name") or "").strip()
        if not key:
            continue
        typ = str(it.get("type") or "text").strip().lower()
        if typ not in ("select", "number", "text", "textarea", "canvas", "checkbox"):
            typ = "text"
        d = {
            "key": key,
            "label": str(it.get("label") or key),
            "type": typ,
            "default": it.get("default", "" if typ != "checkbox" else False),
        }
        if typ == "select":
            opts = it.get("options") or []
            d["options"] = [str(o) for o in opts] if isinstance(opts, list) else []
            if not d["options"]:
                d["type"] = "text"
        if typ == "number":
            for k in ("min", "max", "step"):
                if k in it:
                    try:
                        d[k] = float(it[k]) if k != "step" else it[k]
                    except Exception:
                        pass
        for k in ("placeholder", "unit", "suggestions", "help"):
            if it.get(k):
                d[k] = it[k]
        out.append(d)
    return out


# ---------------------------------------------------------------- 清单解析
def _parse_manifest(path, is_dir):
    """返回 (meta, error)。meta 含 dir 与文件字段，不含可执行对象。"""
    if is_dir:
        mpath = None
        for name in MANIFEST_NAMES:
            p = os.path.join(path, name)
            if os.path.isfile(p):
                mpath = p
                break
        if not mpath:
            return None, "缺少 plugin.json（插件目录里必须有它）"
        base = path
    else:
        mpath = path
        base = os.path.dirname(path)
    try:
        raw = _read_json(mpath)
    except Exception as e:
        return None, "plugin.json 解析失败：%s" % e
    if not isinstance(raw, dict):
        return None, "plugin.json 必须是一个 JSON 对象"

    pid = _slug(raw.get("id") or os.path.basename(base))
    name = str(raw.get("name") or pid)
    entry = str(raw.get("entry") or DEFAULT_ENTRY)
    code_path = os.path.join(base, entry)
    has_code = os.path.isfile(code_path)

    # 规范正文：内联 > 指定文件 > 常见文件名
    spec = raw.get("spec")
    if not isinstance(spec, str) or not spec.strip():
        spec = ""
        cand = []
        if raw.get("spec_file"):
            cand.append(str(raw["spec_file"]))
        cand.extend(SPEC_FALLBACK)
        for fn in cand:
            p = os.path.join(base, fn)
            if os.path.isfile(p):
                try:
                    spec = _read_text(p)
                except Exception:
                    spec = ""
                break

    meta = {
        "id": pid,
        "dir": base,
        "manifest": mpath,
        "name": name,
        "description": str(raw.get("description") or raw.get("tagline") or ""),
        "tagline": str(raw.get("tagline") or raw.get("description") or ""),
        "author": str(raw.get("author") or ""),
        "version": str(raw.get("version") or ""),
        "intro": str(raw.get("intro") or ""),
        "entry": entry,
        "code_path": code_path,
        "has_code": has_code,
        "has_template": bool(spec.strip()) or bool(raw.get("params")),
        "spec": spec,
        "min_images": int(raw.get("min_images") or 0),
        "max_images": int(raw.get("max_images") or 6),
        "need_roles": bool(raw.get("need_roles")),
        "expect_json": bool(raw.get("expect_json")),
        "params": _norm_fields(raw.get("params"), "param"),
        "settings": _norm_fields(raw.get("settings"), "setting"),
        "examples": [str(x) for x in (raw.get("examples") or []) if str(x).strip()],
        "enabled": bool(raw.get("enabled", True)),
        "web": _norm_web(raw.get("web"), base),
    }
    if not meta["has_code"] and not meta["has_template"]:
        return None, "既没有规范正文（spec.md）也没有 plugin.py，等于空插件"
    return meta, ""


def _norm_web(raw, base):
    """插件自带的界面贡献：{"js": "web/panel.js", "css": "web/panel.css", "mount": "prompt"}。
    文件必须存在，路径限定在插件目录内。返回 {} 表示这个插件没有界面。"""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in ("js", "css"):
        rel = str(raw.get(key) or "").strip().replace("\\", "/")
        if not rel:
            continue
        full = os.path.normpath(os.path.join(base, rel))
        if not os.path.abspath(full).startswith(os.path.abspath(base) + os.sep):
            continue
        if os.path.isfile(full):
            out[key] = rel
    if not out:
        return {}
    mount = str(raw.get("mount") or "prompt")
    out["mount"] = mount if mount in ("prompt", "settings", "both", "sidebar") else "prompt"
    out["title"] = str(raw.get("title") or "")
    return out


def web_assets(meta):
    """把 meta["web"] 转成前端可加载的 URL 列表。"""
    web = meta.get("web") or {}
    pid = meta["id"]
    out = {"mount": web.get("mount") or "prompt", "title": web.get("title") or ""}
    if web.get("js"):
        out["js"] = "/api/plugin-static/%s/%s" % (pid, web["js"])
    if web.get("css"):
        out["css"] = "/api/plugin-static/%s/%s" % (pid, web["css"])
    return out if (out.get("js") or out.get("css")) else {}


def static_path(pid, rel):
    """把 /api/plugin-static/<pid>/<rel> 解析成磁盘路径；越界返回 None。"""
    base = None
    for item in scan_all():
        if "meta" in item and item["meta"]["id"] == pid:
            base = item["meta"]["dir"]
            break
    if not base:
        return None
    rel = (rel or "").replace("\\", "/").lstrip("/")
    full = os.path.normpath(os.path.join(base, rel))
    if not os.path.abspath(full).startswith(os.path.abspath(base) + os.sep):
        return None
    return full if os.path.isfile(full) else None


def _iter_entries():
    d = plugins_dir()
    if not d.is_dir():
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if name.startswith(".") or name.startswith("_") or name.lower().startswith("readme"):
            continue
        p = os.path.join(d, name)
        if os.path.isdir(p):
            out.append((p, True))
        elif name.lower().endswith(".json"):
            out.append((p, False))
    return out


def scan_all(cfg=None):
    """扫描全部插件，返回 [{meta 或 {'path','error'}}]。不执行代码。"""
    cfg = cfg or settings.load_config()
    off = set(cfg.get("plugins_off") or [])
    trust = cfg.get("plugin_trust") or {}
    res = []
    seen = {}
    for path, is_dir in _iter_entries():
        meta, err = _parse_manifest(path, is_dir)
        if err:
            res.append({"path": path, "error": err})
            continue
        if meta["id"] in seen:
            res.append({"path": path, "error": "id 与 %s 重复：%s" % (seen[meta["id"]], meta["id"])})
            continue
        seen[meta["id"]] = path
        meta["enabled"] = bool(meta["enabled"]) and meta["id"] not in off
        meta["trusted"] = bool(trust.get(meta["id"]))
        res.append({"meta": meta})
    return res


def scan(cfg=None):
    """给 registry 用的模板视图：只返回「有规范正文」的插件。"""
    cfg = cfg or settings.load_config()
    templates, plugins, errors = [], [], []
    for item in scan_all(cfg):
        if "error" in item:
            errors.append({"path": item["path"], "error": item["error"]})
            continue
        m = item["meta"]
        plugins.append({
            "id": m["id"], "name": m["name"], "version": m["version"],
            "author": m["author"], "description": m["description"],
            "has_code": m["has_code"], "enabled": m["enabled"],
        })
        if not m["has_template"]:
            continue
        templates.append({
            "id": "plugin_" + m["id"],
            "label": m["name"],
            "group": "prompt",
            "desc": m["description"] or "插件模板",
            "builder": "build_plugin",
            "plugin": True,
            "plugin_id": m["id"],
            "plugin_dir": os.path.basename(m["dir"]),
            "plugin_version": m["version"],
            "plugin_author": m["author"],
            "enabled": m["enabled"],
            "min_images": m["min_images"],
            "max_images": m["max_images"],
            "need_roles": m["need_roles"],
            "expect_json": m["expect_json"],
            "params": m["params"],
            "examples": m["examples"],
            "_spec": m["spec"],
            "_intro": m["intro"] or DEFAULT_INTRO.format(name=m["name"]),
        })
    return {"dir": str(plugins_dir()), "templates": templates, "plugins": plugins, "errors": errors}


# ---------------------------------------------------------------- 代码插件运行环境
class Ctx:
    """注入给 plugin.py 的上下文。插件只能通过它接触程序。"""

    def __init__(self, meta, settings_values):
        self.plugin_id = meta["id"]
        self.name = meta["name"]
        self.dir = meta["dir"]
        self.data_dir = str(data_dir_for(meta["id"]))
        self.settings = dict(settings_values or {})
        self.tools = []
        self.routes = []
        self.hooks = {}

    # -- 给插件作者用的 API
    def log(self, msg):
        _log(self.plugin_id, str(msg))

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def tool(self, name, label=None, where="toolbar", hint=""):
        """注册工具按钮。两种写法都支持：

        @ctx.tool("tidy", "整理文本")
        def tidy(text, params): ...

        ctx.tool("tidy", "整理文本")(tidy)
        """
        def add(fn):
            self.tools.append({
                "name": str(name), "label": str(label or name),
                "where": where if where in ("toolbar", "result", "prompt") else "toolbar",
                "hint": str(hint or ""), "fn": fn,
            })
            return fn
        return add

    def route(self, path, methods=("POST",), fn=None):
        """注册后端接口：GET/POST /api/plugin/<插件id>/<path>。

        两种写法都支持：
        @ctx.route("stats", ["GET", "POST"])
        def stats(body, query): ...

        ctx.route("stats", ["GET", "POST"], stats)
        """
        ms = [methods] if isinstance(methods, str) else list(methods)

        def add(f):
            self.routes.append({
                "path": "/" + str(path).strip("/"),
                "methods": [m.upper() for m in ms], "fn": f,
            })
            return f
        if callable(fn):
            return add(fn)
        return add

    def on(self, event, fn=None):
        """挂载事件钩子（目前支持 "generate.after"）。

        @ctx.on("generate.after")
        def after(payload): ...
        """
        def add(f):
            self.hooks.setdefault(str(event), []).append(f)
            return f
        if callable(fn):
            return add(fn)
        return add


def _load_code_plugin(meta, cfg):
    """执行 plugin.py 的 register(ctx)。异常全部捕获，不影响主程序。"""
    pid = meta["id"]
    if not meta["has_code"]:
        return {"ok": True, "error": "", "ctx": Ctx(meta, {}), "meta": meta}
    settings_values = (cfg.get("plugin_settings") or {}).get(pid) or {}
    ctx = Ctx(meta, settings_values)
    modname = "ps_plugin_" + _slug(pid)
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(modname, meta["code_path"])
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载 %s" % meta["code_path"])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[modname] = mod
        spec.loader.exec_module(mod)
        reg = getattr(mod, "register", None)
        if not callable(reg):
            raise RuntimeError("plugin.py 里缺少 register(ctx) 函数")
        reg(ctx)
        if not (ctx.tools or ctx.routes or ctx.hooks):
            ctx.log("register() 没有注册任何工具/接口/钩子")
        _log(pid, "已加载：工具 %d / 接口 %d / 钩子 %d"
             % (len(ctx.tools), len(ctx.routes), sum(len(v) for v in ctx.hooks.values())))
        return {"ok": True, "error": "", "ctx": ctx, "meta": meta}
    except Exception:
        err = traceback.format_exc(limit=6)
        _log(pid, "加载失败：\n" + err)
        return {"ok": False, "error": err.strip().splitlines()[-1], "ctx": None, "meta": meta}


def ensure_loaded(cfg=None, force=False):
    """加载所有「启用 + 已信任」的代码插件（只在进程内执行一次）。"""
    cfg = cfg or settings.load_config()
    with _LOCK:
        if force:
            _LOADED.clear()
        for item in scan_all(cfg):
            if "error" in item:
                continue
            m = item["meta"]
            if not m["has_code"]:
                continue
            pid = m["id"]
            if pid in _LOADED and not force:
                continue
            if not m["enabled"]:
                _LOADED[pid] = {"ok": False, "error": "", "ctx": None, "meta": m,
                                "status": "disabled"}
                continue
            if not m["trusted"]:
                _LOADED[pid] = {"ok": False, "error": "", "ctx": None, "meta": m,
                                "status": "untrusted"}
                continue
            r = _load_code_plugin(m, cfg)
            r["status"] = "loaded" if r["ok"] else "error"
            _LOADED[pid] = r
        return _LOADED


def status(cfg=None):
    """插件中心用的完整状态（含代码插件加载结果）。"""
    cfg = cfg or settings.load_config()
    ensure_loaded(cfg)
    out = []
    for item in scan_all(cfg):
        if "error" in item:
            out.append({
                "id": os.path.basename(item["path"]),
                "dir": os.path.basename(item["path"]),
                "name": os.path.basename(item["path"]),
                "kind": "broken", "status": "error", "error": item["error"],
                "enabled": False, "trusted": False, "tools": [], "routes": [],
                "hooks": [], "settings": [], "values": {},
            })
            continue
        m = item["meta"]
        pid = m["id"]
        loaded = _LOADED.get(pid) or {}
        ctx = loaded.get("ctx")
        st = "template"
        if m["has_code"]:
            st = loaded.get("status") or ("untrusted" if not m["trusted"] else "pending")
        vals = {}
        for s in m["settings"]:
            vals[s["key"]] = (cfg.get("plugin_settings") or {}).get(pid, {}).get(s["key"], s.get("default"))
        out.append({
            "id": pid,
            "dir": os.path.basename(m["dir"]),
            "name": m["name"],
            "description": m["description"],
            "author": m["author"],
            "version": m["version"],
            "kind": "code" if m["has_code"] and m["has_template"] else ("code" if m["has_code"] else "template"),
            "has_template": m["has_template"],
            "has_code": m["has_code"],
            "template_id": ("plugin_" + pid) if m["has_template"] else "",
            "enabled": m["enabled"],
            "trusted": m["trusted"],
            "status": st,
            "error": (loaded.get("error") or "") if m["has_code"] else "",
            "tools": [{"name": t["name"], "label": t["label"], "where": t["where"], "hint": t["hint"]}
                      for t in (ctx.tools if ctx else [])],
            "routes": [{"path": str(r["path"]).strip("/"), "methods": r["methods"]}
                       for r in (ctx.routes if ctx else [])],
            "hooks": sorted((ctx.hooks or {}).keys()) if ctx else [],
            "settings": m["settings"],
            "values": vals,
            "params": len(m["params"]),
            "examples": m["examples"][:3],
            "web": (web_assets(m) if m["enabled"] and (m["trusted"] or not m["has_code"]) else {}),
        })
    return {"dir": str(plugins_dir()), "plugins": out}


# ---------------------------------------------------------------- 运行时调用
def run_tool(pid, tool_name, payload):
    """调用插件注册的工具。返回 {ok, text, note}。"""
    cfg = settings.load_config()
    ensure_loaded(cfg)
    r = _LOADED.get(pid)
    if not r or not r.get("ctx"):
        return {"ok": False, "error": "插件未加载（未启用 / 未信任 / 加载失败）"}
    ctx = r["ctx"]
    for t in ctx.tools:
        if t["name"] == tool_name:
            try:
                res = t["fn"](str(payload.get("text") or ""), {
                    "settings": ctx.settings,
                    "params": payload.get("params") or {},
                    "template": payload.get("template") or "",
                    "images": int(payload.get("images") or 0),
                    "pyqt_note": "",
                })
            except Exception:
                err = traceback.format_exc(limit=6)
                _log(pid, "工具 %s 执行失败：\n%s" % (tool_name, err))
                return {"ok": False, "error": err.strip().splitlines()[-1]}
            if isinstance(res, str):
                return {"ok": True, "text": res, "note": ""}
            if isinstance(res, dict):
                return {"ok": True, "text": str(res.get("text") or ""),
                        "note": str(res.get("note") or "")}
            return {"ok": False, "error": "工具返回值必须是字符串或 {text, note}"}
    return {"ok": False, "error": "没有这个工具：%s" % tool_name}


def call_route(pid, sub_path, body, query):
    """分发插件自定义接口。返回 (handled, result)。"""
    cfg = settings.load_config()
    ensure_loaded(cfg)
    r = _LOADED.get(pid)
    if not r or not r.get("ctx"):
        return False, {"ok": False, "error": "插件未加载"}
    want = "/" + str(sub_path or "").strip("/")
    for rt in r["ctx"].routes:
        if rt["path"] == want:
            try:
                res = rt["fn"](body or {}, query or {})
            except Exception:
                err = traceback.format_exc(limit=6)
                _log(pid, "接口 %s 执行失败：\n%s" % (want, err))
                return True, {"ok": False, "error": err.strip().splitlines()[-1]}
            if isinstance(res, dict) and isinstance(res.get("_raw"), dict):
                raw = res["_raw"]
                return True, {"_raw": {"mime": raw.get("mime") or "application/octet-stream",
                                      "data": raw.get("data") or b""}}
            return True, (res if isinstance(res, dict) else {"ok": True, "result": res})
    return False, {"ok": False, "error": "插件没有这个接口：%s" % want}


def apply_hooks(event, payload):
    """跑生成后钩子；有插件改写了输出就返回新文本，没人改就返回 None。"""
    cfg = settings.load_config()
    ensure_loaded(cfg)
    orig = payload.get("output") or ""
    text = orig
    for pid, r in list(_LOADED.items()):
        ctx = r.get("ctx")
        if not ctx:
            continue
        for fn in (ctx.hooks.get(event) or []):
            try:
                res = fn(dict(payload, output=text))
            except Exception:
                _log(pid, "钩子 %s 执行失败：\n%s" % (event, traceback.format_exc(limit=6)))
                continue
            if isinstance(res, str) and res.strip():
                text = res
            elif isinstance(res, dict) and isinstance(res.get("output"), str):
                text = res["output"]
    return None if text == orig else text


# ---------------------------------------------------------------- 安装 / 删除
def install_zip(raw_bytes, name_hint=""):
    """从 zip 安装插件到 plugins/。返回 {ok, id, dir, error}。"""
    ensure_dir()
    tmp = settings.data_dir() / "_install_tmp"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(raw_bytes)) as z:
            for info in z.infolist():
                n = info.filename.replace("\\", "/")
                if n.startswith("/") or ".." in n.split("/"):
                    return {"ok": False, "error": "压缩包里有非法路径：%s" % n}
            z.extractall(tmp)
    except Exception as e:
        return {"ok": False, "error": "不是有效的 zip：%s" % e}
    # 找到含 plugin.json 的目录（可能在压缩包根，也可能套了一层）
    root = None
    for name in MANIFEST_NAMES:
        if (tmp / name).is_file():
            root = tmp
            break
    if root is None:
        subs = [p for p in tmp.iterdir() if p.is_dir()]
        if len(subs) == 1:
            for name in MANIFEST_NAMES:
                if (subs[0] / name).is_file():
                    root = subs[0]
                    break
        if root is None:
            for p in tmp.rglob("*"):
                if p.is_file() and p.name in MANIFEST_NAMES:
                    root = p.parent
                    break
    if root is None:
        return {"ok": False, "error": "压缩包里找不到 plugin.json"}
    meta, err = _parse_manifest(str(root), True)
    if err:
        return {"ok": False, "error": err}
    target = plugins_dir() / _slug(meta.get("id") or name_hint or os.path.basename(meta["dir"]))
    if target.exists():
        return {"ok": False, "error": "插件目录已存在：%s（先删掉或改名）" % target.name}
    shutil.copytree(root, target)
    shutil.rmtree(tmp, ignore_errors=True)
    ensure_loaded(settings.load_config(), force=True)
    return {"ok": True, "id": meta["id"], "dir": target.name}


def delete_plugin(pid):
    cfg = settings.load_config()
    for item in scan_all(cfg):
        if "error" in item:
            continue
        if item["meta"]["id"] == pid:
            d = item["meta"]["dir"]
            try:
                if os.path.isdir(d):
                    shutil.rmtree(d)
                else:
                    os.remove(d)
            except Exception as e:
                return {"ok": False, "error": "删除失败：%s" % e}
            _LOADED.pop(pid, None)
            return {"ok": True}
    return {"ok": False, "error": "没有这个插件"}


def reveal():
    d = ensure_dir()
    try:
        os.startfile(str(d))  # noqa: 只在 Windows 下用
        return {"ok": True, "dir": str(d)}
    except Exception as e:
        return {"ok": False, "error": str(e), "dir": str(d)}
