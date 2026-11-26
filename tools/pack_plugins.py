# -*- coding: utf-8 -*-
"""把 dist 里的插件打成长这样能直接装进 PM 的 zip：zip 根就是 plugin.json。

用法：python tools/pack_plugins.py comfy_runner sketch2img
产物：dist/release/prompt-studio-plugin-<id>-<version>.zip
"""
import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "dist", "PromptStudio", "plugins")
OUT = os.path.join(ROOT, "dist", "release")

SKIP_DIRS = {"__pycache__", ".git", "out", "wf"}
SKIP_EXT = {".pyc", ".pyo", ".log", ".tmp"}


def pack(name):
    src = os.path.join(SRC, name)
    manifest = os.path.join(src, "plugin.json")
    if not os.path.isfile(manifest):
        print("跳过 %s：没有 plugin.json" % name)
        return None
    meta = json.load(io.open(manifest, encoding="utf-8-sig"))
    pid = meta.get("id") or name
    ver = meta.get("version") or "1.0"
    out = os.path.join(OUT, "prompt-studio-plugin-%s-%s.zip" % (pid, ver))
    os.makedirs(OUT, exist_ok=True)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
            for f in files:
                if os.path.splitext(f)[1].lower() in SKIP_EXT:
                    continue
                full = os.path.join(base, f)
                rel = os.path.relpath(full, src).replace("\\", "/")
                z.write(full, rel)
                n += 1
    print("%-12s -> %s  (%d 文件, %.1f KB, id=%s v=%s)" % (
        name, os.path.basename(out), n, os.path.getsize(out) / 1024.0, pid, ver))
    return out


def main():
    names = sys.argv[1:] or ["comfy_runner", "sketch2img"]
    for n in names:
        pack(n)


if __name__ == "__main__":
    main()
