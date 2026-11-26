# -*- coding: utf-8 -*-
"""保存改动（persist）端到端测试：改模型/分辨率/种子 → 写回工作流 json → 再生成用新值。

自带假 ComfyUI（8188）与 PM dev server（8797），不依赖真 ComfyUI。
用法：python tools\test_persist.py
"""
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "persist_test.log")
SAMPLE = os.path.join(os.path.dirname(ROOT), "work", "workflows", "moss_image_t2i_api.json")
PORT = int(os.environ.get("PERSIST_PORT", "8797"))
PM = "http://127.0.0.1:%d" % PORT
PY = sys.executable

LINES, FAILS = [], []
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def out(s=""):
    print(s)
    LINES.append(s)


def ok(name, cond, extra=""):
    s = ("OK   " if cond else "FAIL ") + name + ("" if extra == "" else "  " + str(extra))
    out("  " + s)
    if not cond:
        FAILS.append(name)


def req(path, body=None, timeout=90):
    url = PM + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    rq = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


class Fake:
    last_prompt = None
    hist_hits = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == "/system_stats":
            return self._j({"devices": [{"name": "Fake RTX", "vram_total": 17179869184}]})
        if p.path.startswith("/history/"):
            pid = p.path.rsplit("/", 1)[-1]
            n = Fake.hist_hits.get(pid, 0)
            Fake.hist_hits[pid] = n + 1
            if n == 0:
                return self._j({})
            return self._j({pid: {"status": {"status_str": "success", "completed": True},
                                  "outputs": {"9": {"images": [{"filename": "persist_out.png", "subfolder": "", "type": "output"}]}}}})
        if p.path == "/view":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG)))
            self.end_headers()
            self.wfile.write(PNG)
            return
        return self._j({}, 404)

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if p.path == "/prompt":
            Fake.last_prompt = json.loads(raw.decode("utf-8")) if raw else {}
            return self._j({"prompt_id": "persist-pid-1"})
        if p.path == "/upload/image":
            m = re.search(rb'filename="([^"]+)"', raw)
            name = m.group(1).decode() if m else "x.png"
            return self._j({"name": name, "subfolder": "", "type": "input"})
        return self._j({}, 404)


