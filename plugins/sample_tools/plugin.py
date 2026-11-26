"""示例代码插件：文本整理与统计。

抄这个文件就能写自己的代码插件。它演示四件事：
1. @ctx.tool(...)  —— 在「提示词撰写」页注册一个按钮（作用于当前结果文本）
2. @ctx.route(...) —— 注册后端接口，网页或其它程序都能调
3. ctx.get(...)    —— 读 plugin.json 里声明的设置项
4. @ctx.on("generate.after") —— 生成完成后自动处理输出（返回字符串即替换）

注意：插件代码在软件进程里执行，权限与软件本身相同。只放你自己信任的插件；
新插件第一次加载需要在设置页点「信任并加载」。
"""


def register(ctx):
    """入口函数（名字必须是 register，参数是 ctx 对象）。"""

    # ---- 1. 工具按钮：整理文本 --------------------------------------------
    @ctx.tool("tidy", "整理文本", where="toolbar",
              hint="去行尾空格、压掉多余空行，按设置加前缀")
    def tidy(text, params=None):
        params = params or {}
        settings = params.get("settings") or {}
        strip_blank = settings.get("strip_blank", True)
        prefix = (settings.get("prefix") or "").strip()

        lines = [ln.rstrip() for ln in (text or "").splitlines()]
        if strip_blank:
            out, blank = [], False
            for ln in lines:
                if not ln.strip():
                    if blank:
                        continue
                    blank = True
                    out.append("")
                else:
                    blank = False
                    out.append(ln)
            lines = out
        body = "\n".join(lines).strip()
        if prefix:
            body = prefix + "\n" + body
        n = len(body.replace("\n", "").replace(" ", ""))
        ctx.log("整理完成，%d 个非空字符" % n)
        return {"text": body, "note": "已整理：%d 字符" % n}

    # ---- 2. 后端接口：字数统计 --------------------------------------------
    @ctx.route("stats", ["GET", "POST"])
    def stats(body, query):
        """GET/POST /api/plugin/sample_tools/stats  {"text": "..."}"""
        text = (body or {}).get("text") or (query or {}).get("text") or ""
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        return {
            "ok": True,
            "chars": len(text),
            "cjk": cjk,
            "lines": len([x for x in text.splitlines() if x.strip()]),
        }

    # ---- 3. 生成后处理钩子 ------------------------------------------------
    @ctx.on("generate.after")
    def after_generate(payload):
        if not ctx.get("append_note"):
            return None  # 返回 None = 不改变输出
        out = payload.get("output") or ""
        if "（由插件整理）" in out:
            return None
        return out.rstrip() + "\n\n（由插件整理）"
