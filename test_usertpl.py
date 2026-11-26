# -*- coding: utf-8 -*-
"""用户自定义模型（提示词撰写页「＋ 添加模型」）自检。

覆盖：新增 → 出现在模板列表 → 注入规范到 system → 编辑 → 真跑一次生成 → 删除；
外加 @ 引用缩略图与前端控件是否落盘。日志：data\\usertpl_test.log
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("UTPL_PORT") or 8797)
BASE = "http://127.0.0.1:%d" % PORT
LOG = ROOT / "data" / "usertpl_test.log"
OK = []
FAIL = []


def out(msg=""):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def ok(name, extra=""):
    OK.append(name)
    out("OK   %s%s" % (name, ("  " + str(extra)) if extra else ""))


def bad(name, why):
    FAIL.append(name)
    out("FAIL %s  %s" % (name, why))


def http(path, body=None, method=None, timeout=180):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_server(secs=60):
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            j = http("/api/state", timeout=4)
            if j.get("templates"):
                return True
        except Exception:
            time.sleep(0.6)
    return False


SPEC = ("写 FLUX.1 提示词的规范：\n"
        "1. 英文单段长句，不分点；\n"
        "2. 顺序：主体 → 动作 → 环境 → 光线 → 材质 → 构图 → 镜头 → 风格；\n"
        "3. 光线写光位（左上柔光箱 / 逆光轮廓）；\n"
        "4. 末尾一行以 negatives: 开头的负面清单；\n"
        "5. 不要反问，缺信息按最合理方案补全。\n"
        "标记 ZZ-FLUX-SPEC-4821")


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    out("== 用户自定义模型自检 %s ==" % time.strftime("%Y-%m-%d %H:%M:%S"))

    # 记录原有自定义模型，测试完恢复
    backup = None
    proc = subprocess.Popen([sys.executable, str(ROOT / "src" / "app.py")],
                            cwd=str(ROOT), env={**os.environ, "PORT": str(PORT), "PYTHONUTF8": "1"},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0x00000200)
    try:
        if not wait_server():
            bad("服务就绪", "%s 60 秒内没有 /api/state" % BASE)
            return
        ok("服务就绪", BASE)
        backup = http("/api/templates").get("templates") or []

        # 1. 新增
        j = http("/api/templates/save", {"template": {
            "name": "FLUX.1 文生图", "tagline": "自然语言长句，重光影与镜头",
            "intro": "你是 FLUX.1 的提示词工程师，把口语需求写成英文长句提示词。",
            "spec": SPEC, "expect_json": False, "min_images": 0, "max_images": 2,
            "params": [{"key": "p1", "label": "画幅", "type": "canvas", "default": "1024x1024"},
                       {"key": "p2", "label": "风格", "type": "select", "default": "电影感",
                        "options": ["电影感", "二次元", "产品图"]}],
            "examples": ["一个穿风衣的女人站在雨夜街头，霓虹反光"],
        }})
        tid = j.get("saved") or ""
        if j.get("ok") and tid.startswith("custom_"):
            ok("新增自定义模型", "id=%s" % tid)
        else:
            bad("新增自定义模型", str(j)[:200])
            return

        # 2. 出现在模板列表
        st = http("/api/state")
        ids = [t["id"] for t in st.get("templates") or []]
        if tid in ids:
            ok("出现在模板列表", "共 %d 个模板" % len(ids))
        else:
            bad("出现在模板列表", "没找到 %s" % tid)

        # 3. 注入规范
        p = http("/api/debug/payload", {"template": tid, "content": "雨夜街头一个穿风衣的女人",
                                        "params": {"p1": "1280x720", "p2": "电影感"}})
        sys_txt = p.get("system") or ""
        usr = p.get("user") or ""
        miss = []
        if "ZZ-FLUX-SPEC-4821" not in sys_txt:
            miss.append("规范正文")
        if "FLUX.1 的提示词工程师" not in sys_txt:
            miss.append("开场角色句")
        if "【输出纪律】" not in sys_txt:
            miss.append("输出纪律")
        if "画幅=1280x720" not in usr or "风格=电影感" not in usr:
            miss.append("参数行")
        if miss:
            bad("注入规范到 system", "缺 " + "、".join(miss))
        else:
            ok("注入规范到 system", "system %d 字 / user %d 字" % (len(sys_txt), len(usr)))

        # 4. 编辑
        j2 = http("/api/templates/save", {"template": {
            "id": tid, "name": "FLUX.1 文生图（改）", "tagline": "改过的简介",
            "spec": SPEC + "\n6. 新增一条：不要出现水印。", "params": [],
        }})
        lst = j2.get("templates") or []
        hit = [t for t in lst if t["id"] == tid]
        if hit and hit[0]["name"].endswith("（改）") and "不要出现水印" in hit[0]["spec"]:
            ok("编辑自定义模型", hit[0]["name"])
        else:
            bad("编辑自定义模型", str(hit)[:200])

        # 5. 真跑一次生成（本地模型，模板走自定义）
        #    开发态目录里没有随包模型，autostart 可能不触发 → 显式启动并等就绪
        try:
            ls = http("/api/local/status")
            if not ls.get("running"):
                http("/api/local/start", {})
            t0 = time.time()
            while time.time() - t0 < 180:
                if http("/api/local/status").get("running"):
                    break
                time.sleep(2)
            out("     本地模型：%s" % ("就绪" if http("/api/local/status").get("running") else "未就绪"))
        except Exception as e:
            out("     本地模型启动异常：%s" % e)

        g = http("/api/generate", {"template": tid, "content": "雨夜街头一个穿风衣的女人，霓虹反光",
                                   "params": {}, "images": [], "fast": True, "provider": "local-gemma"},
                 timeout=300)
        txt = g.get("content") or ""
        if g.get("ok") and len(txt) > 40:
            ok("真跑一次生成", "%d 字：%s" % (len(txt), txt[:60].replace("\n", " ")))
        else:
            bad("真跑一次生成", str(g)[:300])

        # 6. 前端控件落盘
        html = urllib.request.urlopen(BASE + "/", timeout=20).read().decode("utf-8")
        js = urllib.request.urlopen(BASE + "/static/app.js", timeout=20).read().decode("utf-8")
        css = urllib.request.urlopen(BASE + "/static/style.css", timeout=20).read().decode("utf-8")
        need_html = ['id="tplEd"', 'id="teName"', 'id="teSpec"', 'id="teParams"', 'id="teSave"']
        need_js = ["openTplEditor", "saveTplEditor", '"/api/templates/save"', "mthumb", "tplAdd"]
        need_css = [".modal", ".mthumb", ".tpl.add", ".tplops"]
        miss = ([k for k in need_html if k not in html] + [k for k in need_js if k not in js]
                + [k for k in need_css if k not in css])
        if miss:
            bad("前端控件", "缺 " + "、".join(miss))
        else:
            ok("前端控件", "html %.1fKB / js %.1fKB / css %.1fKB"
               % (len(html) / 1024.0, len(js) / 1024.0, len(css) / 1024.0))

        # 7. 删除
        j3 = http("/api/templates/delete", {"id": tid})
        left = [t["id"] for t in j3.get("templates") or []]
        st2 = http("/api/state")
        ids2 = [t["id"] for t in st2.get("templates") or []]
        if tid not in left and tid not in ids2:
            ok("删除自定义模型", "剩余自定义 %d 个" % len(left))
        else:
            bad("删除自定义模型", "还在：%s" % tid)

    finally:
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=0x08000000)
        except Exception:
            pass
        if backup is not None:
            try:
                http("/api/templates/save", {"template": {}})  # 探测服务已停
            except Exception:
                pass
            try:
                sys.path.insert(0, str(ROOT / "src"))
                import settings as S
                S.save_user_templates(backup)
            except Exception as e:
                out("（恢复原自定义模型失败：%s）" % e)

    out("\n结果：OK %d 项，失败 %d 项 %s" % (len(OK), len(FAIL), "→ 通过" if not FAIL else "→ " + ", ".join(FAIL)))
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
