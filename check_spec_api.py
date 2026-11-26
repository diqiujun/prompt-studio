"""规范管理接口端到端核查（对开发版服务，不消耗模型额度）。

覆盖：规范清单读取 → 关闭内置组件后注入文本消失 → 用自定义文本替换后注入生效 →
新增自定义规范注入末尾 → 删除 → 全部恢复默认。"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = os.environ.get("SPEC_PORT", "8791")
BASE = "http://127.0.0.1:%s" % PORT
LOG = ROOT / "data" / "spec_check.log"

FAILS = []
lines = []


def log(s):
    lines.append(str(s))


def flush():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def post(path, body, timeout=25):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8")


def get(path, timeout=25):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8")


def payload(tid, fast=True):
    st, raw = post("/api/debug/payload", {"template": tid, "content": "测试内容", "fast": fast})
    return json.loads(raw)


def main():
    env = dict(os.environ)
    env["PORT"] = PORT
    env["PYTHONUTF8"] = "1"
    proc = subprocess.Popen([sys.executable, str(ROOT / "src" / "app.py")], cwd=str(ROOT),
                            env=env, creationflags=0x00000200,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                get("/api/state", timeout=3)
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("开发版服务未启动")

        st, raw = get("/api/spec")
        spec = json.loads(raw)
        tpl = {t["id"]: t for t in spec["templates"]}
        log("规范清单 %s 个模板；组件数 %s" % (
            len(tpl), {k: len(v["components"]) for k, v in tpl.items()}))
        FAILS.append(("规范清单可读", not spec["templates"]))

        comp = tpl["moss_t2i"]["components"][0]["name"]
        base = payload("moss_t2i")
        base_sys = base["system"]
        needle = base_sys[:0]
        # 取该组件独有的文本片段用于断言
        st, rawc = get("/api/spec/content?name=" + comp)
        txt = json.loads(rawc)["text"]
        needle = txt[200:260]
        log("组件 %s 原文片段用于断言：%r" % (comp, needle[:40]))
        FAILS.append(("组件原文注入", needle not in base_sys))

        st, raw = post("/api/spec/toggle", {"name": comp, "enabled": False})
        off = payload("moss_t2i")
        log("关闭 %s → system_chars %d → %d" % (comp, base["system_chars"], off["system_chars"]))
        FAILS.append(("关闭后原文消失", needle in off["system"]))

        st, raw = post("/api/spec/replace", {"name": comp, "replace": "自定义规范标记 ZZ-CUSTOM-9527：必须全部照做。"})
        rep = payload("moss_t2i")
        log("替换 → system_chars %d 含自定义=%s" % (rep["system_chars"], "ZZ-CUSTOM-9527" in rep["system"]))
        FAILS.append(("替换生效", "ZZ-CUSTOM-9527" not in rep["system"]))

        st, raw = post("/api/spec/save", {"spec": {"template": "moss_t2i", "name": "我的补充规范",
                                                  "text": "EXTRA-MARK-31415 追加要求", "enabled": True}})
        j = json.loads(raw)
        eid = j["extra"][0]["id"]
        ex = payload("moss_t2i")
        log("新增自定义规范 id=%s 含标记=%s 末尾=%r" % (
            eid, "EXTRA-MARK-31415" in ex["system"], ex["system"][-60:]))
        FAILS.append(("自定义规范注入", "EXTRA-MARK-31415" not in ex["system"]))
        FAILS.append(("优先级声明", "优先级高于上方内置规范" not in ex["system"]))

        st, raw = post("/api/spec/delete", {"id": eid})
        after = payload("moss_t2i")
        FAILS.append(("删除生效", "EXTRA-MARK-31415" in after["system"]))

        st, raw = post("/api/spec/reset", {})
        rst = payload("moss_t2i")
        st, rawc = get("/api/spec/content?name=" + comp)
        txt2 = json.loads(rawc)["text"]
        log("恢复默认 → system_chars %d 原文回归=%s" % (rst["system_chars"], txt2[200:260] in rst["system"]))
        FAILS.append(("恢复默认", txt2[200:260] not in rst["system"]))

        # 前端脚本静态检查：注入量 UI 必须不存在
        appjs = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        FAILS.append(("前端无注入量按钮", "id=\"preview\"" in html or "查看注入量" in html))
        FAILS.append(("前端无规范体积显示", "specList" in appjs or "注入量" in appjs))
        FAILS.append(("前端有规范管理", "renderSpecMgr" not in appjs))
        FAILS.append(("前端画幅控件", "canvas" not in appjs))
        for name, bad in FAILS:
            log("%s %s" % ("FAIL" if bad else "OK  ", name))
        bad = [n for n, b in FAILS if b]
        log("结果：失败 %d 项 %s" % (len(bad), bad))
        log("通过" if not bad else "未通过")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        flush()
    return 1 if any(b for _, b in FAILS) else 0


if __name__ == "__main__":
    sys.exit(main())
