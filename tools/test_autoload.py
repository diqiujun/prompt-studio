# -*- coding: utf-8 -*-
"""本地模型「用时加载、生成完自动卸载」的实机验证。

流程：确认 8910 没在跑 → 起本体服务 → POST /api/generate（provider=local-gemma）
     → 生成期间 8910 应该在跑 → 生成返回后 8910 必须已经被关掉。

用法：python tools\test_autoload.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
PORT = int(os.environ.get("PM_PORT", "8796"))
LOG = os.path.join(ROOT, "data", "autoload_test.log")


def out(s=""):
    line = str(s)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def http(path, body=None, timeout=300):
    url = "http://127.0.0.1:%d%s" % (PORT, path) if path.startswith("/") else path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": "%s: %s" % (type(exc).__name__, exc)}


def local_state():
    st, j = http("/api/local/status", timeout=20)
    if st != 200:
        return None
    return {"running": bool(j.get("running")), "port": j.get("port"),
            "auto_unload": (j.get("config") or {}).get("auto_unload"),
            "pid": j.get("pid")}


def main():
    if os.path.exists(LOG):
        os.remove(LOG)
    import localsrv

    out("== 0. 先确保本地模型没在跑 ==")
    localsrv.stop(None)
    time.sleep(2)

    # 打开自动卸载，确保配置是「用时加载」
    cfgp = os.path.join(ROOT, "data", "config.json")
    with open(cfgp, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    loc = dict(cfg.get("local") or {})
    loc["auto_unload"] = True
    loc["enabled"] = True
    cfg["local"] = loc
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    out("  auto_unload=True 已写入配置")

    env = dict(os.environ)
    env["PORT"] = str(PORT)
    env["PYTHONUTF8"] = "1"
    flags = 0x00000200 if os.name == "nt" else 0
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "src", "app.py")],
                           cwd=ROOT, env=env, creationflags=flags)
    fails = []
    try:
        for _ in range(60):
            st, _j = http("/api/state", timeout=3)
            if st == 200:
                break
            time.sleep(1)
        else:
            out("！本体服务没有起来")
            return 1

        out("\n== 1. 生成前状态 ==")
        s0 = local_state()
        out("  %s" % s0)
        if not s0 or s0["running"]:
            fails.append("生成前本地模型不该在跑")
        if not s0 or s0.get("auto_unload") is not True:
            fails.append("auto_unload 没读到 True")

        out("\n== 2. 调一次生成（会先拉起模型）==")
        t0 = time.time()
        st, j = http("/api/generate", {
            "template": "tr_general", "content": "他胸口有把剑，天下都在等它出鞘的那一夜。",
            "provider": "local-gemma", "fast": True, "params": {},
        }, timeout=600)
        dt = time.time() - t0
        out("  用时 %.1fs → ok=%s" % (dt, j.get("ok")))
        out("  输出：%s" % str(j.get("content") or j.get("error"))[:160])
        if not j.get("ok"):
            fails.append("生成失败：%s" % j.get("error"))

        out("\n== 3. 生成后应当已卸载 ==")
        for i in range(6):
            time.sleep(2)
            s1 = local_state()
            out("  +%ds %s" % ((i + 1) * 2, s1))
            if s1 and not s1["running"]:
                break
        else:
            fails.append("生成结束后本地模型还在跑（应自动卸载）")

        out("\n== 4. 再来一次（验证可重复加载）==")
        t1 = time.time()
        st, j = http("/api/generate", {
            "template": "tr_general", "content": "雪落在刀上，他吹了口气。",
            "provider": "local-gemma", "fast": True, "params": {},
        }, timeout=600)
        out("  用时 %.1fs → ok=%s" % (time.time() - t1, j.get("ok")))
        if not j.get("ok"):
            fails.append("第二次生成失败：%s" % j.get("error"))
        time.sleep(4)
        s2 = local_state()
        out("  结束后 %s" % s2)
        if s2 and s2["running"]:
            fails.append("第二次生成后仍在跑")
    finally:
        try:
            srv.terminate()
            srv.wait(timeout=15)
        except Exception:  # noqa: BLE001
            pass
        try:
            localsrv.stop(None)
        except Exception:  # noqa: BLE001
            pass

    out("")
    if fails:
        out("结果：失败 %d 项 → 不通过" % len(fails))
        for f in fails:
            out("  - " + f)
        return 1
    out("结果：全部通过（用时加载 → 生成 → 自动卸载 → 再加载）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
