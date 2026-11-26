"""打发布包：源码 zip + 安装器 + payload 分卷 + 校验值 + 合并脚本。

用法：
    python tools\\release_pack.py            # 用 src\\settings.py 里的 APP_VERSION
    python tools\\release_pack.py --ver 1.1.0 --part-gib 1.6

产出目录：dist\\release\\
    PromptStudio-<ver>-src.zip                 源码（不含 dist/build/models/runtime/data/work）
    PromptStudio-Setup-<ver>.exe               安装器
    PromptStudio-Setup-<ver>.payload.zip.part1…  安装数据分卷（默认每个 1.6 GiB，GitHub 单文件上限 2 GB）
    SHA256SUMS.txt                             全部文件的 sha256
    合并并安装.bat                               用户侧：合卷 + 启动安装器

注意：模型（models\\*.gguf）与 llama.cpp 预编译包（runtime\\packs\\*.zip）**不**打进发布包，
      由安装器随包分发或用户自行准备。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUT = DIST / "release"
APP = "PromptStudio"

# 源码包里要排除的目录（相对 ROOT，正斜杠小写）
SKIP_DIRS = {
    "dist", "build", "data", "models", "runtime", "work", ".git", ".github",
    ".venv", "venv", "__pycache__", ".idea", ".vscode", "node_modules",
    "plugins/pose_gallery", "plugins/comfy_runner",
    "tools/pyi", "tools/site-packages",
}
# 目录名前缀也要排除（dist_dbg、_prev_app_* 这类）
SKIP_DIR_PREFIXES = ("dist_", "_dist", "build_", "_prev_app", "tmp_", "_tmp")
# 排除的文件名模式
SKIP_FILE_PATTERNS = [
    re.compile(r"^tmp_.*\.py$", re.I),
    re.compile(r"^_tmp_.*\.py$", re.I),
    re.compile(r".*\.pyc$", re.I),
    re.compile(r".*\.pyo$", re.I),
    re.compile(r".*\.log$", re.I),
    re.compile(r"^\.DS_Store$", re.I),
    re.compile(r"^Thumbs\.db$", re.I),
    re.compile(r".*\.spec\.bak$", re.I),
]
SKIP_EXTS = {".exe", ".dll", ".pyd", ".zip", ".7z", ".rar"}


def app_version() -> str:
    p = ROOT / "src" / "settings.py"
    try:
        s = io.open(p, encoding="utf-8").read()
        m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', s)
        if m:
            return m.group(1)
    except OSError:
        pass
    return "1.1"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with io.open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def want_dir(rel: str) -> bool:
    """rel 是相对 ROOT 的目录路径（正斜杠，可能为空串）。"""
    if not rel:
        return True
    low = rel.lower().strip("/")
    if low in SKIP_DIRS:
        return False
    for seg in low.split("/"):
        if seg in SKIP_DIRS:
            return False
        if seg.startswith(SKIP_DIR_PREFIXES):
            return False
    return True


def want_file(rel: str) -> bool:
    low = rel.lower()
    parts = low.split("/")
    if not want_dir("/".join(parts[:-1])):
        return False
    name = parts[-1]
    for rx in SKIP_FILE_PATTERNS:
        if rx.match(name):
            return False
    if Path(name).suffix.lower() in SKIP_EXTS:
        return False
    return True


def build_src_zip(ver: str) -> Path:
    out = OUT / f"{APP}-{ver}-src.zip"
    n = 0
    total = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            rel_dir = os.path.relpath(dirpath, ROOT).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirnames[:] = [
                d for d in dirnames
                if want_dir((rel_dir + "/" + d).lstrip("/"))
            ]
            for fn in filenames:
                rel = (rel_dir + "/" + fn).lstrip("/")
                if not want_file(rel):
                    continue
                src = Path(dirpath) / fn
                try:
                    z.write(src, f"{APP}-{ver}/{rel}")
                    n += 1
                    total += src.stat().st_size
                except OSError as e:
                    print(f"  跳过 {rel}：{e}")
    print(f"源码包：{out.name}  {n} 个文件  {total / 1e6:.2f} MB")
    return out


def split_file(src: Path, part_bytes: int, base_name: str) -> list[Path]:
    parts: list[Path] = []
    with io.open(src, "rb") as f:
        idx = 1
        while True:
            chunk = f.read(part_bytes)
            if not chunk:
                break
            p = OUT / f"{base_name}.part{idx}"
            with io.open(p, "wb") as g:
                g.write(chunk)
            parts.append(p)
            print(f"  分卷 {p.name}  {p.stat().st_size / 1e9:.2f} GB")
            idx += 1
    return parts


MERGE_BAT = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
set BASE=PromptStudio-Setup-{ver}
echo === PromptStudio {ver} 安装准备 ===
if not exist "%BASE%.exe" (
  echo [错误] 找不到 %BASE%.exe，请把 Release 里的所有文件下载到同一个文件夹。
  pause & exit /b 1
)
if exist "%BASE%.payload.zip" (
  echo 已存在 %BASE%.payload.zip，跳过合并。
  goto run
)
echo 正在合并分卷...
copy /b "%BASE%.payload.zip.part1"+"%BASE%.payload.zip.part2"+"%BASE%.payload.zip.part3"+"%BASE%.payload.zip.part4" "%BASE%.payload.zip" >nul
if errorlevel 1 (
  echo [错误] 合并失败。请确认 4 个 part 文件都在本目录，且总大小约 6 GB。
  pause & exit /b 1
)
echo 合并完成。
:run
echo 正在启动安装器...
start "" "%BASE%.exe"
exit /b 0
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", default="")
    ap.add_argument("--part-gib", type=float, default=1.6, help="分卷大小（GiB），须小于 2")
    ap.add_argument("--src-only", action="store_true", help="只打源码 zip，不切安装包分卷")
    a = ap.parse_args()

    ver = a.ver or app_version()
    if a.src_only:
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir(parents=True, exist_ok=True)
        z = build_src_zip(ver)
        (OUT / "SHA256SUMS.txt").write_text(f"{sha256_file(z)}  {z.name}\n", encoding="utf-8")
        print(f"\n完成 → {OUT}")
        return 0

    setup_exe = DIST / f"{APP}-Setup-{ver}.exe"
    payload = DIST / f"{APP}-Setup-{ver}.payload.zip"
    if not setup_exe.exists():
        # 兼容旧命名
        alt = DIST / "PromptStudio-Setup-1.1.exe"
        altp = DIST / "PromptStudio-Setup-1.1.payload.zip"
        if alt.exists() and altp.exists():
            setup_exe, payload = alt, altp
            ver = "1.1"
        else:
            print(f"找不到安装器：{setup_exe}（先跑 python build_installer.py）")
            return 1
    if not payload.exists():
        print(f"找不到安装数据：{payload}（先跑 python build_installer.py）")
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"版本 {ver}")
    src_zip = build_src_zip(ver)

    exe_out = OUT / f"{APP}-Setup-{ver}.exe"
    shutil.copy2(setup_exe, exe_out)
    print(f"安装器：{exe_out.name}  {exe_out.stat().st_size / 1e6:.1f} MB")

    part_bytes = int(a.part_gib * 1024 ** 3)
    parts = split_file(payload, part_bytes, f"{APP}-Setup-{ver}.payload.zip")

    bat = OUT / "合并并安装.bat"
    io.open(bat, "w", encoding="utf-8", newline="\r\n").write(MERGE_BAT.replace("{ver}", ver))
    # bat 里含中文，改用无 BOM 的 UTF-8 + chcp 65001；部分 cmd 仍可能显示方块，不影响执行

    files = [src_zip, exe_out, *parts, bat]
    lines = []
    for f in files:
        lines.append(f"{sha256_file(f)}  {f.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"校验值：SHA256SUMS.txt（{len(files)} 个文件）")

    total = sum(f.stat().st_size for f in files)
    print(f"\n完成 → {OUT}  合计 {total / 1e9:.2f} GB")
    print("下一步：gh release create v%s dist\\release\\* --title \"PromptStudio %s\"" % (ver, ver))
    return 0


if __name__ == "__main__":
    sys.exit(main())
