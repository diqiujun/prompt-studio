# -*- coding: utf-8 -*-
"""把两个自制插件分别整理成独立的 git 仓库工作目录（E:\\新建文件夹\\plugin-repos\\<id>）。

只做文件整理：复制源码、写 .gitignore、复制 LICENSE。README 单独手写。
用法：python tools\\prepare_plugin_repos.py
"""
import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "dist", "PromptStudio", "plugins")
OUT = os.path.join(os.path.dirname(ROOT), "plugin-repos")

# 每个插件要带走的额外文件（相对插件目录）；data 里的内置工作流必须带
KEEP = {
    "comfy_runner": [],
    "sketch2img": [os.path.join("data", "workflow.json")],
}
SKIP_DIRS = {"__pycache__", ".git", "out", "wf"}
SKIP_EXT = {".pyc", ".pyo", ".log", ".tmp"}

GITIGNORE = """__pycache__/
*.py[cod]
*.log
# 运行时产物（ComfyUI 输出落盘、保存过的工作流副本）
out/
wf/
"""


def want(rel):
    parts = rel.split("/")
    for p in parts[:-1]:
        if p in SKIP_DIRS:
            return False
    return os.path.splitext(parts[-1])[1].lower() not in SKIP_EXT


def copy_plugin(pid):
    src = os.path.join(SRC, pid)
    dst = os.path.join(OUT, pid)
    if not os.path.isdir(src):
        raise SystemExit("找不到插件目录：%s" % src)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    n = 0
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            ap = os.path.join(base, f)
            rel = os.path.relpath(ap, src).replace("\\", "/")
            if not want(rel):
                continue
            # data/ 下只保留白名单（内置工作流），其余运行时数据不带
            if rel.startswith("data/") and rel not in [k.replace("\\", "/") for k in KEEP.get(pid, [])]:
                continue
            tp = os.path.join(dst, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(tp), exist_ok=True)
            shutil.copy2(ap, tp)
            n += 1
    with io.open(os.path.join(dst, ".gitignore"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GITIGNORE)
    lic = os.path.join(ROOT, "LICENSE")
    if os.path.isfile(lic):
        shutil.copy2(lic, os.path.join(dst, "LICENSE"))
    print("%-12s %d 个文件 -> %s" % (pid, n, dst))
    return dst


def main():
    os.makedirs(OUT, exist_ok=True)
    for pid in ("comfy_runner", "sketch2img"):
        copy_plugin(pid)
    print("\n输出目录：%s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
