# -*- coding: utf-8 -*-
"""给桌面窗口（Qt + QtWebEngine）截真实画面。

用法：
    python tools\\shot_desktop.py [--exe dist\\PromptStudio\\PromptStudio.exe]
                                  [--out data\\desktop_ui.png] [--wait 26] [--theme dark]

为什么不用 QWidget.grab()：QtWebEngine 的内容在独立进程里渲染，grab() 得到全黑。
这里用 PrintWindow(PW_RENDERFULLCONTENT=2) 让系统把窗口（含 WebEngine 合成结果）画到内存 DC。

注意：窗口被别的窗口完全遮挡时 PrintWindow 仍能取到画面；但最小化时取不到，脚本会先把窗口还原。
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import time

from PIL import Image

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32

SW_RESTORE = 9
PW_RENDERFULLCONTENT = 2


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def find_windows(title_part):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        n = u32.GetWindowTextLengthW(hwnd)
        if n > 0:
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            if title_part in buf.value:
                out.append((hwnd, buf.value, bool(u32.IsWindowVisible(hwnd))))
        return True

    u32.EnumWindows(cb, 0)
    return out


def shot(hwnd, path):
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.6)
    rect = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w < 200 or h < 200:
        raise RuntimeError("窗口尺寸异常 %dx%d" % (w, h))
    hdc = u32.GetWindowDC(hwnd)
    mdc = gdi.CreateCompatibleDC(hdc)
    bmp = gdi.CreateCompatibleBitmap(hdc, w, h)
    gdi.SelectObject(mdc, bmp)
    ok = u32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT)
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi.DeleteObject(bmp)
    gdi.DeleteDC(mdc)
    u32.ReleaseDC(hwnd, mdc)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    img.save(path)
    return ok, w, h


def set_theme(root, theme):
    """改 config.json 里的界面主题（桌面版主题持久化在配置里）。"""
    cfg = os.path.join(root, "data", "config.json")
    if not os.path.exists(cfg):
        return False
    try:
        d = json.load(open(cfg, encoding="utf-8"))
    except Exception:
        return False
    d["ui_theme"] = theme
    json.dump(d, open(cfg, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=os.path.join("dist", "PromptStudio", "PromptStudio.exe"))
    ap.add_argument("--out", default=os.path.join("data", "desktop_ui.png"))
    ap.add_argument("--wait", type=float, default=26.0)
    ap.add_argument("--theme", default="")
    args = ap.parse_args()

    exe = os.path.abspath(args.exe)
    root = os.path.dirname(exe)
    if args.theme:
        print("主题 ->", args.theme, set_theme(root, args.theme))

    procs = [p.pid for p in find_children("PromptStudio.exe")]
    if procs:
        print("已有实例在跑，先结束：", procs)
        subprocess.run(["taskkill", "/PID"] + [str(p) for p in procs] + ["/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

    print("启动", exe)
    t0 = time.time()
    p = subprocess.Popen([exe], cwd=root, creationflags=0x00000200)
    hwnd = 0
    while time.time() - t0 < 120:
        time.sleep(1.0)
        ws = [w for w in find_windows("提示词工作台") if w[2]]
        if ws:
            hwnd = ws[0][0]
            # 等页面渲染完成（模型加载 + 首屏）
            if time.time() - t0 >= args.wait:
                break
    if not hwnd:
        print("没找到窗口（标题含「提示词工作台」）")
        return 2
    time.sleep(1.5)
    ok, w, h = shot(hwnd, args.out)
    print("PrintWindow=%s 尺寸=%dx%d -> %s" % (ok, w, h, args.out))
    p.terminate()
    time.sleep(1)
    try:
        p.wait(timeout=10)
    except Exception:
        p.kill()
    return 0


def find_children(name):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + name, "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, errors="ignore").stdout
    class P:
        def __init__(self, pid):
            self.pid = pid
    res = []
    for line in out.splitlines():
        parts = [x.strip('"') for x in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == name.lower():
            try:
                res.append(P(int(parts[1])))
            except Exception:
                pass
    return res


if __name__ == "__main__":
    sys.exit(main())
