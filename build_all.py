"""一条命令重打包：停进程 → 移出模型/运行时 → PyInstaller → 移回 → 组装绿色发行目录。

跑法：python build_all.py
日志：data\\build_all.log
"""
import io
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
APP = os.path.join(DIST, "PromptStudio")
LOG = os.path.join(ROOT, "data", "build_all.log")
KEEP = [("models", os.path.join(DIST, "_models_tmp")),
        ("llama", os.path.join(DIST, "_llama_tmp"))]


def log(msg=""):
    print(msg)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def run(cmd, cwd=ROOT, env=None):
    log("$ " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = (p.stdout or b"").decode("utf-8", "replace")
    tail = "\n".join([ln for ln in text.splitlines() if ln.strip()][-4:])
    log(tail)
    log("   exit=%d" % p.returncode)
    return p.returncode, text


def main():
    io.open(LOG, "w", encoding="utf-8").close()
    log("== 0. 清理进程 ==")
    for name in ("PromptStudio.exe", "PromptStudioDbg.exe", "llama-server.exe"):
        subprocess.run(["taskkill", "/IM", name, "/T", "/F"], capture_output=True)
    time.sleep(2)

    log("== 1. 把旧发行目录整体挪开（避免 PyInstaller 删除时撞占用）==")
    prev = os.path.join(DIST, "_prev_app_%s" % time.strftime("%H%M%S"))
    if os.path.isdir(prev):
        shutil.rmtree(prev, ignore_errors=True)
    if os.path.isdir(APP):
        try:
            os.rename(APP, prev)
            log("   moved %s → %s" % (APP, prev))
        except OSError as e:
            log("   ! 直接改名失败（%s），改用 robocopy 搬移" % e)
            rc = subprocess.run(["robocopy", APP, prev, "/E", "/MOVE",
                                 "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS", "/NP"],
                                capture_output=True).returncode
            shutil.rmtree(APP, ignore_errors=True)
            if rc >= 8 or os.path.isdir(APP):
                log("   !! robocopy 也没搬走（rc=%s），请关掉 PromptStudio 或重启后再试" % rc)
                return 1
            log("   moved by robocopy %s → %s (rc=%s)" % (APP, prev, rc))

    log("== 2. 静态检查 ==")
    run([sys.executable, "compile_check.py"])

    log("== 3. PyInstaller ==")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "tools", "pyi")
    env["PYTHONUTF8"] = "1"
    tmpdir = os.path.join(ROOT, "build", "piptmp")
    os.makedirs(tmpdir, exist_ok=True)
    env["TMP"] = tmpdir
    env["TEMP"] = tmpdir
    code, text = run([sys.executable, "-m", "PyInstaller", os.path.join("build", "promptstudio.spec"),
                      "--noconfirm", "--distpath", "dist", "--workpath", os.path.join("build", "work14")],
                     env=env)
    if "Build complete!" not in text:
        log("!!! PyInstaller 失败，停止")
        return 1

    log("== 4. 删除旧发行目录 ==")
    if os.path.isdir(prev):
        shutil.rmtree(prev, ignore_errors=True)
        log("   removed %s" % prev)

    log("== 5. 组装绿色发行目录 ==")
    run([sys.executable, "build_portable.py"])

    log("== 6. 汇总 ==")
    total = 0
    for dirpath, _, files in os.walk(APP):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    log("发行目录：%s  %.2f GB" % (APP, total / 1024.0 / 1024.0 / 1024.0))
    log("exe：%d 字节" % os.path.getsize(os.path.join(APP, "PromptStudio.exe")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
