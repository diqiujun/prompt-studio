# -*- coding: utf-8 -*-
r"""给侧栏里的 ComfyUI 面板截图（headless Edge）。

起本体服务 → 信任 comfy_runner → 导入 minimax 样本 → Edge 截图（?theme=dark&sbar=comfy_runner）。
用法：python tools\shot_comfy.py [--theme dark] [--out data\ui_comfy_sidebar.png]
"""
import argparse
import json
import shutil
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("PM_PORT", "8799"))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def http(path, body=None, timeout=120):
    url = "http://127.0.0.1:%d%s" % (PORT, path)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", default="dark")
    ap.add_argument("--out", default=os.path.join("data", "ui_comfy_sidebar.png"))
    ap.add_argument("--size", default="1500,1200")
    ap.add_argument("--sample", default="work\\workflows\\minimax_h3_director_api.json")
    ap.add_argument("--name", default="MiniMax 导演台")
    ap.add_argument("--extra", default="", help="追加到 URL 的查询串，如 &allnodes=1")
    ap.add_argument("--only", action="store_true", help="临时清空已导入的工作流，只留这一个（截图用，结束后恢复）")
    a = ap.parse_args()

    env = dict(os.environ)
    env["PORT"] = str(PORT)
    env["PYTHONUTF8"] = "1"
    flags = 0x00000200 if os.name == "nt" else 0
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "src", "app.py")],
                           cwd=ROOT, env=env, creationflags=flags,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bak = os.path.join(ROOT, "data", "_wf_bak")
    src = os.path.join(ROOT, "data", "plugins", "comfy_runner")
    moved = False
    if a.only:
        shutil.rmtree(bak, ignore_errors=True)
        if os.path.exists(src):
            shutil.move(src, bak)
            moved = True
    try:
        for _ in range(60):
            try:
                http("/api/state", timeout=3)
                break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        print("trust:", http("/api/plugins/trust", {"id": "comfy_runner"}).get("ok"))
        sample = os.path.join(os.path.dirname(ROOT), a.sample) if not os.path.isabs(a.sample) else a.sample
        if os.path.exists(sample):
            with open(sample, "r", encoding="utf-8") as f:
                wf = json.load(f)
            r = http("/api/plugin/comfy_runner/import", {"workflow": wf, "name": a.name})
            print("import:", r.get("ok"), r.get("error") or "")
        w, h = a.size.split(",")
        out = os.path.join(ROOT, a.out)
        cmd = [EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
               "--user-data-dir=" + os.path.join(ROOT, "data", "_edge_sb"),
               "--window-size=%s,%s" % (w, h), "--virtual-time-budget=6000",
               "--screenshot=" + out,
               "http://127.0.0.1:%d/?theme=%s&tab=plug-comfy_runner%s" % (PORT, a.theme, a.extra)]
        subprocess.run(cmd, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("shot:", out, os.path.getsize(out) if os.path.exists(out) else "MISSING")
    finally:
        try:
            srv.terminate()
            srv.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        if moved:
            shutil.rmtree(src, ignore_errors=True)
            shutil.move(bak, src)
    return 0


if __name__ == "__main__":
    sys.exit(main())

