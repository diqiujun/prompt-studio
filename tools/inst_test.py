# -*- coding: utf-8 -*-
"""安装包静默安装实测：装到指定目录 → 校验文件/版本/卸载项/记忆目录。

用法：
    python tools\\inst_test.py                 # 默认装到 E:\\_pstest 与中文路径各一次
    python tools\\inst_test.py --dir D:\\xxx   # 只测一个目录
    python tools\\inst_test.py --keep          # 装完不删目录
"""
import os
import sys
import shutil
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(ROOT, "dist", "PromptStudio-Setup-1.1.exe")
LOG = os.path.join(ROOT, "data", "inst_test.log")
CREATE_NO_WINDOW = 0x08000000
TS = time.strftime("%H:%M:%S")


def say(msg):
    line = "[%s] %s" % (TS, msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def dir_size(path):
    n = 0
    total = 0
    for base, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
                n += 1
            except OSError:
                pass
    return n, total


def version_of(exe):
    try:
        import win32api  # noqa
    except Exception:
        pass
    ps = ("(Get-Item '%s').VersionInfo | Select-Object CompanyName,ProductName,"
          "FileVersion,Comments | ConvertTo-Json -Compress" % exe)
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, encoding="mbcs",
                           errors="ignore", creationflags=CREATE_NO_WINDOW, timeout=60)
        return (p.stdout or "").strip()
    except Exception as exc:
        return "读取失败：%s" % exc


def install(target):
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
    say("安装包：%s" % SETUP)
    say("目标目录：%s" % target)
    t0 = time.time()
    try:
        p = subprocess.Popen([SETUP, "--silent", "--dir", target],
                             creationflags=CREATE_NO_WINDOW)
        p.wait(timeout=1800)
        code = p.returncode
    except subprocess.TimeoutExpired:
        p.kill()
        say("超时（30 分钟）→ 失败")
        return False
    dt = time.time() - t0
    n, total = dir_size(target) if os.path.isdir(target) else (0, 0)
    say("退出码 %s · 耗时 %.1f 秒 · 文件 %d 个 · 共 %.2f GB" % (code, dt, n, total / 1024 ** 3))
    exe = os.path.join(target, "PromptStudio.exe")
    if not os.path.isfile(exe):
        say("✗ 没有 %s → 安装失败" % exe)
        log = os.path.join(os.path.dirname(SETUP), "setup_run.log")
        err = os.path.join(os.path.dirname(SETUP), "setup_error.log")
        for f in (log, err):
            if os.path.isfile(f):
                with open(f, encoding="utf-8", errors="ignore") as fh:
                    say("%s 尾部：%s" % (os.path.basename(f), fh.read()[-400:]))
        return False
    say("版本信息：%s" % version_of(exe))
    un = os.path.join(target, "卸载 PromptStudio.cmd")
    say("卸载脚本：%s" % ("有" if os.path.isfile(un) else "缺"))
    reg = ("Test-Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\PromptStudio'")
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-Command", reg],
                           capture_output=True, text=True, encoding="mbcs",
                           errors="ignore", creationflags=CREATE_NO_WINDOW, timeout=60)
        say("注册表卸载项：%s" % (p.stdout or "").strip())
    except Exception:
        pass
    for sub in ("models", "runtime", "plugins", "templates"):
        d = os.path.join(target, sub)
        if os.path.isdir(d):
            c, s = dir_size(d)
            say("  ├ %-9s %5d 个 · %.2f GB" % (sub, c, s / 1024 ** 3))
        else:
            say("  ├ %-9s 缺失！" % sub)
    sd = os.path.join(os.environ.get("LOCALAPPDATA", ""), "PromptStudio", "setup_dir.txt")
    if os.path.isfile(sd):
        with open(sd, encoding="utf-8") as f:
            say("记住的安装目录：%s" % f.read().strip())
    return True


def main():
    args = sys.argv[1:]
    keep = "--keep" in args
    targets = []
    if "--dir" in args:
        targets = [args[args.index("--dir") + 1]]
    else:
        targets = [r"E:\_pstest", os.path.join(ROOT, "build", "inst_custom")]
    open(LOG, "w", encoding="utf-8").close()
    ok_all = True
    for t in targets:
        say("=" * 60)
        ok = install(t)
        ok_all = ok_all and ok
        if ok and not keep:
            say("清理测试目录（--keep 可保留）")
            shutil.rmtree(t, ignore_errors=True)
    say("结果：%s" % ("全部通过" if ok_all else "有失败"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
