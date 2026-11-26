# -*- coding: utf-8 -*-
"""直连 llama-server(8910) 验证文本与图片两条通路。"""
import io
import json
import os
import time
import urllib.request

BASE = "http://127.0.0.1:8910"
ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = io.open(os.path.join(ROOT, "data", "llama_probe.log"), "w", encoding="utf-8")


def out(s):
    print(s)
    LOG.write(s + "\n")
    LOG.flush()


def post(path, body, timeout=600):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path, timeout=30):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


m = get("/v1/models")
out("models: " + json.dumps(m, ensure_ascii=False)[:400])
model = m["data"][0]["id"]

t = time.time()
r = post("/v1/chat/completions", {
    "model": model,
    "messages": [{"role": "user", "content": "用一句中文回答：你是谁？"}],
    "max_tokens": 1500, "temperature": 0.3,
})
out("[文本] %.1fs usage=%s" % (time.time() - t, json.dumps(r.get("usage"), ensure_ascii=False)))
msg = r["choices"][0]["message"]
out("  finish_reason=%s msg_keys=%s" % (r["choices"][0].get("finish_reason"), list(msg.keys())))
out("  content: " + repr((msg.get("content") or ""))[:400])
out("  reasoning_content: " + repr(msg.get("reasoning_content") or "")[:600])

b64 = io.open(os.path.join(ROOT, "data", "probe_img_b64.txt"), encoding="utf-8").read().strip()
t = time.time()
r2 = post("/v1/chat/completions", {
    "model": model,
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": "用中文一句话描述这张图里最主要的物体是什么颜色、什么状态。"},
        {"type": "image_url", "image_url": {"url": b64}},
    ]}],
    "max_tokens": 1500, "temperature": 0.3,
})
out("[视觉] %.1fs usage=%s" % (time.time() - t, json.dumps(r2.get("usage"), ensure_ascii=False)))
m2 = r2["choices"][0]["message"]
out("  finish_reason=%s msg_keys=%s" % (r2["choices"][0].get("finish_reason"), list(m2.keys())))
out("  content: " + repr(m2.get("content") or "")[:500])
out("  reasoning_content: " + repr(m2.get("reasoning_content") or "")[:600])
LOG.close()
