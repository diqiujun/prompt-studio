# -*- coding: utf-8 -*-
"""把 localsrv.py 的模块 docstring 改成 raw 字符串，消掉 \l 转义告警。"""
import io

p = "src/localsrv.py"
s = io.open(p, encoding="utf-8").read()
if not s.startswith('# -*- coding: utf-8 -*-\nr"""'):
    s = s.replace('"""', 'r"""', 1)
    io.open(p, "w", encoding="utf-8").write(s)
    print("patched")
else:
    print("already raw")
