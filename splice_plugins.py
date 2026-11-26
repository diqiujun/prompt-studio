"""把 src/app.py 里旧的插件段替换成新的（含信任/安装/工具/接口分发）。"""
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
APP = os.path.join(SRC, "app.py")
NEW = os.path.join(SRC, "app.py.plugins_new")

src = io.open(APP, encoding="utf-8").read()
new = io.open(NEW, encoding="utf-8").read()

start = src.index("# --------------------------------------------------------------------------- 插件")
end = src.index("# --------------------------------------------------------------------------- 启动")
out = src[:start] + new + src[end:]
io.open(APP, "w", encoding="utf-8", newline="\n").write(out)
os.remove(NEW)
print("replaced bytes:", len(out), "| plugins endpoints:", out.count("/api/plugins"))
print("has tool endpoint:", "/api/plugins/tool" in out, "| has route dispatch:", "/api/plugin/<pid>" in out)
