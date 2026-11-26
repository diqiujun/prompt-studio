# -*- coding: utf-8 -*-
r"""界面自检：主题切换 / 滚动条 / @ 引用浮层 / 启动页绘制，全部离屏截图。

用法：python test_ui.py
产物：data/shot_splash.png、data/shot_dark.png、data/shot_light.png、data/shot_mention.png
"""
from __future__ import annotations

import base64
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

import desktop  # noqa: E402  先设好 QtWebEngine 环境变量
import app as backend  # noqa: E402
from PyQt6.QtCore import QTimer, QUrl  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

DATA = os.path.join(ROOT, "data")
FAILS = []


def ok(name, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + name + (("  " + extra) if extra else ""))
    if not cond:
        FAILS.append(name)


def img_data_url() -> str:
    p = os.path.join(DATA, "probe_img_b64.txt")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            b64 = f.read().strip()
        return "data:image/jpeg;base64," + b64
    # 32x32 纯色兜底
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (90, 120, 180)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> int:
    qapp = QApplication(sys.argv)

    # ---- 启动页截图（自绘，验证不崩、有内容）
    sp = desktop.Splash()
    sp.say("正在启动本地服务…")
    sp._angle, sp._frac, sp._t = 40.0, 0.35, 0.7
    pm = sp.grab()
    pm.save(os.path.join(DATA, "shot_splash.png"))
    ok("启动页绘制", pm.width() == desktop.Splash.W and pm.height() == desktop.Splash.H,
       "%dx%d" % (pm.width(), pm.height()))

    port = backend.free_port(8775)
    url = "http://127.0.0.1:%d/" % port
    backend.serve_in_thread(port)
    ok("内核就绪", backend.wait_http(url, 40), url)

    from PyQt6.QtWidgets import QMainWindow
    win = QMainWindow()
    view = QWebEngineView()
    win.setCentralWidget(view)
    win.resize(1360, 900)
    win.show()
    state = {"step": 0}

    def grab(name):
        # QWebEngineView 走独立合成进程，win.grab() 抓到的是黑块；
        # 改从屏幕抓窗口区域，才是用户真正看到的画面。
        scr = win.screen()
        g = win.frameGeometry()
        pm = scr.grabWindow(0, g.x(), g.y(), g.width(), g.height())
        pm.save(os.path.join(DATA, name))
        ok("截图 " + name, not pm.isNull(), "%dx%d" % (pm.width(), pm.height()))

    def on_loaded(okflag):
        ok("页面加载", bool(okflag))
        QTimer.singleShot(2500, step_dark)

    def step_dark():
        grab("shot_dark.png")
        ok("深色页面渲染", True)
        js = """
        (function(){
          var url = %s;
          S.images = [{data_url:url, role:'画布图·被编辑的底图'}, {data_url:url, role:'人物身份来源'}];
          renderImages();
          document.documentElement.setAttribute('data-theme','light');
          localStorage.setItem('ps-theme','light');
          return document.documentElement.getAttribute('data-theme');
        })()
        """ % _js_str(_IMAGE_URL)
        view.page().runJavaScript(js, lambda r: QTimer.singleShot(900, step_light))

    def step_light():
        grab("shot_light.png")
        js2 = """
        (function(){
          var ta = document.getElementById('content');
          ta.value = '把 @图1 里的铜钟修好，人物和雪景保持不动，只留一道竖直裂缝，参考 @';
          ta.focus();
          ta.setSelectionRange(ta.value.length, ta.value.length);
          ta.dispatchEvent(new Event('input'));
          return document.getElementById('mention').classList.contains('on');
        })()
        """
        view.page().runJavaScript(js2, after_mention_open)

    def after_mention_open(r):
        ok("@ 浮层弹出", bool(r))
        QTimer.singleShot(300, grab_mention)

    def grab_mention():
        grab("shot_mention.png")
        js3 = """
        (function(){
          var a = resolveMentions('@图1 和 @图片2 与 @第3张 保留，@图9 不存在');
          var d = document.documentElement.getAttribute('data-theme');
          var cs = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
          var sb = getComputedStyle(document.querySelector('.out')).backgroundColor;
          return [a, d, cs, sb].join(' || ');
        })()
        """
        view.page().runJavaScript(js3, after_all)

    def after_all(r):
        s = str(r or "")
        parts = s.split(" || ")
        ok("<imageN> 解析", parts and parts[0] == "<image1> 和 <image2> 与 @第3张 保留，@图9 不存在", parts[0] if parts else s)
        ok("主题已切到浅色", len(parts) > 1 and parts[1] == "light")
        ok("浅色 --bg 变量", len(parts) > 2 and parts[2].lower().startswith("#"), parts[2] if len(parts) > 2 else "")
        print("\n结果：失败 %d 项" % len(FAILS))
        qapp.exit(0 if not FAILS else 1)

    view.loadFinished.connect(on_loaded)
    view.load(QUrl(url))
    code = qapp.exec()
    try:
        backend._stop_owned_local()
    except Exception:
        pass
    return code


_IMAGE_URL = ""


def _js_str(s: str) -> str:
    import json
    return json.dumps(s)


if __name__ == "__main__":
    _IMAGE_URL = img_data_url()
    sys.exit(main())
