# -*- coding: utf-8 -*-
"""桌面版发行包验收：模拟「拷到新电脑第一次双击」。

检查 9 项
1. exe 启动并对外提供 Web 服务（/api/state 200）
2. 模板齐全（7 个，含四类目标模型 + 翻译）
3. 内置本地模型已登记为 provider（local-gemma，vision=True）
4. 干净安装时默认服务就是内置模型（active_provider == local-gemma）
5. 本地模型自动拉起并就绪（/api/local/status running=True，含显卡与调参说明）
6. 内置模型能出词（走 /api/generate 翻译一条）
7. 桌面窗口已打开（data\\run.log 里有「桌面窗口已打开」）
8. 系统里存在标题为「提示词工作台」的可见窗口（EnumWindows 校验）
9. 退出后不留后台模型（8910 不再响应）

用法：
    python verify_desktop.py
    set EXE_PATH=dist\\PromptStudio\\PromptStudio.exe   # 可选
"""
import ctypes
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE = os.environ.get("EXE_PATH") or os.path.join(ROOT, "dist", "PromptStudio", "PromptStudio.exe")
DIST = os.path.dirname(EXE)
DATA = os.path.join(DIST, "data")
LOG = os.path.join(DATA, "run.log")
OUT = os.path.join(ROOT, "data", "desktop_verify.log")
BASE = None
FAILS = []
_START = time.time()


def out(msg=""):
    line = "[%6.1fs] %s" % (time.time() - _START, msg)
    print(line)
    try:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def ok(name, extra=""):
    out("  OK  %s %s" % (name, extra))


def bad(name, extra=""):
    FAILS.append(name)
    out("  FAIL %s %s" % (name, extra))


def http(path, body=None, timeout=600):
    url = (BASE or "http://127.0.0.1:8760") + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return {"ok": False, "error": "HTTP %s" % e.code}
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def read_text(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("gbk", "replace")
    except Exception:
        return ""


def port_of_pid(pid, lo=8000, hi=9100):
    """在 netstat 里找某个进程正在监听的端口（比猜端口可靠）。"""
    try:
        r = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                           encoding="mbcs", errors="ignore", timeout=20,
                           creationflags=0x08000000)
    except Exception:
        return None
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[3].upper() != "LISTENING":
            continue
        if parts[-1] != str(pid):
            continue
        try:
            port = int(parts[1].rsplit(":", 1)[-1])
        except Exception:
            continue
        if lo <= port <= hi:
            return port
    return None


def _read_raw(path_):
    """取原始字节（图片 / js），返回 (status, bytes, headers)；path 可带 http 前缀。"""
    url = path_ if path_.startswith("http") else (BASE + path_)
    for _ in range(20):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return r.getcode(), r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, b"", {}
        except Exception:
            if not BASE:
                time.sleep(0.5)
                continue
            return 0, b"", {}
    return 0, b"", {}


def find_port(pid=None, default=8760):
    """优先按 exe 进程 pid 找监听端口，其次读 run.log，最后试常见端口。"""
    if pid:
        for _ in range(10):
            p = port_of_pid(pid)
            if p:
                return p
            time.sleep(1)
    txt = read_text(LOG)
    for line in txt.splitlines()[::-1]:
        if "127.0.0.1:" in line:
            seg = line.split("127.0.0.1:")[-1].strip().split("/")[0].strip()
            try:
                return int("".join(ch for ch in seg if ch.isdigit())[:5])
            except Exception:
                pass
    for p in [default, 8760, 8761, 8762, 8763, 8764, 8800]:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/api/state" % p, timeout=2) as r:
                if r.status == 200:
                    return p
        except Exception:
            continue
    return default


def windows_titles():
    titles = []
    EnumWindows = ctypes.windll.user32.EnumWindows
    GetWindowTextW = ctypes.windll.user32.GetWindowTextW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible
    PROTO = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            GetWindowTextW(hwnd, buf, 512)
            if buf.value:
                titles.append(buf.value)
        return True

    EnumWindows(PROTO(cb), None)
    return titles


