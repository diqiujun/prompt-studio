# -*- coding: utf-8 -*-
r"""提示词工作台 Prompt Studio 安装程序（自解包）。

构建：python build_installer.py
产物：dist\PromptStudio-Setup-1.1.exe（安装程序本体 + 追加在末尾的 payload.zip）
运行：双击即可；命令行参数 --silent --dir "D:\\PromptStudio" 可无界面安装。
"""
import os
import sys
import json
import shutil
import subprocess
import threading
import time
import zipfile

APP_NAME = "提示词工作台 Prompt Studio"
APP_SHORT = "PromptStudio"
APP_VERSION = "1.1"
PUBLISHER = "minut"
NEED_BYTES = 6_400_000_000          # 安装后体积（留余量）
CHUNK = 4 * 1024 * 1024
CREATE_NO_WINDOW = 0x08000000


# ---------------------------------------------------------------- 基础工具
def app_dir():
    return os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))


class PayloadMissing(Exception):
    pass


def _is_payload(path):
    """是不是真正的安装数据：必须是 zip，且里面有 payload/ 前缀的条目。

    不能只看「能不能当 zip 打开」——PyInstaller 打出来的 exe 本身就是个 zip
    （内部是 _internal/*、PYZ 等），误判会把安装器自己的程序文件解到目标目录。
    """
    try:
        if not os.path.isfile(path):
            return False
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()[:4000]
        return any(n.startswith("payload/") for n in names)
    except Exception:
        return False


def payload_zip():
    """安装数据（payload.zip）的位置。

    优先「与安装程序同目录的独立文件」：模型+运行环境有 6 GB，塞进 exe 末尾会让
    exe 超过 Windows 能 execute 的大小（CreateProcess 报 WinError 193），所以默认
    做成 exe + payload.zip 两个文件。只有 payload 很小时才拼进 exe 末尾（--embed）。
    """
    me = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
    here = os.path.dirname(me)
    env_pay = os.environ.get("PS_PAYLOAD")
    cands = ([os.path.abspath(env_pay)] if env_pay else []) + [os.path.join(here, "payload.zip")]
    try:
        for n in sorted(os.listdir(here)):
            low = n.lower()
            if low.endswith(".payload.zip") or low.endswith(".bin"):
                cands.append(os.path.join(here, n))
    except OSError:
        pass
    if not getattr(sys, "frozen", False):
        # 源码调试：用构建出来的 payload.zip
        cands += [os.path.join(app_dir(), "..", "build", "installer", "payload.zip"),
                  os.path.join(app_dir(), "payload.zip")]
    cands.append(me)                      # 拼进 exe 末尾的布局
    for c in cands:
        c = os.path.abspath(c)
        if _is_payload(c):
            return c
    raise PayloadMissing(
        "找不到安装数据。请确认 payload 文件与安装程序放在同一目录：\n"
        "  %s\n和\n  %s\n（文件名形如 PromptStudio-Setup-1.1.payload.zip）"
        % (me, os.path.join(here, "PromptStudio-Setup-1.1.payload.zip")))


def open_payload():
    return zipfile.ZipFile(payload_zip(), "r")


def run_ps(script, timeout=120):
    """跑一段 PowerShell（用来建快捷方式、写注册表），不弹窗。"""
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, encoding="mbcs", errors="ignore",
            creationflags=CREATE_NO_WINDOW, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:
        return 1, str(exc)


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" if unit in ("B", "KB") else "%.1f %s") % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def state_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_SHORT)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return None
    return d


def last_dir():
    """上次用户选的安装目录（记住选择，下次安装默认用它）。"""
    d = state_dir()
    if not d:
        return ""
    try:
        with open(os.path.join(d, "setup_dir.txt"), "r", encoding="utf-8") as f:
            v = f.read().strip().strip('"')
        if v and os.path.isdir(v):
            return v
    except Exception:
        pass
    return ""


def remember_dir(path):
    d = state_dir()
    if not d or not path:
        return
    try:
        with open(os.path.join(d, "setup_dir.txt"), "w", encoding="utf-8") as f:
            f.write(path)
    except Exception:
        pass


