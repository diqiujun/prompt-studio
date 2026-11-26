# -*- coding: utf-8 -*-
"""桌面版补充回归：走打包后的 exe 验证「提示词规范管理」与 H3/MOSS 两条生成链路没被改坏。

用法：python check_desktop_extras.py
日志：data/desktop_extras.log
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist", "PromptStudio")
EXE = os.path.join(DIST, "PromptStudio.exe")
DATA = os.path.join(DIST, "data")
LOG = os.path.join(HERE, "data", "desktop_extras.log")

FAILS = []
T0 = time.time()


def out(msg):
    line = msg if msg.startswith("[") else "[%5.1fs] %s" % (time.time() - T0, msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ok(name, detail=""):
    out("  OK  %s%s" % (name, ("  " + str(detail)) if detail else ""))


def bad(name, detail=""):
    FAILS.append(name)
    out("  FAIL %s%s" % (name, ("  " + str(detail)) if detail else ""))


BASE = None


def http(path, body=None, timeout=600):
    url = (BASE or "http://127.0.0.1:8760") + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def port_of_pid(pid, lo=8000, hi=9100):
    try:
        r = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                           encoding="mbcs", errors="ignore", timeout=20,
                           creationflags=0x08000000)
    except Exception:
        return None
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[3].upper() != "LISTENING" or parts[-1] != str(pid):
            continue
        try:
            port = int(parts[1].rsplit(":", 1)[-1])
        except Exception:
            continue
        if lo <= port <= hi:
            return port
    return None


def main():
    global BASE
    open(LOG, "w", encoding="utf-8").close()
    out("桌面版补充回归 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    for name in ("PromptStudio.exe", "llama-server.exe"):
        subprocess.run(["taskkill", "/IM", name, "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    proc = subprocess.Popen([EXE], cwd=DIST, creationflags=0x00000200,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok("exe 已启动", "pid=%d" % proc.pid)
    for _ in range(150):
        if proc.poll() is not None:
            bad("exe 存活", "退出码 %s" % proc.returncode)
            return 1
        p = port_of_pid(proc.pid)
        if p:
            BASE = "http://127.0.0.1:%d" % p
            st = http("/api/state", None, timeout=5)
            if isinstance(st, dict) and st.get("templates"):
                break
            BASE = None
        time.sleep(2)
    if not BASE:
        bad("对外服务就绪", "150 次轮询未见 /api/state")
        return 1
    ok("对外服务就绪", BASE)

    # 等本地模型就绪（后面两条生成要用）
    for _ in range(120):
        ls = http("/api/local/status")
        if ls.get("running"):
            break
        time.sleep(2)
    if not ls.get("running"):
        bad("本地模型就绪", json.dumps(ls, ensure_ascii=False)[:200])
        return 1
    ok("本地模型就绪", "pid=%s port=%s" % (ls.get("pid"), ls.get("port")))

    # 1) 规范管理：清单
    sp = http("/api/spec")
    tpls = sp.get("templates") or []
    comps = {t["id"]: len(t.get("components") or []) for t in tpls}
    if tpls and comps.get("h3_video") == 7 and comps.get("moss_t2i") == 6:
        ok("规范清单", str(comps))
    else:
        bad("规范清单", str(comps))

    # 2) 关闭一个组件 → 注入量变短
    body = {"template": "moss_t2i", "content": "测试", "fast": True}
    p0 = http("/api/debug/payload", body)
    n0 = p0.get("system_chars")
    http("/api/spec/toggle", {"name": "moss_slots_and_defaults.md", "enabled": False})
    p1 = http("/api/debug/payload", body)
    n1 = p1.get("system_chars")
    if n0 and n1 and n1 < n0:
        ok("关闭组件生效", "%d → %d 字" % (n0, n1))
    else:
        bad("关闭组件生效", "%s → %s" % (n0, n1))
    http("/api/spec/reset", {})

    # 3) 自定义规范注入
    http("/api/spec/save", {"spec": {"template": "moss_t2i", "name": "桌面包回归",
                                     "text": "DESK-EXTRA-5521 必须照做。", "enabled": True}})
    p2 = http("/api/debug/payload", body)
    sys2 = p2.get("system") or ""
    if "DESK-EXTRA-5521" in sys2 and "优先级高于上方内置规范" in sys2:
        ok("自定义规范注入", "system 末尾含声明")
    else:
        bad("自定义规范注入", "未找到标记")
    http("/api/spec/reset", {})

    # 4) H3 生成（本地模型）
    h = http("/api/generate", {
        "template": "h3_video", "content": "沈不违站在雪夜山门前，镜头从靴子上摇到脸，他开口说「都让开」。6 秒。",
        "params": {"mode": "auto", "duration": 6, "aspect": "16:9"},
        "fast": True, "provider": "local-gemma", "images": [],
    }, timeout=900)
    txt = h.get("content") or ""
    need = ["subject_definitions", "summary", "detailed_description", "overall_soundscape"]
    miss = [k for k in need if k not in txt]
    if h.get("ok") and not miss:
        ok("H3 六段结构", "%.1fs | %s tok | note=%s"
           % (h.get("elapsed", 0), (h.get("usage") or {}).get("total_tokens", "-"), h.get("note", "")))
    else:
        bad("H3 六段结构", "缺 %s；error=%s" % (miss, h.get("error")))

    # 5) MOSS 生成（本地模型，JSON）
    m = http("/api/generate", {
        "template": "moss_t2i", "content": "仙侠剧女修站在丹殿废墟里，手捧发光丹炉残件，3D 仙侠渲染风。",
        "params": {"canvas": "1024x1536", "style_pref": "3D 仙侠渲染"},
        "fast": True, "provider": "local-gemma", "images": [],
    }, timeout=900)
    j = m.get("json") or {}
    if m.get("ok") and j.get("positive_prompt") and (j.get("canvas_size") or {}).get("height") == 1536:
        ok("MOSS 结构化输出", "canvas=%s | 负向词 %d 字"
           % (j.get("canvas_size"), len(j.get("negative_prompt") or "")))
    else:
        bad("MOSS 结构化输出", str(m.get("error"))[:160] or str(list(j.keys())))

    # 收尾
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    left = http("/api/local/status", None, timeout=3)
    if not (left.get("ok") and left.get("running")):
        ok("退出后不留后台模型", "8910 已停")
    else:
        bad("退出后不留后台模型", "仍 running pid=%s" % left.get("pid"))
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    out("")
    out("结果：失败 %d 项 %s" % (len(FAILS), ("→ " + ", ".join(FAILS)) if FAILS else "→ 通过"))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