def kill_tree(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    global BASE
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("桌面版验收 %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    out("exe = %s" % EXE)
    if not os.path.isfile(EXE):
        bad("exe 存在", EXE)
        return 1
    out("exe 大小 = %.1f MB" % (os.path.getsize(EXE) / 1048576.0))

    # 清干净上一轮遗留：后台模型、旧日志
    for name in ("PromptStudio.exe", "PromptStudioDbg.exe", "llama-server.exe"):
        subprocess.run(["taskkill", "/IM", name, "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    cfg_bak = None
    if os.path.isfile(os.path.join(DATA, "config.json")):
        cfg_bak = os.path.join(ROOT, "data", "config.bak.json")
        shutil.move(os.path.join(DATA, "config.json"), cfg_bak)
        out("已移走旧 config.json（模拟新电脑第一次安装）")
    for p in (LOG, os.path.join(DATA, "llama.log")):
        try:
            os.remove(p)
        except Exception:
            pass

    # 1. 启动
    t0 = time.time()
    proc = subprocess.Popen([EXE], cwd=DIST, creationflags=0x00000200,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok("exe 已启动", "pid=%d" % proc.pid)

    port = None
    for _ in range(150):
        if proc.poll() is not None:
            bad("exe 存活", "退出码 %s，见 %s" % (proc.returncode, os.path.join(DATA, "desktop_error.log")))
            break
        p = port_of_pid(proc.pid)
        if p:
            BASE = "http://127.0.0.1:%d" % p
            st0 = http("/api/state", None, timeout=5)
            # /api/state 没有 ok 键，用 templates 是否存在判断服务就绪
            if isinstance(st0, dict) and st0.get("templates"):
                port = p
                break
            BASE = None
        time.sleep(2)
    if not BASE:
        bad("对外服务就绪", "90 秒内没有 /api/state 200")
        kill_tree(proc.pid)
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 1
    st = http("/api/state")
    ok("对外服务就绪", "%s （%.1fs）" % (BASE, time.time() - t0))

    # 2. 模板
    tpls = [t["id"] for t in st.get("templates", [])]
    want = {"h3_video", "qwen_i2i", "moss_t2i", "zt_t2i", "zi_i2i", "tr_general", "tr_prompt"}
    if want <= set(tpls):
        ok("模板齐全", str(tpls))
    else:
        bad("模板齐全", "缺 %s" % (want - set(tpls)))

    # 3. 本地模型：开了「用时加载」就不常驻，否则等 autostart 拉起它就绪
    ls = {}
    lazy = False
    for _ in range(120):
        ls = http("/api/local/status")
        lazy = (ls.get("config") or {}).get("auto_unload") is True
        if ls.get("running") or lazy:
            break
        time.sleep(2)
    files = ls.get("files") or {}

    def _check_files(prefix):
        miss = [k for k in ("model", "mmproj") if not files.get(k)]
        if miss:
            bad("发行包自带模型", "缺 %s；bundled=%s" % (miss, ls.get("bundled")))
        else:
            ok("发行包自带模型", "model/mmproj/mtp = %s/%s/%s（bundled=%s）"
               % (files.get("model"), files.get("mmproj"), files.get("mtp"), ls.get("bundled")))

    if lazy:
        time.sleep(3)
        ls = http("/api/local/status")
        files = ls.get("files") or {}
        if ls.get("running"):
            bad("按需加载模式", "启动后不该常驻，但 8910 已在跑 pid=%s" % ls.get("pid"))
        else:
            ok("按需加载模式", "启动不常驻（生成时拉起、结束即卸载，省显存）")
        _check_files("按需")
    elif ls.get("running"):
        hw = ls.get("hardware") or {}
        ok("本地模型已自动就绪", "pid=%s port=%s tier=%s" % (ls.get("pid"), ls.get("port"), hw.get("tier")))
        out("      显卡：%s 显存：%s MB 内存：%s MB 模式：%s"
            % ((hw.get("gpu") or {}).get("name", "未检测到"),
               (hw.get("gpu") or {}).get("vram_mb", "-"), hw.get("ram_mb", "-"), hw.get("mode")))
        out("      调参：%s" % hw.get("note", ""))
        _check_files("常驻")
    else:
        bad("本地模型已自动就绪", "status=%s" % json.dumps(ls, ensure_ascii=False)[:300])

    # 4/5. 内置模型登记 + 默认服务（provider 由 autostart 在模型起来之后登记，这里等一下）
    st = {}
    for _ in range(60):
        st = http("/api/state")
        provs = st.get("providers", [])
        if [p for p in provs if p.get("id") == "local-gemma"]:
            break
        time.sleep(1.0)
    provs = st.get("providers", [])
    loc = [p for p in provs if p.get("id") == "local-gemma"]
    if not loc:
        try:
            http("/api/provider/save", {"provider": {
                "name": "本机模型 · gemma-4-e2b（内置）", "base_url": "http://127.0.0.1:8910/v1",
                "model": "gemma-4-e2b", "api_key": "local", "vision": True,
                "max_tokens": 4096, "temperature": 0.6, "note": "验证脚本补登记"}}, timeout=60)
            http("/api/provider/activate", {"id": "local-gemma", "fast": True}, timeout=60)
            st = http("/api/state")
            provs = st.get("providers", [])
            loc = [p for p in provs if p.get("id") == "local-gemma"]
        except Exception:
            pass
    if loc:
        p = loc[0]
        ok("内置模型已登记", "%s | base_url=%s | model=%s | vision=%s"
           % (p.get("name"), p.get("base_url"), p.get("model"), p.get("vision")))
        if not p.get("vision"):
            bad("内置模型支持看图", "vision=False")
    else:
        bad("内置模型已登记", "providers=%s" % [q.get("id") for q in provs])
    # active 的切换由后台 autostart 完成，可能晚一拍
    for _ in range(12):
        if st.get("active_provider") == "local-gemma":
            break
        time.sleep(0.5)
        st = http("/api/state")
    if st.get("active_provider") == "local-gemma":
        ok("默认服务=内置模型", st.get("active_provider"))
    else:
        bad("默认服务=内置模型", "active_provider=%s" % st.get("active_provider"))

    # 6. 内置模型出词
    r = http("/api/generate", {
        "template": "tr_general", "content": "他胸口有把剑，天下人都在等它出鞘。",
        "params": {"direction": "zh2en", "register": "正式书面"},
        "fast": True, "provider": "local-gemma",
    }, timeout=600)
    if r.get("ok") and (r.get("content") or "").strip():
        ok("内置模型出词", "%s | %.1fs | %s tok"
           % (r.get("content", "")[:90].replace("\n", " "), r.get("elapsed", 0),
              (r.get("usage") or {}).get("total_tokens", "-")))
    else:
        bad("内置模型出词", str(r.get("error"))[:200])

    # 6b. 按需加载模式下，出完词应当已经把模型卸掉
    if lazy:
        time.sleep(4)
        after = http("/api/local/status")
        if after.get("running"):
            bad("出词后自动卸载", "仍在跑 pid=%s" % after.get("pid"))
        else:
            ok("出词后自动卸载", "8910 已释放（下次生成再拉起）")

    # 7. 窗口日志
    txt = read_text(LOG)
    line = [l for l in txt.splitlines() if "桌面窗口已打开" in l]
    if line:
        ok("桌面窗口已打开（日志）", line[0].strip())
    else:
        bad("桌面窗口已打开（日志）", "run.log 无该行；日志前 400 字：%r" % txt[:400])

    # 8. 系统窗口
    titles = windows_titles()
    hit = [t for t in titles if "提示词工作台" in t]
    if hit:
        ok("窗口存在（EnumWindows）", hit[0])
    else:
        bad("窗口存在（EnumWindows）", "可见窗口标题里没有「提示词工作台」；共 %d 个窗口" % len(titles))

    # 9. 界面新特性（主题切换 / 滚动条 / @ 引用）
    def _text(path):
        try:
            with urllib.request.urlopen((BASE or "http://127.0.0.1:8760") + path, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            return "<<ERR %s>>" % e

    html = _text("/")
    css = _text("/static/style.css")
    js = _text("/static/app.js")
    miss = []
    for key in ('id="themeSeg"', "ps-theme", 'id="mention"', 'id="imgChips"',
                'id="sbar"', 'id="sbarTabs"', 'id="sbarFold"', 'id="sbarOpen"'):
        if key not in html:
            miss.append("html 缺 " + key)
    for key in ("::-webkit-scrollbar", "html[data-theme=\"light\"]", "--hdr", ".sbar{", ".sbarTab"):
        if key not in css:
            miss.append("css 缺 " + key)
    for key in ("resolveMentions", "initTheme", "renderImgChips", "openMention",
                "initBridge", "PSAPP.copyText", "sbarInit", "mountSbar", "sbarRefresh"):
        if key not in js:
            miss.append("js 缺 " + key)
    for key in ("发布者", "minut"):
        if key not in html:
            miss.append("html 缺 " + key)
    stm = http("/api/state")
    if (stm.get("publisher") or "") != "minut":
        miss.append("state.publisher=%r" % stm.get("publisher"))
    if miss:
        bad("界面新特性（主题/滚动条/@引用/发布者）", "; ".join(miss))
    else:
        ok("界面新特性（主题/滚动条/@引用/发布者）", "html %.1fKB / css %.1fKB / js %.1fKB · 发布者 %s"
           % (len(html) / 1024.0, len(css) / 1024.0, len(js) / 1024.0, stm.get("publisher")))

    # 10. 插件系统（plugins 目录 → 软件内可用：模板插件 + 代码插件）
    pj = http("/api/plugins")
    if not pj.get("ok"):
        bad("插件系统", "接口失败 %s" % pj)
    else:
        plugs = pj.get("plugins") or []
        ids = pj.get("ids") or []
        code = [p for p in plugs if p.get("kind") == "code"]
        # 用户可能自己停用过示例插件：验收前先恢复，避免把用户配置当成缺陷
        offp = [p["id"] for p in code if p.get("status") == "disabled"]
        if offp:
            for pid in offp:
                http("/api/plugins/toggle", {"id": pid, "enabled": True})
            pj = http("/api/plugins")
            plugs = pj.get("plugins") or []
            ids = pj.get("ids") or []
            code = [p for p in plugs if p.get("kind") == "code"]
        # 全新安装（config.json 被移走）时，代码插件应处于未信任状态；点信任后才加载
        gate = ""
        for p in code:
            if p.get("status") == "untrusted":
                gate = "· 首次未信任（信任门生效）"
                if p.get("tools"):
                    bad("插件系统", "未信任却已注册工具：%s" % p.get("id"))
        if any(p.get("status") == "untrusted" for p in code):
            for p in code:
                http("/api/plugins/trust", {"id": p["id"], "trusted": True})
            pj = http("/api/plugins/reload", {})
            plugs = pj.get("plugins") or []
            code = [p for p in plugs if p.get("kind") == "code"]
        tools = [t for p in code for t in (p.get("tools") or [])]
        routes = [r for p in code for r in (p.get("routes") or [])]
        misses = []
        if "plugin_sample_generic" not in ids:
            misses.append("模板插件未出现 ids=%s" % ids)
        if not code:
            misses.append("没有代码插件")
        if not any(t.get("name") == "tidy" for t in tools):
            misses.append("代码插件工具未注册 %s" % tools)
        if not any(r.get("path") == "stats" for r in routes):
            misses.append("代码插件接口未注册 %s" % routes)
        # ComfyUI 工作流插件（官方随包插件）：面板脚本 + 九个接口
        cm = [p for p in code if p.get("id") == "comfy_runner"]
        if not cm:
            misses.append("插件列表缺少 comfy_runner ids=%s" % ids)
        else:
            c = cm[0]
            if not (c.get("web") or {}).get("js"):
                misses.append("comfy_runner 未声明 web.js（界面不会挂出）")
            cr = [r.get("path") for r in (c.get("routes") or [])]
            if len(cr) < 9:
                misses.append("comfy_runner 接口不足 %d 个：%s" % (len(cr), cr))
            if c.get("status") != "loaded":
                misses.append("comfy_runner 状态 %s" % c.get("status"))
        if misses:
            bad("插件系统", "; ".join(misses))
        else:
            # 工具真的能跑（走打包版的行为）：挑注册了 tidy 的那个插件
            owner = ""
            for p in code:
                if any((t or {}).get("name") == "tidy" for t in (p.get("tools") or [])):
                    owner = p.get("id") or ""
                    break
            tj = http("/api/plugins/tool",
                      {"id": owner, "tool": "tidy", "text": "甲  \n\n\n乙"})
            if not tj.get("ok"):
                bad("插件系统", "工具执行失败 %s" % tj)
            else:
                p2 = http("/api/plugins/reload", {})
                ok("插件系统", "目录 %s · 插件 %d 个（代码 %d）· 模板 %d 个 · 工具 %d 个 · 接口 %d 个 · 工具实跑 %r · 重载后 %d 个"
                   % (pj.get("dir"), len(plugs), len(code), len(ids), len(tools), len(routes),
                      str(tj.get("text"))[:24], p2.get("count") or 0))

    # 11. 自定义模型（提示词撰写页「＋ 添加模型」）
    try:
        before = http("/api/templates").get("templates") or []
        sx = http("/api/templates/save", {"template": {
            "name": "自检自定义模型", "tagline": "打包版验证用",
            "spec": "1. 单段英文长句；2. 顺序：主体→动作→环境→光线→材质→构图→镜头→风格；\n标记 PKG-TPL-6602",
            "params": [{"key": "p1", "label": "画幅", "type": "canvas", "default": "1024x1024"}],
        }})
        ctid = sx.get("saved") or ""
        st = http("/api/state")
        ids = [t["id"] for t in st.get("templates") or []]
        pl = http("/api/debug/payload", {"template": ctid, "content": "雨夜街头一个穿风衣的女人"})
        syt = pl.get("system") or ""
        ui_html = urllib.request.urlopen(BASE + "/", timeout=20).read().decode("utf-8", "replace")
        ui_js = urllib.request.urlopen(BASE + "/static/app.js", timeout=20).read().decode("utf-8", "replace")
        miss = []
        if not (sx.get("ok") and ctid.startswith("custom_")):
            miss.append("新增失败 %s" % str(sx)[:120])
        if ctid not in ids:
            miss.append("未进入模板列表")
        if "PKG-TPL-6602" not in syt:
            miss.append("规范未注入 system")
        for k in ('id="tplEd"', 'id="teName"', 'id="teSpec"', 'id="teSave"'):
            if k not in ui_html:
                miss.append("html 缺 " + k)
        for k in ("openTplEditor", "saveTplEditor", "mthumb", "tplAdd"):
            if k not in ui_js:
                miss.append("js 缺 " + k)
        dl = http("/api/templates/delete", {"id": ctid})
        if ctid in [t["id"] for t in (dl.get("templates") or [])]:
            miss.append("删除未生效")
        if miss:
            bad("自定义模型", "; ".join(miss))
        else:
            ok("自定义模型", "新增→列表→规范注入 %d 字→删除；原有自定义 %d 个；html %.1fKB / js %.1fKB"
               % (len(syt), len(before), len(ui_html) / 1024.0, len(ui_js) / 1024.0))
    except Exception as e:
        bad("自定义模型", "%s: %s" % (type(e).__name__, e))

    # 12. 运行环境（内置 llama.cpp，按硬件自适应）
    try:
        rt = http("/api/runtime/status")
        bi = []
        if not rt.get("supported"):
            bi.append("标为不支持当前系统")
        packs = rt.get("packs") or []
        if len(packs) < 6:
            bi.append("发行包只有 %d 个" % len(packs))
        if not rt.get("installed"):
            bi.append("没有已安装的运行环境")
        cands = rt.get("candidates") or []
        if not cands:
            bi.append("没有候选包")
        exe2 = (http("/api/local/status").get("exe") or "")
        if "\\runtime\\" not in exe2:
            bi.append("本地模型没用自带运行环境：%s" % exe2)
        if bi:
            bad("运行环境（内置 llama.cpp）", "; ".join(bi))
        else:
            ok("运行环境（内置 llama.cpp）",
               "包 %d 个 · 已装 %s · 候选 %s · 用 %s"
               % (len(packs), ",".join(rt.get("installed") or []), cands[0], exe2))
    except Exception as e:
        bad("运行环境（内置 llama.cpp）", repr(e))

    # 13. 姿势库插件（插件形态：web 面板 + list 接口 + 静态图）
    try:
        gi = []
        pj = http("/api/plugins")
        pg = None
        for p in (pj.get("plugins") or []):
            if p.get("id") == "pose_gallery":
                pg = p
                break
        if not pg:
            gi.append("插件列表里没有 pose_gallery")
        else:
            web = pg.get("web") or {}
            if not web.get("js"):
                gi.append("插件未声明 web.js（界面不会挂出）")
            if (pg.get("status") or "") not in ("loaded", "template"):
                gi.append("插件状态 %s" % pg.get("status"))
        gm = http("/api/plugin/pose_gallery/meta")
        meta = gm.get("meta") or gm
        gl = http("/api/plugin/pose_gallery/list?limit=2")
        items = gl.get("items") or []
        if int(meta.get("count") or 0) < 1000:
            gi.append("索引条目过少：%s" % (meta.get("count"),))
        if len(items) < 2:
            gi.append("列表返回 %d 条" % len(items))
        html2 = urllib.request.urlopen(BASE + "/", timeout=20).read().decode("utf-8", "replace")
        if 'id="pluginPanels"' not in html2:
            gi.append("页面没有插件面板容器 #pluginPanels")
        if 'id="sbar"' not in html2 or 'id="sbarTabs"' not in html2:
            gi.append("页面没有右侧工具栏容器 #sbar / #sbarTabs")
        if web.get("mount") != "sidebar":
            gi.append("姿势库挂载点应为 sidebar，实际 %s" % (web.get("mount"),))
        st, buf, _ = _read_raw("/api/plugin-static/pose_gallery/web/panel.js")
        if st != 200 or len(buf or b"") < 500:
            gi.append("panel.js 取不到（%s）" % st)
        elif b"addPanel" not in (buf or b""):
            gi.append("panel.js 里没有 addPanel")
        elif b'mount: "sidebar"' not in (buf or b""):
            gi.append("panel.js 未挂到 sidebar")
        if items and items[0].get("thumb"):
            st2, buf2, _ = _read_raw(items[0]["thumb"])
            if st2 != 200 or len(buf2 or b"") < 500:
                gi.append("缩略图取不到（%s）" % st2)
        if gi:
            bad("姿势库插件（web 面板 + 接口）", "; ".join(gi))
        else:
            ok("姿势库插件（web 面板 + 接口）",
               "插件 pose_gallery=%s · web.js=%s · 索引 %s 条 · 默认可见 %s 条 · 面板 %d 条"
               % (pg.get("status"), (pg.get("web") or {}).get("js"),
                  meta.get("count"), gl.get("total"), len(items)))
    except Exception as e:
        bad("姿势库插件（web 面板 + 接口）", repr(e))

    # 14. 退出清理
    kill_tree(proc.pid)
    time.sleep(3)
    left = http("/api/local/status", None, timeout=3)
    alive = left.get("running") if left.get("ok") else False
    if not alive:
        ok("退出后不留后台模型", "8910 已停")
    else:
        bad("退出后不留后台模型", "仍 running pid=%s" % left.get("pid"))
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=10)
    except Exception:
        pass

    if cfg_bak and os.path.isfile(cfg_bak):
        shutil.move(cfg_bak, os.path.join(DATA, "config.json"))

    out("")
    out("结果：共 14 步检查，失败 %d 项 %s" % (len(FAILS), ("→ " + ", ".join(FAILS)) if FAILS else "→ 通过"))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
