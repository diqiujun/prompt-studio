# -*- coding: utf-8 -*-
"""构建安装包：dist\PromptStudio-Setup-1.1.exe

做法：
1) 把 dist\PromptStudio 整个目录打成 payload.zip（不压缩，硬盘镜像式，解包最快）；
2) 用 PyInstaller 把 installer\setup.py 打成无控制台窗口的 setup.exe；
3) 把 payload.zip 追加到 setup.exe 末尾 —— zipfile 按路径打开即可读到末尾的中央目录，
   所以安装程序无需额外依赖，也不受单文件 4 GB 限制影响（zip64）。

用法：python build_installer.py [--no-compress]
"""
import os
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_APP = os.path.join(ROOT, "dist", "PromptStudio")
BUILD = os.path.join(ROOT, "build", "installer")
OUT_NAME = "PromptStudio-Setup-1.1.exe"
APP_SHORT = "PromptStudio"
PAYLOAD = os.path.join(BUILD, "payload.zip")
SETUP_ICO = os.path.join(ROOT, "build", "app.ico")


def log(msg):
    print(msg, flush=True)


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def make_payload(compress=False):
    src = os.environ.get("PS_DIST") or DIST_APP
    if not os.path.isdir(src):
        raise SystemExit("找不到 %s，先跑 build_all.py" % src)
    os.makedirs(BUILD, exist_ok=True)
    if os.path.isfile(PAYLOAD):
        os.remove(PAYLOAD)
    files = []
    for base, _dirs, names in os.walk(src):
        for n in names:
            p = os.path.join(base, n)
            rel = os.path.relpath(p, src)
            files.append((p, rel.replace("\\", "/")))
    files.sort()
    total = sum(os.path.getsize(p) for p, _ in files)
    log("payload：%d 个文件 · %s" % (len(files), human(total)))
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    t0 = time.time()
    done = 0
    with zipfile.ZipFile(PAYLOAD, "w", mode, allowZip64=True, compresslevel=1) as zf:
        for p, rel in files:
            zf.write(p, "payload/" + rel)
            done += os.path.getsize(p)
            if done % (300 * 1024 * 1024) < os.path.getsize(p):
                log("  …%s / %s（%.0fs）" % (human(done), human(total), time.time() - t0))
    log("payload 完成：%s（%.0f 秒）" % (human(os.path.getsize(PAYLOAD)), time.time() - t0))


def _clean(path):
    """PyInstaller 会把图标缓存在 workpath 里，不清掉会继续用旧 icon。"""
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def build_setup_exe():
    os.makedirs(BUILD, exist_ok=True)
    dist = os.path.join(BUILD, "dist")
    work = os.path.join(BUILD, "work")
    _clean(work)
    _clean(dist)
    debug = os.environ.get("PS_CONSOLE") == "1"
    name = "PromptStudioSetupDbg" if debug else "PromptStudioSetup"
    cmd = [
        sys.executable, "-m", "PyInstaller", os.path.join(ROOT, "installer", "setup.py"),
        "--name", name, "--onefile", ("--console" if debug else "--windowed"), "--noconfirm",
        "--distpath", dist, "--workpath", work, "--specpath", BUILD,
        "--hidden-import", "PyQt6.QtCore", "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "PyQt6.QtWidgets",
        "--exclude-module", "tkinter", "--exclude-module", "numpy",
        "--exclude-module", "matplotlib", "--exclude-module", "IPython",
        "--exclude-module", "pandas", "--exclude-module", "scipy",
    ]
    if os.path.isfile(SETUP_ICO):
        cmd += ["--icon", SETUP_ICO]
    logo_png = os.path.join(ROOT, "static", "logo-256.png")
    if os.path.isfile(logo_png):
        cmd += ["--add-data", logo_png + os.pathsep + "static"]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "tools", "pyi")
    env["PYTHONUTF8"] = "1"
    env["TMP"] = env["TEMP"] = os.path.join(ROOT, "build", "piptmp")
    log("打包安装程序 …")
    p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                       encoding="mbcs", errors="ignore")
    exe = os.path.join(dist, name + ".exe")
    if not os.path.isfile(exe):
        log(p.stdout[-3000:])
        log(p.stderr[-3000:])
        raise SystemExit("setup.exe 打包失败")
    log("setup.exe：%s" % human(os.path.getsize(exe)))
    return exe