def default_dir():
    v = last_dir()
    if v:
        return v
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", APP_SHORT)


BAD_CHARS = set('<>:"|?*')


def check_dir(path):
    """安装目录预检 → (ok, level, note)，level: '' / warn / error。"""
    path = (path or "").strip().strip('"')
    if not path:
        return False, "error", "请填写安装目录"
    if len(path) < 4 or path[1:3] != ":\\":
        return False, "error", "请填写完整路径，例如 D:\\PromptStudio"
    body = path[2:]                     # 盘符后的部分才检查非法字符（"C:" 本身就是冒号）
    if any(ch in BAD_CHARS for ch in body):
        return False, "error", "路径里有不能用的字符（< > : \" | ? *）"
    if os.path.isfile(path):
        return False, "error", "这个路径是一个文件，请换一个目录"
    drive = os.path.splitdrive(path)[0] + "\\"
    if not os.path.isdir(drive):
        return False, "error", "磁盘 %s 不存在" % drive
    note = ""
    if os.path.isfile(os.path.join(path, APP_SHORT + ".exe")):
        note = "该目录里已有 %s，安装将覆盖（等于升级）" % APP_SHORT
    probe = os.path.join(path, ".ps_write_test_%d" % os.getpid())
    try:
        os.makedirs(path, exist_ok=True)
        with open(probe, "wb") as f:
            f.write(b"ok")
    except Exception as exc:
        return (False, "error",
                "这个目录写不进去（%s）。常见原因是选到了 Program Files："
                "请改到 D:\\PromptStudio 这类普通目录，或用管理员身份重新运行安装包。"
                % (exc.__class__.__name__ + "：" + str(exc)))
    try:
        os.remove(probe)          # 杀软可能短暂占用删除失败：不影响「可写」结论
    except Exception:
        pass
    try:                          # 顺手清掉以前预检留下的探测文件
        for n in os.listdir(path):
            if n.startswith(".ps_write_test"):
                try:
                    os.remove(os.path.join(path, n))
                except OSError:
                    pass
    except OSError:
        pass
    return True, ("warn" if note else ""), note


def make_shortcuts(target_dir, desktop=True, startmenu=True):
    exe = os.path.join(target_dir, APP_SHORT + ".exe")
    ps = ["$ws = New-Object -ComObject WScript.Shell"]
    if desktop:
        lnk = os.path.join(os.path.expanduser("~"), "Desktop", APP_NAME + ".lnk")
        ps.append("$s = $ws.CreateShortcut('%s'); $s.TargetPath = '%s'; $s.WorkingDirectory = '%s'; "
                  "$s.IconLocation = '%s,0'; $s.Description = '%s %s'; $s.Save()"
                  % (lnk.replace("'", "''"), exe.replace("'", "''"), target_dir.replace("'", "''"),
                     exe.replace("'", "''"), APP_NAME, APP_VERSION))
    if startmenu:
        folder = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
        lnk2 = os.path.join(folder, APP_NAME + ".lnk")
        ps.append("$s = $ws.CreateShortcut('%s'); $s.TargetPath = '%s'; $s.WorkingDirectory = '%s'; "
                  "$s.IconLocation = '%s,0'; $s.Save()"
                  % (lnk2.replace("'", "''"), exe.replace("'", "''"), target_dir.replace("'", "''"),
                     exe.replace("'", "''")))
    run_ps("; ".join(ps))


