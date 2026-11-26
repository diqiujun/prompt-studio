"""DSH 式插件系统自检：代码插件（工具 / 接口 / 设置项 / 钩子）+ 信任门 + 安装 zip + 模板插件。

跑法：python test_plugins2.py
日志：data\\plugin2_test.log
"""
import io
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

PORT = int(os.environ.get("PLUGIN2_PORT") or 8796)
BASE = "http://127.0.0.1:%d" % PORT
LOG = os.path.join(ROOT, "data", "plugin2_test.log")
FAILS = []


def out(msg=""):
    print(msg)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def ok(name, detail=""):
    out("  OK   %s%s" % (name, ("  " + detail) if detail else ""))


def bad(name, detail=""):
    FAILS.append(name)
    out("  FAIL %s%s" % (name, ("  " + detail) if detail else ""))


def http(path, body=None, method=None, raw=None, ctype=None):
    url = BASE + path
    data = None
    headers = {}
    if raw is not None:
        data = raw
        headers["Content-Type"] = ctype or "application/octet-stream"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method or ("POST" if data is not None else "GET"))
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


SERVER = {"proc": None}


def ensure_server():
    """起一个 app 进程（只起一次），返回 BASE。"""
    if SERVER["proc"] is not None:
        return BASE
    import subprocess
    env = dict(os.environ)
    env["PORT"] = str(PORT)
    env["PYTHONUTF8"] = "1"
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "src", "app.py")], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0x08000000)
    SERVER["proc"] = proc
    for _ in range(90):
        try:
            http("/api/state")
            ok("app 启动", BASE)
            return BASE
        except Exception:
            time.sleep(1)
    bad("app 启动")
    return BASE


def stop_server():
    proc = SERVER.get("proc")
    if not proc:
        return
    import subprocess
    try:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    except Exception:
        pass
    SERVER["proc"] = None


