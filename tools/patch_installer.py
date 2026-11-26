# -*- coding: utf-8 -*-
"""一次性补丁：给 installer/setup.py 与 build_installer.py 打上调试/测试用的小改动。"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding="utf-8").read()
    done = []
    for old, new, tag in pairs:
        if new in s:
            done.append(tag + ":已存在")
            continue
        if old not in s:
            done.append(tag + ":未找到原文")
            continue
        s = s.replace(old, new, 1)
        done.append(tag + ":已改")
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print(path, "->", ", ".join(done))


patch("installer/setup.py", [
    ("            % exc.__class__.__name__)",
     '            % (exc.__class__.__name__ + "：" + str(exc)))',
     "err-detail"),
    ('    cands = [os.path.join(here, "payload.zip")]',
     '    env_pay = os.environ.get("PS_PAYLOAD")\n'
     '    cands = ([os.path.abspath(env_pay)] if env_pay else []) + [os.path.join(here, "payload.zip")]',
     "ps-payload"),
])

patch("build_installer.py", [
    ('    shutil.copy2(PAYLOAD, os.path.join(out, "payload.zip"))',
     '    if os.environ.get("PS_NO_PAYLOAD") != "1":\n'
     '        shutil.copy2(PAYLOAD, os.path.join(out, "payload.zip"))',
     "no-payload-flag"),
])
