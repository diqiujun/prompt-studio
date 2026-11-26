# -*- coding: utf-8 -*-
"""端到端联调：用本机 8080 的 OpenAI 兼容服务（swift-1.5-iq3_xxs, 支持图像）跑真实生成。"""
import base64, io, json, sys, time, urllib.request
from pathlib import Path

import requests
from PIL import Image

BASE = "http://127.0.0.1:8760"
ROOT = Path(r"E:\新建文件夹\prompt-studio")
SRC = Path(r"E:\新建文件夹\work\storyboard_q\R04_A5.png")
if not SRC.exists():
    cands = sorted(Path(r"E:\新建文件夹\work\storyboard_q").glob("*.png"))
    SRC = cands[0]
print("test image:", SRC, SRC.exists())

im = Image.open(SRC).convert("RGB")
im.thumbnail((760, 760))
buf = io.BytesIO(); im.save(buf, "JPEG", quality=87)
b64 = base64.b64encode(buf.getvalue()).decode()
data_url = "data:image/jpeg;base64," + b64
print("jpeg bytes:", len(b64))

# 1) 注册本地服务
r = requests.post(BASE + "/api/provider/save", json={"provider": {
    "name": "本机 swift 8080", "base_url": "http://127.0.0.1:8080/v1",
    "model": "swift-1.5-iq3_xxs", "api_key": "local", "vision": True,
    "max_tokens": 6000, "temperature": 0.6}}, timeout=30)
prov = [p for p in r.json()["providers"] if p["base_url"].endswith("8080/v1")][-1]
print("provider:", prov["id"], prov["name"], prov["vision"])
print("activate:", requests.post(BASE + "/api/provider/activate", json={"id": prov["id"]}).status_code)

def run(tpl, content, params, images=None, label=""):
    t0 = time.time()
    r = requests.post(BASE + "/api/generate", json={
        "template": tpl, "content": content, "params": params,
        "images": images or [], "provider": prov["id"], "fast": True}, timeout=600)
    d = r.json()
    print("\n===== %s [%s] HTTP %s  %.1fs =====" % (label or tpl, tpl, r.status_code, time.time() - t0))
    if not d.get("ok"):
        print("ERROR:", str(d.get("error"))[:800]); return d
    print("meta:", d.get("label"), "| model", d.get("model"), "| sys_chars", d.get("system_chars"),
          "| usage", d.get("usage"))
    print(d.get("content", "")[:2600])
    if d.get("json"):
        print("--- parsed json keys:", list(d["json"].keys()))
        print(json.dumps(d["json"], ensure_ascii=False)[:1200])
    return d

run("qwen_i2i", "把画面里的铜钟改成完整无缺的旧铜钟：钟口不缺块、没有破洞，只留一道从钟口向上延伸的竖直长裂缝，其余全部保持不变。输出竖版 9:16。",
    {"ratio": "9:16"}, [{"data_url": data_url, "role": "画布图·被编辑的底图"}], "图生图(带真图)")

run("h3_video", "沈不违提刀立于雪夜山门前，呼出白气，刀刃上有雪粒反光；镜头从他的靴子慢慢上摇到脸，最后他开口说「都让开」。时长 6 秒。",
    {"mode": "auto", "duration": 6, "aspect": "16:9", "subject_kind": "人物特写", "lang": "中文", "lora": "不加 LoRA"}, None, "H3 文生视频")

run("moss_t2i", "仙侠剧里的女修站在丹殿废墟中，身后是断裂的铜钟，手里捧着发光的丹炉残件，3D 仙侠渲染风。",
    {"canvas": "1024x1536", "style_pref": "3D 仙侠渲染", "scene_tags": "古风室内", "lang": "中文槽位+中文内容"}, None, "MOSS 文生图")

run("tr_general", "他胸口有把剑，天下人都在等它出鞘的那一夜。", {"direction": "zh2en", "register": "正式书面"}, None, "翻译 中→英")

print("\nhistory size:", len(requests.get(BASE + "/api/history", timeout=30).json()["history"]))
