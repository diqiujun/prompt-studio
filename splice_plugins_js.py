"""把 static/app.js 里的插件段替换成新版（信任/安装/设置项/工具按钮）。"""
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(ROOT, "static", "app.js")
NEW = os.path.join(ROOT, "static", "_plug_new.js")

src = io.open(APP, encoding="utf-8").read()
new = io.open(NEW, encoding="utf-8").read()

start = src.index("/* ------------------------------------------------------------------ 插件 */")
end = src.index("let SPEC = null;")
out = src[:start] + new + "\n" + src[end:]
io.open(APP, "w", encoding="utf-8", newline="\n").write(out)
os.remove(NEW)
print("app.js bytes:", len(out))
for k in ("renderPluginTools", "data-pg-trust", "pluginInstall", "placeResult", "/api/plugins/tool"):
    print(k, "->", k in out)
