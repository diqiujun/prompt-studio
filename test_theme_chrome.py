# -*- coding: utf-8 -*-
"""检查桌面外壳（菜单栏 / 状态栏）是否跟随网页主题切换。

做法：起一个 Flask 内核（用 dev 端口），构造 Main 窗口，分别按 dark / light 取样式表与截图，
再通过 /api/ui/theme 走一次「网页侧切换 → 窗口侧跟随」的联动。
"""
import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"

import app as backend            # noqa: E402
import settings                  # noqa: E402
import desktop                   # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

FAILS = []
DATA = settings.data_dir()
PORT = 8788


def http(path, body=None):
    url = "http://127.0.0.1:%d%s" % (PORT, path)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def wait_http(n=60):
    for _ in range(n):
        try:
            http("/api/state")
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    th = threading.Thread(target=lambda: backend.app.run(host="127.0.0.1", port=PORT,
                                                        threaded=True, use_reloader=False),
                          daemon=True)
    th.start()
    if not wait_http():
        print("内核没起来")
        return 1

    qapp = QApplication.instance() or QApplication(sys.argv or ["theme-test"])
    win = desktop.Main("http://127.0.0.1:%d/" % PORT, PORT)
    win.resize(1200, 800)
    win.show()
    qapp.processEvents()
    time.sleep(1.0)

    # 1. 深色外壳
    http("/api/ui/theme", {"theme": "dark"})
    win.apply_theme("dark")
    qapp.processEvents()
    dark_qss = win.styleSheet()
    dark_bar = win.statusBar().styleSheet()
    if "#12151b" in dark_qss and "#12151b" in dark_bar:
        print("OK  深色外壳（菜单栏/状态栏 #12151b）")
    else:
        FAILS.append("深色外壳")
        print("FAIL 深色外壳", dark_qss[:120])
    time.sleep(0.6)
    win.grab().save(str(DATA / "chrome_dark.png"))

    # 2. 网页侧切到浅色 → 窗口应自动跟随（不再手动催 refresh_local，测真实延迟）
    http("/api/ui/theme", {"theme": "light"})
    t0 = time.time()
    followed = False
    while time.time() - t0 < 6:
        qapp.processEvents()
        time.sleep(0.02)
        if "#f6f7f9" in win.styleSheet():
            followed = True
            break
    ms = int((time.time() - t0) * 1000)
    if followed:
        print("OK  网页切浅色后外壳自动跟随（%d ms 内生效）" % ms)
    else:
        FAILS.append("外壳跟随主题")
        print("FAIL 外壳跟随主题，当前 QSS:", win.styleSheet()[:160])
        ms = -1
    print("     跟随延迟 = %s ms" % ms)

    time.sleep(0.6)
    win.grab().save(str(DATA / "chrome_light.png"))

    # 3. 状态栏文字颜色是否随主题变
    bar_light = win.statusBar().styleSheet()
    if "#ffffff" in bar_light and "#5a6472" in bar_light:
        print("OK  浅色状态栏（白底 + #5a6472 文字）")
    else:
        FAILS.append("浅色状态栏")
        print("FAIL 浅色状态栏", bar_light[:160])

    # 4. 切回深色
    http("/api/ui/theme", {"theme": "dark"})
    t0 = time.time()
    for _ in range(300):
        qapp.processEvents()
        time.sleep(0.02)
        if "#12151b" in win.styleSheet():
            break
    back_ms = int((time.time() - t0) * 1000)
    print("OK  切回深色（%d ms）" % back_ms if "#12151b" in win.styleSheet() else "FAIL 切回深色")
    if "#12151b" not in win.styleSheet():
        FAILS.append("切回深色")

    win.close()
    qapp.processEvents()
    print("")
    print("结果：失败 %d 项" % len(FAILS))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
