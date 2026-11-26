# -*- coding: utf-8 -*-
"""Prompt Studio 桌面窗口（PyQt6 + QtWebEngine）。

- 双击 exe 直接出原生窗口，不再弹浏览器；界面仍是 static 目录下那套（内嵌 Chromium 渲染）。
- 启动时先显示启动页：起 Flask → 等页面可访问 → 等本地模型就绪（有进度文字）→ 打开主窗口。
- 关窗即退出：杀掉自己拉起的 llama-server，不留后台进程。
- 状态栏常驻显示本地模型状态 / 显卡 / 端口，方便判断是 GPU 还是 CPU 在跑。
"""
from __future__ import annotations

import math
import os
import sys
import threading
import time
import traceback
import urllib.request
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _setup_webengine_env() -> None:
    """打包版里 QtWebEngineProcess.exe 不在默认搜索路径，必须显式指路。

    PyInstaller 把 QtWebEngineProcess.exe 放在 _internal/PyQt6/Qt6/lib/qt6/，
    而 Qt 只在 bin/ 与程序根目录找它 → 找不到就静默崩（退出码 0xC0000409）。
    这里在导入 QtWebEngine 之前把路径、资源与语言包目录都设好。
    """
    base = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else ROOT
    intern = os.path.join(base, "_internal")
    if not os.path.isdir(intern):
        intern = base
    qt = os.path.join(intern, "PyQt6", "Qt6")

    if not os.environ.get("QTWEBENGINEPROCESS_PATH"):
        cands = [
            os.path.join(qt, "lib", "qt6", "QtWebEngineProcess.exe"),
            os.path.join(qt, "bin", "QtWebEngineProcess.exe"),
            os.path.join(base, "QtWebEngineProcess.exe"),
            os.path.join(intern, "QtWebEngineProcess.exe"),
        ]
        hit = next((p for p in cands if os.path.isfile(p)), None)
        if not hit:                                  # 兜底：全盘找一次
            for dirpath, _dirs, files in os.walk(intern):
                if "QtWebEngineProcess.exe" in files:
                    hit = os.path.join(dirpath, "QtWebEngineProcess.exe")
                    break
        if hit:
            os.environ["QTWEBENGINEPROCESS_PATH"] = hit

    res = os.path.join(qt, "resources")
    if os.path.isdir(res) and not os.environ.get("QTWEBENGINE_RESOURCES_PATH"):
        os.environ["QTWEBENGINE_RESOURCES_PATH"] = res
    loc = os.path.join(qt, "translations", "qtwebengine_locales")
    if os.path.isdir(loc) and not os.environ.get("QTWEBENGINE_LOCALES_PATH"):
        os.environ["QTWEBENGINE_LOCALES_PATH"] = loc
    # 打包环境里 Chromium 的沙箱与 GPU 常因权限报错，本地回环页面用不到，直接关掉更稳。
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    for f in ("--no-sandbox", "--disable-gpu-sandbox"):
        if f not in flags:
            flags = (flags + " " + f).strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
    # Qt 插件路径（打包版必须在 _internal/PyQt6/Qt6/plugins）
    plug = os.path.join(qt, "plugins")
    if os.path.isdir(plug) and not os.environ.get("QT_PLUGIN_PATH"):
        os.environ["QT_PLUGIN_PATH"] = plug


_setup_webengine_env()

import app as backend          # noqa: E402  Flask 应用
import localsrv                # noqa: E402
import settings                # noqa: E402

from PyQt6.QtCore import QObject, QRectF, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot  # noqa: E402
from PyQt6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient,  # noqa: E402
                         QPainter, QPainterPath, QPen, QPixmap)
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PyQt6.QtWebChannel import QWebChannel  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QLabel, QMainWindow, QMenu,  # noqa: E402
                             QMessageBox, QStatusBar, QWidget)

APP_NAME = "提示词工作台 Prompt Studio"
PUBLISHER = "minut"
APP_VERSION = "1.1"
BG = "#0f1115"
FG = "#e7e9ee"
ACCENT = "#5b8cff"

