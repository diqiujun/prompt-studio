# -*- coding: utf-8 -*-
"""重排 README：按期望顺序重排章节（含正文），并统一编号「一、二、…十一」。"""
import io
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(ROOT, "README.md")
CN = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
      "十一", "十二", "十三", "十四", "十五"]

ORDER = ["启动", "配置模型服务", "撰写提示词", "翻译", "自定义模型",
         "@ 引用参考图", "提示词规范管理", "插件", "运行环境", "常见问题", "二次开发"]


def cn(n):
    return CN[n] if 0 <= n < len(CN) else str(n)


def main():
    text = io.open(P, encoding="utf-8").read()
    lines = text.splitlines()
    head, sections = [], []
    cur = None
    for ln in lines:
        if ln.startswith("## "):
            cur = {"title": ln[3:].strip(), "body": []}
            sections.append(cur)
        elif cur is None:
            head.append(ln)
        else:
            cur["body"].append(ln)

    def clean(t):
        return re.sub(r"^[零一二三四五六七八九十百\d.．]+\s*、\s*", "", t).strip()

    for s in sections:
        s["clean"] = clean(s["title"])
        s["idx"] = next((i for i, k in enumerate(ORDER, 1) if k in s["clean"]), 99)

    sections.sort(key=lambda s: (s["idx"], s["clean"]))
    out = list(head)
    for n, s in enumerate(sections, 1):
        body = "\n".join(s["body"]).rstrip()
        out.append("## %s、%s" % (cn(n), s["clean"]))
        out.append("")
        out.append(body)
        out.append("")
    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    io.open(P, "w", encoding="utf-8", newline="\n").write(text)
    for ln in text.splitlines():
        if ln.startswith("## "):
            print(ln)


if __name__ == "__main__":
    main()
