# -*- coding: utf-8 -*-
"""运行环境（llama.cpp 预编译包）自检：
检测 → 按硬件安装 → 自检可执行 → 起本地模型 → 出词 → 停。

python test_runtimes.py
日志：data\runtime_test.log
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

import localsrv          # noqa: E402
import runtimes          # noqa: E402
import settings          # noqa: E402

LOG_PATH = os.path.join(ROOT, "data", "runtime_test.log")
FAILS = []
LINES = []


def out(msg=""):
    LINES.append(msg)
    print(msg, flush=True)


def ok(name, detail=""):
    out("OK   %-34s %s" % (name, detail))


def bad(name, detail=""):
    FAILS.append(name)
    out("FAIL %-34s %s" % (name, detail))


def main() -> int:
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    out("=== 运行环境自检 %s ===" % time.strftime("%Y-%m-%d %H:%M:%S"))

    st = runtimes.status()
    det = st["detect"]
    out("检测：os=%s arch=%s nvidia=%s cuda=%s amd=%s cpus=%s" % (
        det["os"], det["arch"], (det.get("nvidia") or {}).get("present"),
        det.get("cuda"), (det.get("amd") or {}).get("present"), det.get("cpus")))
    out("候选：%s" % ", ".join(st["candidates"]))
    if not st["supported"]:
        bad("平台支持", st["message"])
        return finish()

    # 1) 安装推荐包
    pid = st["preferred"]
    t0 = time.time()
    r = runtimes.install(pid)
    if not r.get("ok"):
        bad("安装推荐包", r.get("error"))
        return finish()
    ok("安装推荐包", "%s → %.1fs，%s" % (pid, time.time() - t0, r.get("dir")))

    # 2) 二进制自检
    v = runtimes.verify(pid)
    ok("二进制自检", (v.get("output") or "").splitlines()[0] if v.get("ok") else str(v.get("error") or v)[:120])
    if not v.get("ok"):
        bad("二进制自检", str(v)[:200])

    # 3) 已安装列表 + find_exe
    out("已安装：%s" % ", ".join(runtimes.installed()) or "（空）")
    try:
        exe = localsrv.find_exe(str((settings.load_config().get("local") or {}).get("llama_dir") or r"E:\llama"))
        if os.path.dirname(exe).startswith(str(runtimes.runtime_dir())):
            ok("find_exe 指向自带运行环境", exe)
        else:
            out("..   find_exe 用了外部目录：%s" % exe)
            ok("find_exe 可用", exe)
    except Exception as e:
        bad("find_exe", "%s: %s" % (type(e).__name__, e))
        return finish()

    # 4) 起本地模型（用自带运行环境）
    cfg = settings.load_config()
    c = localsrv.normalize(cfg.get("local"))
    c["port"] = int(os.environ.get("RUNTIME_TEST_PORT") or 8920)
    t0 = time.time()
    s = localsrv.start(c, os.path.join(ROOT, "data", "runtime_test_llama.log"))
    if not s.get("ok"):
        bad("启动本地模型", s.get("error"))
        return finish()
    ok("启动本地模型", "%.1fs pid=%s port=%s %s" % (
        time.time() - t0, s.get("pid"), s.get("port"), s.get("tier") or s.get("note") or ""))
    ok("运行环境来源", str(c.get("llama_dir")))

    # 5) 出词
    import urllib.request
    try:
        body = json.dumps({"model": c["alias"], "messages": [
            {"role": "user", "content": "只回答两个字：就绪"}], "max_tokens": 900,
            "temperature": 0.2}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % c["port"], data=body,
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=180) as resp:
            j = json.loads(resp.read().decode("utf-8"))
        msg = (j.get("choices") or [{}])[0].get("message") or {}
        txt = (msg.get("content") or "").strip() or (msg.get("reasoning_content") or "").strip()
        ok("本地模型出词", "%.1fs 「%s」" % (time.time() - t0, txt[:40].replace("\n", " ")))
    except Exception as e:
        bad("本地模型出词", "%s: %s" % (type(e).__name__, e))

    # 6) 停掉
    pid_running = localsrv.running_pid(c["port"])
    stp = localsrv.stop(pid_running or s.get("pid"))
    if stp.get("ok") and not localsrv.running_pid(c["port"]):
        ok("停止本地模型", "端口 %d 已释放" % c["port"])
    else:
        bad("停止本地模型", str(stp))
    return finish()


def finish() -> int:
    out("\n结果：失败 %d 项 %s" % (len(FAILS), ("→ " + ", ".join(FAILS)) if FAILS else "→ 通过"))
    try:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(LINES) + "\n")
    except Exception:
        pass
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