def write_uninstall(target_dir):
    """写卸载脚本 + 注册到「应用和功能」。"""
    exe = os.path.join(target_dir, APP_SHORT + ".exe")
    cmd_path = os.path.join(target_dir, "卸载 " + APP_SHORT + ".cmd")
    body = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "echo 正在卸载 %s ...\r\n"
        "taskkill /IM %s.exe /T /F >nul 2>nul\r\n"
        "taskkill /IM llama-server.exe /T /F >nul 2>nul\r\n"
        "del \"%%USERPROFILE%%\\Desktop\\%s.lnk\" >nul 2>nul\r\n"
        "del \"%%APPDATA%%\\Microsoft\\Windows\\Start Menu\\Programs\\%s.lnk\" >nul 2>nul\r\n"
        "reg delete \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s\" /f >nul 2>nul\r\n"
        "echo 正在删除程序文件 ...\r\n"
        "start \"\" /min cmd /c \"timeout /t 2 >nul & rd /s /q \"\"%%~dp0\"\"\"\r\n"
        "exit\r\n" % (APP_NAME, APP_SHORT, APP_NAME, APP_NAME, APP_SHORT))
    with open(cmd_path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(body)

    # 卸载脚本自己会被 rd 删掉（在目录内），所以再放一个外部清理不用管
    size_kb = 0
    for root, _dirs, files in os.walk(target_dir):
        for f in files:
            try:
                size_kb += os.path.getsize(os.path.join(root, f)) // 1024
            except OSError:
                pass
    quoted = cmd_path.replace("'", "''")
    ps = ("New-Item -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s' -Force | Out-Null; "
          "$k = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%s'; "
          "New-ItemProperty -Path $k -Name DisplayName -Value '%s' -PropertyType String -Force | Out-Null; "
          "New-ItemProperty -Path $k -Name DisplayVersion -Value '%s' -PropertyType String -Force | Out-Null; "
          "New-ItemProperty -Path $k -Name Publisher -Value '%s' -PropertyType String -Force | Out-Null; "
          "New-ItemProperty -Path $k -Name InstallLocation -Value '%s' -PropertyType String -Force | Out-Null; "
          "New-ItemProperty -Path $k -Name DisplayIcon -Value '%s' -PropertyType String -Force | Out-Null; "
          "New-ItemProperty -Path $k -Name UninstallString -Value '\"%s\"' -PropertyType String -Force | Out-Null; "
          "New-ItemProperty -Path $k -Name EstimatedSize -Value %d -PropertyType DWord -Force | Out-Null"
          % (APP_SHORT, APP_SHORT, APP_NAME, APP_VERSION, PUBLISHER,
             target_dir.replace("'", "''"), exe.replace("'", "''"), quoted, size_kb))
    run_ps(ps)


# ---------------------------------------------------------------- 解包
class Extractor(threading.Thread):
    def __init__(self, target, progress_cb, done_cb, log_cb):
        super().__init__(daemon=True)
        self.target = target
        self.progress_cb = progress_cb
        self.done_cb = done_cb
        self.log_cb = log_cb
        self.stop = False

    def run(self):
        try:
            zf = open_payload()
            items = [i for i in zf.infolist() if not i.filename.endswith("/")]
            total = sum(i.file_size for i in items) or 1
            done = 0
            t0 = time.time()
            for info in items:
                if self.stop:
                    raise RuntimeError("已取消")
                name = info.filename
                if name.startswith("payload/"):
                    name = name[len("payload/"):]
                dst = os.path.join(self.target, *name.split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with zf.open(info, "r") as src, open(dst, "wb") as out:
                    while True:
                        buf = src.read(CHUNK)
                        if not buf:
                            break
                        out.write(buf)
                        done += len(buf)
                        if self.progress_cb:
                            speed = done / max(0.001, time.time() - t0)
                            self.progress_cb(done, total, speed)
                if self.log_cb:
                    self.log_cb(name)
            self.done_cb(True, "解包完成")
        except Exception as exc:
            self.done_cb(False, str(exc))


# ---------------------------------------------------------------- 界面
def logo_file():
    """安装器窗口用的 logo：优先打包进来的 static/logo-256.png，其次源码目录。"""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in (("static", "logo-256.png"), ("static", "logo.png"), ("build", "app.png")):
        p = os.path.join(base, *rel)
        if os.path.isfile(p):
            return p
    return ""


def run_gui():
    from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                 QPushButton, QLineEdit, QFileDialog, QCheckBox,
                                 QProgressBar, QStackedWidget, QMessageBox, QFrame)
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    from PyQt6.QtGui import QIcon, QPixmap

    payload_error = ""
    try:
        zf = open_payload()
        total = sum(i.file_size for i in zf.infolist() if not i.filename.endswith("/"))
        zf.close()
    except PayloadMissing as exc:
        total = 0
        payload_error = str(exc)
    except Exception as exc:
        total = 0
        payload_error = "安装数据读不出来：%s" % exc

    QSS = """
    QWidget { background:#0e1014; color:#e8ecf3; font-family:"Microsoft YaHei UI","Microsoft YaHei",sans-serif; font-size:13px; }
    QLabel#h1 { font-size:20px; font-weight:600; }
    QLabel#hint { color:#98a2b3; }
    QLabel#sub { color:#69737f; font-size:12px; }
    QLineEdit { background:#151920; border:1px solid #272e3a; border-radius:8px; padding:7px 10px; }
    QPushButton { background:#1f2733; border:1px solid #2b3442; border-radius:8px; padding:8px 16px; }
    QPushButton:hover { background:#26303e; }
    QPushButton#primary { background:#2b7cf0; border:1px solid #2b7cf0; color:#fff; font-weight:600; }
    QPushButton#primary:hover { background:#3b88f7; }
    QPushButton#primary:disabled { background:#233044; border-color:#233044; color:#7c8798; }
    QProgressBar { border:1px solid #272e3a; border-radius:8px; background:#151920; height:20px; text-align:center; }
    QProgressBar::chunk { background:#2b7cf0; border-radius:7px; }
    QCheckBox { color:#c2c9d6; }
    QFrame#card { background:#151920; border:1px solid #272e3a; border-radius:12px; }
    """

    class Setup(QWidget):
        sig_progress = pyqtSignal(int, int, float)
        sig_done = pyqtSignal(bool, str)

        def __init__(self):
            super().__init__()
            self.setWindowTitle("%s %s 安装程序" % (APP_NAME, APP_VERSION))
            self.setMinimumSize(680, 460)
            self.setStyleSheet(QSS)
            ic = os.path.join(app_dir(), "setup.ico")
            if os.path.isfile(ic):
                self.setWindowIcon(QIcon(ic))
            self.target = default_dir()
            self.extractor = None
            self.finished_ok = False

            root = QVBoxLayout(self)
            root.setContentsMargins(22, 20, 22, 18)
            root.setSpacing(12)

            head = QHBoxLayout()
            head.setSpacing(10)
            logo = QLabel()
            lp = logo_file()
            if lp:
                pm = QPixmap(lp)
                if not pm.isNull():
                    logo.setPixmap(pm.scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))
                    logo.setFixedSize(34, 34)
                    head.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
            title = QLabel("提示词工作台 Prompt Studio")
            title.setObjectName("h1")
            head.addWidget(title)
            head.addStretch(1)
            ver = QLabel("v%s · 发布者 %s" % (APP_VERSION, PUBLISHER))
            ver.setObjectName("sub")
            head.addWidget(ver)
            root.addLayout(head)

            self.stack = QStackedWidget()
            root.addWidget(self.stack, 1)

            # ---- 第 1 页：欢迎 + 目录 + 选项
            p1 = QWidget()
            v1 = QVBoxLayout(p1)
            v1.setContentsMargins(0, 0, 0, 0)
            v1.setSpacing(10)
            card = QFrame()
            card.setObjectName("card")
            cv = QVBoxLayout(card)
            cv.setContentsMargins(16, 14, 16, 14)
            cv.setSpacing(8)
            t = QLabel("安装到")
            cv.addWidget(t)
            row = QHBoxLayout()
            self.ed_dir = QLineEdit(self.target)
            row.addWidget(self.ed_dir, 1)
            b = QPushButton("浏览…")
            b.clicked.connect(self.pick_dir)
            row.addWidget(b)
            cv.addLayout(row)
            quick = QHBoxLayout()
            quick.setSpacing(6)
            lb_q = QLabel("常用：")
            lb_q.setObjectName("hint")
            quick.addWidget(lb_q)
            for cap, path in self.quick_dirs():
                qb = QPushButton(cap)
                qb.setObjectName("mini")
                qb.setToolTip(path)
                qb.clicked.connect(lambda _=False, p=path: self.ed_dir.setText(p))
                quick.addWidget(qb)
            quick.addStretch(1)
            cv.addLayout(quick)
            self.lb_space = QLabel("")
            self.lb_space.setObjectName("hint")
            self.lb_space.setWordWrap(True)
            cv.addWidget(self.lb_space)
            v1.addWidget(card)

            card2 = QFrame()
            card2.setObjectName("card")
            c2 = QVBoxLayout(card2)
            c2.setContentsMargins(16, 12, 16, 12)
            c2.setSpacing(6)
            self.cb_desktop = QCheckBox("创建桌面快捷方式")
            self.cb_desktop.setChecked(True)
            self.cb_menu = QCheckBox("添加到开始菜单")
            self.cb_menu.setChecked(True)
            self.cb_launch = QCheckBox("安装完成后立即启动")
            self.cb_launch.setChecked(True)
            c2.addWidget(self.cb_desktop)
            c2.addWidget(self.cb_menu)
            c2.addWidget(self.cb_launch)
            v1.addWidget(card2)

            tip = QLabel("安装后约占用 6 GB（含内置模型与 6 套运行环境包）。"
                         "无需安装 Python / CUDA，装完双击即可用。")
            tip.setObjectName("hint")
            tip.setWordWrap(True)
            v1.addWidget(tip)
            v1.addStretch(1)
            self.stack.addWidget(p1)

            # ---- 第 2 页：进度
            p2 = QWidget()
            v2 = QVBoxLayout(p2)
            v2.setContentsMargins(0, 0, 0, 0)
            v2.setSpacing(10)
            self.lb_step = QLabel("正在解包…")
            v2.addWidget(self.lb_step)
            self.bar = QProgressBar()
            self.bar.setRange(0, 1000)
            v2.addWidget(self.bar)
            self.lb_stat = QLabel("")
            self.lb_stat.setObjectName("hint")
            v2.addWidget(self.lb_stat)
            self.lb_file = QLabel("")
            self.lb_file.setObjectName("sub")
            self.lb_file.setWordWrap(True)
            v2.addWidget(self.lb_file)
            v2.addStretch(1)
            self.stack.addWidget(p2)

            # ---- 第 3 页：完成
            p3 = QWidget()
            v3 = QVBoxLayout(p3)
            v3.setContentsMargins(0, 0, 0, 0)
            ok = QLabel("安装完成")
            ok.setObjectName("h1")
            v3.addWidget(ok)
            self.lb_done = QLabel("")
            self.lb_done.setObjectName("hint")
            self.lb_done.setWordWrap(True)
            v3.addWidget(self.lb_done)
            v3.addStretch(1)
            self.stack.addWidget(p3)

            # ---- 底部按钮
            foot = QHBoxLayout()
            self.lb_note = QLabel("")
            self.lb_note.setObjectName("sub")
            foot.addWidget(self.lb_note)
            foot.addStretch(1)
            self.btn_cancel = QPushButton("取消")
            self.btn_cancel.clicked.connect(self.on_cancel)
            foot.addWidget(self.btn_cancel)
            self.btn_next = QPushButton("开始安装")
            self.btn_next.setObjectName("primary")
            self.btn_next.clicked.connect(self.on_next)
            foot.addWidget(self.btn_next)
            root.addLayout(foot)

            self.sig_progress.connect(self.on_progress)
            self.sig_done.connect(self.on_done)
            self.update_space()
            self.ed_dir.textChanged.connect(self.update_space)

        # --- 工具
        def quick_dirs(self):
            home = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            out = [("C 盘用户目录", os.path.join(home, "Programs", APP_SHORT))]
            for d in ("D:\\", "E:\\", "F:\\", "G:\\"):
                if os.path.isdir(d) and len(out) < 4:
                    out.append((d.rstrip("\\") + " 盘", os.path.join(d, APP_SHORT)))
            return out

        def update_space(self):
            path = self.ed_dir.text().strip() or default_dir()
            drive = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
            try:
                free = shutil.disk_usage(drive).free
            except Exception:
                free = 0
            need = max(NEED_BYTES, total + 512 * 1024 * 1024)
            if payload_error:
                line = "安装数据缺失，无法安装"
            else:
                line = ("安装包内容 %s · 需要空间 %s · 该磁盘可用 %s"
                        % (human(total), human(need), human(free) if free else "未知"))
            ok_dir, level, note = check_dir(path)
            if payload_error:
                ok_dir, level, note = False, "error", payload_error.split("\n")[0]
            space_ok = (free == 0) or (free > need)
            if not space_ok:
                ok_dir, level = False, "error"
                note = note or "该磁盘剩余空间不足（约需 %s）" % human(need)
            self.lb_space.setText(line + ("\n" + note if note else ""))
            self.btn_next.setEnabled(bool(ok_dir and space_ok))
            self.lb_note.setText("" if (ok_dir and space_ok) else (note or "请检查安装目录"))

        def pick_dir(self):
            p = QFileDialog.getExistingDirectory(self, "选择安装目录", self.ed_dir.text())
            if p:
                self.ed_dir.setText(os.path.join(p, APP_SHORT) if os.path.basename(p).lower() != APP_SHORT.lower() else p)

        def on_next(self):
            if self.stack.currentIndex() == 0:
                self.start_install()
            elif self.stack.currentIndex() == 2:
                self.close()

        def on_cancel(self):
            if self.extractor and self.extractor.is_alive():
                self.extractor.stop = True
                self.btn_cancel.setEnabled(False)
                self.btn_cancel.setText("正在取消…")
                return
            self.close()

        def start_install(self):
            if payload_error:
                QMessageBox.critical(self, "找不到安装数据", payload_error)
                return
            path = self.ed_dir.text().strip()
            path = path or default_dir()
            ok, level, note = check_dir(path)
            if not ok:
                QMessageBox.warning(self, "安装目录不可用", note)
                return
            if level == "warn" and note:
                ans = QMessageBox.question(self, "确认覆盖", note + "。\n\n继续安装？")
                if ans != QMessageBox.StandardButton.Yes:
                    return
            self.target = path
            remember_dir(self.target)
            self.stack.setCurrentIndex(1)
            self.btn_next.setEnabled(False)
            self.btn_next.setText("安装中…")
            self.lb_step.setText("正在解包（约 1–3 分钟，视硬盘速度）…")
            self.extractor = Extractor(self.target, self.sig_progress.emit, self.sig_done.emit, self.on_file)
            self.extractor.start()

        def on_file(self, name):
            short = name if len(name) <= 90 else name[:42] + " … " + name[-42:]
            self.lb_file.setText(short)

        def on_progress(self, done, tot, speed):
            self.bar.setValue(int(1000.0 * done / max(1, tot)))
            self.lb_stat.setText("%s / %s · %s/s · 剩余约 %d 秒"
                                 % (human(done), human(tot), human(speed),
                                    int((tot - done) / max(1.0, speed))))

        def on_done(self, ok, msg):
            if not ok:
                QMessageBox.critical(self, "安装失败", "解包失败：%s\n\n可换个目录重试，或用管理员身份运行。" % msg)
                self.btn_next.setEnabled(True)
                self.btn_next.setText("重新安装")
                self.btn_cancel.setEnabled(True)
                self.stack.setCurrentIndex(0)
                return
            self.lb_step.setText("正在创建快捷方式…")
            QApplication.processEvents()
            exe = os.path.join(self.target, APP_SHORT + ".exe")
            if not os.path.isfile(exe):
                QMessageBox.critical(self, "安装失败", "解包后没有找到 %s.exe，安装包可能损坏。" % APP_SHORT)
                return
            make_shortcuts(self.target, self.cb_desktop.isChecked(), self.cb_menu.isChecked())
            self.lb_step.setText("正在登记卸载信息…")
            QApplication.processEvents()
            write_uninstall(self.target)
            remember_dir(self.target)
            self.finished_ok = True
            self.stack.setCurrentIndex(2)
            self.lb_done.setText("已安装到：%s\n\n双击桌面（或开始菜单）里的「%s」即可启动。"
                                 "首次启动会自动加载内置模型，约 10–40 秒。\n\n"
                                 "要卸载：运行 %s 里的「卸载 %s.cmd」，或从 Windows「应用和功能」里卸载。"
                                 % (self.target, APP_NAME, self.target, APP_SHORT))
            self.btn_cancel.setVisible(False)
            self.btn_next.setEnabled(True)
            self.btn_next.setText("启动并完成")
            if self.cb_launch.isChecked():
                QTimer.singleShot(400, lambda: self.launch(exe))

        def launch(self, exe):
            try:
                subprocess.Popen([exe], cwd=self.target, creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass

    app = QApplication(sys.argv or ["PromptStudioSetup"])
    _lp = logo_file()
    if _lp:
        _ico = QIcon(_lp)
        if not _ico.isNull():
            app.setWindowIcon(_ico)
    w = Setup()
    if _lp:
        w.setWindowIcon(QIcon(_lp))
    w.show()

    if "--shot" in sys.argv:
        # 仅供开发时截图：--shot <目录>
        idx = sys.argv.index("--shot")
        outdir = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "."
        os.makedirs(outdir, exist_ok=True)

        def snap(name, page=None, frac=None):
            if page is not None:
                w.stack.setCurrentIndex(page)
            if frac is not None:
                w.bar.setValue(int(frac * 1000))
                w.lb_stat.setText("3.1 GB / 5.6 GB · 168 MB/s · 剩余约 15 秒")
                w.lb_file.setText("payload/models/gemma-4-e2b/gemma-4-E2B-it-Q4_K_M.gguf")
            app.processEvents()
            time.sleep(0.25)
            app.processEvents()
            w.grab().save(os.path.join(outdir, name))
            print("saved", name, flush=True)

        QTimer.singleShot(600, lambda: snap("setup_1.png", 0))
        QTimer.singleShot(1100, lambda: snap("setup_2.png", 1, 0.55))
        QTimer.singleShot(1600, lambda: snap("setup_3.png", 2))
        QTimer.singleShot(2100, app.quit)
        app.exec()
        return 0

    app.exec()
    return 0 if w.finished_ok else 1


# ---------------------------------------------------------------- 静默安装
def say(msg):
    """窗口化打包时 sys.stdout 为 None，直接 print 会抛异常；同时把日志落到文件便于排查。"""
    try:
        if sys.stdout is not None:
            print(msg, flush=True)
    except Exception:
        pass
    try:
        lp = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "setup_run.log")
        with open(lp, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%H:%M:%S] ") + msg + "\n")
    except Exception:
        pass


