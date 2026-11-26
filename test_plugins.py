"""插件系统端到端自检：扫描 / 注入 / 启用停用 / 坏插件报错 / 前端接线。

直接调 registry + pluginlib（不起服务），再起一次服务检查 HTTP 端点。
日志：data\plugin_test.log
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
os.chdir(ROOT)

import pluginlib  # noqa: E402
import registry  # noqa: E402
import settings  # noqa: E402

LOG = open(os.path.join(ROOT, "data", "plugin_test.log"), "w", encoding="utf-8")
FAILS = []


def out(msg):
    print(msg)
    LOG.write(msg + "\n")
    LOG.flush()


def ok(name, extra=""):
    out("OK   %s%s" % (name, ("  " + extra) if extra else ""))


def bad(name, extra=""):
    FAILS.append(name)
    out("FAIL %s%s" % (name, ("  → " + extra) if extra else ""))


def check():
    # 1. 扫描：示例插件存在
    d = pluginlib.plugins_dir()
    out("插件目录：%s（存在=%s）" % (d, d.exists()))
    info = pluginlib.scan([])
    ids = [t["id"] for t in info["templates"]]
    if "plugin_sample_generic" in ids:
        ok("扫描到示例插件", "templates=%s" % ids)
    else:
        bad("扫描到示例插件", "templates=%s errors=%s" % (ids, info["errors"]))

    # 2. catalog 带插件、且不泄漏规范正文
    cat = registry.catalog()
    plug = [c for c in cat if c.get("plugin")]
    if plug:
        t = plug[0]
        leak = [k for k in t if k.startswith("_")]
        if leak:
            bad("catalog 不泄漏内部字段", str(leak))
        else:
            ok("catalog 含插件且字段干净", "params=%d" % len(t.get("params") or []))
    else:
        bad("catalog 含插件")

    # 3. 注入：system 里有规范正文 + 输出纪律 + 参数行
    built = registry.build("plugin_sample_generic", {"lang": "中文", "style": "电影感", "shots": 2}, [], True)
    sys_txt, user = built["system"], built["user"]
    for needle, label in (("插件规范", "注入插件规范段"), ("通用提示词润色规范", "注入 spec.md 正文"),
                          ("【输出纪律】", "注入输出纪律"), ("风格=电影感", "参数进用户消息")):
        if needle in (sys_txt + user):
            ok(label)
        else:
            bad(label, needle)
    if built.get("expect_json") is False:
        ok("expect_json 默认 false")
    else:
        bad("expect_json 默认 false", str(built.get("expect_json")))
    out("   插件 system 字数=%d user 字数=%d" % (len(sys_txt), len(user)))

    # 4. 关掉插件 → 模板消失；再打开 → 回来
    pid = "sample_generic"
    info_off = pluginlib.scan([pid])
    if "plugin_sample_generic" not in [t["id"] for t in info_off["templates"]]:
        ok("停用后不再出现在模板里")
    else:
        bad("停用后不再出现在模板里")
    cfg = settings.load_config()
    off = [x for x in (cfg.get("plugins_off") or []) if x != pid]
    cfg["plugins_off"] = off
    settings.save_config(cfg)
    if "plugin_sample_generic" in registry.template_ids():
        ok("重新启用后模板回来")
    else:
        bad("重新启用后模板回来")

    # 5. 坏插件：缺 spec、JSON 语法错 → errors 里报出，不崩
    bad_dir = os.path.join(d, "zz_broken_tmp")
    bad_json_dir = os.path.join(d, "zz_badjson_tmp")
    try:
        os.makedirs(bad_dir, exist_ok=True)
        with open(os.path.join(bad_dir, "plugin.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"id": "broken", "name": "坏插件"}, ensure_ascii=False))
        os.makedirs(bad_json_dir, exist_ok=True)
        with open(os.path.join(bad_json_dir, "plugin.json"), "w", encoding="utf-8") as f:
            f.write("{ 这不是 JSON }")
        info2 = pluginlib.scan([])
        joined = " | ".join(info2["errors"])
        if "缺少规范正文" in joined or "zz_broken_tmp" in joined:
            ok("缺规范正文的插件被报错", joined[:90])
        else:
            bad("缺规范正文的插件被报错", joined[:120])
        if "zz_badjson_tmp" in joined:
            ok("JSON 写错的插件被报错")
        else:
            bad("JSON 写错的插件被报错", joined[:120])
        if "plugin_sample_generic" in [t["id"] for t in info2["templates"]]:
            ok("坏插件不影响好插件")
        else:
            bad("坏插件不影响好插件")
    finally:
        shutil.rmtree(bad_dir, ignore_errors=True)
        shutil.rmtree(bad_json_dir, ignore_errors=True)

    # 6. 前端接线：模板卡片 / 设置页插件区块 / 重新加载按钮
    app_js = open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8").read()
    idx = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    for key in ("loadPlugins", "renderPlugins", "data-pg-id"):
        if key in app_js:
            ok("app.js 有插件代码：%s" % key)
        else:
            bad("app.js 有插件代码：%s" % key)
    for key in ('id="pluginList"', 'id="pluginReload"'):
        if key in idx:
            ok("index.html 有 %s" % key)
        else:
            bad("index.html 有 %s" % key)


def http_check():
    """起 dev server，验证 /api/plugins 三个端点。"""
    port = 8795
    env = dict(os.environ)
    env["PORT"] = str(port)
    env["SPEC_PORT"] = str(port)
    env["PYTHONUTF8"] = "1"
    proc = subprocess.Popen([sys.executable, os.path.join(SRC, "app.py")], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0x00000200)
    base = "http://127.0.0.1:%d" % port
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen(base + "/api/state", timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.5)
        else:
            bad("服务启动")
            return

        def get(p):
            with urllib.request.urlopen(base + p, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))

        def post(p, body=None):
            data = json.dumps(body or {}).encode("utf-8")
            req = urllib.request.Request(base + p, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))

        j = get("/api/plugins")
        if j.get("ok") and any(p["id"] == "sample_generic" for p in j["plugins"]):
            ok("GET /api/plugins", "count=%s dir=%s" % (j.get("count"), j.get("dir")))
        else:
            bad("GET /api/plugins", json.dumps(j, ensure_ascii=False)[:160])

        j = post("/api/plugins/toggle", {"id": "sample_generic", "enabled": False})
        gone = "plugin_sample_generic" not in (j.get("ids") or [])
        if gone:
            ok("POST /api/plugins/toggle 关闭")
        else:
            bad("POST /api/plugins/toggle 关闭", str(j.get("ids")))
        j = post("/api/plugins/toggle", {"id": "sample_generic", "enabled": True})
        if "plugin_sample_generic" in (j.get("ids") or []):
            ok("POST /api/plugins/toggle 打开")
        else:
            bad("POST /api/plugins/toggle 打开")

        j = post("/api/plugins/reload")
        if j.get("ok"):
            ok("POST /api/plugins/reload")
        else:
            bad("POST /api/plugins/reload")

        st = get("/api/state")
        tpls = [t["id"] for t in st.get("templates") or []]
        if "plugin_sample_generic" in tpls:
            ok("/api/state 模板列表含插件", "共 %d 个模板" % len(tpls))
        else:
            bad("/api/state 模板列表含插件", str(tpls))

        payload = post("/api/debug/payload", {"template": "plugin_sample_generic", "content": "测试",
                                             "fast": True})
        if payload.get("ok") and "插件规范" in payload.get("system", ""):
            ok("插件模板可预览注入", "%s 字" % payload.get("system_chars"))
        else:
            bad("插件模板可预览注入", json.dumps(payload, ensure_ascii=False)[:160])
    finally:
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=20)
        except Exception:
            pass


if __name__ == "__main__":
    check()
    http_check()
    out("\n结果：失败 %d 项%s" % (len(FAILS), ("→ " + ", ".join(FAILS)) if FAILS else "→ 通过"))
    LOG.close()
    sys.exit(1 if FAILS else 0)
