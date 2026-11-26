"""提示词工作台 · 本地服务入口。

运行方式：
  开发态   python src/app.py
  打包后   双击 PromptStudio.exe（自动打开浏览器）
"""
from __future__ import annotations

import atexit
import socket
import os
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser

from flask import Flask, jsonify, request, send_file, send_from_directory

import llm
import localsrv
import pluginlib
import registry
import runtimes
import settings

ROOT = settings.resource_root()
STATIC_DIR = ROOT / "static"

# 桌面窗口模式下没有控制台：stdout/stderr 为 None 时兜到 data\run.log，
# 避免 print() 抛 AttributeError，同时方便排查启动问题。
if sys.stdout is None or sys.stderr is None:
    try:
        _logf = open(str(settings.data_dir() / "run.log"), "a", encoding="utf-8", buffering=1)
    except Exception:
        _logf = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _logf
    if sys.stderr is None:
        sys.stderr = _logf

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
app.config["JSON_AS_ASCII"] = False


def json_ok(payload: dict) -> tuple:
    return jsonify(payload)


# --------------------------------------------------------------------------- 页面


@app.get("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.get("/static/<path:rel>")
def static_files(rel: str):
    return send_from_directory(str(STATIC_DIR), rel)


@app.get("/favicon.ico")
def favicon():
    return ("", 204)


# --------------------------------------------------------------------------- 状态


@app.get("/api/state")
def api_state():
    cfg = settings.load_config()
    return json_ok(
        {
            "providers": [settings.public_provider(p) for p in cfg["providers"]],
            "active_provider": cfg["active_provider"],
            "template": cfg["template"],
            "fast": cfg["fast"],
            "port": cfg["port"],
            "templates": registry.catalog(),
            "presets": settings.PRESETS,
            "specs": registry.template_stats(),
            "config_path": str(settings.CONFIG_PATH),
            "publisher": settings.PUBLISHER,
            "version": settings.APP_VERSION,
        }
    )


# --------------------------------------------------------------------------- 配置


@app.post("/api/provider/save")
def api_provider_save():
    body = request.get_json(force=True, silent=True) or {}
    cfg = settings.load_config()
    p = body.get("provider") or {}
    pid = p.get("id")
    found = None
    for item in cfg["providers"]:
        if item["id"] == pid:
            found = item
            break
    if found:
        # api_key 为空字符串表示"沿用已存 key"，None/缺失表示清空
        merged = dict(found)
        for k in ("name", "base_url", "model", "note", "extra_json"):
            if k in p:
                merged[k] = str(p[k])
        if "api_key" in p:
            merged["api_key"] = str(p.get("api_key") or "")
        if "vision" in p:
            merged["vision"] = bool(p["vision"])
        if "temperature" in p:
            merged["temperature"] = float(p["temperature"])
        if "max_tokens" in p:
            merged["max_tokens"] = int(p["max_tokens"])
        if not merged["api_key"]:
            merged["api_key"] = found["api_key"]
        cfg["providers"] = [merged if x["id"] == pid else x for x in cfg["providers"]]
    else:
        new = settings._clean_provider(p)
        new["api_key"] = str(p.get("api_key") or "")
        cfg["providers"].append(new)
    settings.save_config(cfg)
    return json_ok(
        {
            "ok": True,
            "providers": [settings.public_provider(x) for x in cfg["providers"]],
        }
    )


@app.post("/api/provider/delete")
def api_provider_delete():
    body = request.get_json(force=True, silent=True) or {}
    pid = body.get("id")
    cfg = settings.load_config()
    cfg["providers"] = [x for x in cfg["providers"] if x["id"] != pid]
    if cfg["providers"] and not any(x["id"] == cfg["active_provider"] for x in cfg["providers"]):
        cfg["active_provider"] = cfg["providers"][0]["id"]
    settings.save_config(cfg)
    return json_ok({"ok": True, "providers": [settings.public_provider(x) for x in cfg["providers"]]})


@app.post("/api/provider/activate")
def api_provider_activate():
    body = request.get_json(force=True, silent=True) or {}
    cfg = settings.load_config()
    cfg["active_provider"] = body.get("id") or cfg["active_provider"]
    cfg["fast"] = bool(body.get("fast", cfg["fast"]))
    if body.get("template"):
        cfg["template"] = body["template"]
    if body.get("port"):
        cfg["port"] = int(body["port"])
    settings.save_config(cfg)
    return json_ok({"ok": True, "active_provider": cfg["active_provider"], "fast": cfg["fast"]})


@app.post("/api/provider/test")
def api_provider_test():
    body = request.get_json(force=True, silent=True) or {}
    cfg = settings.load_config()
    p = settings.get_provider(cfg, body.get("id"))
    if body.get("base_url"):
        p = dict(p or {})
        p["base_url"] = body.get("base_url") or ""
        p["api_key"] = body.get("api_key") if body.get("api_key") else (p or {}).get("api_key", "")
        p["model"] = body.get("model") or (p or {}).get("model", "")
    if not p:
        return json_ok({"ok": False, "error": "没有这个 provider"})
    try:
        res = llm.chat(p, system="You are a health check.", user_text="Reply with exactly: OK",
                       fast=True, temperature=0.0, max_tokens=32)
    except Exception as exc:  # 任何异常都转成前端可读的 JSON
        return json_ok({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})
    return json_ok(res)


# --------------------------------------------------------------------------- 生成


@app.post("/api/generate")
def api_generate():
    body = request.get_json(force=True, silent=True) or {}
    cfg = settings.load_config()
    tid = body.get("template") or cfg["template"]
    tpl = registry.get_template(tid)
    if not tpl:
        return json_ok({"ok": False, "error": "未知模板"})
    content = (body.get("content") or "").strip()
    if not content:
        return json_ok({"ok": False, "error": "内容描述为空"})
    images = body.get("images") or []
    # 前端发的是 data_url；脚本/第三方调用可能用 data，两种都收
    for _im in images:
        if isinstance(_im, dict) and not _im.get("data_url") and _im.get("data"):
            _im["data_url"] = _im["data"]
    images = [i for i in images if isinstance(i, dict) and i.get("data_url")][: int(tpl.get("max_images", 4))]
    if len(content) < 4:
        return json_ok({"ok": False, "error": "内容太短（至少 4 个字）"})
    if int(tpl.get("min_images", 0)) > 0 and not images:
        return json_ok(
            {
                "ok": False,
                "error": "该模板要求至少上传 1 张参考图（图生图类任务必须喂原图）。",
            }
        )

    p = settings.get_provider(cfg, body.get("provider"))
    if not p:
        return json_ok({"ok": False, "error": "还没有可用的 API 配置，请先到「设置」页添加。"})
    if (body.get("provider") or "") and body["provider"] != cfg.get("active_provider"):
        p = settings.get_provider(cfg, body["provider"])

    fast = bool(body.get("fast", cfg.get("fast", True)))
    if images and not p.get("vision"):
        # 无视觉能力的模型不喂图，只把图片编号写进文字清单
        images_text = "\n".join(
            [f"第 {i} 张 = <image{i}> 角色：{(im.get('role') or '参考图')}" for i, im in enumerate(images, 1)]
        )
        content = (
            content
            + "\n\n（注意：本服务无视觉输入能力，以下图片仅作为编号占位供提示词引用，"
            + "不要臆想图片内容；请把与图片相关的描述写成由用户提供的文字。）\n"
            + images_text
        )
        images = []

    params = dict(body.get("params") or {})
    params["content"] = content
    try:
        built = registry.build(tid, params, images, fast)
    except Exception as exc:  # 拼装异常不应整包崩
        return json_ok({"ok": False, "error": f"模板拼装失败：{exc}"})

    # 内置本地模型：按需加载 → 生成（含 H3 格式修复）→ 自动卸载，把显存还给系统
    local_auto, local_err = _local_auto_load(cfg, p)
    if local_err:
        return json_ok({"ok": False, "error": local_err})
    try:
        res = llm.chat(
            p,
            system=built["system"],
            user_text=built["user"],
            images=images,
            fast=fast,
            expect_json=bool(built.get("expect_json")),
        )
        if not res.get("ok"):
            return json_ok(res)

        repair_note = ""
        if tid == "h3_video":
            fixed, repair_note = _repair_h3(p, res.get("content") or "", fast)
            if fixed:
                res["content"] = fixed
    finally:
        _local_auto_unload(local_auto)

    parsed = llm.extract_json(res["content"]) if built.get("expect_json") else None

    # 插件钩子：generate.after 可以改写最终输出（只对启用+已信任的插件生效）
    hook_note = ""
    try:
        cfg_now = settings.load_config()
        hooked = pluginlib.apply_hooks(
            "generate.after",
            {
                "template": tid,
                "content": content,
                "output": res["content"],
                "json": parsed,
                "params": params,
                "settings": cfg_now,
            },
        )
        if hooked is not None and hooked != res["content"]:
            res["content"] = hooked
            hook_note = "已应用插件后处理。"
            if built.get("expect_json"):
                parsed = llm.extract_json(hooked)
    except Exception as exc:
        hook_note = "插件后处理出错：%s: %s" % (type(exc).__name__, exc)

    settings.append_history(
        {
            "id": uuid.uuid4().hex[:10],
            "template": tid,
            "label": built["label"],
            "model": p.get("model"),
            "provider": p.get("name"),
            "params": {k: v for k, v in params.items() if k != "content" and len(str(v)) < 200},
            "input": content[:600],
            "output": res["content"][:6000],
            "images": len(images),
            "usage": res.get("usage") or {},
        }
    )
    out = dict(res)
    out["json"] = parsed
    if repair_note:
        out["note"] = (out.get("note") or "") + repair_note
    if hook_note:
        out["note"] = (out.get("note") or "") + hook_note
    out["system_chars"] = len(built["system"])
    out["user_chars"] = len(built["user"])
    out["template"] = tid
    out["label"] = built["label"]
    out["provider_name"] = p.get("name")
    out["model"] = p.get("model")
    return json_ok(out)


H3_FIELDS = ("subject_definitions", "summary", "detailed_description",
             "overall_soundscape", "non_diegetic_music")


def _h3_missing(text: str) -> list:
    """小模型常见的格式漏项：六段字段名、[Shot N] 时间码、台词 <d> 标签。"""
    miss = [f for f in H3_FIELDS if f not in text]
    if "[Shot 1]" not in text:
        miss.append("[Shot 1] 时间码")
    has_dialogue = any(k in text for k in ("“", "”", "说道", "开口", "台词"))
    if has_dialogue and "<d>" not in text:
        miss.append("台词标签 <d>")
    return miss


def _repair_h3(p: dict, text: str, fast: bool):
    """对 H3 输出做一次格式修补（只补格式不改内容）。修补有效才采用。"""
    miss = _h3_missing(text)
    if not miss or not text.strip():
        return None, ""
    prompt = (
        "下面这份 MiniMax H3 提示词缺少：%s。\n"
        "请只补齐这些格式项，不要改写已有内容：\n"
        "- 六段字段名必须用英文（subject_definitions / summary / retention_analysis / "
        "detailed_description / overall_soundscape / non_diegetic_music），retention_analysis 没有内容就写 N/A；\n"
        "- 镜头段落以 [Shot 1] 00:00.000 开头；\n"
        "- 台词必须写成 `身份短语 (S1) 动作与语气：<d>[Chinese] 台词原文</d>`，不要用中文引号转述台词。\n"
        "只输出修补后的完整提示词，不要解释。\n\n%s" % ("、".join(miss), text)
    )
    fix = llm.chat(
        p,
        system="你是 MiniMax H3 提示词的格式校对器。只做格式修补，不改写内容，只输出修补后的完整提示词。",
        user_text=prompt,
        fast=fast,
        temperature=0.2,
    )
    if not fix.get("ok"):
        return None, ""
    new_text = (fix.get("content") or "").strip()
    if not new_text:
        return None, ""
    after = _h3_missing(new_text)
    if len(after) >= len(miss):
        return None, ""
    note = "已自动补齐格式：%s" % "、".join([m for m in miss if m not in after])
    return new_text, note


@app.post("/api/debug/payload")
def api_debug_payload():
    """预览当前拼装出来的 system / user 全文（不计费、不调模型）。"""
    body = request.get_json(force=True, silent=True) or {}
    tid = body.get("template")
    params = dict(body.get("params") or {})
    params["content"] = body.get("content") or ""
    images = [i for i in (body.get("images") or []) if isinstance(i, dict)]
    for i, im in enumerate(images):
        im["data_url"] = ""  # 预览不需要 base64
    try:
        built = registry.build(tid, params, images, bool(body.get("fast", True)))
    except Exception as exc:
        return json_ok({"ok": False, "error": str(exc)})
    return json_ok(
        {
            "ok": True,
            "system": built["system"],
            "user": built["user"],
            "system_chars": len(built["system"]),
            "expect_json": built.get("expect_json", False),
        }
    )


@app.get("/api/history")
def api_history():
    return json_ok({"ok": True, "history": settings.load_history()})


@app.post("/api/history/clear")
def api_history_clear():
    settings.clear_history()
    return json_ok({"ok": True, "history": []})


# --------------------------------------------------------------------------- 本地模型
# gemma-4-e2b 三件套由本程序托管：启动时自动拉起 llama-server，退出时杀掉；
# 模型文件不进 exe（2.96GB + 940MB + 93MB），只引用外部路径。

LOCAL_LOG = "llama.log"
_LOCAL_OWNED: dict = {"pid": None, "port": None}


def _local_cfg(cfg: dict) -> dict:
    return localsrv.normalize(cfg.get("local") or {})


def _local_log_path() -> str:
    return str(settings.data_dir() / LOCAL_LOG)


def _ensure_local_provider(cfg: dict, c: dict) -> dict | None:
    """把内置本地模型登记（或刷新）到 providers 里，供前端直接选用。"""
    pid = localsrv.PROV_ID
    ent = {
        "id": pid,
        "name": "本机模型 · gemma-4-e2b（内置）",
        "base_url": "http://127.0.0.1:%d/v1" % int(c["port"]),
        "api_key": "local",
        "model": str(c["alias"]),
        "vision": True,
        "temperature": 0.6,
        "max_tokens": 4096,
        "extra_json": "",
        "note": "由程序托管的 llama.cpp：主模型 + 视觉投影"
                + (" + MTP 草稿" if c.get("use_mtp") else "") + "，免 key",
    }
    replaced = False
    for i, p in enumerate(cfg["providers"]):
        if p.get("id") == pid:
            ent["api_key"] = p.get("api_key") or "local"
            cfg["providers"][i] = settings._clean_provider(ent)
            replaced = True
            break
    if not replaced:
        cfg["providers"].append(settings._clean_provider(ent))

    # 首次开箱：当前选中的服务没有 key（例如默认是云端 DeepSeek 但没填），
    # 就默认切到内置本地模型，保证打开就能用、不需要配置。
    act = settings.get_provider(cfg, cfg.get("active_provider"))
    if not act or not (act.get("api_key") or "").strip() or act.get("id") == pid:
        cfg["active_provider"] = pid
    settings.save_config(cfg)
    return settings.get_provider(cfg, pid)


def _merge_local(body: dict, cfg: dict) -> dict:
    incoming = body.get("local") or body.get("config") or {}
    return localsrv.normalize({**(cfg.get("local") or {}), **incoming})


def _local_auto_load(cfg: dict, p: dict):
    """生成前按需拉起内置本地模型。返回 (用完要卸载的配置 or None, 错误说明)。

    只在三件事同时成立时生效：用的是内置本地服务、用户没自己启动它、开了「生成完自动卸载」。
    用户手动点过「启动服务」就尊重他的静止状态——不替他关掉，也不重复起。
    """
    if not p or p.get("id") != localsrv.PROV_ID:
        return None, ""
    c = _local_cfg(cfg)
    if not c.get("enabled") or not c.get("auto_unload"):
        return None, ""
    port = int(c["port"])
    if localsrv.probe(port, 1.0):
        return None, ""                      # 已经在跑，多半是用户自己开的
    try:
        res = localsrv.start(c, _local_log_path())
    except Exception as exc:
        return None, "本地模型启动失败：%s: %s" % (type(exc).__name__, exc)
    if not res.get("ok"):
        return None, res.get("error") or "本地模型启动失败"
    _LOCAL_OWNED["pid"] = res.get("pid")
    _LOCAL_OWNED["port"] = res.get("port")
    if not localsrv.wait_ready(port, None, int(c.get("ready_timeout") or 240)):
        localsrv.stop(res.get("pid"))
        _LOCAL_OWNED["pid"] = None
        return None, "本地模型启动超时（%s 秒内没就绪），详细日志见 data\\%s" % (
            c.get("ready_timeout") or 240, LOCAL_LOG)
    return c, ""


def _local_auto_unload(c) -> None:
    """生成结束就把按需拉起的本地模型关掉，把显存让出来。"""
    if not c:
        return
    try:
        pid = localsrv.running_pid(int(c["port"]))
        localsrv.stop(pid if pid and pid > 0 else _LOCAL_OWNED.get("pid"))
    except Exception:
        pass
    finally:
        _LOCAL_OWNED["pid"] = None


@app.get("/api/local/status")
def api_local_status():
    cfg = settings.load_config()
    c = _local_cfg(cfg)
    st = localsrv.status(c)
    st["provider_id"] = localsrv.PROV_ID
    return json_ok(st)


@app.get("/api/ui/theme")
def api_ui_theme_get():
    cfg = settings.load_config()
    return json_ok({"ok": True, "theme": cfg.get("ui_theme") or "dark"})


@app.post("/api/ui/theme")
def api_ui_theme_set():
    body = request.get_json(force=True, silent=True) or {}
    t = (body.get("theme") or "").strip()
    if t not in ("dark", "light"):
        return json_ok({"ok": False, "error": "theme 只能是 dark 或 light"})
    cfg = settings.load_config()
    cfg["ui_theme"] = t
    settings.save_config(cfg)
    return json_ok({"ok": True, "theme": t})


@app.post("/api/local/save")
def api_local_save():
    body = request.get_json(force=True, silent=True) or {}
    cfg = settings.load_config()
    c = _merge_local(body, cfg)
    cfg["local"] = c
    settings.save_config(cfg)
    return json_ok({"ok": True, "local": c})


@app.post("/api/local/browse")
def api_local_browse():
    """弹系统选择框（网页版兜底）。

    桌面版里前端优先调 Qt 桥（psApp.pickPath），不走这里；
    浏览器里退到后端 tkinter——个别环境弹不出来就提示手填。
    """
    body = request.get_json(silent=True) or {}
    mode = str(body.get("mode") or "file")
    title = str(body.get("title") or "选择")
    filt = str(body.get("filter") or "")
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        if mode == "dir":
            p = filedialog.askdirectory(title=title)
        else:
            types = [("所有文件", "*.*")]
            if "gguf" in filt.lower():
                types = [("GGUF 模型", "*.gguf"), ("所有文件", "*.*")]
            p = filedialog.askopenfilename(title=title, filetypes=types)
        root.destroy()
        return json_ok({"ok": bool(p), "path": p or ""})
    except Exception as e:  # noqa: BLE001
        return json_ok({"ok": False, "error": "这个环境弹不出选择框（%s）。可以直接把路径粘到输入框里。" % e})


@app.post("/api/local/start")
def api_local_start():
    body = request.get_json(force=True, silent=True) or {}
    cfg = settings.load_config()
    c = _merge_local(body, cfg)
    cfg["local"] = c
    settings.save_config(cfg)
    try:
        res = localsrv.start(c, _local_log_path())
    except Exception as exc:
        return json_ok({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})
    if not res.get("ok"):
        return json_ok(res)
    _LOCAL_OWNED["pid"] = res.get("pid")
    _LOCAL_OWNED["port"] = res.get("port")
    prov = _ensure_local_provider(cfg, c)
    res["provider"] = settings.public_provider(prov) if prov else None
    return json_ok(res)


@app.post("/api/local/stop")
def api_local_stop():
    cfg = settings.load_config()
    c = _local_cfg(cfg)
    pid = localsrv.running_pid(int(c["port"]))
    res = localsrv.stop(pid if pid else _LOCAL_OWNED.get("pid"))
    if res.get("ok"):
        _LOCAL_OWNED["pid"] = None
    return json_ok(res)


@app.get("/api/runtime/status")
def api_runtime_status():
    """运行环境（llama.cpp 预编译包）状态：本机系统/架构/显卡 + 各包是否已装。"""
    try:
        return json_ok(runtimes.status())
    except Exception as exc:
        return json_ok({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})


@app.post("/api/runtime/install")
def api_runtime_install():
    """安装指定运行环境包（不传 id 就按硬件选最合适的）。"""
    body = request.get_json(force=True, silent=True) or {}
    pid = str(body.get("id") or "").strip()
    if not pid:
        st = runtimes.status()
        pid = st.get("preferred") or ""
    if not pid:
        return json_ok({"ok": False, "error": "本机没有对应的运行环境包（只支持 Windows）。"})
    try:
        r = runtimes.install(pid)
    except Exception as exc:
        return json_ok({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})
    if r.get("ok"):
        r["verify"] = runtimes.verify(pid)
    return json_ok(r)


def _autostart_local() -> None:
    """启动时把本地模型拉起来（后台线程，不阻塞浏览器打开）。"""
    try:
        cfg = settings.load_config()
        c = _local_cfg(cfg)
        if not (c.get("enabled") and c.get("auto")):
            return
        # 开了「用时加载、生成完自动卸载」就不常驻：第一次生成时再拉起来，省显存
        if c.get("auto_unload"):
            print("  本地模型：按需加载模式（生成时拉起、结束即卸载），启动时不常驻", flush=True)
            _ensure_local_provider(cfg, c)      # 先把服务登记好，选它就能用
            return
        if not os.path.isfile(str(c.get("model") or "")):
            print("  本地模型：未找到模型文件，跳过自动启动（%s）" % c.get("model"), flush=True)
            return
        # 运行环境：随包分发的 llama.cpp 预编译包按硬件自动解压安装
        if not localsrv.find_exe_ok():
            print("  运行环境：正在按硬件安装 llama.cpp（首次约 10–60 秒）…", flush=True)
            r = runtimes.ensure()
            if not r.get("ok"):
                print("  运行环境安装失败：%s" % r.get("error"), flush=True)
                return
            print("  运行环境：已就绪（%s → %s）" % (r.get("pack"), r.get("exe")), flush=True)
        res = localsrv.start(c, _local_log_path())
        if res.get("ok"):
            _LOCAL_OWNED["pid"] = res.get("pid")
            _LOCAL_OWNED["port"] = res.get("port")
            _ensure_local_provider(settings.load_config(), c)
            print("  本地模型：%s（端口 %s，模型 %s）" % (
                res.get("note"), res.get("port"), c.get("alias")), flush=True)
        else:
            print("  本地模型启动失败：%s" % res.get("error"), flush=True)
    except Exception as exc:
        print("  本地模型启动异常：%s: %s" % (type(exc).__name__, exc), flush=True)


def _stop_owned_local() -> None:
    pid = _LOCAL_OWNED.get("pid")
    if pid:
        try:
            localsrv.stop(pid)
        except Exception:
            pass


def _open_browser_when_ready(url: str, timeout: float = 40.0) -> None:
    """等本地服务真的能返回 200 再打开浏览器，避免只打开一个连不上的页面。"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.35)
    try:
        ok = webbrowser.open(url)
        print("  已打开浏览器：%s" % url if ok else "  浏览器未接受打开请求，请手动访问 %s" % url,
              flush=True)
    except Exception as exc:
        print("  自动打开浏览器失败：%s（请手动访问 %s）" % (exc, url), flush=True)


# --------------------------------------------------------------------------- 规范管理


@app.get("/api/spec")
def api_spec():
    """内置规范组件清单（含启停/替换状态）+ 用户自定义规范。"""
    st = settings.load_specs()
    out = []
    for t in registry.TEMPLATES:
        tid = t["id"]
        comps = []
        for f in registry.COMPONENTS.get(tid, []):
            ent = st["files"].get(f) or {}
            txt = registry.file_text(f)
            comps.append(
                {
                    "name": f,
                    "bytes": len(txt.encode("utf-8")),
                    "enabled": bool(ent.get("enabled", True)),
                    "replaced": bool((ent.get("replace") or "").strip()),
                    "replace_chars": len((ent.get("replace") or "").strip()),
                }
            )
        out.append(
            {
                "id": tid,
                "label": t["label"],
                "components": comps,
                "extra": [e for e in st["extra"] if e["template"] == tid],
            }
        )
    return json_ok({"ok": True, "templates": out})


@app.post("/api/spec/save")
def api_spec_save():
    """新增/更新一条用户自定义规范。body: {spec:{id?,template,name,text,enabled}}"""
    body = request.get_json(force=True, silent=True) or {}
    s = body.get("spec") or {}
    tid = str(s.get("template") or "")
    if not registry.get_template(tid):
        return json_ok({"ok": False, "error": "模板不存在：" + tid})
    if not (s.get("text") or "").strip():
        return json_ok({"ok": False, "error": "规范正文为空"})
    st = settings.load_specs()
    sid = str(s.get("id") or "")
    item = {
        "id": sid or uuid.uuid4().hex[:10],
        "template": tid,
        "name": str(s.get("name") or "自定义规范").strip()[:60],
        "text": str(s.get("text") or "").strip(),
        "enabled": bool(s.get("enabled", True)),
    }
    st["extra"] = [item if e["id"] == sid else e for e in st["extra"]]
    if not any(e["id"] == sid for e in st["extra"]):
        st["extra"].append(item)
    st = settings.save_specs(st)
    return json_ok({"ok": True, "extra": [e for e in st["extra"] if e["template"] == tid]})


@app.post("/api/spec/delete")
def api_spec_delete():
    body = request.get_json(force=True, silent=True) or {}
    sid = str(body.get("id") or "")
    st = settings.load_specs()
    st["extra"] = [e for e in st["extra"] if e["id"] != sid]
    st = settings.save_specs(st)
    return json_ok({"ok": True, "extra": st["extra"]})


@app.post("/api/spec/toggle")
def api_spec_toggle():
    """body: {name: 内置规范文件名, enabled: bool} 或 {id: 自定义规范id, enabled: bool}"""
    body = request.get_json(force=True, silent=True) or {}
    st = settings.load_specs()
    name = str(body.get("name") or "")
    sid = str(body.get("id") or "")
    enabled = bool(body.get("enabled", True))
    if name:
        cur = st["files"].get(name) or {"enabled": True, "replace": ""}
        cur["enabled"] = enabled
        st["files"][name] = cur
    elif sid:
        st["extra"] = [
            {**e, "enabled": enabled} if e["id"] == sid else e for e in st["extra"]
        ]
    else:
        return json_ok({"ok": False, "error": "缺少 name 或 id"})
    settings.save_specs(st)
    return json_ok({"ok": True})


@app.post("/api/spec/replace")
def api_spec_replace():
    """用用户文本替换内置规范正文；replace 为空串＝恢复内置原文。body: {name, replace}"""
    body = request.get_json(force=True, silent=True) or {}
    name = str(body.get("name") or "")
    rep = str(body.get("replace") or "")
    known = {f for lst in registry.COMPONENTS.values() for f in lst}
    if name not in known:
        return json_ok({"ok": False, "error": "未知规范文件：" + name})
    st = settings.load_specs()
    cur = st["files"].get(name) or {"enabled": True, "replace": ""}
    cur["replace"] = rep.strip()
    if cur["replace"]:
        cur["enabled"] = True
    st["files"][name] = cur
    settings.save_specs(st)
    return json_ok({"ok": True, "replaced": bool(cur["replace"])})


@app.post("/api/spec/reset")
def api_spec_reset():
    """恢复默认：所有内置规范启用、清除替换文本与自定义规范。"""
    settings.save_specs({"files": {}, "extra": []})
    return json_ok({"ok": True})


@app.get("/api/spec/content")
def api_spec_content():
    """查看某内置规范当前生效正文（内置原文或用户替换文本）。?name=xxx"""
    name = str(request.args.get("name") or "")
    return json_ok({"ok": True, "name": name, "text": registry.effective_text(name)})


# --------------------------------------------------------------------------- 插件


def _plugins_payload(cfg=None) -> dict:
    cfg = cfg or settings.load_config()
    try:
        info = pluginlib.status(cfg)
    except Exception as exc:
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
                "dir": str(pluginlib.plugins_dir()), "plugins": [], "ids": [], "count": 0}
    try:
        tmpl = pluginlib.scan(cfg)
        tpl_ids = [t["id"] for t in (tmpl.get("templates") or [])]
        errors = tmpl.get("errors") or []
    except Exception:
        tpl_ids, errors = [], []
    return {
        "ok": True,
        "dir": info["dir"],
        "plugins": info["plugins"],
        "ids": tpl_ids,
        "count": len(tpl_ids),
        "errors": errors,
    }


@app.get("/api/plugins")
def api_plugins():
    """插件清单与状态（每次现扫目录，丢进去即生效；代码插件按信任名单加载）。"""
    return json_ok(_plugins_payload())


@app.post("/api/plugins/reload")
def api_plugins_reload():
    """重新加载：重扫目录并重新执行已信任插件的 register()。"""
    try:
        pluginlib.ensure_loaded(settings.load_config(), force=True)
    except Exception as exc:
        return json_ok({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})
    return json_ok(_plugins_payload())


@app.post("/api/plugins/toggle")
def api_plugins_toggle():
    """启用/停用某个插件（只写 config.json，不改用户插件文件）。"""
    body = request.get_json(silent=True) or {}
    pid = str(body.get("id") or "").strip()
    if not pid:
        return json_ok({"ok": False, "error": "缺少插件 id"})
    enabled = bool(body.get("enabled", True))
    cfg = settings.load_config()
    off = [x for x in (cfg.get("plugins_off") or []) if x != pid]
    if not enabled:
        off.append(pid)
    cfg["plugins_off"] = off
    settings.save_config(cfg)
    pluginlib.ensure_loaded(settings.load_config(), force=True)
    return json_ok(_plugins_payload())


@app.post("/api/plugins/trust")
def api_plugins_trust():
    """信任/取消信任某个代码插件（信任后才会执行它的 plugin.py）。"""
    body = request.get_json(silent=True) or {}
    pid = str(body.get("id") or "").strip()
    if not pid:
        return json_ok({"ok": False, "error": "缺少插件 id"})
    trusted = bool(body.get("trusted", True))
    cfg = settings.load_config()
    trust = dict(cfg.get("plugin_trust") or {})
    if trusted:
        trust[pid] = True
    else:
        trust.pop(pid, None)
    cfg["plugin_trust"] = trust
    settings.save_config(cfg)
    pluginlib.ensure_loaded(settings.load_config(), force=True)
    return json_ok(_plugins_payload())


@app.post("/api/plugins/settings")
def api_plugins_settings():
    """保存某个插件的设置项（插件用 ctx.get(key) 读取）。"""
    body = request.get_json(silent=True) or {}
    pid = str(body.get("id") or "").strip()
    values = body.get("values") or {}
    if not pid or not isinstance(values, dict):
        return json_ok({"ok": False, "error": "参数不完整"})
    cfg = settings.load_config()
    store = dict(cfg.get("plugin_settings") or {})
    cur = dict(store.get(pid) or {})
    cur.update({str(k): v for k, v in values.items()})
    store[pid] = cur
    cfg["plugin_settings"] = store
    settings.save_config(cfg)
    pluginlib.ensure_loaded(settings.load_config(), force=True)
    return json_ok(_plugins_payload())


@app.post("/api/plugins/delete")
def api_plugins_delete():
    """删除插件目录（用户自己放进去的插件）。"""
    body = request.get_json(silent=True) or {}
    pid = str(body.get("id") or "").strip()
    r = pluginlib.delete_plugin(pid) if pid else {"ok": False, "error": "缺少插件 id"}
    payload = _plugins_payload()
    payload.update({"deleted": r})
    return json_ok(payload)


@app.post("/api/plugins/install")
def api_plugins_install():
    """从 zip 安装插件（设置页「安装插件」上传）。"""
    f = request.files.get("file")
    if f is None:
        return json_ok({"ok": False, "error": "没有收到文件"})
    raw = f.read()
    if len(raw) > 32 * 1024 * 1024:
        return json_ok({"ok": False, "error": "插件包太大（上限 32 MB）"})
    r = pluginlib.install_zip(raw, f.filename or "")
    payload = _plugins_payload()
    payload.update({"installed": r})
    return json_ok(payload)


@app.post("/api/plugins/reveal")
def api_plugins_reveal():
    """打开插件目录（资源管理器）。"""
    pluginlib.ensure_dir()
    ok = pluginlib.reveal()
    return json_ok({"ok": True, "opened": ok, "dir": str(pluginlib.plugins_dir())})


@app.post("/api/plugins/tool")
def api_plugins_tool():
    """调用插件注册的工具（结果区/输入框的按钮）。"""
    body = request.get_json(silent=True) or {}
    pid = str(body.get("id") or "").strip()
    tool = str(body.get("tool") or "").strip()
    if not pid or not tool:
        return json_ok({"ok": False, "error": "缺少插件 id 或工具名"})
    r = pluginlib.run_tool(pid, tool, body)
    r["ok"] = bool(r.get("ok"))
    return json_ok(r)


# ---- 用户自定义模型（提示词撰写页「＋ 添加模型」）
def _utpl_payload() -> dict:
    items = settings.load_user_templates()
    return {"ok": True, "templates": items, "count": len(items),
            "path": str(settings.USER_TPL_PATH)}


@app.get("/api/templates")
def api_templates():
    return json_ok(_utpl_payload())


@app.post("/api/templates/save")
def api_templates_save():
    """新增或修改一个自定义模型。body: {template: {...}}（id 为空=新建）。"""
    body = request.get_json(silent=True) or {}
    t = body.get("template") if isinstance(body.get("template"), dict) else body
    name = str(t.get("name") or "").strip()
    spec = str(t.get("spec") or "").strip()
    if not name:
        return json_ok({"ok": False, "error": "请填写模型名称"})
    if not spec:
        return json_ok({"ok": False, "error": "请填写规范正文（你在正文里写清楚要模型怎么写提示词）"})
    items = settings.load_user_templates()
    tid = str(t.get("id") or "").strip()
    if not tid:
        tid = "custom_" + uuid.uuid4().hex[:8]
    item = {
        "id": tid,
        "name": name,
        "tagline": str(t.get("tagline") or ""),
        "intro": str(t.get("intro") or ""),
        "spec": spec,
        "expect_json": bool(t.get("expect_json")),
        "min_images": t.get("min_images"),
        "max_images": t.get("max_images"),
        "params": t.get("params") or [],
        "examples": t.get("examples") or [],
        "enabled": bool(t.get("enabled", True)),
    }
    found = False
    for i, old in enumerate(items):
        if old.get("id") == tid:
            items[i] = item
            found = True
            break
    if not found:
        items.append(item)
    settings.save_user_templates(items)
    p = _utpl_payload()
    p["saved"] = tid
    return json_ok(p)


@app.post("/api/templates/delete")
def api_templates_delete():
    body = request.get_json(silent=True) or {}
    tid = str(body.get("id") or "").strip()
    items = [it for it in settings.load_user_templates() if it.get("id") != tid]
    settings.save_user_templates(items)
    return json_ok(_utpl_payload())


# --------------------------------------------------------------------------- 插件静态资源
@app.get("/api/plugin-static/<pid>/<path:rel>")
def api_plugin_static(pid, rel):
    """插件目录里的静态文件（面板 JS/CSS、图片等）。"""
    path = pluginlib.static_path(pid, rel)
    if not path:
        return json_ok({"ok": False, "error": "文件不存在"}), 404
    return send_file(path, max_age=0)


# --------------------------------------------------------------------------- 插件接口
@app.route("/api/plugin/<pid>/<path:sub>", methods=["GET", "POST"])
def api_plugin_route(pid, sub):
    """插件自定义接口：/api/plugin/<插件id>/<插件里声明的路径>。"""
    body = request.get_json(silent=True) or {}
    query = {k: v for k, v in request.args.items()}
    handled, res = pluginlib.call_route(pid, sub, body, query)
    if not handled:
        return json_ok({"ok": False, "error": res.get("error") or "插件没有这个接口"})
    raw = res.get("_raw") if isinstance(res, dict) else None
    if isinstance(raw, dict):
        # 插件返回二进制（图片 / 视频）：直接当文件流出，不做 base64
        from flask import Response
        data = raw.get("data") or b""
        ret = Response(data, mimetype=raw.get("mime") or "application/octet-stream")
        ret.headers["Cache-Control"] = "public, max-age=3600"
        return ret
    return json_ok(res)


# --------------------------------------------------------------------------- 启动


def free_port(preferred: int) -> int:
    for port in [preferred] + [preferred + i for i in range(1, 12)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            try:
                s.connect(("127.0.0.1", port))
            except OSError:
                return port
    return 0


def serve_in_thread(port: int) -> threading.Thread:
    """把 Flask 起在后台线程（桌面窗口模式下用，不再弹浏览器）。"""
    def run():
        try:
            app.run(host="127.0.0.1", port=port, threaded=True, debug=False,
                    use_reloader=False)
        finally:
            _stop_owned_local()

    th = threading.Thread(target=run, name="flask", daemon=True)
    th.start()
    return th


def wait_http(url: str, timeout: float = 40.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> None:
    """命令行/开发模式：起服务 + 自动开浏览器。桌面窗口走 desktop.py。"""
    cfg = settings.load_config()
    port = free_port(int(os.environ.get("PORT") or cfg.get("port") or 8760))
    url = f"http://127.0.0.1:{port}/"
    print("=" * 62)
    print("  提示词工作台 Prompt Studio")
    print(f"  本机地址：{url}")
    print(f"  配置与历史：{settings.data_dir()}")
    print("  关闭本窗口即退出程序。")
    print("=" * 62)

    atexit.register(_stop_owned_local)
    threading.Thread(target=_autostart_local, name="local-autostart", daemon=True).start()
    threading.Thread(target=_open_browser_when_ready, args=(url,), name="open-browser",
                     daemon=True).start()
    try:
        app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
    finally:
        _stop_owned_local()


if __name__ == "__main__":
    main()
