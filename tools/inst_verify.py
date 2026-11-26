# -*- coding: utf-8 -*-
"""安装 → 跑 14 步验收 → 汇总。用法：python tools\\inst_verify.py [目标目录]"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(ROOT, "dist", "PromptStudio-Setup-1.1", "PromptStudioSetup.exe")
LOG = os.path.join(ROOT, "data", "inst_verify.log")


def say(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else r"E:\新建文件夹\_psinst"
    open(LOG, "w", encoding="utf-8").close()
    say("安装器 %s" % SETUP)
    t = time.time()
    p = subprocess.run([SETUP, "--silent", "--dir", target], capture_output=True, timeout=3600)
    say("安装完成 rc=%s %.1fs" % (p.returncode, time.time() - t))
    if p.returncode != 0:
        say("安装失败：" + (p.stdout or b"").decode("utf-8", "replace")[:400])
        return 1
    exe = os.path.join(target, "PromptStudio.exe")
    say("可执行 %s 存在=%s" % (exe, os.path.isfile(exe)))
    env = dict(os.environ)
    env["EXE_PATH"] = exe
    env["PYTHONUTF8"] = "1"
    t = time.time()
    v = subprocess.run([sys.executable, "verify_desktop.py"], cwd=ROOT, env=env,
                       capture_output=True, timeout=5400)
    tail = (v.stdout or b"").decode("utf-8", "replace")
    say("验收 rc=%s %.1fs" % (v.returncode, time.time() - t))
    for line in tail.splitlines()[-14:]:
        say("  " + line)
    if v.returncode != 0:
        say("stderr: " + (v.stderr or b"").decode("utf-8", "replace")[-600:])
    return v.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        say("异常 %s: %s" % (exc.__class__.__name__, exc))
        sys.exit(3)