def wait_port(port, secs=40):
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            with socket.create_connection(("127.0.0.1", port), 1):
                return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def main():
    if not os.path.isfile(SAMPLE):
        out("缺少样本：" + SAMPLE)
        return 1
    if not wait_port(8188, 1):
        fake = ThreadingHTTPServer(("127.0.0.1", 8188), Handler)
        threading.Thread(target=fake.serve_forever, daemon=True).start()
        out("假 ComfyUI 已起 :8188")

    # 清场：只删本测试用的工作流
    pm2 = os.path.join(ROOT, "data", "plugins", "comfy_runner")
    if os.path.isdir(pm2):
        shutil.rmtree(pm2, ignore_errors=True)
    env = dict(os.environ)
    env["PORT"] = str(PORT)
    env["PYTHONUTF8"] = "1"
    pm = subprocess.Popen([PY, os.path.join("src", "app.py")], cwd=ROOT, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          creationflags=0x00000200)
    try:
        if not wait_port(PORT, 60):
            out("PM 服务没起来")
            return 1
        out("\n== 保存改动（persist） ==")

        # 信任插件
        st, j = req("/api/plugins")
        ids = [p.get("id") for p in (j.get("plugins") or []) if p.get("id") == "comfy_runner"]
        if ids:
            req("/api/plugins/trust", {"id": "comfy_runner"})
            req("/api/plugins/reload", {})

        raw = io.open(SAMPLE, encoding="utf-8").read()
        st, j = req("/api/plugin/comfy_runner/import", {"workflow": json.loads(raw), "name": "保存测试"})
        it = j.get("item") or {}
        wid = it.get("id")
        d = it.get("detect") or {}
        sz = d.get("size") or {}
        ok("导入 moss 样本", j.get("ok") is True, j.get("error"))
        ok("初始分辨率 1360x768", (sz.get("width"), sz.get("height")) == (1360, 768),
           (sz.get("width"), sz.get("height")))
        models0 = {m.get("field"): m.get("value") for m in (d.get("models") or [])}
        ok("初始 unet 是 moss_image_sft", str(models0.get("unet_name", "")).startswith("moss_image_sft"),
           models0.get("unet_name"))

        # 保存改动
        st, j = req("/api/plugin/comfy_runner/persist", {
            "id": wid, "width": 832, "height": 1216, "seed": 424242,
            "models": [{"node": "18:1", "field": "unet_name", "value": "SAVED-UNET.safetensors"}],
        })
        ch = j.get("changed") or []
        ok("persist 成功", j.get("ok") is True, j.get("error"))
        ok("persist 列出分辨率改动", any("分辨率" in c for c in ch), ch)
        ok("persist 列出模型改动", any("模型" in c for c in ch), ch)
        ok("persist 列出种子改动", any("种子" in c for c in ch), ch)

        # 磁盘校验
        wfp = os.path.join(pm2, "wf", str(wid) + ".json")
        if not os.path.isfile(wfp):
            ok("工作流文件已落盘", False, wfp)
            raise SystemExit(1)
        g = json.load(io.open(wfp, encoding="utf-8"))
        ok("磁盘文件 unet 已换", g["18:1"]["inputs"]["unet_name"] == "SAVED-UNET.safetensors",
           g["18:1"]["inputs"]["unet_name"])
        ok("磁盘文件 seed 已换", g["18:7"]["inputs"]["seed"] == 424242, g["18:7"]["inputs"]["seed"])
        ar = str(g["19"]["inputs"]["aspect_ratio"])
        ok("磁盘文件比例变 2:3", "2:3" in ar, ar)
        mp = float(g["19"]["inputs"].get("megapixels") or 0)
        ok("megapixels 约 0.97MP", 0.9 < mp < 1.05, mp)

        # detail 复查（快照也更新了）
        st, j = req("/api/plugin/comfy_runner/detail?id=" + urllib.parse.quote(str(wid)))
        it2 = j.get("item") or {}
        ok("detail 里 saved 时间戳有值", (it2.get("saved") or 0) > 0, it2.get("saved"))
        m2 = {m.get("field"): m.get("value") for m in ((it2.get("detect") or {}).get("models") or [])}
        ok("detail 里 unet 已是新值", m2.get("unet_name") == "SAVED-UNET.safetensors", m2.get("unet_name"))

        # 用保存后的工作流生成一次
        st, j = req("/api/plugin/comfy_runner/run", {"id": wid, "prompt": "保存后生成 PERSIST-OK"})
        ok("保存后再生成成功", j.get("ok") is True, j.get("error"))
        gp = Fake.last_prompt or {}
        gp = gp.get("prompt") or gp
        ok("提交图用的是保存后的 unet",
           ((gp.get("18:1") or {}).get("inputs") or {}).get("unet_name") == "SAVED-UNET.safetensors",
           ((gp.get("18:1") or {}).get("inputs") or {}).get("unet_name"))
        ok("提交图用的是保存后的 seed",
           ((gp.get("18:7") or {}).get("inputs") or {}).get("seed") == 424242,
           ((gp.get("18:7") or {}).get("inputs") or {}).get("seed"))

        # 空改动提示
        st, j = req("/api/plugin/comfy_runner/persist", {"id": wid})
        ok("没有改动时返回空 changed", (j.get("changed") or []) == [], j.get("changed"))
    finally:
        try:
            pm.terminate()
            pm.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass

    out("\n结果：共 %d 项，失败 %d 项 → %s" % (
        len(LINES) - len([l for l in LINES if l.startswith("==")]) - 1 + 0, len(FAILS),
        "通过" if not FAILS else "不通过"))
    with io.open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
