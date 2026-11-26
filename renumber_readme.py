# -*- coding: utf-8 -*-
"""按当前出现顺序给 README.md 的 ## 章节重新编号，并插入「运行环境」一节（若缺）。"""
import io
import re
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(ROOT, "README.md")

CN = "零一二三四五六七八九十"


def cn(n):
    if n <= 10:
        return CN[n]
    if n < 20:
        return "十" + CN[n - 10]
    return str(n)


RUNTIME_SEC = """## 九、运行环境（自带 llama.cpp，按硬件自动适配）

程序自带 6 套 llama.cpp 预编译包（`runtime\\packs\\`，共约 1.04 GB），第一次启动时按你的机器自动挑一套解压到 `runtime\\` 下：

| 你的机器 | 用哪个包 |
| --- | --- |
| NVIDIA，驱动支持 CUDA 13.x | `cuda-13.5-x64`（x64）／`cuda-13.5-arm64`（ARM） |
| NVIDIA，驱动只到 CUDA 12.x | `cuda-12.4-x64` |
| AMD 显卡（已装 ROCm） | `rocm-10.0-x64` |
| 没有独显／想稳一点 | `cpu-x64`／`cpu-arm64`（纯 CPU，慢但一定能跑） |

- 不用自己装 CUDA、也不用装 Python——包里就是编译好的 `llama-server.exe`。
- 设置页「运行环境」能看到检测结论（显卡型号 / 显存 / CUDA 版本 / 架构）、推荐包和已装包，也可以手动「重装」某一套。
- 换了显卡／换了机器：删掉 `runtime\\` 下的包目录，重启程序会重新适配。
- 显存 8 GB 及以上可全量 GPU；4–8 GB 会自动少放层（也能跑）；没有 N 卡自动走 CPU。
- 只支持 Windows（x64 / ARM64）。Linux、macOS 不提供运行环境。

"""


def main():
    text = io.open(P, encoding="utf-8").read()
    if "运行环境（自带 llama.cpp" not in text:
        # 插到「常见问题」之前
        m = re.search(r"^## [^\n]*常见问题", text, re.M)
        if m:
            text = text[: m.start()] + RUNTIME_SEC + text[m.start():]
        else:
            text = text.rstrip() + "\n\n" + RUNTIME_SEC
    # 重新编号所有 ## 标题（保留「常见问题」等原名，只换序号前缀）
    n = [0]

    def repl(mo):
        title = re.sub(r"^[零一二三四五六七八九十百\d]+([、.．]\s*)?", "", mo.group(2)).strip()
        n[0] += 1
        return "## %s、%s" % (cn(n[0]), title)

    text = text
    lines = text.splitlines()
    out = []
    k = 0
    for ln in lines:
        if ln.startswith("## "):
            title = ln[3:].strip()
            title = re.sub(r"^[零一二三四五六七八九十百\d]+\s*[、.．]\s*", "", title).strip()
            k += 1
            out.append("## %s、%s" % (cn(k), title))
        else:
            out.append(ln)
    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    io.open(P, "w", encoding="utf-8", newline="\n").write(text)
    print("renumbered %d sections" % k)


if __name__ == "__main__":
    main()