# 窗口外壳（菜单栏 / 状态栏 / 菜单）配色，跟网页主题同步
CHROME = {
    "dark": {
        "win": "#0e1014", "bar": "#12151b", "bar_fg": "#c2c9d6", "border": "#232a35",
        "menu": "#161a21", "menu_fg": "#d7dce5", "menu_sel": "#233046",
        "status_fg": "#96a0af", "item_sel": "#1e2430",
    },
    "light": {
        "win": "#f6f7f9", "bar": "#ffffff", "bar_fg": "#33404f", "border": "#e4e7ee",
        "menu": "#ffffff", "menu_fg": "#1b2029", "menu_sel": "#eaf1ff",
        "status_fg": "#5a6472", "item_sel": "#eef2f8",
    },
}


def chrome_qss(theme: str) -> str:
    c = CHROME["light" if theme == "light" else "dark"]
    return (
        "QMainWindow{background:%(win)s;}"
        "QMenuBar{background:%(bar)s;color:%(bar_fg)s;border-bottom:1px solid %(border)s;padding:2px 4px;}"
        "QMenuBar::item{background:transparent;padding:5px 12px;border-radius:6px;}"
        "QMenuBar::item:selected{background:%(item_sel)s;}"
        "QMenu{background:%(menu)s;color:%(menu_fg)s;border:1px solid %(border)s;padding:4px;}"
        "QMenu::item{padding:6px 22px;border-radius:6px;background:transparent;}"
        "QMenu::item:selected{background:%(menu_sel)s;}"
        "QStatusBar{background:%(bar)s;color:%(status_fg)s;border-top:1px solid %(border)s;}"
        "QStatusBar::item{border:none;}"
        "QStatusBar QLabel{color:%(status_fg)s;font-size:12px;padding:0 8px;background:transparent;}"
    ) % c



LOGO_NAME = "logo-256.png"


