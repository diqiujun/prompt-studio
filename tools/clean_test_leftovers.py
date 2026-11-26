# -*- coding: utf-8 -*-
"""清理 PM 的测试残留。默认 dry-run，加 --yes 才真删。"""
import glob
import os
import shutil
import sys

PS = r"E:\新建文件夹\prompt-studio"

TARGETS = [
    r"E:\_inst_test",
    r"E:\_pstest4",
    r"E:\新建文件夹\_inst_icon",
    os.path.join(PS, "build", "installer", "dist"),
    os.path.join(PS, "build", "installer", "dist_onedir"),
    os.path.join(PS, "build", "installer", "work_onedir"),
]
TARGETS += sorted(glob.glob(os.path.join(PS, "build", "work[0-9]*")))

# 绝不能碰的东西（绝对路径；目标等于它或位于它之下就跳过，说明通配写错了）
FORBIDDEN = [os.path.join(PS, x) for x in
             ("dist", "src", "static", "templates", "plugins", "models", "runtime", "data",
              os.path.join("build", "installer", "payload.zip"))]


def size_of(path):
    n = s = 0
    for b, ds, fs in os.walk(path):
        for f in fs:
            try:
                s += os.path.getsize(os.path.join(b, f))
                n += 1
            except OSError:
                pass
        if len(b.split(os.sep)) - len(path.split(os.sep)) > 6:
            ds[:] = []
    return n, s


def main():
    apply = "--yes" in sys.argv
    print("模式：%s" % ("真删" if apply else "预演（加 --yes 才删）"))
    total = 0
    for t in TARGETS:
        t = os.path.abspath(t)
        low = t.lower()
        bad = [f for f in FORBIDDEN
               if low == f.lower() or low.startswith(f.lower() + "\\") or low.startswith(f.lower() + "/")]
        if bad:
            print("!! 跳过（命中禁区 %s）：%s" % (bad, t))
            continue
        if not os.path.exists(t):
            print("-- 不存在：%s" % t)
            continue
        if not os.path.isdir(t):
            print("!! 不是目录，跳过：%s" % t)
            continue
        n, s = size_of(t)
        total += s
        print("删除 %-58s %5d 文件 %8.1f MB" % (t, n, s / 1024 ** 2))
        if apply:
            try:
                shutil.rmtree(t)
            except Exception as exc:
                print("   失败 %s: %s" % (exc.__class__.__name__, exc))
    print("合计 %.2f GB" % (total / 1024 ** 3))
    if apply:
        print()
        print("复核：")
        for t in TARGETS:
            print("  %s  %s" % ("残留" if os.path.exists(t) else "已清除", t))


if __name__ == "__main__":
    main()
