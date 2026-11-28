r"""把 plugin-repos\<id> 打成可直接安装的 zip（根目录就是 plugin.json）。"""
import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOS = os.path.join(os.path.dirname(ROOT), "plugin-repos")
OUT = os.path.join(ROOT, "dist", "release")
SKIP_DIRS = {"__pycache__", "out", "wf", ".git"}
SKIP_EXT = {".pyc", ".pyo", ".log", ".tmp"}


def pack(pid):
    src = os.path.join(REPOS, pid)
    meta = json.load(io.open(os.path.join(src, "plugin.json"), encoding="utf-8"))
    ver = meta.get("version") or "0.0.0"
    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, "prompt-studio-plugin-%s-%s.zip" % (pid, ver))
    n = 0
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            rel = os.path.relpath(base, src)
            for f in files:
                if os.path.splitext(f)[1].lower() in SKIP_EXT:
                    continue
                arc = f if rel == "." else os.path.join(rel, f).replace("\\", "/")
                z.write(os.path.join(base, f), arc)
                n += 1
    return dst, n, ver


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "comfy_runner"
    dst, n, ver = pack(pid)
    print("%s v%s -> %s（%d 文件，%.1f KB）" % (
        pid, ver, dst, n, os.path.getsize(dst) / 1024.0))