def logo_pixmap(size: int = 256) -> QPixmap:
    """读取 static/logo-256.png（黑底白字 Pm）；打包后从 _MEIPASS/static 取。

    找不到文件时退回程序化绘制（黑底 + 白色 P、m 各占一半），保证不会没图标。
    """
    for base in (settings.resource_root(), os.path.dirname(os.path.abspath(__file__))):
        p = os.path.join(str(base), "static", LOGO_NAME)
        if os.path.isfile(p):
            pm = QPixmap(p)
            if not pm.isNull():
                return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
    pm = QPixmap(size, size)
    pm.fill(QColor("#000000"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("#ffffff"))
    half = size // 2
    f = QFont("Segoe UI Black")
    f.setPixelSize(int(size * 0.62))
    f.setWeight(QFont.Weight.Black)
    p.setFont(f)
    p.drawText(QRectF(0, 0, half, size), Qt.AlignmentFlag.AlignCenter, "P")
    f2 = QFont("Segoe UI Black")
    f2.setPixelSize(int(size * 0.44))
    f2.setWeight(QFont.Weight.Black)
    p.setFont(f2)
    p.drawText(QRectF(half, int(size * 0.18), half, size), Qt.AlignmentFlag.AlignCenter, "m")
    p.end()
    return pm


def app_icon() -> QIcon:
    return QIcon(logo_pixmap(256))


class Splash(QWidget):
    """启动页：自绘 + 60fps 动画（旋转弧线 + 流动进度条 + 淡入淡出）。

    避免使用 QProgressBar 的 busy 动画（在 Windows 上会卡顿、跳帧），
    改用 QTimer(16ms) 驱动自绘，帧率与缓动都可控。
    """

    W, H = 460, 268

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.W, self.H)
        self._angle = 0.0
        self._t = 0.0
        self._frac = 0.0          # 0..1 的“进度感”（由阶段推进，仅用于视觉）
        self._msg = "正在启动…"
        self._sub = "提示词改写 · 中英互译 · 本地模型开箱即用"
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        self.center()

    # ---------- 动画
    def _tick(self):
        self._angle = (self._angle + 4.2) % 360.0
        self._t += 0.016
        if self._frac < 0.9:
            self._frac = min(0.9, self._frac + 0.0016)
        self.update()

    def center(self):
        scr = QApplication.primaryScreen().availableGeometry()
        self.move((scr.width() - self.width()) // 2, (scr.height() - self.height()) // 2)

    def say(self, text: str):
        self._msg = text
        self.update()

    def show_animated(self):
        self.setWindowOpacity(0.0)
        self.show()
        self._fade(0.0, 1.0, 240, then=None)

    def fade_out(self, then=None):
        self._fade(self.windowOpacity(), 0.0, 200, then=then)

    def _fade(self, a, b, ms, then=None):
        from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(ms)
        anim.setStartValue(float(a))
        anim.setEndValue(float(b))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if then:
            anim.finished.connect(then)
        anim.start()
        self._anim = anim          # 保引用，否则会被 GC 掉导致动画不动

    # ---------- 自绘
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(r), 18, 18)
        p.fillPath(path, QColor("#141922"))
        p.setPen(QPen(QColor("#252c38"), 1))
        p.drawPath(path)

        # 图标块：新 logo（黑底白字 Pm），圆角裁切 + 细边，深色启动页上也能看清
        tile = QRectF(32, 30, 46, 46)
        tile_path = QPainterPath()
        tile_path.addRoundedRect(tile, 11, 11)
        p.save()
        p.setClipPath(tile_path)
        p.drawPixmap(tile.toRect(), logo_pixmap(92))
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#3a4453"), 1))
        p.drawPath(tile_path)
        p.setPen(Qt.PenStyle.NoPen)

        # 标题 / 副标题
        p.setPen(QColor("#e8ecf3"))
        p.setFont(QFont("Microsoft YaHei UI", 15, QFont.Weight.DemiBold))
        p.drawText(QRectF(92, 32, 340, 26), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "提示词工作台")
        p.setPen(QColor("#7d8798"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(92, 58, 340, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Prompt Studio · 本地 · by minut")

        # 状态文字（呼吸式淡入淡出）
        alpha = 190 + int(55 * (0.5 + 0.5 * math.sin(self._t * 3.0)))
        p.setPen(QColor(160, 190, 255, alpha))
        p.setFont(QFont("Microsoft YaHei UI", 10))
        p.drawText(QRectF(34, 132, self.W - 68, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._msg)

        # 进度条：底槽 + 流动高光
        track = QRectF(34, 176, self.W - 68, 6)
        tp = QPainterPath()
        tp.addRoundedRect(track, 3, 3)
        p.fillPath(tp, QColor("#1c212a"))
        seg_w = (self.W - 68) * 0.28
        pos = (self.W - 68) * self._frac * 0.9 + (self.W - 68 - seg_w) * (0.5 + 0.5 * math.sin(self._t * 1.7))
        seg = QRectF(34 + max(0, min(self.W - 68 - seg_w, pos)), 176, seg_w, 6)
        sp = QPainterPath()
        sp.addRoundedRect(seg, 3, 3)
        grad = QLinearGradient(seg.topLeft(), seg.topRight())
        grad.setColorAt(0.0, QColor("#2b7cf0"))
        grad.setColorAt(0.5, QColor("#6fb0ff"))
        grad.setColorAt(1.0, QColor("#2b7cf0"))
        p.fillPath(sp, QBrush(grad))

        # 旋转弧
        cx, cy, rr = self.W - 52.0, 44.0, 11.0
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor("#2f3846"), 2.4)
        p.setPen(pen)
        p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))
        pen = QPen(QColor("#5aa8ff"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2), int(-self._angle * 16), int(100 * 16))

        # 底部提示
        p.setPen(QColor("#5c6675"))
        p.setFont(QFont("Microsoft YaHei UI", 8))
        p.drawText(QRectF(34, 198, self.W - 68, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "首次启动需加载本地模型（10–40 秒）；之后秒开")
        p.end()


class Bridge(QObject):
    """网页 ↔ 桌面程序 的桥：网页调 copyText 直接写系统剪贴板；setTheme 让 Qt 外壳立刻换色。"""

    theme = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @pyqtSlot(str)
    def setTheme(self, name):
        self.theme.emit("light" if name == "light" else "dark")

    @pyqtSlot(str)
    def copyText(self, text):
        cb = QApplication.clipboard()
        cb.setText(text or "")
        # 同时写入 selection 缓冲，个别输入框右键"粘贴"读的是它
        try:
            cb.setText(text or "", cb.Mode.Selection)
        except Exception:
            pass

    @pyqtSlot(str, str)
    def openUrl(self, url, _unused=""):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl as _QUrl
        QDesktopServices.openUrl(_QUrl(url))

    @pyqtSlot(str, str, str, result="QString")
    def pickPath(self, mode, title, filt):
        """网页里点「浏览…」时弹系统对话框，返回选中的绝对路径（取消返回空串）。"""
        try:
            from PyQt6.QtWidgets import QFileDialog
            t = title or "选择"
            if str(mode) == "dir":
                p = QFileDialog.getExistingDirectory(None, t)
            else:
                p, _ = QFileDialog.getOpenFileName(
                    None, t, "", (filt or "所有文件 (*.*)"))
            return p or ""
        except Exception:
            return ""

    @pyqtSlot(result="QString")
    def readText(self):
        try:
            return QApplication.clipboard().text()
        except Exception:
            return ""


class View(QWebEngineView):
    """右键菜单自己画（全中文）：Chromium 自带菜单的文案来自 Qt 翻译包，
    打包版里常常是英文，而且各系统不一致，索性全部换成中文条目。"""

    MENU_ITEMS = (
        ("撤销", QWebEnginePage.WebAction.Undo),
        ("重做", QWebEnginePage.WebAction.Redo),
        (None, None),
        ("剪切", QWebEnginePage.WebAction.Cut),
        ("复制", QWebEnginePage.WebAction.Copy),
        ("粘贴", QWebEnginePage.WebAction.Paste),
        ("全选", QWebEnginePage.WebAction.SelectAll),
        (None, None),
        ("刷新界面", QWebEnginePage.WebAction.Reload),
        ("后退", QWebEnginePage.WebAction.Back),
        ("前进", QWebEnginePage.WebAction.Forward),
        (None, None),
        ("保存页面…", QWebEnginePage.WebAction.SavePage),
    )

    def build_menu(self) -> QMenu:
        page = self.page()
        menu = QMenu(self)
        for label, action in self.MENU_ITEMS:
            if label is None:
                menu.addSeparator()
                continue
            try:
                enabled = page.action(action).isEnabled()
            except Exception:
                enabled = True
            act = menu.addAction(label)
            act.setEnabled(enabled)
            act.triggered.connect(lambda _c=False, a=action: page.triggerAction(a))
        return menu

    def contextMenuEvent(self, ev):
        m = self.build_menu()
        m.exec(ev.globalPos())


class Main(QMainWindow):
    themeChanged = pyqtSignal(str)   # 后台线程 → 主线程（跨线程必须走信号，单一 shot 会丢）

    def __init__(self, url: str, port: int):
        super().__init__()
        self.url = url
        self.port = port
        self.themeChanged.connect(self.apply_theme)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1360, 900)
        self.setMinimumSize(1040, 700)

        self.view = View(self)
        prof = self.view.page().profile()
        prof.setPersistentStoragePath(str(settings.data_dir() / "webprofile"))
        prof.setCachePath(str(settings.data_dir() / "webcache"))
        prof.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        # 让网页可以直接用系统剪贴板（Qt 侧写，绕开浏览器的剪贴板权限限制）
        self.bridge = Bridge(self)
        self.bridge.theme.connect(self.themeChanged.emit)
        self.bridge.theme.connect(lambda t: self.apply_theme(t))
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("psApp", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.view.page().featurePermissionRequested.connect(self._on_feature_permission)
        self.setCentralWidget(self.view)

        sb = QStatusBar()
        self.lbl_model = QLabel("本地模型：检查中…")
        self.lbl_hw = QLabel("")
        self.lbl_port = QLabel("127.0.0.1:%d" % port)
        sb.addWidget(self.lbl_model, 1)
        sb.addPermanentWidget(self.lbl_hw)
        sb.addPermanentWidget(self.lbl_port)
        self.setStatusBar(sb)

        mb = self.menuBar()
        m_view = mb.addMenu("视图")
        m_view.addAction("刷新界面", lambda: self.view.reload())
        m_view.addAction("放大", lambda: self.view.setZoomFactor(min(2.0, self.view.zoomFactor() + 0.1)))
        m_view.addAction("缩小", lambda: self.view.setZoomFactor(max(0.6, self.view.zoomFactor() - 0.1)))
        m_view.addAction("重置缩放", lambda: self.view.setZoomFactor(1.0))
        m_help = mb.addMenu("帮助")
        m_help.addAction("打开数据目录", self.open_data_dir)
        m_help.addAction("打开本地模型日志", self.open_model_log)
        m_help.addAction("关于", self.about)

        self.view.load(QUrl(url))
        self._theme = None
        try:
            self.apply_theme(settings.load_config().get("ui_theme") or "dark")
        except Exception:
            self.apply_theme("dark")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_local)
        self.timer.start(4000)
        QTimer.singleShot(600, self.refresh_local)
        threading.Thread(target=self._theme_loop, name="theme-follow", daemon=True).start()

    def _on_feature_permission(self, origin, feature):
        """本地回环页面是全信任的：剪贴板、全屏等权限一律直接给。"""
        try:
            self.view.page().setFeaturePermission(
                origin, feature, QWebEnginePage.PermissionPolicy.PermissionGranted)
        except Exception:
            pass

    # ---------------- 外观（菜单栏 / 状态栏跟网页主题一起变）
    def apply_theme(self, theme: str):
        t = "light" if theme == "light" else "dark"
        if t == self._theme:
            return
        self._theme = t
        self.setStyleSheet(chrome_qss(t))
        self.menuBar().setStyleSheet(chrome_qss(t))
        if self.statusBar():
            self.statusBar().setStyleSheet(chrome_qss(t))

    # ---------------- 状态栏
    def refresh_local(self):
        threading.Thread(target=self._status_worker, daemon=True).start()

    def _status_worker(self):
        try:
            cfg = settings.load_config()
            c = localsrv.normalize(cfg.get("local") or {})
            st = localsrv.status(c)
            hw = st.get("hardware") or {}
            gpu = hw.get("gpu") or {}
            gpu_txt = ("%s · %.1f GB" % (gpu.get("name"), (gpu.get("vram_mb") or 0) / 1024.0)
                       if gpu else "无 NVIDIA 显卡")
            run = st.get("running")
            txt = "本地模型：● 运行中（pid %s）" % st.get("pid") if run else "本地模型：○ 未启动"
            self.lbl_model.setText(txt)
            self.lbl_hw.setText("%s · %s" % (gpu_txt, hw.get("note") or ""))
        except Exception:
            pass

    def _theme_loop(self):
        """主题跟随：直接读本地配置，0.25 秒一探，避免 4 秒轮询造成"切了色但要等一会儿"的迟滞。"""
        while True:
            try:
                t = settings.load_config().get("ui_theme") or "dark"
                if t != self._theme:
                    self.themeChanged.emit(t)
            except Exception:
                pass
            time.sleep(0.25)

    def open_data_dir(self):
        path = str(settings.data_dir())
        os.startfile(path)  # noqa: S606

    def open_model_log(self):
        p = settings.data_dir() / "llama.log"
        if p.exists():
            os.startfile(str(p))  # noqa: S606
        else:
            QMessageBox.information(self, "提示", "还没有本地模型日志（模型未启动过）。")

    def about(self):
        QMessageBox.information(
            self, "关于",
            "%s\n\n发布者：%s\n版本 %s\n\n"
            "本地 Flask + 内嵌 Chromium 界面；提示词规范随程序分发，"
            "支持 MiniMax H3 / Qwen Image 2.1 / MOSS-Image / Z-Image Turbo 与中英互译。\n"
            "数据目录：%s" % (APP_NAME, PUBLISHER, APP_VERSION, settings.data_dir()))

    def closeEvent(self, ev):
        try:
            backend._stop_owned_local()
        except Exception:
            pass
        ev.accept()


def _runlog(msg: str) -> None:
    """启动里程碑直接写 data\\run.log：窗口模式没有控制台，print 可能被丢弃。"""
    try:
        p = os.path.join(str(settings.data_dir()), "run.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def boot() -> int:
    # 界面语言固定中文：右键菜单（复制/粘贴/全选…）由 Chromium 自己的界面语言决定
    try:
        from PyQt6.QtCore import QLocale
        QLocale.setDefault(QLocale(QLocale.Language.Chinese, QLocale.Country.China))
    except Exception:
        pass
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "--lang=" not in flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (flags + " --lang=zh-CN").strip()
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("PromptStudio")
    qapp.setWindowIcon(app_icon())
    qapp.setStyleSheet(
        "QToolTip{background:#161a21;color:#dfe4ec;border:1px solid #2a3240;}")
    splash = Splash()
    splash.show_animated()
    qapp.processEvents()

    cfg = settings.load_config()
    port = backend.free_port(int(os.environ.get("PORT") or cfg.get("port") or 8760))
    url = "http://127.0.0.1:%d/" % port
    _runlog("程序启动，内核端口 %d" % port)

    # 运行环境（llama.cpp）按硬件自动安装：只支持 Windows
    import runtimes
    det = runtimes.detect()
    if not det.get("windows"):
        _runlog("不支持的平台：%s（只支持 Windows）" % det.get("os"))
        QMessageBox.critical(None, "不支持该系统",
                             "本软件只支持 Windows（当前：%s）。\n"
                             "Linux / macOS 暂不提供运行环境。" % det.get("os"))
        return 2
    splash.say("正在检测硬件…")
    qapp.processEvents()
    rt = runtimes.ensure()
    if rt.get("ok"):
        _runlog("运行环境就绪：%s（%s）" % (rt.get("pack"), rt.get("exe")))
    else:
        _runlog("运行环境安装失败：%s" % rt.get("error"))

    backend.serve_in_thread(port)
    splash.say("正在启动本地服务…")
    qapp.processEvents()
    if not backend.wait_http(url, 40):
        _runlog("启动失败：本地服务 40 秒内没起来（端口 %d）" % port)
        QMessageBox.critical(None, "启动失败",
                             "本地服务没有起来（端口 %d）。\n可以查看 data\\serve.log 或重试。" % port)
        return 1
    _runlog("本地服务就绪 %s" % url)

    # 本地模型在后台加载：界面先出来，状态栏实时显示「加载中 → 运行中」，
    # 不让用户对着启动页干等（模型加载慢时尤其明显）。
    splash.say("正在打开界面…")
    qapp.processEvents()
    threading.Thread(target=backend._autostart_local, name="local-autostart", daemon=True).start()

    win = Main(url, port)
    win.show()
    splash.fade_out(lambda: (splash.close(), _runlog("桌面窗口已打开 %s（端口 %d）" % (url, port))))
    print("[desktop] 桌面窗口已打开 %s（端口 %d）" % (url, port), flush=True)
    return qapp.exec()


if __name__ == "__main__":
    try:
        sys.exit(boot())
    except Exception:
        with open(os.path.join(str(settings.data_dir()), "desktop_error.log"), "a",
                  encoding="utf-8") as f:
            f.write("\n===== %s =====\n%s" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                             traceback.format_exc()))
        raise