def run_silent(target, desktop=True, startmenu=True, launch=False):
    try:
        open_payload().close()
    except Exception as exc:
        say("找不到可用的安装数据：%s" % exc)
        return 2
    ok_dir, _level, note = check_dir(target)
    if not ok_dir:
        say("安装目录不可用：%s" % note)
        return 1
    os.makedirs(target, exist_ok=True)
    remember_dir(target)
    state = {"ok": False, "msg": ""}

    def done(ok, msg):
        state["ok"], state["msg"] = ok, msg

    ex = Extractor(target, None, done, None)
    ex.run()                                  # 同步执行
    if not state["ok"]:
        say("安装失败：%s" % state["msg"])
        return 1
    make_shortcuts(target, desktop, startmenu)
    write_uninstall(target)
    exe = os.path.join(target, APP_SHORT + ".exe")
    if launch and os.path.isfile(exe):
        subprocess.Popen([exe], cwd=target, creationflags=CREATE_NO_WINDOW)
    say("已安装到 %s" % target)
    return 0


def main():
    args = sys.argv[1:]
    if "--silent" in args:
        target = default_dir()
        for i, a in enumerate(args):
            if a == "--dir" and i + 1 < len(args):
                target = args[i + 1]
        ok = run_silent(target, "--no-desktop" not in args, "--no-menu" not in args, "--launch" in args)
        return ok
    return run_gui()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        try:
            lp = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "setup_error.log")
            with open(lp, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise
