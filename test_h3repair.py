# -*- coding: utf-8 -*-
"""验证 H3 格式自动修补：本地小模型漏 <d>/[Shot 1] 时能否补回来。

用法：python test_h3repair.py
日志：data/h3repair.log
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("SPEC_PORT") or 8762)
BASE = "http://127.0.0.1:%d" % PORT
LOG = os.path.join(ROOT, "data", "h3repair.log")


def log(msg):
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def post(path, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    open(LOG, "w", encoding="utf-8").close()
    env = dict(os.environ)
    env["PORT"] = str(PORT)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen([sys.executable, os.path.join("src", "app.py")],
                            cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0x00000200)
    fails = []
    try:
        ok = False
        for _ in range(90):
            try:
                get("/api/state")
                ok = True
                break
            except Exception:
                time.sleep(1)
        if not ok:
            log("[FAIL] 开发服务没起来")
            return 1
        log("[OK] 开发服务 http://127.0.0.1:%d/ 已就绪" % PORT)

        # 先把本地模型拉起来并等它就绪（自带 autostart 是异步的，这里显式等一下）
        st = post("/api/local/start", {})
        log("本地模型启动：ok=%s pid=%s port=%s" % (st.get("ok"), st.get("pid"), st.get("port")))
        ready = False
        for _ in range(60):
            s = get("/api/local/status")
            if s.get("running"):
                ready = True
                break
            time.sleep(2)
        if not ready:
            log("[FAIL] 本地模型没起来：%s" % str(st)[:300])
            return 1
        log("[OK] 本地模型已就绪 pid=%s" % get("/api/local/status").get("pid"))

        body = {
            "template": "h3_video",
            "provider": "local-gemma",
            "fast": True,
            "content": "沈不违提刀立于雪夜山门前，呼出白气，刀刃上有雪粒反光；镜头从他的靴子慢慢上摇到脸，最后他开口说「都让开」。时长 6 秒。",
            "params": {"mode": "auto", "duration": "6", "aspect": "16:9",
                       "subject_kind": "人物特写", "lang": "中文", "lora": "不加 LoRA"},
        }
        r = post("/api/generate", body)
        if not r.get("ok"):
            log("[FAIL] 生成失败：%s" % str(r)[:400])
            fails.append("生成失败")
        else:
            txt = r.get("content") or ""
            log("生成 %.1fs usage=%s" % (r.get("elapsed") or 0, r.get("usage")))
            log("note=%r" % (r.get("note") or ""))
            log("含 <d>=%s  含 [Shot 1]=%s  六段齐=%s" % (
                "<d>" in txt, "[Shot 1]" in txt,
                all(f in txt for f in ("subject_definitions", "summary",
                                       "detailed_description", "overall_soundscape",
                                       "non_diegetic_music"))))
            log("---- 输出片段 ----")
            log(txt[:1200])
            if "<d>" not in txt:
                fails.append("修补后仍缺 <d>")
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
    log("\n结果：失败 %d 项" % len(fails))
    for f in fails:
        log("  - " + f)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
