# -*- coding: utf-8 -*-
"""验证 dist\release 里打好的插件 zip 能被 PM 正常安装（安装目录名=id、清单可读）。"""
import io
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import pluginlib  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX = os.path.join(ROOT, "build", "_pl_upload_test", "plugins")
RELS = os.path.join(ROOT, "dist", "release")


def main():
    if os.path.isdir(SANDBOX):
        shutil.rmtree(SANDBOX)
    os.makedirs(SANDBOX, exist_ok=True)
    pluginlib.plugins_dir = lambda: __import__("pathlib").Path(SANDBOX)
    fails = []
    zips = sorted(f for f in os.listdir(RELS) if f.startswith("prompt-studio-plugin-") and f.endswith(".zip"))
    if not zips:
        print("没有找到插件 zip")
        return 1
    for name in zips:
        path = os.path.join(RELS, name)
        data = io.open(path, "rb").read()
        try:
            res = pluginlib.install_zip(data, name)
        except Exception as e:
            fails.append("%s 安装抛错: %s" % (name, e))
            print("FAIL %s → %s" % (name, e))
            continue
        pid = res.get("id") or ""
        d = os.path.join(SANDBOX, pid)
        ok = bool(pid) and os.path.isdir(d) and os.path.isfile(os.path.join(d, "plugin.json"))
        print("%s %-52s → %s（%s）" % ("OK  " if ok else "FAIL", name, pid, "plugin.json 就位" if ok else "缺 plugin.json"))
        if not ok:
            fails.append("%s 装完找不到 manifest" % name)
    print("\n结果：%s" % ("全部通过" if not fails else "失败 %d 项：%s" % (len(fails), fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
