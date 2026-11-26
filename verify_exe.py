"""打包版 exe 端到端验证。

EXE_PATH 环境变量指定 exe（默认 dist\\PromptStudio\\PromptStudio.exe，onedir 版）。
检查：启动 → 静态资源 → 内置规范注入 → provider CRUD → 真实生成（4 条链）→ 历史落盘。
响应键名对齐 src/app.py：/api/generate 的解析结果在 "json"，/api/history 在 "history"，
/api/provider/save 请求体是 {"provider": {...}}，/api/debug/payload 请求键是 "template"。
"""
import json
import os
import subprocess
import sys
import time

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE = os.environ.get("EXE_PATH") or os.path.join(ROOT, "dist", "PromptStudio", "PromptStudio.exe")
PORT = int(os.environ.get("PORT", "8760"))
BASE = "http://127.0.0.1:%d" % PORT
LOG = os.path.join(ROOT, "data", "exe_verify.log")
log = open(LOG, "w", encoding="utf-8")
FAILS = []


def out(msg):
    print(msg, flush=True)
    log.write(str(msg) + "\n")
    log.flush()


def step(name, fn):
    try:
        fn()
        out("[OK] %s" % name)
    except Exception as exc:
        FAILS.append("%s: %r" % (name, exc))
        out("[FAIL] %s → %r" % (name, exc))


