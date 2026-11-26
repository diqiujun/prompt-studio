# -*- coding: utf-8 -*-
"""列出本机所有 PromptStudio（PM）副本：注册表、磁盘、快捷方式、进程。"""
import glob
import os
import subprocess
import time

NAMES = {"promptstudio.exe", "promptstudiosetup.exe", "promptstudiosetupdbg.exe"}
SKIP = {"windows", "programdata", "$recycle.bin", "system volume information", "winsxs",
        "windowsapps", "node_modules", ".git", "__pycache__", "appdata\\local\\temp"}
MAX_DEPTH_ROOT = 4      # 各盘根往下最多 4 层
MAX_DEPTH_HOME = 6      # 用户目录/Program Files 往下 6 层


def walk(root, depth, maxdepth, hits, t0):
    if time.time() - t0 > 300:
        return
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for e in entries:
        try:
            if e.is_dir(follow_symlinks=False):
                low = e.name.lower()
                if low in SKIP or depth >= maxdepth:
                    continue
                walk(e.path, depth + 1, maxdepth, hits, t0)
            elif e.name.lower() in NAMES:
                st = e.stat()
                hits.append({"path": e.path, "size": st.st_size,
                             "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                             "dir": os.path.dirname(e.path)})
        except OSError:
            pass


def dir_size(path, limit=25):
    n = s = 0
    for b, ds, fs in os.walk(path):
        for f in fs:
            try:
                s += os.path.getsize(os.path.join(b, f))
                n += 1
            except OSError:
                pass
        if len(b.split(os.sep)) - len(path.split(os.sep)) > limit:
            ds[:] = []
    return n, s


def reg_entries():
    import winreg
    out = []
    paths = [r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
             r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"]
    for root, tag in [(winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")]:
        for view, vtag in [(winreg.KEY_WOW64_64KEY, "64"), (winreg.KEY_WOW64_32KEY, "32")]:
            for rel in paths:
                try:
                    k = winreg.OpenKey(root, rel, 0, winreg.KEY_READ | view)
                except OSError:
                    continue
                for i in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        sub = winreg.EnumKey(k, i)
                        sk = winreg.OpenKey(k, sub)

                        def v(name):
                            try:
                                return winreg.QueryValueEx(sk, name)[0]
                            except OSError:
                                return ""
                        dn = str(v("DisplayName"))
                        if "PromptStudio" in sub or "Prompt" in dn or "提示词" in dn:
                            out.append("%s%s %s | %s | v%s | %s" % (
                                tag, vtag, sub, dn, v("DisplayVersion"),
                                v("InstallLocation") or v("DisplayIcon")))
                    except OSError:
                        pass
    return out


def main():
    t0 = time.time()
    hits = []
    roots = []
    for drive in "CDEFGH":
        r = drive + ":\\"
        if os.path.isdir(r):
            roots.append((r, MAX_DEPTH_ROOT))
    for extra in [os.path.expanduser("~"), os.path.join(os.path.expanduser("~"), "AppData", "Local", "Programs"),
                  r"C:\Program Files", r"C:\Program Files (x86)", r"C:\Users\minut\Desktop",
                  r"C:\Users\minut\Downloads", r"E:\新建文件夹"]:
        if os.path.isdir(extra):
            roots.append((extra, MAX_DEPTH_HOME))
    seen = set()
    for root, depth in roots:
        walk(root, 0, depth, hits, t0)

    print("扫描用时 %.0f 秒，命中 %d 个可执行" % (time.time() - t0, len(hits)))
    print()
    print("=== 注册表卸载项 ===")
    regs = reg_entries()
    print("\n".join("  " + r for r in regs) if regs else "  （无）")
    print()
    print("=== 磁盘上的副本 ===")
    rows = []
    for h in sorted(hits, key=lambda x: x["path"].lower()):
        key = h["dir"].lower()
        if key in seen:
            continue
        seen.add(key)
        n, s = dir_size(h["dir"])
        rows.append((h["path"], h["size"], h["mtime"], n, s / 1024 ** 2))
    for p, size, mt, n, mb in rows:
        print("  目录 %s" % os.path.dirname(p))
        print("      exe  %s  %d 字节  %s" % (os.path.basename(p), size, mt))
        print("      体量 %d 个文件 / %.1f MB" % (n, mb))
    if not rows:
        print("  （无）")
    print()
    print("=== 运行中的进程 ===")
    ps = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                        encoding="mbcs", errors="ignore")
    live = [l for l in ps.stdout.splitlines()
            if "PromptStudio" in l or "llama-server" in l or "QtWebEngineProcess" in l]
    print("\n".join("  " + l for l in live) if live else "  （没有 PromptStudio / llama-server 进程）")
    print()
    print("=== 快捷方式 ===")
    lnks = []
    for pat in [r"C:\Users\minut\Desktop\*.lnk", r"C:\Users\Public\Desktop\*.lnk",
                r"C:\Users\minut\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\*.lnk",
                r"C:\Users\minut\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\**\*.lnk",
                r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\*.lnk"]:
        for f in glob.glob(pat, recursive=True):
            if "Prompt" in os.path.basename(f) or "提示词" in os.path.basename(f):
                lnks.append(f)
    print("\n".join("  " + l for l in lnks) if lnks else "  （无）")


if __name__ == "__main__":
    main()
