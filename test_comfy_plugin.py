"""假 ComfyUI + PM 插件端到端测试。

流程：起假 ComfyUI(8188) → 起 PM dev server → 信任 comfy_runner → 导入两个真实工作流
→ 断言检测结果 → run（图生图带参考图）→ 轮询 status → 取 view → 前端静态断言。

用法：python test_comfy_plugin.py
日志：data\\comfy_test.log
"""
import base64
import json
import io
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "data", "comfy_test.log")
COMFY_PORT = int(os.environ.get("COMFY_PORT", "18188"))
PM_PORT = int(os.environ.get("PM_PORT", "8798"))
PM = "http://127.0.0.1:%d" % PM_PORT

FAILS = []
LINES = []
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")


def out(s=""):
    LINES.append(str(s))
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("gbk", "replace").decode("gbk"))


def bad(name, extra=""):
    FAILS.append(name)
    LINES.append("FAIL " + name + (" " + str(extra) if extra else ""))


def ok(name, cond, extra=""):
    out(("  OK   " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILS.append(name)


def req(path, body=None, timeout=60, raw=False):
    url = path if path.startswith("http") else PM + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    rq = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            b = r.read()
            return r.status, (b if raw else json.loads(b.decode("utf-8", "replace")))
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")[:500]}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


# ----------------------------------------------------------- 假 ComfyUI
class Fake(ThreadingHTTPServer):
    last_prompt = None
    uploads = []
    hist_hits = 0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hist_hits = 0

    def log_message(self, *a):
        pass

    def _send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/system_stats":
            return self._send_json({"devices": [{"name": "Fake RTX 5060 Ti", "vram_total": 17179869184,
                                                 "vram_free": 10737418240}]})
        if p.startswith("/object_info/"):
            cls = p.rsplit("/", 1)[-1]
            if cls == "ResolutionSelector":
                return self._send_json({cls: {"input": {"required": {
                    "aspect_ratio": [["1:1 (Square)", "2:3 (Portrait Photo)", "3:2 (Photo)",
                                      "3:4 (Portrait Standard)", "4:3 (Standard)",
                                      "9:16 (Portrait Widescreen)", "16:9 (Widescreen)",
                                      "21:9 (Ultrawide)"], {}],
                    "megapixels": ["FLOAT", {"default": 1.0, "min": 0.1, "max": 16.0, "step": 0.1}],
                    "multiple": ["INT", {"default": 8, "min": 8, "max": 128, "step": 8}],
                }}, "output": ["INT", "INT"], "output_name": ["width", "height"]}})
            if cls == "KSampler":
                return self._send_json({cls: {"input": {"required": {
                    "model": ["MODEL", {}],
                    "seed": ["INT", {"default": 0, "min": 0, "max": 1 << 50, "step": 1}],
                    "steps": ["INT", {"default": 20, "min": 1, "max": 10000, "step": 1}],
                    "cfg": ["FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1}],
                    "sampler_name": [["euler", "er_sde", "dpmpp_2m"], {}],
                }}, "output": ["LATENT"], "output_name": ["LATENT"]}})
            return self._send_json({"error": "no class " + cls}, 404)
        if p.startswith("/history/"):
            Handler.hist_hits += 1
            pid = p.rsplit("/", 1)[-1]
            if Handler.hist_hits < 2:
                return self._send_json({})          # 第一次：还在跑
            return self._send_json({pid: {
                "status": {"status_str": "success", "completed": True},
                "outputs": {"14": {"images": [{"filename": "fake_out.png", "subfolder": "",
                                               "type": "output"}]}}
            }})
        if p == "/view":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG)))
            self.end_headers()
            self.wfile.write(PNG)
            return
        if p == "/_last":
            return self._send_json(Fake.last_prompt or {})
        if p == "/_uploads":
            return self._send_json({"uploads": Fake.uploads})
        return self._send_json({"error": "no route " + p}, 404)

    def do_POST(self):
        p = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if p == "/prompt":
            try:
                Fake.last_prompt = json.loads(body.decode("utf-8"))
            except ValueError:
                Fake.last_prompt = {}
            Handler.hist_hits = 0
            return self._send_json({"prompt_id": "fake-pid-1", "number": 1})
        if p == "/upload/image":
            m = re.search(rb'filename="([^"]+)"', body)
            name = m.group(1).decode("utf-8", "replace") if m else "x.png"
            Fake.uploads.append(name)
            return self._send_json({"name": name, "subfolder": "", "type": "input"})
        return self._send_json({"error": "no route " + p}, 404)


def start_fake():
    try:
        srv = Fake(("127.0.0.1", COMFY_PORT), Handler)
    except OSError as e:
        out("假 ComfyUI 起不来（端口 %d 被占？）：%s" % (COMFY_PORT, e))
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def start_pm():
    env = dict(os.environ)
    env["PORT"] = str(PM_PORT)
    env["PYTHONUTF8"] = "1"
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "src", "app.py")], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(60):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(PM + "/api/state", timeout=2):
                return p
        except Exception:  # noqa: BLE001
            continue
    return p