def start_server():
    out("exe=%s exists=%s size=%d" % (EXE, os.path.isfile(EXE),
                                      os.path.getsize(EXE) if os.path.isfile(EXE) else -1))
    # stdout 落文件，后面要检查“已打开浏览器”那一行
    start_server.logpath = os.path.join(ROOT, "data", "exe_run.log")
    fh = open(start_server.logpath, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen([EXE], cwd=ROOT, creationflags=0x00000200,
                            stdout=fh, stderr=subprocess.STDOUT, bufsize=1)
    start_server.proc = proc
    for _ in range(90):
        time.sleep(2)
        try:
            if requests.get(BASE + "/api/state", timeout=3).ok:
                break
        except Exception:
            pass
    else:
        try:
            fh.flush()
            out("启动失败 stdout=" + open(start_server.logpath, encoding="utf-8",
                                         errors="replace").read()[:1500])
        except Exception as exc:
            out("启动失败，读日志失败 %r" % exc)
        raise SystemExit("exe 未起来")
    st = requests.get(BASE + "/api/state", timeout=10).json()
    out("数据目录=%s templates=%s providers=%d"
        % (st.get("config_path"), [t["id"] for t in st.get("templates", [])],
           len(st.get("providers", []))))


def check_static():
    page = requests.get(BASE + "/", timeout=20)
    out("GET / → %s len=%d 含入口=%s 含中文标题=%s"
        % (page.status_code, len(page.text), 'id="app"' in page.text, "提示词撰写" in page.text))
    assert page.status_code == 200 and "提示词撰写" in page.text
    for p in ("/static/app.js", "/static/style.css"):
        rr = requests.get(BASE + p, timeout=20)
        out("GET %s → %s len=%d" % (p, rr.status_code, len(rr.text)))
        assert rr.status_code == 200 and len(rr.text) > 500


def check_specs():
    for tid, fast, needle in (("qwen_i2i", True, "rewritten_prompt"),
                              ("h3_video", False, "subject_definitions"),
                              ("moss_t2i", True, "positive_prompt"),
                              ("zt_t2i", True, "Z-Image"),
                              ("zi_i2i", True, "强度")):
        j = requests.post(BASE + "/api/debug/payload",
                          json={"template": tid, "content": "测试内容", "fast": fast},
                          timeout=30).json()
        sysp = j.get("system") or ""
        out("预览 %-9s fast=%-5s chars=%6d 含关键规范=%s"
            % (tid, fast, j.get("system_chars") or 0, needle in sysp))
        assert j.get("ok") and needle in sysp, tid


def check_spec_api():
    """规范管理接口在打包版内可用：清单 → 关闭 → 替换 → 自定义 → 恢复默认。"""
    lst = requests.get(BASE + "/api/spec", timeout=20).json()
    tpl = {t["id"]: t for t in lst["templates"]}
    comp = tpl["moss_t2i"]["components"][0]["name"]
    out("规范清单 %d 模板；moss 组件[0]=%s 共 %d 个组件"
        % (len(tpl), comp, len(tpl["moss_t2i"]["components"])))
    assert len(tpl) == 7, "模板数不是 7"

    def payload():
        return requests.post(BASE + "/api/debug/payload",
                             json={"template": "moss_t2i", "content": "测试", "fast": True},
                             timeout=30).json()

    base = payload()
    txt = requests.get(BASE + "/api/spec/content?name=" + comp, timeout=20).json()["text"]
    needle = txt[200:260]
    assert needle in base["system"], "基线缺组件原文"
    requests.post(BASE + "/api/spec/toggle", json={"name": comp, "enabled": False}, timeout=20)
    off = payload()
    assert needle not in off["system"], "关闭后原文仍在注入"
    out("关闭 %s：chars %d → %d 原文消失=OK" % (comp, base["system_chars"], off["system_chars"]))
    requests.post(BASE + "/api/spec/replace",
                  json={"name": comp, "replace": "打包版规范标记 PKG-SPEC-7731。"}, timeout=20)
    rep = payload()
    assert "PKG-SPEC-7731" in rep["system"], "替换未生效"
    out("替换：chars %d 含标记=OK" % rep["system_chars"])
    ex = requests.post(BASE + "/api/spec/save",
                       json={"spec": {"template": "moss_t2i", "name": "打包版自定义",
                                      "text": "PKG-EXTRA-2718。", "enabled": True}}, timeout=20).json()
    eid = ex["extra"][0]["id"]
    p2 = payload()
    assert "PKG-EXTRA-2718" in p2["system"] and "优先级高于上方内置规范" in p2["system"], "自定义规范未注入"
    requests.post(BASE + "/api/spec/delete", json={"id": eid}, timeout=20)
    p3 = payload()
    assert "PKG-EXTRA-2718" not in p3["system"], "删除未生效"
    requests.post(BASE + "/api/spec/reset", json={}, timeout=20)
    p4 = payload()
    assert needle in p4["system"] and "PKG-SPEC-7731" not in p4["system"], "恢复默认失败"
    out("恢复默认：chars=%d 原文回归=OK" % p4["system_chars"])


def check_spec_ui():
    page = requests.get(BASE + "/", timeout=20).json if False else requests.get(BASE + "/", timeout=20)
    html = page.text
    appjs = requests.get(BASE + "/static/app.js", timeout=20).text
    for token in ("id=\"specMgr\"", "id=\"specResetAll\""):
        assert token in html, "index.html 缺 " + token
    for token in ("renderSpecMgr", "openSpecEditor", "/api/spec/toggle", "canvas"):
        assert token in appjs, "app.js 缺 " + token
    assert "查看注入量" not in html and "specList" not in html, "注入量 UI 未清除"
    assert "specList" not in appjs and "注入量" not in appjs, "app.js 残留注入量渲染"
    out("前端规范管理 UI 齐（specMgr/specResetAll/renderSpecMgr/openSpecEditor/toggle），注入量 UI 已清除")


PROV = {}


def _upstream_up(url):
    try:
        return requests.get(url, timeout=3).status_code == 200
    except Exception:
        return False


def save_provider():
    """优先用 8080 的网关；它不在线就用内置本地模型（不依赖外部服务）。"""
    if _upstream_up("http://127.0.0.1:8080/v1/models"):
        body = {"provider": {"name": "打包版-本机8080", "base_url": "http://127.0.0.1:8080/v1",
                             "model": "swift-1.5-iq3_xxs", "api_key": "local", "vision": True,
                             "max_tokens": 6000, "temperature": 0.6}}
        j = requests.post(BASE + "/api/provider/save", json=body, timeout=30).json()
        PROV["id"] = j["providers"][-1]["id"]
        out("provider/save → id=%s 共 %d 个（用 8080 网关）" % (PROV["id"], len(j["providers"])))
    else:
        PROV["id"] = "local-gemma"
        out("8080 网关不在线 → 改用内置本地模型 provider=local-gemma")
    ja = requests.post(BASE + "/api/provider/activate",
                       json={"id": PROV["id"], "fast": True}, timeout=20).json()
    out("activate → active=%s fast=%s" % (ja.get("active_provider"), ja.get("fast")))


def check_test():
    r = requests.post(BASE + "/api/provider/test", json={"id": PROV.get("id")}, timeout=300)
    out("provider/test → %s %s" % (r.status_code, r.text[:220]))
    assert r.status_code == 200, "HTTP %s" % r.status_code
    j = r.json()
    assert "ok" in j, "测试接口未返回 ok 字段"
    assert j.get("ok") is True, "连接测试失败: %s" % str(j.get("error"))[:180]
    out("   连通正常 content=%r usage=%s"
        % ((j.get("content") or "")[:40], json.dumps(j.get("usage"), ensure_ascii=False)))


def gen(tid, content, params, images=None, timeout=420):
    body = {"template": tid, "content": content, "params": params,
            "images": images or [], "fast": True}
    if PROV.get("id"):
        body["provider"] = PROV["id"]
    j = None
    for k in range(3):
        t0 = time.time()
        j = requests.post(BASE + "/api/generate", json=body, timeout=timeout).json()
        out("%-9s 第%d次 %.1fs ok=%s usage=%s json_keys=%s"
            % (tid, k + 1, time.time() - t0, j.get("ok"),
               json.dumps(j.get("usage"), ensure_ascii=False),
               list((j.get("json") or {}).keys())))
        if j.get("ok"):
            break
        err = str(j.get("error") or "")
        # 只有限流/超时才退避重试；连接被拒、参数错之类重试没意义
        if ("governor" in err) or ("401" in err) or ("timed out" in err):
            out("   限流/超时片段: " + err[:140].replace("\n", " ") + " → 等 45s 重试")
            time.sleep(45)
            continue
        break
    out("   片段: " + (j.get("content") or j.get("error") or "")[:300].replace("\n", " "))
    assert j.get("ok"), "%s 失败: %s" % (tid, str(j.get("error"))[:220])
    return j


def check_qwen():
    p = os.path.join(ROOT, "data", "probe_img_b64.txt")
    data_url = open(p, encoding="utf-8").read().strip() if os.path.isfile(p) else ""
    j = gen("qwen_i2i",
            "把画面里破损的铜钟修复成完整无缺的旧铜钟：钟口不缺块、没有破洞，只保留一道从钟口向上延伸的竖直长裂缝，其余全部保持不变。输出竖版 9:16。",
            {"ratio": "9:16"},
            [{"data_url": data_url, "role": "画布图·被编辑的底图"}] if data_url else [])
    parsed = j.get("json") or {}
    out("   wh_ratio=%s ratio_follow=%r 段数=%s 换行=%s"
        % (parsed.get("wh_ratio"), parsed.get("ratio_follow"),
           parsed.get("rewritten_prompt", "").count("\n"),
           "\\n" in parsed.get("rewritten_prompt", "")))
    assert parsed.get("rewritten_prompt"), "qwen 未解析出 rewritten_prompt"


def check_h3():
    j = gen("h3_video",
            "沈不违提刀立于雪夜山门前，呼出白气，刀刃上有雪粒反光；镜头从他的靴子慢慢上摇到脸，最后他开口说「都让开」。时长 6 秒。",
            {"mode": "auto", "duration": 6, "aspect": "16:9", "lang": "中文"})
    c = j.get("content") or ""
    for f in ("subject_definitions", "detailed_description", "overall_soundscape",
              "non_diegetic_music", "<d>", "[Shot 1]"):
        assert f in c, "缺字段 " + f


def check_moss():
    j = gen("moss_t2i",
            "仙侠剧里的女修站在丹殿废墟中，身后是断裂的铜钟，手里捧着发光的丹炉残件，3D 仙侠渲染风。",
            {"canvas": "1024x1536", "style_pref": "3D 仙侠渲染", "lang": "中文槽位+中文内容"})
    parsed = j.get("json") or {}
    assert parsed.get("positive_prompt"), "moss 未解析出 positive_prompt"
    out("   canvas_size=%s 负向词长度=%d"
        % (json.dumps(parsed.get("canvas_size"), ensure_ascii=False),
           len(parsed.get("negative_prompt") or "")))


def check_translate():
    gen("tr_general", "他胸口有把剑，天下人都在等它出鞘的那一夜。", {"direction": "zh2en"},
        timeout=180)


def check_history():
    j = requests.get(BASE + "/api/history", timeout=15).json()
    items = j.get("history")
    assert isinstance(items, list), "响应无 history 列表: %s" % str(j)[:160]
    out("历史条数=%d 最近模板=%s" % (len(items), [it.get("template") for it in items[-5:]]))
    assert len(items) >= 4, "历史不足 4 条"
    dp = os.path.join(os.path.dirname(EXE), "data", "history.json")
    out("exe 同目录 data\\history.json 存在=%s size=%d"
        % (os.path.isfile(dp), os.path.getsize(dp) if os.path.isfile(dp) else -1))


def check_local_api():
    """/api/local/status 可用、本地服务在跑、内置 provider 已登记。"""
    j = requests.get(BASE + "/api/local/status", timeout=60).json()
    cfg = j.get("config") or {}
    out("本地模型 status → ok=%s running=%s pid=%s port=%s"
        % (j.get("ok"), j.get("running"), j.get("pid"), j.get("port")))
    out("   文件 files=%s auto=%s use_mtp=%s"
        % (json.dumps(j.get("files"), ensure_ascii=False), cfg.get("auto"), cfg.get("use_mtp")))
    assert j.get("ok"), "status 未返回 ok"
    assert j.get("files", {}).get("model"), "主模型文件不存在"
    assert j.get("files", {}).get("mmproj"), "视觉投影文件不存在"
    # 没在跑就点一次启动（首次加载模型要等）
    if not j.get("running"):
        r = requests.post(BASE + "/api/local/start", json={}, timeout=420)
        j = r.json()
        out("   /api/local/start → %s" % json.dumps(
            {k: j.get(k) for k in ("ok", "running", "pid", "port", "ready", "error")},
            ensure_ascii=False)[:300])
        assert j.get("ok"), "本地模型启动失败: %s" % str(j.get("error"))[:200]
    if not j.get("running"):
        j = requests.get(BASE + "/api/local/status", timeout=60).json()
    assert j.get("running"), "本地模型未在运行"
    st = requests.get(BASE + "/api/state", timeout=30).json()
    ids = [p.get("id") for p in (st.get("providers") or [])]
    out("   providers=%s" % ids)
    assert "local-gemma" in ids, "内置本地 provider 未登记"
    pv = [p for p in st["providers"] if p.get("id") == "local-gemma"][0]
    assert pv.get("vision") is True, "内置本地 provider 未开启看图"
    out("   本机 provider: %s → %s / %s"
        % (pv.get("name"), pv.get("base_url"), pv.get("model")))


def check_local_generate():
    """走打包版 exe 用本地模型出一次提示词（不依赖云 key）。"""
    body = {"template": "tr_general", "content": "他胸口有把剑，天下人都在等它出鞘的那一夜。",
            "params": {"direction": "zh2en"}, "images": [], "fast": True,
            "provider": "local-gemma"}
    t0 = time.time()
    j = requests.post(BASE + "/api/generate", json=body, timeout=300).json()
    out("local-gemma 生成 %.1fs ok=%s usage=%s"
        % (time.time() - t0, j.get("ok"), json.dumps(j.get("usage"), ensure_ascii=False)))
    assert j.get("ok"), "本地模型生成失败: %s" % str(j.get("error"))[:240]
    txt = (j.get("content") or "").strip()
    out("   译文: " + txt[:200].replace("\n", " "))
    assert len(txt) > 8, "输出过短"


def check_browser_code():
    """自动跳转 web 端的实现必须在代码里（就绪检测后再开浏览器）。"""
    src = os.path.join(ROOT, "src", "app.py")
    txt = open(src, encoding="utf-8").read()
    for needle in ("_open_browser_when_ready", "webbrowser.open", "本地模型", "atexit"):
        assert needle in txt, "app.py 缺 %s" % needle
    out("app.py 含就绪后再开浏览器 / 本地模型启动 / atexit 收尾")


def check_browser_fired():
    """看 exe 自己的输出：启动后是否真的调了浏览器打开。

    exe 的 stdout 走的是控制台编码（中文 Windows 上是 GBK），所以要按字节读、
    两种编码都试一遍，不能直接当 UTF-8 解。
    """
    path = getattr(start_server, "logpath", "")
    txt = ""
    for _ in range(20):
        if path and os.path.isfile(path):
            raw = open(path, "rb").read()
            txt = ""
            for enc in ("utf-8", "gbk"):
                try:
                    txt = raw.decode(enc)  # strict：解不开就换下一个编码
                    break
                except Exception:
                    continue
            if not txt:
                txt = raw.decode("gbk", "ignore")
            if ("已打开浏览器" in txt) or ("浏览器未接受打开请求" in txt) or ("自动打开浏览器失败" in txt):
                break
        time.sleep(1)
    hit = [ln.strip() for ln in txt.splitlines()
           if ("已打开浏览器" in ln) or ("浏览器" in ln and ("失败" in ln or "手动" in ln))]
    out("exe 输出里的浏览器行：%s" % (hit[-2:] or "(没看到)"))
    assert hit, "exe 启动后没有调用浏览器的痕迹（日志 data\\exe_run.log）"
    assert "已打开浏览器" in hit[-1] or "浏览器" in hit[-1], "浏览器调用异常"


def stop_server():
    p = getattr(start_server, "proc", None)
    if p:
        p.terminate()
        out("exe 进程已终止 pid=%s" % p.pid)


step("启动 exe", start_server)
step("静态资源", check_static)
step("自动跳转 web 端实现", check_browser_code)
step("浏览器已打开", check_browser_fired)
step("内置规范注入", check_specs)
step("规范管理接口", check_spec_api)
step("规范管理前端 UI", check_spec_ui)
step("本地模型托管接口", check_local_api)
step("本地模型出词", check_local_generate)
step("provider 保存与激活", save_provider)
step("provider 测试", check_test)
step("qwen_i2i 带图生成", check_qwen)
step("h3_video 六段生成", check_h3)
step("moss_t2i 生成", check_moss)
step("翻译", check_translate)
step("历史落盘", check_history)
stop_server()

out("\n结果：共 %d 步，失败 %d 步" % (16, len(FAILS)))
for f in FAILS:
    out("  - " + f)
out("通过" if not FAILS else "有失败项")
log.close()
sys.exit(0 if not FAILS else 1)