def build_setup_onedir():
    """目录版安装器：exe + _internal + payload.zip 放同一目录。

    为什么还留一份：PyInstaller onefile 启动时要先把自身解包到临时目录，
    某些机器（杀软拦截 / 临时目录受限）会报 “Could not create temporary directory!”；
    onedir 不需要自解包，任何机器都能起。
    """
    os.makedirs(BUILD, exist_ok=True)
    debug = os.environ.get("PS_CONSOLE") == "1"
    name = "PromptStudioSetupDbg" if debug else "PromptStudioSetup"
    dist = os.path.join(BUILD, "dist_onedir")
    work = os.path.join(BUILD, "work_onedir")
    _clean(work)
    _clean(dist)
    cmd = [
        sys.executable, "-m", "PyInstaller", os.path.join(ROOT, "installer", "setup.py"),
        "--name", name, "--onedir", ("--console" if debug else "--windowed"), "--noconfirm",
        "--distpath", dist, "--workpath", work, "--specpath", BUILD,
        "--hidden-import", "PyQt6.QtCore", "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "PyQt6.QtWidgets",
        "--exclude-module", "tkinter", "--exclude-module", "numpy",
        "--exclude-module", "matplotlib", "--exclude-module", "IPython",
        "--exclude-module", "pandas", "--exclude-module", "scipy",
    ]
    if os.path.isfile(SETUP_ICO):
        cmd += ["--icon", SETUP_ICO]
    logo_png = os.path.join(ROOT, "static", "logo-256.png")
    if os.path.isfile(logo_png):
        cmd += ["--add-data", logo_png + os.pathsep + "static"]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "tools", "pyi")
    env["PYTHONUTF8"] = "1"
    env["TMP"] = env["TEMP"] = os.path.join(ROOT, "build", "piptmp")
    log("打包目录版安装程序 …")
    p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                       encoding="mbcs", errors="ignore")
    src = os.path.join(dist, name)
    if not os.path.isdir(src):
        log(p.stdout[-3000:])
        log(p.stderr[-3000:])
        raise SystemExit("目录版安装程序打包失败")
    out = os.path.join(ROOT, "dist", "PromptStudio-Setup-1.1")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(out, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    if os.environ.get("PS_NO_PAYLOAD") != "1":
        shutil.copy2(PAYLOAD, os.path.join(out, "payload.zip"))
    total = 0
    for base, _dirs, names in os.walk(out):
        for n in names:
            total += os.path.getsize(os.path.join(base, n))
    log("目录版安装器：%s（%s）" % (out, human(total)))
    return out


def assemble(setup_exe, embed=False):
    """默认出两个文件：安装器 exe + payload.zip。

    为什么不把 6 GB 拼进 exe：超过 Windows 能执行的 PE 大小，CreateProcess 直接报
    WinError 193（%1 不是有效的 Win32 应用程序），双击也起不来。只有 payload 很小时
    才用 --embed 拼成一个文件。
    """
    out_exe = os.path.join(ROOT, "dist", OUT_NAME)
    out_pay = os.path.join(ROOT, "dist", OUT_NAME[:-4] + ".payload.zip")
    if embed:
        size = os.path.getsize(PAYLOAD)
        if size > 3.6 * 1024 ** 3:
            raise SystemExit("payload %s 太大，不能拼进 exe（上限约 3.6 GB）；去掉 --embed"
                             % human(size))
        if os.path.isfile(out_exe):
            os.remove(out_exe)
        log("拼接：setup.exe + payload.zip → %s" % os.path.basename(out_exe))
        with open(out_exe, "wb") as w, open(setup_exe, "rb") as a, open(PAYLOAD, "rb") as b:
            shutil.copyfileobj(a, w, 16 * 1024 * 1024)
            shutil.copyfileobj(b, w, 16 * 1024 * 1024)
        with zipfile.ZipFile(out_exe) as zf:
            names = zf.namelist()
            bad = zf.testzip()
        log("自检：条目 %d 个，首项 %s，损坏项 %s" % (len(names), names[0] if names else "-", bad or "无"))
        log("安装包：%s（%s）" % (out_exe, human(os.path.getsize(out_exe))))
        return out_exe

    if os.path.isfile(out_exe):
        os.remove(out_exe)
    shutil.copy2(setup_exe, out_exe)
    if os.path.isfile(out_pay):
        os.remove(out_pay)
    shutil.copy2(PAYLOAD, out_pay)
    with zipfile.ZipFile(out_pay) as zf:
        names = zf.namelist()
        bad = zf.testzip()
        exe_inside = "payload/%s.exe" % APP_SHORT
    log("自检 payload：条目 %d 个，首项 %s，含 %s %s，损坏项 %s"
        % (len(names), names[0] if names else "-", exe_inside,
           "是" if exe_inside in names else "否！", bad or "无"))
    log("安装器：%s（%s）" % (out_exe, human(os.path.getsize(out_exe))))
    log("安装数据：%s（%s）" % (out_pay, human(os.path.getsize(out_pay))))
    log("发布时这两个文件必须放在同一目录（安装器会自动找同目录的 *.payload.zip 或 payload.zip）。")
    return out_exe


def main():
    # 默认不压缩：模型是 gguf（已高熵），deflate 收益极小而耗时数倍；store 解包最快
    compress = "--compress" in sys.argv
    if "--skip-payload" in sys.argv and os.path.isfile(PAYLOAD):
        log("复用已有 payload：%s（%s）" % (PAYLOAD, human(os.path.getsize(PAYLOAD))))
    else:
        make_payload(compress=compress)
    if "--onedir" in sys.argv:
        out = build_setup_onedir()
        log("完成：%s" % out)
        return
    exe = build_setup_exe()
    out = assemble(exe, embed="--embed" in sys.argv)
    log("完成：%s" % out)


if __name__ == "__main__":
    main()
