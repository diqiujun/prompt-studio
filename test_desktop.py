# -*- coding: utf-8 -*-
"""桌面窗口自检（不弹真窗口）：离屏渲染页面并截图，用于验证 PyQt6 + QtWebEngine 链路。

用法：
    $env:QT_QPA_PLATFORM='offscreen'; $env:QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox'; python test_desktop.py

产物：data\\desktop_shot.png、日志 data\\desktop_test.log
退出码：0 全部通过
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import app as backend          # noqa: E402
import desktop                 # noqa: E402
import settings                # noqa: E402

FAILS = []
LOG = []


def out(msg=""):
    print(msg)
    LOG.append(msg)


def step(name, ok, detail=""):
    if ok:
        out("[ OK ] %s %s" % (name, detail))
    else:
        out("[FAIL] %s %s" % (name, detail))
        FAILS.append(name)


def main() -> int:
    from PyQt6.QtCore import QTimer, QUrl
    from PyQt6.QtWidgets import QApplication

    port = backend.free_port(8765)
    backend.serve_in_thread(port)
    url = "http://127.0.0.1:%d/" % port
    ok = backend.wait_http(url, timeout=30)
    step("服务线程就绪", ok, url)

    qapp = QApplication(sys.argv[:1])
    win = desktop.Main(url, port)
    win.resize(1280, 860)
    win.show()

    state = {"loaded": False, "tries": 0}

    def poll():
        state["tries"] += 1
        view = win.view
        title = view.title()
        if title:
            state["loaded"] = True
            shot()
        elif state["tries"] > 40:
            shot()
        else:
            QTimer.singleShot(500, poll)

    def shot():
        path = str(settings.data_dir() / "desktop_shot.png")
        pix = win.grab()
        pix.save(path)
        step("窗口已渲染", os.path.isfile(path) and os.path.getsize(path) > 5000,
             "%s  %d B  标题=%r" % (path, os.path.getsize(path) if os.path.isfile(path) else -1, win.view.title()))
        step("页面标题正确", "提示词" in (win.view.title() or ""), repr(win.view.title()))
        step("状态栏有本地模型段", "本地模型" in win.statusBar().currentMessage() or bool(win.lbl_model.text()),
             repr(win.lbl_model.text()))
        QTimer.singleShot(300, qapp.quit)

    QTimer.singleShot(1500, poll)
    try:
        qapp.exec()
    finally:
        backend._stop_owned_local()

    out("\n结果：共 %d 步，失败 %d 步" % (4, len(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        LOG.append(traceback.format_exc())
        code = 1
    try:
        with open(str(settings.data_dir() / "desktop_test.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(LOG) + "\n")
    except Exception:
        pass
    sys.exit(code)
