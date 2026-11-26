# -*- coding: utf-8 -*-
"""验证安装器解包逻辑（源码模式，直接读 build\installer\payload.zip）。"""
import os
import sys
import time
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "installer"))
sys.argv = ["probe"]
import setup as S  # noqa: E402

print("payload =", S.payload_zip())
z = zipfile.ZipFile(S.payload_zip())
names = z.namelist()
print("entries =", len(names), "first =", names[0], "last =", names[-1])
z.close()

tgt = r"E:\_inst_test\ProbeStudio"
shutil.rmtree(tgt, ignore_errors=True)
t0 = time.time()
state = {}
ex = S.Extractor(tgt, None, lambda ok, msg: state.update(ok=ok, msg=msg), None)
ex.run()
print("extract =", state, "secs =", round(time.time() - t0, 1))

files = 0
total = 0
for base, _d, fs in os.walk(tgt):
    for f in fs:
        files += 1
        total += os.path.getsize(os.path.join(base, f))
print("files =", files, "GB =", round(total / 1024.0 ** 3, 2))
print("exe =", os.path.isfile(os.path.join(tgt, "PromptStudio.exe")))
print("models =", os.path.isdir(os.path.join(tgt, "models", "gemma-4-e2b")))
print("packs =", len(os.listdir(os.path.join(tgt, "runtime", "packs"))) if os.path.isdir(os.path.join(tgt, "runtime", "packs")) else -1)
print("plugins =", os.listdir(os.path.join(tgt, "plugins")) if os.path.isdir(os.path.join(tgt, "plugins")) else -1)

S.make_shortcuts(tgt, desktop=False, startmenu=False)
S.write_uninstall(tgt)
print("uninstall =", os.path.isfile(os.path.join(tgt, "卸载 PromptStudio.cmd")))
