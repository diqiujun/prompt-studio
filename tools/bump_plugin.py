r"""把 dist 里的插件同步到 plugin-repos，并可选改版本号。

用法：
    python tools\bump_plugin.py comfy_runner 1.0.1
"""
import io
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "dist", "PromptStudio", "plugins")
REPOS = os.path.join(os.path.dirname(ROOT), "plugin-repos")
SKIP_DIRS = {"__pycache__", "out", "wf", ".git"}
SKIP_EXT = {".pyc", ".pyo", ".log", ".tmp"}


def sync(pid):
    src = os.path.join(SRC, pid)
    dst = os.path.join(REPOS, pid)
    if not os.path.isdir(src):
        raise SystemExit("找不到插件目录：%s" % src)
    if not os.path.isdir(dst):
        raise SystemExit("找不到仓库目录：%s（先跑 tools\\prepare_plugin_repos.py）" % dst)
    n = 0
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(base, src)
        tgt = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(tgt, exist_ok=True)
        for f in files:
            if os.path.splitext(f)[1].lower() in SKIP_EXT:
                continue
            shutil.copy2(os.path.join(base, f), os.path.join(tgt, f))
            n += 1
    return n


def bump(pid, ver):
    p = os.path.join(REPOS, pid, "plugin.json")
    if not os.path.exists(p):
        return None
    d = json.load(io.open(p, encoding="utf-8"))
    old = d.get("version")
    if ver:
        d["version"] = ver
        io.open(p, "w", encoding="utf-8", newline="\n").write(
            json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    return old, d.get("version")


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "comfy_runner"
    ver = sys.argv[2] if len(sys.argv) > 2 else ""
    n = sync(pid)
    print("同步 %d 个文件 → %s" % (n, os.path.join(REPOS, pid)))
    r = bump(pid, ver)
    if r:
        print("版本 %s → %s" % r)