def main():
    io.open(LOG, "w", encoding="utf-8").close()
    import app as backend
    import pluginlib
    import registry
    import settings

    out("== 1. 目录扫描与清单 ==")
    cfg = settings.load_config()
    # 先清掉上次测试留下的信任/设置，保证从「未信任」状态起跑
    cfg["plugin_trust"] = {}
    cfg["plugin_settings"] = {}
    settings.save_config(cfg)
    pluginlib.ensure_loaded(settings.load_config(), force=True)
    cfg = settings.load_config()
    st = pluginlib.status(cfg)
    ids = [p["id"] for p in st["plugins"]]
    out("     插件目录：%s" % st["dir"])
    out("     插件：%s" % ", ".join("%s(%s/%s)" % (p["id"], p["kind"], p["status"]) for p in st["plugins"]))
    if "sample_generic" in ids:
        ok("扫描到模板插件 sample_generic")
    else:
        bad("扫描到模板插件 sample_generic", str(ids))
    if "sample_tools" in ids:
        code = [p for p in st["plugins"] if p["id"] == "sample_tools"][0]
        ok("扫描到代码插件 sample_tools", "kind=%s status=%s" % (code["kind"], code["status"]))
        if code["status"] == "untrusted":
            ok("未信任时不执行代码（status=untrusted）")
        else:
            bad("未信任时不执行代码", code["status"])
    else:
        bad("扫描到代码插件 sample_tools", str(ids))

    out("== 2. 信任门 ==")
    cfg = settings.load_config()
    cfg["plugin_trust"] = {"sample_tools": True}
    settings.save_config(cfg)
    pluginlib.ensure_loaded(settings.load_config(), force=True)
    st = pluginlib.status(settings.load_config())
    code = [p for p in st["plugins"] if p["id"] == "sample_tools"][0]
    if code["status"] == "loaded":
        ok("信任后加载成功", "工具 %d 个 / 接口 %d 个 / 钩子 %s"
           % (len(code["tools"]), len(code["routes"]), ",".join(code["hooks"]) or "无"))
    else:
        bad("信任后加载成功", "%s %s" % (code["status"], code.get("error")))
    if code["tools"] and code["tools"][0]["name"] == "tidy":
        ok("注册了工具 tidy", code["tools"][0].get("label"))
    else:
        bad("注册了工具 tidy", str(code["tools"]))
    if any(r["path"] == "stats" for r in code["routes"]):
        ok("注册了接口 stats")
    else:
        bad("注册了接口 stats", str(code["routes"]))
    if "generate.after" in code["hooks"]:
        ok("注册了 generate.after 钩子")
    else:
        bad("注册了 generate.after 钩子", str(code["hooks"]))

    out("== 3. 工具调用 ==")
    r = pluginlib.run_tool("sample_tools", "tidy",
                           {"text": "第一行   \n\n\n第二行\t\n", "params": {}, "settings": {}})
    if r.get("ok") and "第一行" in (r.get("text") or "") and "\n\n\n" not in (r.get("text") or ""):
        ok("工具整理文本", repr(r.get("text"))[:60] + " note=" + str(r.get("note")))
    else:
        bad("工具整理文本", str(r)[:200])

    out("== 4. 设置项读写 ==")
    cfg = settings.load_config()
    cfg["plugin_settings"] = {"sample_tools": {"strip_blank": True, "prefix": "【前缀】", "append_note": True}}
    settings.save_config(cfg)
    pluginlib.ensure_loaded(settings.load_config(), force=True)
    r = pluginlib.run_tool("sample_tools", "tidy", {"text": "内容", "params": {}, "settings": {}})
    if r.get("ok") and (r.get("text") or "").startswith("【前缀】"):
        ok("工具读到设置项（prefix 生效）", repr(r.get("text")))
    else:
        bad("工具读到设置项（prefix 生效）", str(r)[:200])

    out("== 5. 接口调用 ==")
    handled, res = pluginlib.call_route("sample_tools", "stats", {"text": "你好abc"}, {})
    if handled and res.get("ok") and res.get("cjk") == 2:
        ok("接口 stats 返回统计", str(res))
    else:
        bad("接口 stats 返回统计", "%s %s" % (handled, res))
    handled2, res2 = pluginlib.call_route("sample_tools", "nope", {}, {})
    if not handled2:
        ok("未声明的接口不接管", str(res2))
    else:
        bad("未声明的接口不接管", str(res2))

    out("== 6. generate.after 钩子 ==")
    out2 = pluginlib.apply_hooks("generate.after", {"template": "h3_video", "content": "x", "output": "正文", "json": None})
    if isinstance(out2, str) and "由插件整理" in out2:
        ok("钩子改写输出", repr(out2))
    else:
        bad("钩子改写输出", str(out2)[:120])
    cfg = settings.load_config()
    cfg["plugin_settings"] = {"sample_tools": {"append_note": False}}
    settings.save_config(cfg)
    pluginlib.ensure_loaded(settings.load_config(), force=True)
    out3 = pluginlib.apply_hooks("generate.after", {"template": "h3_video", "content": "x", "output": "正文", "json": None})
    if out3 is None:
        ok("设置关闭时钩子不改输出")
    else:
        bad("设置关闭时钩子不改输出", str(out3)[:120])
    cfg = settings.load_config()
    cfg["plugin_settings"] = {"sample_tools": {"append_note": True}}
    settings.save_config(cfg)
    pluginlib.ensure_loaded(settings.load_config(), force=True)

    out("== 7. 模板插件照旧可用 ==")
    tid = "plugin_sample_generic"
    built = registry.build(tid, {"style": "电影感"}, [], True)
    if "插件规范" in built["system"] and "电影感" in built["user"]:
        ok("模板插件注入规范与参数", "%d 字 / %d 字" % (len(built["system"]), len(built["user"])))
    else:
        bad("模板插件注入规范与参数")

    out("== 8. zip 安装 / 删除 ==")
    ensure_server()
    tmpzip = os.path.join(ROOT, "data", "_plugtest.zip")
    with zipfile.ZipFile(tmpzip, "w") as z:
        z.writestr("zipdemo/plugin.json", json.dumps(
            {"id": "zipdemo", "name": "压缩包插件", "spec": "spec.md"}, ensure_ascii=False))
        z.writestr("zipdemo/spec.md", "这是从 zip 安装的规范。")
    with open(tmpzip, "rb") as f:
        raw = f.read()
    body = (b"--X\r\nContent-Disposition: form-data; name=\"file\"; filename=\"zipdemo.zip\"\r\n"
            b"Content-Type: application/zip\r\n\r\n" + raw + b"\r\n--X--\r\n")
    r = http("/api/plugins/install", raw=body, ctype="multipart/form-data; boundary=X")
    ins = r.get("installed") or {}
    if ins.get("ok") and ins.get("id") == "zipdemo":
        ok("zip 安装成功", str(ins)[:120])
    else:
        bad("zip 安装成功", str(ins)[:200])
    if "plugin_zipdemo" in (r.get("ids") or []):
        ok("安装后模板立即可用")
    else:
        bad("安装后模板立即可用", str(r.get("ids")))
    r2 = http("/api/plugins/delete", {"id": "zipdemo"})
    if (r2.get("deleted") or {}).get("ok"):
        ok("删除插件", str((r2.get("deleted") or {}))[:80])
    else:
        bad("删除插件", str(r2.get("deleted"))[:200])
    os.remove(tmpzip)
    if not os.path.isdir(os.path.join(ROOT, "plugins", "zipdemo")):
        ok("删除后目录已移除")
    else:
        bad("删除后目录已移除")

    out("== 9. HTTP 端点（复用上面起的 app 进程） ==")
    ensure_server()
    try:
        j = http("/api/plugins")
        if j.get("ok") and j.get("plugins") is not None:
            ok("GET /api/plugins", "count=%s plugins=%d" % (j.get("count"), len(j.get("plugins") or [])))
        else:
            bad("GET /api/plugins", str(j)[:200])
        meta = [p for p in j["plugins"] if p["id"] == "sample_tools"][0]
        if meta["settings"] and meta["values"] is not None:
            ok("设置项 schema 下发", str([s["key"] for s in meta["settings"]]))
        else:
            bad("设置项 schema 下发", str(meta)[:200])
        j = http("/api/plugins/settings", {"id": "sample_tools", "values": {"prefix": "【HTTP】"}})
        vals = j.get("values") if isinstance(j, dict) else None
        ok("POST /api/plugins/settings", "ok=%s" % bool(j.get("ok")))
        j = http("/api/plugins/tool", {"id": "sample_tools", "tool": "tidy", "text": "abc"})
        if j.get("ok") and "【HTTP】" in (j.get("text") or ""):
            ok("POST /api/plugins/tool（设置已生效）", repr(j.get("text")))
        else:
            bad("POST /api/plugins/tool（设置已生效）", str(j)[:200])
        j = http("/api/plugin/sample_tools/stats", {"text": "中文abc"})
        if j.get("ok") and j.get("cjk") == 2:
            ok("POST /api/plugin/<id>/stats", str(j))
        else:
            bad("POST /api/plugin/<id>/stats", str(j)[:200])
        j = http("/api/plugins/trust", {"id": "sample_tools", "trusted": False})
        meta = [p for p in (j.get("plugins") or []) if p["id"] == "sample_tools"]
        if meta and meta[0]["status"] == "untrusted":
            ok("POST /api/plugins/trust（取消信任后不再执行）")
        else:
            bad("POST /api/plugins/trust（取消信任后不再执行）", str(meta)[:200])
        http("/api/plugins/trust", {"id": "sample_tools", "trusted": True})
        j = http("/api/plugins/reload", {})
        if j.get("ok"):
            ok("POST /api/plugins/reload")
        else:
            bad("POST /api/plugins/reload", str(j)[:200])
    finally:
        stop_server()

    out("\n结果：共 %d 项失败 %s" % (len(FAILS), ("→ " + ", ".join(FAILS)) if FAILS else "→ 通过"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
