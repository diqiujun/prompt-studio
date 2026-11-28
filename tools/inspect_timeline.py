# -*- coding: utf-8 -*-
"""看导演台 timeline_data 的结构：global / segments / refs 长什么样。"""
import io
import json
import sys

path = sys.argv[1]
d = json.loads(io.open(path, encoding="utf-8-sig").read())
nid = sys.argv[2] if len(sys.argv) > 2 else None
for k, v in d.items():
    if isinstance(v, dict) and isinstance(v.get("inputs"), dict) and "timeline_data" in v["inputs"]:
        nid = nid or k
        break
node = d[nid]
raw = node["inputs"]["timeline_data"]
tl = json.loads(raw) if isinstance(raw, str) else raw

print("节点 %s（%s） task_type=%r" % (nid, node.get("class_type"), node["inputs"].get("task_type")))
print("timeline 顶层键：", list(tl.keys()))
print("global 键：", list((tl.get("global") or {}).keys()))
g = tl.get("global") or {}
for k in ("taskType", "prompt", "refs", "referenceVideo", "continuousReference"):
    v = g.get(k)
    print("  global.%s = %r" % (k, (v if not isinstance(v, str) or len(v) < 120 else v[:117] + "…")))
segs = tl.get("segments") or []
print("\nsegments：%d 段" % len(segs))
for i, s in enumerate(segs[:3]):
    print(" [%d] 键：%s" % (i, list(s.keys())))
    for k in ("taskType", "prompt", "negativePrompt", "length", "durationSec", "refs", "referenceVideo", "loras"):
        v = s.get(k)
        if isinstance(v, str) and len(v) > 120:
            v = v[:117] + "…"
        print("      %s = %r" % (k, v))
print("\n原始 timeline 长度：%d 字符" % len(raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)))
