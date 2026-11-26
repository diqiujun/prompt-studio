r"""插件 zip 安装自检：把仓库里的两个示例插件打成 zip，走 pluginlib.install_zip 真正装一遍。

用法：python tools\test_plugin_zip.py
产物：dist\release\plugin-sample-generic-1.1.zip 与 plugin-sample-tools-1.1.zip（同时就是发布用资产）
"""
import io
import json
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import pluginlib  # noqa: E402

OUT = os.path.join(ROOT, "dist", "release")
SRC = os.path.join(ROOT, "plugins")
VERSION = "1.1"
CASES = [("sample_generic", "plugin-sample-generic-%s.zip" % VERSION),
         ("sample_tools", "plugin-sample-tools-%s.zip" % VERSION)]

FAILS = []


def ok(label, extra=""):
    print("OK   %s %s" % (label, extra))


def bad(label, extra=""):
    FAILS.append(label)
    print("FAIL %s %s" % (label, extra))


def make_zip(pid, out_path):
    """根直接放 plugin.json（不套外层目录），装的时候最省事。"""
    src_dir = os.path.join(SRC, pid)
    if not os.path.isdir(src_dir):
        raise SystemExit("找不到源插件目录：%s" % src_dir)
    os.makedirs(OUT, exist_ok=True)
    names = []
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in files:
                full = os.path.join(base, fn)
                rel = os.path.relpath(full, src_dir).replace("\\", "/")
                z.write(full, rel)
                names.append(rel)
    return names


def main():
    tmp_plugins = os.path.join(ROOT, "build", "_pl_zip_test", "plugins")
    if os.path.isdir(os.path.dirname(tmp_plugins)):
        shutil.rmtree(os.path.dirname(tmp_plugins), ignore_errors=True)
    os.makedirs(tmp_plugins, exist_ok=True)

    # 让 install_zip 往临时目录装，别污染真实 plugins\
    pluginlib.plugins_dir = lambda: __import__("pathlib").Path(tmp_plugins)

    for pid, fname in CASES:
        out_path = os.path.join(OUT, fname)
        names = make_zip(pid, out_path)
        size = os.path.getsize(out_path)
        ok("%s 打包" % pid, "%s · %d 文件 · %.1f KB" % (fname, len(names), size / 1024.0))
        if "plugin.json" not in names:
            bad("%s 包根有 plugin.json" % pid)

        raw = open(out_path, "rb").read()
        r = pluginlib.install_zip(raw, fname)
        if not r.get("ok"):
            bad("%s 安装" % pid, str(r.get("error")))
            continue
        ok("%s 安装到" % pid, r.get("dir", ""))

        target = os.path.join(tmp_plugins, r["dir"])
        man = os.path.join(target, "plugin.json")
        if os.path.isfile(man):
            meta = json.load(open(man, encoding="utf-8-sig"))
            ok("%s 安装后清单可读" % pid, "id=%s name=%s" % (meta.get("id"), meta.get("name")))
        else:
            bad("%s 安装后清单已落盘" % pid)

        # 重复安装应当被拒绝（提示已存在），说明不会覆盖用户改过的插件
        r2 = pluginlib.install_zip(raw, fname)
        if r2.get("ok"):
            bad("%s 重复安装被拒" % pid)
        else:
            ok("%s 重复安装被拒" % pid, str(r2.get("error"))[:40])

    shutil.rmtree(os.path.dirname(tmp_plugins), ignore_errors=True)

    print("\n结果：%d 项失败" % len(FAILS) if FAILS else "\n结果：全部通过")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
