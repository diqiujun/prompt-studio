# -*- coding: utf-8 -*-
"""检测器探测：给一个 API 工作流 json，打印 detect() 的关键结论。

用法：
    python tools\\det_probe.py <workflow.json>
    python tools\\det_probe.py <workflow.json> --apply "提示词正文" [--duration 5] [--size 1024x1536]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "plugins", "comfy_runner"))
sys.path.insert(0, ROOT)

import plugin  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--apply", default="")
    ap.add_argument("--duration", default="")
    ap.add_argument("--size", default="")
    a = ap.parse_args()
    graph = json.load(open(a.path, encoding="utf-8"))
    if isinstance(graph.get("prompt"), dict):
        graph = graph["prompt"]
    info = plugin.detect(graph)
    keys = ("kind", "mode", "mode_label", "mode_desc", "mode_need", "mode_from",
            "task_type", "director", "refs", "nodes", "prompt", "negative",
            "size", "length", "note")
    print(json.dumps({k: info.get(k) for k in keys}, ensure_ascii=False, indent=1))

    if a.apply:
        ok = plugin._set_text(graph, info.get("prompt"), a.apply)
        print("写提示词:", ok)
        back = plugin._path_get(json.loads(graph[info["prompt"]["node"]]["inputs"][info["prompt"]["field"]]),
                                info["prompt"]["path"]) if info.get("prompt", {}).get("path") else \
            graph[info["prompt"]["node"]]["inputs"][info["prompt"]["field"]]
        print("回读:", str(back)[:160].replace("\n", "\\n"))
    if a.size:
        w, h = a.size.lower().split("x")
        ok = plugin._set_size(graph, info.get("size"), int(w), int(h))
        print("写尺寸:", ok, info.get("size", {}).get("node"))
        nid = info["size"]["node"]
        raw = graph[nid]["inputs"].get("width")
        print("回读 width/height:", raw, graph[nid]["inputs"].get("height"))
    if a.duration:
        ok = plugin._set_length(graph, info.get("length"), float(a.duration))
        print("写时长:", ok, info.get("length", {}).get("field"))
        nid = info["length"]["node"]
        print("回读:", graph[nid]["inputs"].get(info["length"]["field"]))
        for f in plugin.EMBED_FIELDS:
            raw = graph[nid]["inputs"].get(f)
            if isinstance(raw, str):
                try:
                    o = json.loads(raw)
                except ValueError:
                    continue
                print("  同步后 %s: totalFrames=%s durationSec=%s" % (
                    f, o.get("totalFrames"), (o.get("segments") or [{}])[0].get("durationSec")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
