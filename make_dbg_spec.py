# -*- coding: utf-8 -*-
"""生成一个 console=True 的调试 spec，用于捕获打包版崩溃输出。"""
import io

src = io.open("build/promptstudio.spec", encoding="utf-8").read()
dbg = src.replace("console=False", "console=True").replace(
    'name="PromptStudio"', 'name="PromptStudioDbg"')
if "console=True" not in dbg:
    raise SystemExit("未找到 console=False，检查 spec")
io.open("build/promptstudio_dbg.spec", "w", encoding="utf-8").write(dbg)
print("dbg spec written")