def main():
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    # 每次从干净状态开始（否则上一轮存的工作流会让计数断言失效）
    import shutil
    shutil.rmtree(os.path.join(ROOT, "data", "plugins", "comfy_runner"), ignore_errors=True)
    fake = start_fake()
    if not fake:
        return 1
    pm = start_pm()
    try:
        out("== 1. 服务与插件 ==")
        st, j = req("/api/state")
        ok("PM 起来了", st == 200 and j.get("ok") is not False)

        # 信任（幂等）
        st, j = req("/api/plugins/trust", {"id": "comfy_runner"})
        ok("信任 comfy_runner", st == 200 and (j.get("ok") is not False), j.get("error", ""))
        # 插件要连假 ComfyUI，而不是本机真跑着的那个（用户可能在用 ComfyUI）
        st, j = req("/api/plugins/settings", {"id": "comfy_runner",
                                             "values": {"comfy_url": "http://127.0.0.1:%d" % COMFY_PORT}})
        ok("插件指向假 ComfyUI", st == 200 and (j.get("ok") is not False), str(j)[:120])
        st, j = req("/api/plugins/reload", {})
        st, j = req("/api/plugins")
        items = j.get("plugins") or j.get("items") or []
        me = next((x for x in items if x.get("id") == "comfy_runner"), None)
        ok("插件列表里有 comfy_runner", bool(me))
        ok("插件已加载", bool(me) and me.get("status") == "loaded",
           (me or {}).get("status"))
        web = (me or {}).get("web") or {}
        ok("web 面板声明生效", bool(web.get("js")), web.get("js"))
        routes = (me or {}).get("routes") or []
        ok("接口 8 个", len(routes) >= 8, [r.get("path") if isinstance(r, dict) else r for r in routes])

        out("\n== 2. ping ==")
        st, j = req("/api/plugin/comfy_runner/ping")
        ok("ping 通", j.get("ok") is True, j.get("device"))
        ok("GPU 名取到", "Fake" in str(j.get("device")), j.get("device"))

        out("\n== 3. 导入真实工作流 ==")
        zimg = os.path.join(os.path.dirname(ROOT), "work", "workflows", "z_image_img2img_6batch.json")
        if not os.path.exists(zimg):
            zimg = os.path.join(os.path.dirname(ROOT), "work", "workflows", "z_image_img2img_6batch.json")
        with open(zimg, "r", encoding="utf-8") as f:
            zg = json.load(f)
        st, j = req("/api/plugin/comfy_runner/import", {"workflow": zg, "name": "Z-Image 洗图"})
        ok("导入 z_image", j.get("ok") is True, j.get("error"))
        zi = j.get("item") or {}
        d = zi.get("detect") or {}
        ok("z_image kind=image", zi.get("kind") == "image", zi.get("kind"))
        ok("z_image mode=i2i（6 张参考图）", zi.get("mode") == "i2i", zi.get("mode"))
        ok("z_image 提示词定位到 CLIPTextEncode", (d.get("prompt") or {}).get("node") == "4", d.get("prompt"))
        ok("z_image 参考图 6 个", len(d.get("load_images") or []) == 6, len(d.get("load_images") or []))
        ok("z_image 采样参数读到 steps=20", ((d.get("samplers") or [{}])[0] or {}).get("steps") == 20,
           (d.get("samplers") or [{}])[0])

        qimg = os.path.join(os.path.dirname(ROOT), "work", "workflows", "qwen_image_2_1_edit_api.json")
        qd = None
        if os.path.exists(qimg):
            with open(qimg, "r", encoding="utf-8") as f:
                qg = json.load(f)
            st, j = req("/api/plugin/comfy_runner/import", {"workflow": qg, "name": "Qwen 编辑"})
            ok("导入 qwen", j.get("ok") is True, j.get("error"))
            qi = j.get("item") or {}
            qd = qi.get("detect") or {}
            ok("qwen kind=image", qi.get("kind") == "image", qi.get("kind"))
            ok("qwen 提示词落在文本节点上",
               (qd.get("prompt") or {}).get("node") in [t["node"] for t in (qd.get("texts") or [])],
               qd.get("prompt"))
            ok("qwen 多文本节点时提示可改选", "可改选" in (qd.get("note") or ""), qd.get("note"))
            ok("qwen 画幅 1024x1024", (qd.get("size") or {}).get("width") == 1024, (qd.get("size") or {}))
        else:
            out("  (跳过 qwen：样本不存在 %s)" % qimg)

        out("\n== 3b. 复合节点工作流（MiniMax H3 导演台：提示词藏在 timeline_data 里）==")
        mmin = os.path.join(os.path.dirname(ROOT), "work", "workflows", "minimax_h3_director_api.json")
        mid = None
        if os.path.exists(mmin):
            with open(mmin, "r", encoding="utf-8") as f:
                mg = json.load(f)
            st, j = req("/api/plugin/comfy_runner/import", {"workflow": mg, "name": "MiniMax 导演台"})
            ok("导入 minimax", j.get("ok") is True, j.get("error"))
            mi = j.get("item") or {}
            mid = mi.get("id")
            md = mi.get("detect") or {}
            mp = md.get("prompt") or {}
            ok("minimax kind=video", mi.get("kind") == "video", mi.get("kind"))
            ok("minimax mode=t2v", mi.get("mode") == "t2v", mi.get("mode"))
            ok("提示词定位到复合节点 1 的 timeline_data", mp.get("node") == "1" and mp.get("field") == "timeline_data", mp)
            ok("提示词路径 = segments[0].prompt", mp.get("path") == "segments[0].prompt", mp.get("path"))
            ok("注释说明提示词在 JSON 里", "复合节点" in (md.get("note") or ""), md.get("note"))
            ok("分辨率回退读到 864×480",
               (md.get("size") or {}).get("width") == 864 and (md.get("size") or {}).get("height") == 480,
               md.get("size"))
            lh = md.get("length") or {}
            ok("时长 124 帧 @24fps", lh.get("frames") == 124 and lh.get("fps") == 24.0, lh)
            st, j = req("/api/plugin/comfy_runner/save", {
                "id": mid, "name": "MiniMax 导演台",
                "slots": {"prompt": {"node": "1", "field": "timeline_data", "path": "segments[0].prompt"}},
            })
            ok("保存带 path 的槽位", j.get("ok") is True, j.get("error"))
            st, j = req("/api/plugin/comfy_runner/run", {
                "id": mid, "prompt": "复合节点提示词 MINIMAX-TEST-7", "mode": "t2v",
                "duration": 4, "width": 1024, "height": 576,
            })
            ok("minimax 提交成功", j.get("ok") is True, j.get("error"))
            time.sleep(0.4)
            g2 = (Fake.last_prompt or {}).get("prompt") or {}
            n1 = ((g2.get("1") or {}).get("inputs") or {})
            tl = {}
            try:
                tl = json.loads(n1.get("timeline_data") or "{}")
            except ValueError:
                tl = {}
            seg = (tl.get("segments") or [{}])[0] or {}
            ok("提示词写进 timeline_data.segments[0].prompt", seg.get("prompt") == "复合节点提示词 MINIMAX-TEST-7",
               str(seg.get("prompt"))[:60])
            ok("timeline 总帧数同步成 96（4 秒 ×24）", tl.get("totalFrames") == 96, tl.get("totalFrames"))
            ok("画幅写到节点 1 的 width/height", n1.get("width") == 1024 and n1.get("height") == 576,
               (n1.get("width"), n1.get("height")))
        else:
            out("  (跳过 minimax：样本不存在 %s)" % mmin)

        out("\n== 3c. 导演台提示词副本同步（global_prompt ↔ timeline_data.global.prompt）==")
        t2v = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "work", "workflows", "dir_api", "minimax_h3_director_t2v_api.json")
        if os.path.exists(t2v):
            body2 = io.open(t2v, encoding="utf-8-sig").read()
            st, r2 = req("/api/plugin/comfy_runner/import", {"json": body2, "name": "导演台 T2V 同步"})
            ok("t2v 样本导入", r2.get("ok") is True, r2.get("error"))
            it2 = r2.get("item") or {}
            d2 = it2.get("detect") or {}
            p2 = d2.get("prompt") or {}
            ok("t2v 提示词落在 global_prompt（timeline 段为空）",
               p2.get("field") == "global_prompt", (p2.get("field"), p2.get("path")))
            st, r3 = req("/api/plugin/comfy_runner/run", {
                "id": it2.get("id"), "prompt": "导演台同步测试 TWIN-2026",
            })
            ok("t2v 提交成功", r3.get("ok") is True, r3.get("error"))
            time.sleep(0.4)
            g3 = (Fake.last_prompt or {}).get("prompt") or {}
            n5 = ((g3.get("5") or {}).get("inputs") or {})
            tl5 = {}
            try:
                tl5 = json.loads(n5.get("timeline_data") or "{}")
            except ValueError:
                tl5 = {}
            gp = ((tl5.get("global") or {}).get("prompt")) or ""
            ok("inputs.global_prompt 写入", n5.get("global_prompt") == "导演台同步测试 TWIN-2026",
               str(n5.get("global_prompt"))[:40])
            ok("timeline_data.global.prompt 同步写入", gp == "导演台同步测试 TWIN-2026", gp[:40])
            req("/api/plugin/comfy_runner/delete", {"id": it2.get("id")})   # 清掉，别影响后面的清单计数
        else:
            out("  (跳过 3c：样本不存在 %s)" % t2v)

        out("\n== 4. run + 组图 ==")
        st, j = req("/api/plugin/comfy_runner/workflows")
        want = 2 + (1 if mid else 0)
        ok("工作流清单 %d 条" % want, j.get("count") == want, j.get("count"))
        zid = zi.get("id")
        ref = "data:image/png;base64," + base64.b64encode(PNG).decode()
        st, j = req("/api/plugin/comfy_runner/run", {
            "id": zid, "prompt": "测试提示词 COMFY-TEST-9", "mode": "i2i",
            "width": 832, "height": 1216, "images": [{"name": "ref1", "data_url": ref}],
        })
        ok("提交成功", j.get("ok") is True, j.get("error"))
        pid = j.get("prompt_id")
        ok("拿到 prompt_id", pid == "fake-pid-1", pid)
        ok("用到的槽位里有提示词", "提示词" in (j.get("used") or []), j.get("used"))
        time.sleep(0.4)
        lp = Fake.last_prompt or {}
        g = lp.get("prompt") or {}
        ok("提交图带 client_id", bool(lp.get("client_id")), lp.get("client_id"))
        ok("提示词已写进 4.text", ((g.get("4") or {}).get("inputs") or {}).get("text") == "测试提示词 COMFY-TEST-9",
           ((g.get("4") or {}).get("inputs") or {}).get("text"))
        ok("步数沿用工作流（20）", ((g.get("2") or {}).get("inputs") or {}).get("steps") == 20,
           ((g.get("2") or {}).get("inputs") or {}).get("steps"))
        li = ((g.get("8") or {}).get("inputs") or {}).get("image")
        ok("参考图上传并回填 LoadImage", bool(li) and str(li).startswith("pm_"), li)
        ok("上传接口收到文件", len(Fake.uploads) >= 1, Fake.uploads)
        # z_image 工作流本身没有分辨率节点（尺寸由输入图决定）→ 改分辨率应自动插 ImageScale
        scales = {k: (v.get("inputs") or {}) for k, v in g.items()
                  if (v or {}).get("class_type") == "ImageScale"}
        ok("没有分辨率节点的工作流自动插了缩放", len(scales) >= 1, "%d 个 ImageScale" % len(scales))
        ok("缩放尺寸 = 面板填的 832×1216",
           bool(scales) and all(x.get("width") == 832 and x.get("height") == 1216 for x in scales.values()),
           [(x.get("width"), x.get("height")) for x in scales.values()][:3])
        bi = ((g.get("9") or {}).get("inputs") or {})
        ok("组图节点的输入改指向新缩放节点",
           any(isinstance(v, list) and str(v[0]) in scales for v in bi.values()),
           {k: v for k, v in list(bi.items())[:2]})
        ok("分辨率进 used 列表", "分辨率" in (j.get("used") or []), j.get("used"))

        out("\n== 4b. 像素（MP）预设 ==")
        st, j = req("/api/plugin/comfy_runner/detail?id=" + urllib.parse.quote(zid))
        dz = (j.get("item") or {}).get("detect") or {}
        pz = dz.get("presets") or {}
        ok("预设清单里有图片分辨率", len(pz.get("image") or []) >= 5, len(pz.get("image") or []))
        ok("预设清单里有视频分辨率", len(pz.get("video") or []) >= 5, len(pz.get("video") or []))
        ok("detect 给了当前 MP", abs(float((dz.get("size") or {}).get("mp") or 0) - 1.05) < 0.5,
           (dz.get("size") or {}).get("mp"))
        ok("detect 给了宽高比", abs(float((dz.get("size") or {}).get("ratio") or 0) - 1.0) < 0.01,
           (dz.get("size") or {}).get("ratio"))
        st, j = req("/api/plugin/comfy_runner/run", {
            "id": zid, "prompt": "MP 测试", "mp": 2.0,
            "images": [{"name": "ref1", "data_url": ref}],
        })
        ok("只给 mp 也能提交", j.get("ok") is True, j.get("error"))
        time.sleep(0.4)
        g2 = (Fake.last_prompt or {}).get("prompt") or {}
        sc2 = [(v.get("inputs") or {}) for v in g2.values()
               if (v or {}).get("class_type") == "ImageScale"]
        ok("mp=2 自动插了缩放", len(sc2) >= 1, len(sc2))
        if sc2:
            w2, h2 = sc2[0].get("width"), sc2[0].get("height")
            ok("mp=2 换成 2.0MP 附近（≤5% 误差）",
               abs(w2 * h2 / 1000000.0 - 2.0) < 0.1, "%s×%s=%.2fMP" % (w2, h2, w2 * h2 / 1e6))
            ok("mp 换算的宽高都是 8 的倍数", w2 % 8 == 0 and h2 % 8 == 0, (w2, h2))
        ok("used 里写明像素", any("MP" in str(x) for x in (j.get("used") or [])), j.get("used"))
        ok("返回里带实际尺寸", bool((j.get("size") or {}).get("width")), j.get("size"))

        out("\n== 5. 轮询与产物 ==")
        st, j = req("/api/plugin/comfy_runner/status?prompt_id=fake-pid-1")
        ok("第一次 running", j.get("state") in ("running", "done"), j.get("state"))
        time.sleep(1.2)
        st, j = req("/api/plugin/comfy_runner/status?prompt_id=fake-pid-1")
        ok("最终 done", j.get("state") == "done", j.get("state"))
        outs = j.get("outputs") or []
        ok("有 1 个产物", len(outs) == 1, len(outs))
        ok("产物有 url", bool(outs) and "view?" in str(outs[0].get("url")), (outs or [{}])[0].get("url"))

        url = (outs or [{}])[0].get("url") or ""
        st, body_raw = req(url, raw=True)
        is_png = isinstance(body_raw, (bytes, bytearray)) and bytes(body_raw[:4]) == b"\x89PNG"
        ok("view 返回真图片流（PNG 字节）", st == 200 and is_png, (st, len(body_raw) if isinstance(body_raw, (bytes, bytearray)) else 0))
        cached = os.path.join(ROOT, "data", "plugins", "comfy_runner", "out", "fake-pid-1", "fake_out.png")
        ok("产物已落盘到 out/", os.path.exists(cached) and os.path.getsize(cached) > 0, os.path.getsize(cached) if os.path.exists(cached) else -1)

        out("\n== 6. 保存映射 / 删除 ==")
        st, j = req("/api/plugin/comfy_runner/save", {"id": zid, "name": "Z-Image 洗图（改名）"})
        ok("改名成功", j.get("ok") is True and (j.get("item") or {}).get("name", "").endswith("（改名）"),
           (j.get("item") or {}).get("name"))
        if qd:
            st, j = req("/api/plugin/comfy_runner/workflows")
            qid = [x for x in (j.get("items") or []) if x.get("name") == "Qwen 编辑"]
            if qid:
                before = len(j.get("items") or [])
                st, j = req("/api/plugin/comfy_runner/delete", {"id": qid[0]["id"]})
                ok("删除成功", len(j.get("items") or []) == before - 1, len(j.get("items") or []))

        out("\n== 7. 前端静态 ==")
        dep = os.path.join(ROOT, "plugins", "comfy_runner")
        pj = json.load(open(os.path.join(dep, "plugin.json"), encoding="utf-8"))
        ok("plugin.json 有 web", bool((pj.get("web") or {}).get("js")), (pj.get("web") or {}).get("js"))
        ok("web.mount = page（独立主界面页）", (pj.get("web") or {}).get("mount") == "page", (pj.get("web") or {}).get("mount"))
        for f in ("plugin.py", "web/panel.js", "web/panel.css", "plugin.json"):
            ok("文件存在 %s" % f, os.path.exists(os.path.join(dep, f)))
        js = open(os.path.join(dep, "web", "panel.js"), encoding="utf-8").read()
        ok("panel.js 注册面板", "PSPlugin.addPanel" in js and 'id: "comfy_runner"' in js)
        ok("panel.js 挂到 page", 'mount: "page"' in js)
        ok("panel.js 两页签", '"imp"' in js and '"gen"' in js)
        ok("panel.js 提交 / 轮询", "run" in js and "status?prompt_id=" in js)
        ok("panel.js 取内容描述", "#content" in js)
        css = open(os.path.join(dep, "web", "panel.css"), encoding="utf-8").read()
        ok("css 覆盖 panel.js 用到的类", all(c in css for c in (".cr-tabs", ".cr-drop", ".cr-media", ".cr-prog", ".cr-err")))

        st, j = req("/api/plugin-static/comfy_runner/web/panel.js", raw=True)
        if isinstance(j, dict):
            j = b""
        ok("面板 js 可经静态路由取到", len(j) > 5000, len(j))

        out("\n== 8. 出错路径 ==")
        st, j = req("/api/plugin/comfy_runner/import", {"json": "not json{"})
        ok("坏 JSON 给中文提示", j.get("ok") is False and "JSON" in str(j.get("error")), j.get("error"))
        st, j = req("/api/plugin/comfy_runner/import", {"workflow": {"a": {"inputs": {}}}})
        ok("非 API 格式给中文提示", j.get("ok") is False and "导出（API）" in str(j.get("error")), j.get("error"))
        st, j = req("/api/plugin/comfy_runner/run", {"id": "nope"})
        ok("不存在的工作流报错", j.get("ok") is False, j.get("error"))

        out("\n== 9. 导演台多模式 ==")
        DIR = os.path.join(ROOT, "work", "workflows", "dir_api")
        want = {
            "minimax_h3_director_t2v_api.json": ("t2v", "文生视频"),
            "minimax_h3_director_fl2v_api.json": ("fl2v", "首尾帧生视频"),
            "minimax_h3_director_r2v_api.json": ("r2v", "参考主体生视频"),
            "minimax_h3_director_v2v_api.json": ("v2v", "视频转视频"),
            "minimax_h3_director_rv2v_api.json": ("rv2v", "参考素材改视频"),
            "minimax_h3_director_external_groups_i2v_api.json": ("fl2v", "首尾帧生视频"),
            "minimax_h3_director_external_groups_r2v_api.json": ("r2v", "参考主体生视频"),
        }
        ids = {}
        for fn, (mode, label) in want.items():
            p = os.path.join(DIR, fn)
            if not os.path.exists(p):
                ok("样本存在 %s" % fn, False, "缺文件")
                continue
            txt = open(p, encoding="utf-8").read()
            st, j = req("/api/plugin/comfy_runner/import", {"json": txt, "name": fn.replace("_api.json", "")})
            it = j.get("item") or {}
            d = it.get("detect") or {}
            ids[fn] = it.get("id")
            ok("识别 %s → %s" % (fn.replace("minimax_h3_director_", "").replace("_api.json", ""), mode),
               j.get("ok") is True and it.get("mode") == mode and d.get("mode_from") == "导演台 task_type",
               "%s / %s / %s" % (it.get("mode"), (d or {}).get("mode_from"), (d or {}).get("mode_label")))
            ok("  中文名 %s" % label, (d.get("mode_label") or "") == label, d.get("mode_label"))

        # r2v 外部组：5 个参考图槽
        p = os.path.join(DIR, "minimax_h3_director_external_groups_r2v_api.json")
        st, j = req("/api/plugin/comfy_runner/detail?id=%s" % ids.get(os.path.basename(p), ""))
        d = (j.get("item") or {}).get("detect") or j.get("detect") or {}
        refs = d.get("refs") or []
        ok("r2v 认出 5 个参考图槽", len(refs) == 5, [r.get("label") for r in refs])
        ok("槽标签带组号", all("组" in (r.get("label") or "") for r in refs),
           [r.get("label") for r in refs][:3])

        # i2v 外部组：含首帧/尾帧 + 有空槽
        p2 = os.path.join(DIR, "minimax_h3_director_external_groups_i2v_api.json")
        st, j = req("/api/plugin/comfy_runner/detail?id=%s" % ids.get(os.path.basename(p2), ""))
        d2 = (j.get("item") or {}).get("detect") or j.get("detect") or {}
        refs2 = d2.get("refs") or []
        labels2 = [r.get("label") or "" for r in refs2]
        ok("i2v 外部组认出首帧/尾帧", any("首帧" in x for x in labels2) and any("尾帧" in x for x in labels2), labels2[:6])
        ok("存在空槽（生成时自动新建）", any(r.get("empty") for r in refs2),
           [r.get("label") for r in refs2 if r.get("empty")])

        # 端到端：给 i2v 外部组上传 2 张图，检查进了组槽
        if ids.get(os.path.basename(p2)):
            before = len(Fake.uploads)
            st, j = req("/api/plugin/comfy_runner/run", {
                "id": ids[os.path.basename(p2)], "prompt": "外部组测试 EXT-GRP-5", "duration": 5,
                "images": [{"name": "a", "data_url": ref}, {"name": "b", "data_url": ref}],
            })
            ok("外部组 run 提交成功", j.get("ok") is True, j.get("error"))
            used = " ".join(j.get("used") or [])
            ok("回填提示带槽位名", ("首帧" in used) or ("参考图" in used), used[:120])
            ok("上传了 2 张", len(Fake.uploads) - before == 2, Fake.uploads[before:])
            g = (Fake.last_prompt or {}).get("prompt") or Fake.last_prompt or {}
            im18 = ((g.get("18") or {}).get("inputs") or {}).get("image") if isinstance(g, dict) else None
            ok("组槽 18 被写成上传图", bool(im18) and str(im18).startswith("pm_"), im18)

        # == 10. ResolutionSelector / 模型 / LoRA ==
        out("\n== 10. 分辨率节点 · 模型 · LoRA ==")
        moss = os.path.join(os.path.dirname(ROOT), "work", "workflows", "moss_image_t2i_api.json")
        if os.path.exists(moss):
            with open(moss, "r", encoding="utf-8") as f:
                mg = json.load(f)
            st, j = req("/api/plugin/comfy_runner/import", {"workflow": mg, "name": "MOSS 文生图"})
            ok("导入 moss 工作流", j.get("ok") is True, j.get("error"))
            mi = j.get("item") or {}
            md = mi.get("detect") or {}
            msz = md.get("size") or {}
            ok("分辨率取自 ResolutionSelector", msz.get("class") == "ResolutionSelector", msz.get("class"))
            ok("按比例算成 1360×768", msz.get("width") == 1360 and msz.get("height") == 768,
               (msz.get("width"), msz.get("height")))
            ok("分辨率模式=ratio", msz.get("mode") == "ratio", msz.get("mode"))
            kinds = [x.get("field") for x in (md.get("models") or [])]
            ok("认出 3 个模型槽", len(md.get("models") or []) == 3, kinds)
            ok("含 unet/clip/vae", set(kinds) == {"unet_name", "clip_name", "vae_name"}, kinds)
            ok("moss 没有 LoRA", (md.get("loras") or []) == [], md.get("loras"))

            mid = mi.get("id")
            st, j = req("/api/plugin/comfy_runner/run", {
                "id": mid, "prompt": "分辨率测试 MOSS-RES-3", "width": 832, "height": 1216,
                "models": [{"node": "18:1", "field": "unet_name", "value": "FAKE-UNET.safetensors"}],
            })
            ok("moss run 提交成功", j.get("ok") is True, j.get("error"))
            used = " ".join(j.get("used") or [])
            ok("提示按比例算出实际尺寸", "按比例算出" in used, used[:140])
            ok("返回尺寸按比例校正", (j.get("size") or {}).get("width") not in (None, 832),
               j.get("size"))
            g = (Fake.last_prompt or {}).get("prompt") or Fake.last_prompt or {}
            r19 = ((g.get("19") or {}).get("inputs") or {}) if isinstance(g, dict) else {}
            ok("aspect_ratio 写成 2:3", str(r19.get("aspect_ratio") or "").startswith("2:3"),
               r19.get("aspect_ratio"))
            ok("megapixels 落在 0.9–1.0", 0.9 <= float(r19.get("megapixels") or 0) <= 1.0,
               r19.get("megapixels"))
            u1 = ((g.get("18:1") or {}).get("inputs") or {}).get("unet_name") if isinstance(g, dict) else None
            ok("模型选择写回工作流", u1 == "FAKE-UNET.safetensors", u1)
            ok("used 记了模型", "模型×1" in used, used[:140])

        # LoRA：造一个带 LoraLoader 的小图
        lg = {
            "1": {"class_type": "LoraLoader", "inputs": {"lora_name": "add_detail.safetensors",
                                                        "strength_model": 0.8, "strength_clip": 0.8,
                                                        "model": ["2", 0], "clip": ["3", 0]}},
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "base.safetensors"}},
            "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
            "4": {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": "x"}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["3", 0]}},
            "6": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20, "positive": ["5", 0]}},
        }
        st, j = req("/api/plugin/comfy_runner/import", {"workflow": lg, "name": "带 LoRA"})
        ok("导入带 LoRA 工作流", j.get("ok") is True, j.get("error"))
        li = j.get("item") or {}
        ld = li.get("detect") or {}
        ok("认出 1 个 LoRA", len(ld.get("loras") or []) == 1, ld.get("loras"))
        ok("LoRA 名称正确", ((ld.get("loras") or [{}])[0] or {}).get("name") == "add_detail.safetensors",
           (ld.get("loras") or [{}])[0])
        st, j = req("/api/plugin/comfy_runner/run", {
            "id": li.get("id"), "prompt": "lora 测试",
            "loras": [{"node": "1", "strength_model": 0.55, "strength_clip": 0.35}],
        })
        ok("LoRA run 提交成功", j.get("ok") is True, j.get("error"))
        g = (Fake.last_prompt or {}).get("prompt") or Fake.last_prompt or {}
        l1 = ((g.get("1") or {}).get("inputs") or {}) if isinstance(g, dict) else {}
        ok("LoRA 模型强度写回", abs(float(l1.get("strength_model") or 0) - 0.55) < 1e-6, l1.get("strength_model"))
        ok("LoRA 文本强度写回", abs(float(l1.get("strength_clip") or 0) - 0.35) < 1e-6, l1.get("strength_clip"))

        # 假 ComfyUI 没实现 /object_info：接口要给出中文错误而不是崩
        st, j = req("/api/plugin/comfy_runner/options?cls=UNETLoader&field=unet_name")
        ok("模型列表接口不崩", st == 200, st)
        ok("拉不到时给错误说明", (j.get("ok") is False and bool(j.get("error"))) or bool(j.get("options")),
           str(j)[:120])

        # == 11. 多图编辑：参考图槽语义 + 提示词开关旁路 ==
        out("\n== 11. 多图编辑（Qwen 2.1 Edit） ==")
        qp = os.path.join(os.path.dirname(ROOT), "work", "workflows", "qwen_edit_multi_api.json")
        if os.path.exists(qp):
            with open(qp, "r", encoding="utf-8") as f:
                qg = json.load(f)
            st, j = req("/api/plugin/comfy_runner/import", {"workflow": qg, "name": "多图编辑"})
            ok("导入多图编辑工作流", j.get("ok") is True, j.get("error"))
            qi = j.get("item") or {}
            qd = qi.get("detect") or {}
            rl = [x.get("label") for x in (qd.get("refs") or [])]
            ok("多图槽补到上限 9 个", len(rl) == 9, rl)
            ok("前三个槽已接图", all("TextEncode" in str(x) for x in rl[:3]), rl[:3])
            ok("空槽标（空）", all("（空）" in str(x) for x in rl[3:]), rl[3:])
            sw = (qd.get("prompt") or {}).get("switch") or {}
            ok("认出提示词开关节点", sw.get("node") == "459:484", sw)
            ok("开关当前是关的", sw.get("on") is False, sw.get("on"))
            ok("note 说明会自动打开", "自动打开" in (qd.get("note") or ""), (qd.get("note") or "")[-60:])

            st, j = req("/api/plugin/comfy_runner/run", {
                "id": qi.get("id"), "prompt": "多图测试 QWEN-MULTI-5",
                "images": [{"name": "p1", "data_url": ref}, {"name": "p2", "data_url": ref},
                           {"name": "p3", "data_url": ref}, {"name": "p4", "data_url": ref},
                           {"name": "p5", "data_url": ref}],
            })
            ok("多图 run 提交成功", j.get("ok") is True, j.get("error"))
            used = " ".join(j.get("used") or [])
            ok("提示已打开开关", "打开提示词开关 459:484" in used, used[:160])
            gp = (Fake.last_prompt or {}).get("prompt") or Fake.last_prompt or {}
            oksw = ((gp.get("459:484") or {}).get("inputs") or {}).get("switch")
            ok("提交图里开关=开", oksw is True, oksw)
            slots = {n: (((gp.get(n) or {}).get("inputs") or {}).get("image") or "")
                     for n in ("470", "475", "502")}
            ok("三张图各进一个 slot", all(str(v).startswith("pm_") for v in slots.values()), slots)
            ok("三张图互不相同", len(set(slots.values())) == 3, slots)
            enc = (gp.get("459:474") or {}).get("inputs") or {}
            new4 = enc.get("images.image_4")
            new5 = enc.get("images.image_5")
            ok("第 4 张图新建了 LoadImage 并接上", isinstance(new4, list) and len(new4) == 2, new4)
            ok("第 5 张图同样接上", isinstance(new5, list) and len(new5) == 2, new5)
            n4 = (gp.get(str(new4[0])) or {}).get("inputs") if isinstance(new4, list) else {}
            n5 = (gp.get(str(new5[0])) or {}).get("inputs") if isinstance(new5, list) else {}
            ok("新建的两个 LoadImage 各带一张上传图",
               str((n4 or {}).get("image", "")).startswith("pm_")
               and str((n5 or {}).get("image", "")).startswith("pm_"), [n4, n5])
        # == 11b. latent 开关：分辨率节点被旁路时改分辨率要能生效 ==
        out("\n== 11b. latent 开关（Qwen 2.1 Edit 原版） ==")
        qp2 = os.path.join(os.path.dirname(ROOT), "work", "workflows", "qwen_image_2_1_edit_api.json")
        if os.path.exists(qp2):
            with open(qp2, "r", encoding="utf-8") as f:
                qg2 = json.load(f)
            st, j = req("/api/plugin/comfy_runner/import", {"workflow": qg2, "name": "原版编辑"})
            ok("导入原版编辑工作流", j.get("ok") is True, j.get("error"))
            q2 = j.get("item") or {}
            d2 = q2.get("detect") or {}
            s2 = d2.get("size") or {}
            sw2 = s2.get("switch") or {}
            ok("认出 latent 开关", sw2.get("node") == "459:468", sw2)
            ok("latent 开关当前是关的", sw2.get("on") is False, sw2.get("on"))
            ok("note 说明会自动切 fixed latent", "latent" in (d2.get("note") or ""), (d2.get("note") or "")[-70:])

            st, j = req("/api/plugin/comfy_runner/run", {
                "id": q2.get("id"), "prompt": "原版测试 QWEN-ORIG-3", "width": 768, "height": 1344,
            })
            ok("原版 run 提交成功", j.get("ok") is True, j.get("error"))
            used2 = " ".join(j.get("used") or [])
            ok("提示已切 latent 开关", "打开latent开关 459:468" in used2, used2[:160])
            gp2 = (Fake.last_prompt or {}).get("prompt") or Fake.last_prompt or {}
            ok("提交图里 latent 开关=开",
               ((gp2.get("459:468") or {}).get("inputs") or {}).get("switch") is True,
               ((gp2.get("459:468") or {}).get("inputs") or {}).get("switch"))
            lat = ((gp2.get("459:456") or {}).get("inputs") or {})
            ok("固定 latent 尺寸被写成 768×1344", (lat.get("width"), lat.get("height")) == (768, 1344),
               (lat.get("width"), lat.get("height")))

        # == 12. 时间轴素材：参考图存在 timeline_data 里（没有 LoadImage） ==
        out("\n== 12. 时间轴素材（导演台 r2v） ==")
        u2 = os.path.join(os.path.dirname(ROOT), "work", "workflows", "unsaved2.json")
        if os.path.exists(u2):
            with open(u2, "r", encoding="utf-8") as f:
                ug = json.load(f)
            st, j = req("/api/plugin/comfy_runner/import", {"workflow": ug, "name": "时间轴多参"})
            ok("导入时间轴多参工作流", j.get("ok") is True, j.get("error"))
            uitem = j.get("item") or {}
            ud = uitem.get("detect") or {}
            ur = ud.get("refs") or []
            ul = [x.get("label") for x in ur]
            ok("时间轴槽补到上限 9 个", len(ur) == 9, ul)
            ok("槽位标出段号与参考图", any(str(x).startswith("段1·参考图1") for x in ul), ul[:3])
            ok("空槽标（空）", sum(1 for x in ul if "（空）" in str(x)) == 8, ul[:3])
            ok("r2v 只留参考图槽（不列首尾帧）",
               not any("首帧" in str(x) or "尾帧" in str(x) for x in ul), ul)
            ok("note 说明写在时间轴里", "时间轴" in (ud.get("note") or ""),
               (ud.get("note") or "")[-60:])

            st, j = req("/api/plugin/comfy_runner/run", {
                "id": uitem.get("id"), "prompt": "时间轴测试 TIMELINE-7",
                "images": [{"name": "t1", "data_url": ref}],
            })
            ok("时间轴 run 提交成功", j.get("ok") is True, j.get("error"))
            used3 = " ".join(j.get("used") or [])
            ok("提示写进时间轴素材", "时间轴素材" in used3, used3[:160])
            gu = (Fake.last_prompt or {}).get("prompt") or Fake.last_prompt or {}
            tl_str = str((((gu.get("1") or {}).get("inputs") or {}).get("timeline_data")) or "")
            fname = ""
            try:
                tlo = json.loads(tl_str)
                fname = ((tlo.get("segments") or [{}])[0].get("refs") or [{}])[0].get("imageFile") or ""
            except Exception:  # noqa: BLE001
                pass
            ok("参考图文件名写回 imageFile", str(fname).startswith("pm_"), fname)

        # == 13. 全部节点：识别 + 读写 ==
        out("\n== 13. 全部节点面板 ==")
        mw = os.path.join(os.path.dirname(ROOT), "work", "workflows", "moss_image_t2i_api.json")
        if os.path.exists(mw):
            with open(mw, "r", encoding="utf-8") as f:
                mg = json.load(f)
            st, j = req("/api/plugin/comfy_runner/import", {"workflow": mg, "name": "MOSS 全节点"})
            ok("导入 MOSS 工作流", j.get("ok") is True, j.get("error"))
            mitem = j.get("item") or {}
            mid = mitem.get("id")

            st, j = req("/api/plugin/comfy_runner/nodes?id=%s" % urllib.parse.quote(str(mid)))
            ok("nodes 接口通", j.get("ok") is True and st == 200, j.get("error"))
            ok("节点数与原图一致", j.get("count") == len(mg), [j.get("count"), len(mg)])
            ok("拿到 ComfyUI 官方定义（online≥2）", int(j.get("online") or 0) >= 2, j.get("online"))
            ok("可改的输入够多", int(j.get("writable") or 0) > 10, j.get("writable"))
            rows = j.get("nodes") or []
            byid = {str(r.get("id")): r for r in rows}
            rs = byid.get("19") or {}
            ai = {i["name"]: i for i in (rs.get("inputs") or [])}
            ok("节点 19 认出 ResolutionSelector", rs.get("class") == "ResolutionSelector", rs.get("class"))
            ok("aspect_ratio 是下拉且 8 个选项",
               (ai.get("aspect_ratio") or {}).get("type") == "combo"
               and len((ai.get("aspect_ratio") or {}).get("options") or []) == 8,
               (ai.get("aspect_ratio") or {}).get("type"))
            ok("megapixels 是数字且带上限 16",
               (ai.get("megapixels") or {}).get("type") == "number"
               and (ai.get("megapixels") or {}).get("max") == 16.0, ai.get("megapixels"))
            ks = byid.get("18:7") or {}
            ki = {i["name"]: i for i in (ks.get("inputs") or [])}
            ok("KSampler 分到采样组", ks.get("cat") == "sampler", ks.get("cat"))
            ok("steps 是数字且 max=10000", (ki.get("steps") or {}).get("max") == 10000, ki.get("steps"))
            ok("sampler_name 是下拉", (ki.get("sampler_name") or {}).get("type") == "combo", ki.get("sampler_name"))
            ok("model 这类连线输入是只读 link", (ki.get("model") or {}).get("type") == "link", ki.get("model"))
            lat = byid.get("18:6") or {}
            li = {i["name"]: i for i in (lat.get("inputs") or [])}
            ok("latent 的 width 显示成连线来源 19",
               (li.get("width") or {}).get("type") == "link"
               and str((li.get("width") or {}).get("from")) == "19", li.get("width"))

            st, j = req("/api/plugin/comfy_runner/setnodes", {"id": mid, "edits": [
                {"node": "18:6", "field": "width", "value": 111}]})
            ok("连线输入写不进去", j.get("changed") in (0, None), j)

            st, j = req("/api/plugin/comfy_runner/setnodes", {"id": mid, "edits": [
                {"node": "18:7", "field": "steps", "value": 33},
                {"node": "18:7", "field": "sampler_name", "value": "dpmpp_2m"},
                {"node": "19", "field": "aspect_ratio", "value": "3:4 (Portrait Standard)"}]})
            ok("setnodes 写入 3 项", j.get("changed") == 3, j)
            st, j2 = req("/api/plugin/comfy_runner/nodes?id=%s" % urllib.parse.quote(str(mid)))
            r2 = {str(r.get("id")): r for r in (j2.get("nodes") or [])}
            v2 = {i["name"]: i.get("value") for i in ((r2.get("18:7") or {}).get("inputs") or [])}
            ok("steps 读回 33", v2.get("steps") == 33, v2.get("steps"))
            ok("sampler_name 读回 dpmpp_2m", v2.get("sampler_name") == "dpmpp_2m", v2.get("sampler_name"))

            st, j = req("/api/plugin/comfy_runner/run", {
                "id": mid, "prompt": "全节点测试 NODES-9",
                "nodes": [{"node": "18:7", "field": "cfg", "value": 4.5}]})
            ok("run 带节点改动提交成功", j.get("ok") is True, j.get("error"))
            ok("used 里记了节点改动", any("节点改动" in str(x) for x in (j.get("used") or [])), j.get("used"))
            gk = (Fake.last_prompt or {}).get("prompt") or Fake.last_prompt or {}
            kk = ((gk.get("18:7") or {}).get("inputs") or {})
            ok("Fake 收到 cfg=4.5", abs(float(kk.get("cfg") or 0) - 4.5) < 1e-6, kk.get("cfg"))
            ok("Fake 收到之前保存的 steps=33", int(kk.get("steps") or 0) == 33, kk.get("steps"))

            # 画布用的拓扑数据：连线 / 分层 / 组 / 复合节点
            edges = j2.get("edges") or []
            layers = j2.get("layers") or []
            ok("nodes 返回连线 edges", isinstance(edges, list) and len(edges) > 10, len(edges))
            ok("每条连线是 [from, slot, to, idx] 四元",
               bool(edges) and isinstance(edges[0], list) and len(edges[0]) == 4, edges[:1])
            ok("nodes 返回分层 layers", isinstance(layers, list) and len(layers) >= 2, len(layers))
            ok("分层里没有重复节点",
               len([x for L in layers for x in L]) == len(set(x for L in layers for x in L)),
               [len(L) for L in layers])
            ok("每层里的节点在原图里都存在",
               all(str(x) in {str(r.get("id")) for r in rows} for L in layers for x in L), True)
            ok("节点带 group 字段（复合节点靠 id 前缀）",
               all("group" in r for r in rows), [r.get("id") for r in rows if "group" not in r])
            ok("画布需要的 complex 字段存在", any("complex" in r for r in rows), None)
            ok("ResolutionSelector 不算复合节点", not rs.get("complex"), rs.get("complex"))
            ok("nodes 返回 cats 供分组标题",
               isinstance(j2.get("cats"), dict) and len(j2.get("cats") or {}) >= 4, j2.get("cats"))

            pj = json.load(open(os.path.join(ROOT, "plugins", "comfy_runner", "plugin.json"), "r", encoding="utf-8"))
            ok("插件改成独立页面 mount=page", (pj.get("web") or {}).get("mount") == "page",
               (pj.get("web") or {}).get("mount"))
            pjs = ""
            with open(os.path.join(ROOT, "plugins", "comfy_runner", "web", "panel.js"), "r", encoding="utf-8") as f:
                pjs = f.read()
            ok("panel.js 声明 mount: page", 'mount: "page"' in pjs, None)
            ok("panel.js 有整页外壳 SHELL", "function SHELL(" in pjs and 'class="cv-bar"' in pjs, None)
            ok("panel.js 有画布渲染 cvDraw", "function cvDraw(" in pjs, None)
            ok("panel.js 有缩放适配 cvFit", "function cvFit(" in pjs, None)

            # == 14. 主界面参考图直接引用（stage 一次，之后只传文件名）==
            out("\n== 14. 主界面参考图直接引用 ==")
            png = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH"
                   "/q842iQAAAABJRU5ErkJggg==")
            durl = "data:image/png;base64," + png
            before = len(Fake.uploads)
            st, j = req("/api/plugin/comfy_runner/stage", {"images": [
                {"name": "pm1", "data_url": durl}, {"name": "pm2", "data_url": durl}]})
            ok("stage 上传两张", j.get("ok") is True and len(j.get("files") or []) == 2, j)
            ok("确实传到 ComfyUI 两张", len(Fake.uploads) - before == 2, Fake.uploads[before:])
            pfiles = [f.get("file") for f in (j.get("files") or [])]
            ok("返回 pm 前缀文件名", len(pfiles) == 2 and all(str(f).startswith("pm") for f in pfiles), pfiles)
            ok("返回预览地址", all("view?" in str(f.get("url")) for f in (j.get("files") or [])),
               (j.get("files") or [{}])[0])

            st, j = req("/api/plugin/comfy_runner/stage", {"images": []})
            ok("没有图时给中文提示", j.get("ok") is False and "参考图" in str(j.get("error")), j)

            before = len(Fake.uploads)
            st, j = req("/api/plugin/comfy_runner/run", {
                "id": mid, "prompt": "PM 参考图直接引用 PMREF", "files": pfiles})
            ok("run 用文件名提交成功", j.get("ok") is True, j.get("error"))
            ok("不再重复上传整图", len(Fake.uploads) == before, Fake.uploads[before:])
            ok("used 记了引用主界面图",
               any("引用主界面图" in str(x) for x in (j.get("used") or [])), j.get("used"))
            # MOSS 是文生图（没有图槽），文件名无处落 → 换带图槽的多图编辑工作流验证填槽
            st, jj = req("/api/plugin/comfy_runner/import",
                         {"workflow": qg, "name": "PM 参考图·多图编辑"})
            pmid = (jj.get("item") or {}).get("id")
            st, j = req("/api/plugin/comfy_runner/run", {
                "id": pmid, "prompt": "PM 参考图填槽 PMREF2", "files": pfiles})
            ok("带图槽的工作流用文件名填槽成功", j.get("ok") is True, j.get("error"))
            gj = json.dumps(Fake.last_prompt or {}, ensure_ascii=False)
            ok("工作流里用上了这两个文件名", pfiles[0] in gj and pfiles[1] in gj, pfiles)

    finally:
        # 把插件的 ComfyUI 地址还原成默认，免得测试把用户配置改成假服务
        try:
            req("/api/plugins/settings", {"id": "comfy_runner",
                                          "values": {"comfy_url": "http://127.0.0.1:8188"}}, timeout=10)
        except Exception:  # noqa: BLE001
            pass
        try:
            pm.terminate()
            pm.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        fake.shutdown()

    out("\n结果：共 %d 项检查，失败 %d 项 → %s" % (
        len(FAILS) + sum(1 for l in LINES if l.strip().startswith("OK")), len(FAILS),
        "通过" if not FAILS else "不通过"))
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
