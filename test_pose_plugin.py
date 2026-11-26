"""姿势库插件（plugins\\pose_gallery）验收：接口 / 静态图 / 前端宿主接线。

用法：python test_pose_plugin.py            # 起 dev server（默认 8797）跑全流程
      SPEC_PORT=8798 python test_pose_plugin.py
日志：data\\pose_plugin_test.log
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
LOG = os.path.join(DATA, "pose_plugin_test.log")
PORT = int(os.environ.get("SPEC_PORT") or 8797)
BASE = "http://127.0.0.1:%d" % PORT
FAILS = []
LINES = []


def out(msg):
    LINES.append(msg)
    print(msg)


def ok(name, extra=""):
    out("OK   %s%s" % (name, ("  " + str(extra)) if extra else ""))


def bad(name, err):
    FAILS.append(name)
    out("FAIL %s  %s" % (name, err))


def http(path, body=None, raw=False, timeout=30):
    url = BASE + path
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        buf = r.read()
        if raw:
            return r.status, buf, r.headers.get("Content-Type")
        return json.loads(buf.decode("utf-8"))


def ensure_server():
    try:
        http("/api/state", timeout=3)
        return None
    except Exception:
        pass
    env = dict(os.environ)
    env["PORT"] = str(PORT)
    env["PYTHONUTF8"] = "1"
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "src", "app.py")],
                         cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=0x08000000)
    for _ in range(60):
        time.sleep(1)
        try:
            http("/api/state", timeout=2)
            return p
        except Exception:
            continue
    raise RuntimeError("dev server 没起来（端口 %d）" % PORT)


def main():
    proc = ensure_server()
    try:
        # 1) 插件被扫描到且已信任（信任门只作用于代码插件）
        pj = http("/api/plugins")
        pg = None
        for p in pj.get("plugins") or []:
            if p.get("id") == "pose_gallery":
                pg = p
                break
        if not pg:
            bad("插件已注册", "插件列表里没有 pose_gallery（%s）" % pj.get("ids"))
            return
        if not pg.get("trusted"):
            http("/api/plugins/trust", {"id": "pose_gallery", "trusted": True})
            http("/api/plugins/reload", {})
            pj = http("/api/plugins")
            pg = [p for p in pj["plugins"] if p.get("id") == "pose_gallery"][0]
        ok("插件已注册", "status=%s · kind=%s · 目录 %s" % (pg.get("status"), pg.get("kind"), pg.get("dir")))

        # 2) web 贡献声明（面板注入的前提）
        web = pg.get("web") or {}
        if not web.get("js") or not web.get("css"):
            bad("web 面板声明", "web 缺失：%s" % web)
        else:
            ok("web 面板声明", "js=%s · css=%s · mount=%s" % (web.get("js"), web.get("css"), web.get("mount")))

        # 3) meta
        gm = http("/api/plugin/pose_gallery/meta")
        meta = gm.get("meta") or gm
        if int(meta.get("count") or 0) < 1000:
            bad("meta 索引", "count=%s" % meta.get("count"))
        else:
            ok("meta 索引", "count=%s · 体系 %d · 分类 %d · 视角 %d · 深度 %s"
               % (meta.get("count"), len(meta.get("systems") or []), len(meta.get("cats") or []),
                  len(meta.get("angles") or []), meta.get("depth_count")))

        # 4) list 默认隐藏性感系
        gl = http("/api/plugin/pose_gallery/list?limit=3")
        items = gl.get("items") or []
        if not items:
            bad("list 列表", "返回 0 条")
        else:
            it = items[0]
            miss = [k for k in ("id", "name", "system", "cat", "angle", "thumb", "ref", "zh")
                    if not it.get(k)]
            if miss:
                bad("list 字段", "缺 %s" % miss)
            else:
                ok("list 列表", "total=%s（默认隐藏性感系）· 首项 %s / %s / %s / %s"
                   % (gl.get("total"), it.get("id"), it.get("system"), it.get("cat"), it.get("angle")))
        gn = http("/api/plugin/pose_gallery/list?limit=3&nsfw=1")
        if int(gn.get("total") or 0) <= int(gl.get("total") or 0):
            bad("性感系开关", "打开后没有变多：%s vs %s" % (gn.get("total"), gl.get("total")))
        else:
            ok("性感系开关", "%s → %s" % (gl.get("total"), gn.get("total")))

        # 5) 搜索与三个筛选
        for label, qs in (("搜索「坐姿」", "q=" + urllib.parse.quote("坐姿")),
                          ("筛选体系", "system=" + urllib.parse.quote("全身单人・标准系")),
                          ("筛选视角", "angle=" + urllib.parse.quote("俯视"))):
            d = http("/api/plugin/pose_gallery/list?limit=3&" + qs)
            if int(d.get("total") or 0) <= 0:
                bad(label, "0 条")
            else:
                ok(label, "%s 条" % d.get("total"))

        # 6) 缩略图 / 参考图 / 深度图静态路由
        tid = items[0]["id"]
        for kind, key in (("缩略图", "thumb"), ("参考图", "ref"), ("深度图", "depth_thumb")):
            rel = (items[0].get(key) or "").split("/data/", 1)[-1]
            if not rel:
                bad(kind, "字段为空")
                continue
            st, buf, ctype = http("/api/plugin-static/pose_gallery/data/" + rel, raw=True)
            if st != 200 or not buf or len(buf) < 500:
                bad(kind, "HTTP %s / %d 字节" % (st, len(buf or b"")))
            else:
                ok(kind, "%s · %d 字节 · %s" % (rel.split("/")[0], len(buf), ctype))

        # 7) 路径穿越被拦
        try:
            http("/api/plugin-static/pose_gallery/../config.json", raw=True, timeout=15)
            bad("路径穿越防护", "居然返回了 200")
        except Exception as e:
            ok("路径穿越防护", "已拦（%s）" % str(e)[:40])

        # 8) detail
        det = http("/api/plugin/pose_gallery/detail?id=" + tid)
        item = det.get("item") or det
        if not item.get("id"):
            bad("detail 详情", "返回 %s" % det)
        else:
            ok("detail 详情", "%s · %s" % (item.get("id"), item.get("zh") or item.get("name")))

        # 9) 前端宿主接线
        html = urllib.request.urlopen(BASE + "/", timeout=20).read().decode("utf-8", "replace")
        js = urllib.request.urlopen(BASE + "/static/app.js", timeout=20).read().decode("utf-8", "replace")
        miss = []
        if 'id="pluginPanels"' not in html:
            miss.append("html 缺 #pluginPanels")
        if 'id="pluginPanelsCfg"' not in html:
            miss.append("html 缺 #pluginPanelsCfg")
        for k in ("PSPlugin", "addPanel", "insertImage", "mountAll", "pluginPanels"):
            if k not in js:
                miss.append("app.js 缺 " + k)
        if "poseGrid" in html or "galleryInit" in js:
            miss.append("内置姿势库残留")
        if miss:
            bad("前端宿主接线", "; ".join(miss))
        else:
            ok("前端宿主接线", "html %.1fKB / js %.1fKB" % (len(html) / 1024.0, len(js) / 1024.0))

        # 10) 选图后进入生成请求体
        st, buf, _ = http("/api/plugin-static/pose_gallery/data/" + (items[0].get("ref") or "").split("/data/", 1)[-1], raw=True)
        import base64
        data_url = "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")
        r = http("/api/debug/payload", {"template": "qwen_i2i", "content": "把这张图的姿势换成站立",
                                        "params": {}, "fast": True,
                                        "images": [{"data_url": data_url, "role": "姿势参考（人体动态与构图）"}]})
        if "姿势参考" not in (r.get("user") or "") or "<image1>" not in (r.get("user") or ""):
            bad("选图进入请求体", "user 里没有姿势参考/图片占位：%s" % (r.get("user") or "")[:120])
        else:
            ok("选图进入请求体", "system %s 字 · user %s 字"
               % (r.get("system_chars"), len(r.get("user") or "")))
    finally:
        if proc is not None:
            try:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, creationflags=0x08000000)
            except Exception:
                pass
        os.makedirs(DATA, exist_ok=True)
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(LINES) + "\n\n结果：失败 %d 项 %s\n"
                    % (len(FAILS), ("→ " + ", ".join(FAILS)) if FAILS else "→ 通过"))
    out("\n结果：失败 %d 项 %s" % (len(FAILS), ("→ " + ", ".join(FAILS)) if FAILS else "→ 通过"))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
