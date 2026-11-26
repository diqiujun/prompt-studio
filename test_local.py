# -*- coding: utf-8 -*-
"""通过 PromptStudio 接口实测本机 gemma-4-e2b（文本 + 图生图视觉通路）。"""
import io
import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("BASE", "http://127.0.0.1:8760")
ROOT = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(ROOT, "data", "probe_img_b64.txt")
LOG = io.open(os.path.join(ROOT, "data", "local_test.log"), "w", encoding="utf-8")
PROV = os.environ.get("PROV", "local-gemma")


def out(s):
    print(s)
    LOG.write(s + "\n")
    LOG.flush()


def api(path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode("utf-8"))


CASES = [
    ("翻译 zh2en", "tr_general",
     "他胸口有把剑，天下人都在等它出鞘的那一夜。",
     {"direction": "zh2en", "register": "正式书面"}, False),
    ("MOSS 文生图", "moss_t2i",
     "仙侠剧里的女修站在丹殿废墟中，身后是断裂的铜钟，手里捧着发光的丹炉残件，3D 仙侠渲染风。",
     {"canvas": "1024x1536", "style_pref": "3D 仙侠渲染", "scene_tags": "古风室内",
      "lang": "中文槽位+中文内容"}, True),
    ("H3 视频", "h3_video",
     "沈不违提刀立于雪夜山门前，呼出白气，刀刃上有雪粒反光；镜头从他的靴子慢慢上摇到脸，"
     "最后他开口说「都让开」。时长 6 秒。",
     {"mode": "auto", "duration": "6", "aspect": "16:9", "subject_kind": "人物特写",
      "lang": "中文", "lora": "不加 LoRA"}, False),
    ("Qwen 图生图（带真图）", "qwen_i2i",
     "把画面里的铜钟改成完整无缺的旧铜钟：钟口不缺块、没有破洞，只留一道从钟口向上延伸的竖直长裂缝，"
     "其余全部保持不变。输出竖版 9:16。",
     {"ratio": "9:16"}, True),
]

fails = []
out("=== 本机 gemma-4-e2b 走应用接口实测 provider=%s ===" % PROV)
st = api("/api/local/status")
out("本地服务 running=%s port=%s" % (st.get("running"), (st.get("config") or {}).get("port")))

for i, (label, tid, content, params, use_img) in enumerate(CASES):
    body = {"template": tid, "content": content, "params": params,
            "fast": True, "provider": PROV}
    if use_img:
        b64 = open(IMG, encoding="utf-8").read().strip()
        if not b64.startswith("data:"):
            b64 = "data:image/jpeg;base64," + b64
        body["images"] = [{"name": "probe.jpg", "data_url": b64,
                           "role": "画布图·被编辑的底图"}]
    t = time.time()
    try:
        j = api("/api/generate", body)
    except Exception as exc:
        out("[%s] 请求异常：%s" % (label, exc))
        fails.append(label)
        continue
    el = time.time() - t
    ok = j.get("ok")
    u = j.get("usage") or {}
    out("[%s] ok=%s %.1fs tokens=%s+%s=%s sys=%s" % (
        label, ok, el, u.get("prompt_tokens"), u.get("completion_tokens"),
        u.get("total_tokens"), j.get("system_chars")))
    if not ok:
        out("  错误：%s" % str(j.get("error"))[:400])
        fails.append(label)
        continue
    txt = (j.get("content") or "").strip()
    out("  输出前 1200 字：\n%s" % txt[:1200])
    js = j.get("json")
    out("  解析 JSON keys=%s" % (list(js.keys()) if isinstance(js, dict) else None))

out("\n结果：失败 %d 项" % len(fails))
out("失败清单：%s" % fails)
LOG.close()
sys.exit(1 if fails else 0)
