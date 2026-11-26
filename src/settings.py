"""配置与资源路径。

- 打包成 exe 后：配置与历史记录写在 exe 同目录的 data\\ 下（便携、可直接拷走）。
- 开发态：写在项目目录的 data\\ 下。
- 模板与前端资源在 resource_root()（PyInstaller 解包目录 _MEIPASS）。
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

# --------------------------------------------------------------------------- paths


def resource_root() -> Path:
    """只读资源（templates/ static/）所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def app_root() -> Path:
    """可写根目录：exe 所在目录（打包后）/ 项目目录（开发态）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    d = app_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = data_dir() / "config.json"
HISTORY_PATH = data_dir() / "history.json"
HISTORY_LIMIT = 200

# 发布信息（界面上显示「发布者：minut」；exe 文件属性另由 build\version_info.txt 控制）
PUBLISHER = "minut"
APP_VERSION = "1.1"
APP_NAME = "提示词工作台 Prompt Studio"

# --------------------------------------------------------------------------- presets

# 常用 OpenAI 兼容服务预设；api_key 一律留空，由用户在设置页自行填写。
PRESETS = [
    {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "vision": False,
        "note": "中文强、便宜；deepseek-chat 建议开「快速模式」(关闭思考)",
    },
    {
        "name": "本地 · LM Studio",
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "local-model",
        "vision": True,
        "note": "LM Studio 本地服务，默认端口 1234，无需 key",
    },
    {
        "name": "本地 · Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5vl:7b",
        "vision": True,
        "note": "Ollama 本地服务，默认端口 11434，无需 key",
    },
    {
        "name": "本地 · vLLM / 其它",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "your-model-name",
        "vision": True,
        "note": "vLLM、llama.cpp server、SGLang 等 OpenAI 兼容服务",
    },
    {
        "name": "OpenAI",
        "base_url": "https://api.openai.com",
        "model": "gpt-4.1-mini",
        "vision": True,
        "note": "需要海外网络",
    },
    {
        "name": "阿里云 · 通义 DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode",
        "model": "qwen-plus",
        "vision": True,
        "note": "qwen-vl-max 支持看图；qwen-plus 只看文字",
    },
]

DEFAULT_PROVIDERS = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "api_key": "",
        "model": "deepseek-chat",
        "vision": False,
        "temperature": 0.7,
        "max_tokens": 8000,
        "extra_json": "",
        "note": "中文强、便宜",
    },
    {
        "id": "local-lmstudio",
        "name": "本地 · LM Studio",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "local",
        "model": "local-model",
        "vision": True,
        "temperature": 0.7,
        "max_tokens": 8000,
        "extra_json": "",
        "note": "本地模型，免 key",
    },
]

DEFAULTS = {
    "providers": DEFAULT_PROVIDERS,
    "active_provider": "deepseek",
    "template": "h3_video",
    "fast": True,
    "port": 8760,
    "ui_theme": "dark",
    # 本地 llama.cpp 托管配置（字段含义见 src/localsrv.py 的 DEFAULT_LOCAL）
    "local": {},
    # 用户在界面里关掉的插件 id（不修改插件文件本身）
    "plugins_off": [],
    # 用户点过「信任并加载」的代码插件（插件 id → True）；未信任的插件不会被执行
    "plugin_trust": {},
    # 插件自己的设置项（插件 id → {键: 值}），插件里用 ctx.get(键) 读取
    "plugin_settings": {},
}


def _clean_provider(raw: dict) -> dict:
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex[:8]),
        "name": str(raw.get("name") or "未命名"),
        "base_url": str(raw.get("base_url") or ""),
        "api_key": str(raw.get("api_key") or ""),
        "model": str(raw.get("model") or ""),
        "vision": bool(raw.get("vision", False)),
        "temperature": float(raw.get("temperature", 0.7) or 0.7),
        "max_tokens": int(raw.get("max_tokens", 8000) or 8000),
        "extra_json": str(raw.get("extra_json") or ""),
        "note": str(raw.get("note") or ""),
    }


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return cfg
    if isinstance(saved.get("providers"), list):
        cfg["providers"] = [_clean_provider(p) for p in saved["providers"]]
    for k in ("active_provider", "template", "port", "ui_theme"):
        if k in saved:
            cfg[k] = saved[k]
    if "fast" in saved:
        cfg["fast"] = bool(saved["fast"])
    if isinstance(saved.get("local"), dict):
        cfg["local"] = saved["local"]
    if isinstance(saved.get("plugins_off"), list):
        cfg["plugins_off"] = [str(x) for x in saved["plugins_off"] if str(x).strip()]
    if isinstance(saved.get("plugin_trust"), dict):
        cfg["plugin_trust"] = {str(k): bool(v) for k, v in saved["plugin_trust"].items() if v}
    if isinstance(saved.get("plugin_settings"), dict):
        cfg["plugin_settings"] = {
            str(k): (v if isinstance(v, dict) else {})
            for k, v in saved["plugin_settings"].items()
        }
    if cfg["providers"] and not any(
        p["id"] == cfg["active_provider"] for p in cfg["providers"]
    ):
        cfg["active_provider"] = cfg["providers"][0]["id"]
    return cfg


def save_config(cfg: dict) -> None:
    """写回配置：先读现有文件再合并，避免把 specs（用户规范）等键顺手抹掉。"""
    data = {}
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = raw
    except Exception:
        data = {}
    if isinstance(cfg, dict):
        data.update(cfg)
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_provider(cfg: dict, pid: str | None = None) -> dict | None:
    pid = pid or cfg.get("active_provider")
    for p in cfg["providers"]:
        if p["id"] == pid:
            return p
    return cfg["providers"][0] if cfg["providers"] else None


def public_provider(p: dict) -> dict:
    """去掉 key 后给前端：只暴露尾 4 位。"""
    out = dict(p)
    key = out.get("api_key") or ""
    out["api_key_masked"] = ("****" + key[-4:]) if len(key) > 4 else ("已设置" if key else "未设置")
    out.pop("api_key", None)
    return out


# --------------------------------------------------------------------------- history


def load_history() -> list:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append_history(item: dict) -> list:
    item = dict(item)
    item.setdefault("id", uuid.uuid4().hex[:10])
    item.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
    hist = load_history()
    hist.insert(0, item)
    del hist[HISTORY_LIMIT:]
    try:
        HISTORY_PATH.write_text(
            json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except Exception:
        pass
    return hist


def clear_history() -> None:
    try:
        HISTORY_PATH.write_text("[]", encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------------------- 规范开关/自定义规范

# 存于 config.json 的 "specs" 段：
#   files: {内置规范文件名: {"enabled": bool, "replace": 用户替换文本}}
#   extra: [{"id","template","name","text","enabled"}] 用户自己添加的规范，注入到对应模板
def normalize_specs(raw) -> dict:
    out = {"files": {}, "extra": []}
    if not isinstance(raw, dict):
        return out
    files = raw.get("files")
    if isinstance(files, dict):
        for k, v in files.items():
            if not isinstance(v, dict):
                continue
            out["files"][str(k)] = {
                "enabled": bool(v.get("enabled", True)),
                "replace": str(v.get("replace") or ""),
            }
    extra = raw.get("extra")
    if isinstance(extra, list):
        for e in extra:
            if not isinstance(e, dict):
                continue
            out["extra"].append(
                {
                    "id": str(e.get("id") or uuid.uuid4().hex[:10]),
                    "template": str(e.get("template") or ""),
                    "name": str(e.get("name") or "自定义规范"),
                    "text": str(e.get("text") or ""),
                    "enabled": bool(e.get("enabled", True)),
                }
            )
    return out


def load_specs() -> dict:
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("specs")
    except Exception:
        raw = None
    return normalize_specs(raw)


def save_specs(state: dict) -> dict:
    """只更新 config.json 的 specs 段，不动其它键。"""
    state = normalize_specs(state)
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    cfg["specs"] = state
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


# --------------------------------------------------------------------------- 用户自定义模板

USER_TPL_PATH = data_dir() / "custom_templates.json"


def _norm_params(raw) -> list:
    """参数定义（与内置模板同结构）：key/label/type/default/options/placeholder/unit/min/max。"""
    out = []
    allowed = ("select", "number", "text", "textarea", "canvas")
    for p in (raw or []):
        if not isinstance(p, dict):
            continue
        key = str(p.get("key") or "").strip()
        if not key:
            continue
        typ = str(p.get("type") or "text").strip().lower()
        if typ not in allowed:
            typ = "text"
        item = {
            "key": key,
            "label": str(p.get("label") or key),
            "type": typ,
            "default": p.get("default", ""),
        }
        if typ == "select":
            opts = [str(o) for o in (p.get("options") or []) if str(o).strip()]
            item["options"] = opts or [""]
            if item["default"] not in opts:
                item["default"] = opts[0] if opts else ""
        for k in ("placeholder", "unit"):
            if p.get(k):
                item[k] = str(p[k])
        if typ == "number":
            for k in ("min", "max"):
                if isinstance(p.get(k), (int, float)):
                    item[k] = p[k]
        out.append(item)
    return out


def normalize_user_templates(raw) -> list:
    out = []
    for t in (raw or []):
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "").strip()
        spec = str(t.get("spec") or "").strip()
        if not name or not spec:
            continue
        out.append({
            "id": str(t.get("id") or "").strip(),
            "name": name[:40],
            "tagline": str(t.get("tagline") or "")[:120],
            "intro": str(t.get("intro") or "")[:800],
            "spec": spec,
            "expect_json": bool(t.get("expect_json")),
            "min_images": max(0, int(t.get("min_images") or 0)),
            "max_images": max(0, int(t.get("max_images") or 4)),
            "params": _norm_params(t.get("params")),
            "examples": [str(e) for e in (t.get("examples") or []) if str(e).strip()][:6],
            "enabled": bool(t.get("enabled", True)),
        })
    return out


def load_user_templates() -> list:
    try:
        raw = json.loads(USER_TPL_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("templates")
    except Exception:
        raw = []
    return normalize_user_templates(raw)


def save_user_templates(items: list) -> list:
    items = normalize_user_templates(items)
    USER_TPL_PATH.write_text(json.dumps({"templates": items}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return items
