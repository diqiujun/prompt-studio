# -*- coding: utf-8 -*-
"""勘察一份 ComfyUI 工作流 json：判断是 UI 格式还是 API 格式，打印节点/连接/关键 inputs。"""
import io
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\minut\.dsh\attachments\v1\files\cb\cb6abd42d13c49992dbd21dd53f055a945d34ace7e577e89db534553619f6df6\Unsaved Workflow(2).json"
raw = io.open(path, encoding="utf-8-sig").read()
d = json.loads(raw)

print("顶层键：", list(d.keys())[:12])
fmt = "API" if all(isinstance(v, dict) and "class_type" in v for v in list(d.values())[:3]) else "UI"
print("格式判定：", fmt)

if fmt == "API":
    nodes = d
    for nid, n in nodes.items():
        ins = n.get("inputs") or {}
        links = {k: v for k, v in ins.items() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)}
        vals = {k: (v if not isinstance(v, str) or len(v) < 60 else v[:57] + "…") for k, v in ins.items() if k not in links}
        print("\n[%s] %s" % (nid, n.get("class_type")))
        if links:
            print("   links:", links)
        for k, v in vals.items():
            print("   %s = %r" % (k, v))
else:
    nodes = d.get("nodes") or []
    links = d.get("links") or []
    print("nodes=%d links=%d" % (len(nodes), len(links)))
    byid = {n["id"]: n for n in nodes}
    for n in nodes:
        wv = n.get("widgets_values")
        show = wv if not isinstance(wv, list) or len(json.dumps(wv, ensure_ascii=False)) < 300 else str(wv)[:300] + "…"
        print("\n[%s] %s  widgets=%r" % (n["id"], n.get("type"), show))
        ins = n.get("inputs") or []
        if ins:
            print("   inputs:", [(i.get("name"), i.get("link")) for i in ins])
