# -*- coding: utf-8 -*-
"""桌面版：右键菜单中文化 + 复制按钮走 Qt 剪贴板 的实机自检。

用法：python test_clipboard_menu.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu-sandbox --lang=zh-CN")

import desktop  # noqa: E402
import app as backend  # noqa: E402

PORT = 8790
DATA = os.path.join(ROOT, "data")
FAILS = []


def ok(name, extra=""):
    print("OK  %s %s" % (name, extra))


def bad(name, extra=""):
    FAILS.append(name)
    print("FAIL %s %s" % (name, extra))


def wait_http(n=60):
    import urllib.request
    for _ in range(n):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/api/state" % PORT, timeout=2) as r:
                r.read()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    th = threading.Thread(
        target=lambda: backend.app.run(host="127.0.0.1", port=PORT, threaded=True,
                                       use_reloader=False),
        daemon=True)
    th.start()
    if not wait_http():
        print("内核没起来")
        return 1

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop, QTimer

    qapp = QApplication.instance() or QApplication(sys.argv or ["clip-test"])
    win = desktop.Main("http://127.0.0.1:%d/" % PORT, PORT)
    win.resize(1200, 800)
    win.show()

    # 等页面加载完（最多 30 秒）
    loop = QEventLoop()
    done = {"v": False}

    def _fin():
        done["v"] = True
        loop.quit()

    win.view.loadFinished.connect(lambda _ok_flag: _fin())
    QTimer.singleShot(30000, loop.quit)
    loop.exec()
    if not done["v"]:
        bad("页面加载")
    else:
        ok("页面加载")

    # 给 qwebchannel.js 与桥初始化留时间
    for _ in range(40):
        qapp.processEvents()
        time.sleep(0.1)

    # 1. 桥是否存在
    res = {"v": None}

    def _cb(v):
        res["v"] = v

    win.view.page().runJavaScript("(typeof PSAPP !== 'undefined' && PSAPP) ? 'yes' : 'no'", _cb)
    for _ in range(60):
        qapp.processEvents()
        time.sleep(0.05)
        if res["v"] is not None:
            break
    if res["v"] == "yes":
        ok("网页已连上桌面桥 PSAPP")
    else:
        bad("桌面桥 PSAPP", repr(res["v"]))

    # 2. 通过桥写剪贴板（模拟点“复制全部”）
    marker = "复制测试-%d" % int(time.time())
    win.view.page().runJavaScript("try{PSAPP.copyText(%s);'ok'}catch(e){'err:'+e}" % json.dumps(marker))
    got = ""
    for _ in range(60):
        qapp.processEvents()
        time.sleep(0.05)
        got = QApplication.clipboard().text()
        if got == marker:
            break
    if got == marker:
        ok("复制按钮写系统剪贴板", repr(got))
    else:
        bad("复制按钮写系统剪贴板", "剪贴板=%r" % (got[:40],))

    # 3. 右键菜单全中文
    menu = win.view.build_menu()
    labels = [a.text() for a in menu.actions() if a.text()]
    ascii_only = [t for t in labels if all(ord(c) < 128 for c in t)]
    if labels and not ascii_only:
        ok("右键菜单中文", " / ".join(labels))
    else:
        bad("右键菜单中文", "英文项=%r 全部=%r" % (ascii_only, labels))

    # 4. 网页切主题 → 外壳立即跟随（走桥，不等轮询）
    win.view.page().runJavaScript("applyTheme('light')")
    t0 = time.time()
    followed = False
    while time.time() - t0 < 3:
        qapp.processEvents()
        time.sleep(0.01)
        if "#f6f7f9" in win.styleSheet():
            followed = True
            break
    ms = int((time.time() - t0) * 1000)
    if followed:
        ok("点主题按钮 → 菜单栏/状态栏立即换色", "%d ms" % ms)
    else:
        bad("主题即时跟随", "%d ms 未变" % ms)
    win.view.page().runJavaScript("applyTheme('dark')")
    for _ in range(60):
        qapp.processEvents()
        time.sleep(0.02)
        if "#12151b" in win.styleSheet():
            break

    win.close()
    qapp.processEvents()
    print("")
    print("结果：失败 %d 项" % len(FAILS))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
