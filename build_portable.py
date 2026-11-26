# -*- coding: utf-8 -*-
"""把模型与 llama.cpp 运行时组装进发行目录，做成"拷目录即装好"的绿色版。

用法（先打好 exe）：
    python -m PyInstaller build\\promptstudio.spec --noconfirm --distpath dist --workpath build\\work
    python build_portable.py

结果：
    dist\\PromptStudio\\
        PromptStudio.exe / _internal\\
        models\\gemma-4-e2b\\  （主模型 + 视觉投影 + MTP）
        llama\\                （llama-server.exe + 全部 DLL，GPU 与 CPU 都在里面）
        README.md
        启动提示.txt

只拷需要的运行时：E:\\llama 顶层的 *.exe / *.dll（约 250 MB），跳过源码与 models 目录。
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist", "PromptStudio")

LLAMA_SRC = r"E:\llama"
MODEL_SRC = r"E:\llama\models\gemma-4-e2b"
MODELS = ["gemma-4-E2B-it-Q4_K_M.gguf", "mmproj-F16.gguf", "mtp-gemma-4-E2B-it.gguf"]

START_TXT = """提示词工作台 Prompt Studio —— 绿色版使用说明
发布者：minut　版本：1.1

1. 把整个 PromptStudio 文件夹拷到目标电脑（任意路径，不要拆开文件）。
2. 双击 PromptStudio.exe，会直接打开程序窗口（不再弹浏览器）。
   首次启动会自动加载本地模型，窗口上有进度提示，约 10–40 秒。
3. 默认就用内置的 gemma-4-e2b（免 API Key，离线可用）。
   想用云端模型：设置 → 模型服务 → 选预设（DeepSeek / OpenAI / 通义等），填 API Key 保存。
4. 关闭窗口即退出，程序会把自己拉起的本地模型一起关掉。

硬件要求
- 显卡：NVIDIA 显存 8 GB 及以上效果最好（自动全量 GPU 加速）；
  显存 4–8 GB 会部分层放 GPU；没有 NVIDIA 显卡则自动用 CPU（能用，但慢）。
- 内存：建议 16 GB（CPU 模式建议 16 GB 以上）。
- 磁盘：解压后约 7 GB（含模型 4 GB + 运行环境包 1 GB）。
- 系统：Windows 10 / 11（x64 与 ARM64 都支持；Linux / macOS 不支持）。

运行环境（不用自己装 CUDA）
- 程序自带 6 套 llama.cpp 预编译包：NVIDIA CUDA 13.5 / 12.4、AMD ROCm 10.0、CPU 通用，
  分 x64 与 ARM64 两种架构，全部放在 runtime\\packs\\。
- 首次启动自动检测系统架构与显卡（驱动支持的 CUDA 版本），挑最合适的一套解压到 runtime\\<包名>\\；
  没有 NVIDIA 卡就自动用 CPU 版，AMD 卡用 ROCm 版。更换显卡后，删掉 runtime 下已解压的目录即可重新适配。
"""


def main() -> int:
    if not os.path.isfile(os.path.join(DIST, "PromptStudio.exe")):
        print("[FAIL] 没找到 dist\\PromptStudio\\PromptStudio.exe，先打 exe")
        return 1

    # 1) 运行时
    dst_llama = os.path.join(DIST, "llama")
    os.makedirs(dst_llama, exist_ok=True)
    n = 0
    total = 0
    for name in os.listdir(LLAMA_SRC):
        src = os.path.join(LLAMA_SRC, name)
        if not os.path.isfile(src):
            continue
        if not name.lower().endswith((".exe", ".dll")):
            continue
        if name.lower().startswith(("test-", "llama-bench", "llama-quantize", "llama-cli",
                                    "llama-mtmd-cli", "llama-gemma3-cli", "llama-embedding",
                                    "llama-perplexity", "llama-batched", "llama-imatrix",
                                    "llama-gguf", "llama-gguf-split", "llama-save-load-state")):
            continue
        shutil.copy2(src, os.path.join(dst_llama, name))
        n += 1
        total += os.path.getsize(src)
    print("运行时：%d 个文件，%.0f MB" % (n, total / 1048576.0))

    # 2) 模型
    dst_model = os.path.join(DIST, "models", "gemma-4-e2b")
    os.makedirs(dst_model, exist_ok=True)
    for m in MODELS:
        src = os.path.join(MODEL_SRC, m)
        if not os.path.isfile(src):
            print("[WARN] 缺模型文件：%s" % src)
            continue
        shutil.copy2(src, os.path.join(dst_model, m))
        print("模型：%s  %.0f MB" % (m, os.path.getsize(src) / 1048576.0))

    # 3) 文档
    for doc, name in ((os.path.join(ROOT, "README.md"), "README.md"),):
        if os.path.isfile(doc):
            shutil.copy2(doc, os.path.join(DIST, name))

    # 4) 插件目录（用户自己往里丢插件，程序启动后就能看到）
    src_plugins = os.path.join(ROOT, "plugins")
    dst_plugins = os.path.join(DIST, "plugins")
    if os.path.isdir(src_plugins):
        if os.path.isdir(dst_plugins):
            shutil.rmtree(dst_plugins, ignore_errors=True)
        shutil.copytree(src_plugins, dst_plugins)
        print("插件：%s" % ", ".join(sorted(os.listdir(dst_plugins))))
    else:
        os.makedirs(dst_plugins, exist_ok=True)

    # 4.5) 姿势库随插件分发（plugins\pose_gallery\data\ 已随上面的插件整体复制，无需额外步骤）

    # 5) 运行环境包（llama.cpp 各平台预编译 zip，首次启动按硬件自动解压安装）
    src_packs = os.path.join(ROOT, "runtime", "packs")
    dst_packs = os.path.join(DIST, "runtime", "packs")
    os.makedirs(dst_packs, exist_ok=True)
    if os.path.isdir(src_packs):
        names = [f for f in sorted(os.listdir(src_packs)) if f.lower().endswith(".zip")]
        for f in names:
            shutil.copy2(os.path.join(src_packs, f), os.path.join(dst_packs, f))
        print("运行环境包：%d 个 → %.2f GB" % (
            len(names), sum(os.path.getsize(os.path.join(dst_packs, f)) for f in names) / (1024.0 ** 3)))
    else:
        print("运行环境包：源目录不存在（%s），跳过" % src_packs)

    with open(os.path.join(DIST, "启动提示.txt"), "w", encoding="utf-8-sig") as f:
        f.write(START_TXT)

    # 6) 分发用启动器：清掉「来自网络」标记（SmartScreen 弹窗的主因）后再启动
    extra = os.path.join(ROOT, "dist_extra")
    if os.path.isdir(extra):
        copied = []
        for f in sorted(os.listdir(extra)):
            src = os.path.join(extra, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(DIST, f))
                copied.append(f)
        print("启动器：%s" % (", ".join(copied) if copied else "（无）"))

    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(DIST) for f in fs)
    print("完成：%s（共 %.2f GB）" % (DIST, size / (1024.0 ** 3)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
