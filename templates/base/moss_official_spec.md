# MOSS-Image 官方口径细则（2026-11-20 增补）

来源：OpenMOSS/MOSS-Image 官方 `README_ZH.md`、`USERGUIDE_ZH.md`、官方 `skills/moss-image-prompt-enhancer/`（SKILL.md + references/layout.md）、ComfyUI 官方模板口径；取证日期 2026-11-20。

**优先级约定**：目标是 MOSS-Image 时，本文件在「负向词、画质词、画布与参数、坐标」四类事项上优先于 `references/negative-lexicon.md` 与源规范 `assets/source-moss-prompt-composer.txt`；本技能独有的安全类槽位（`safe_stable_state`、事故类场景负向词）是官方没有的增量，继续保留。

## 1. 参数档位表

| 项目 | 官方口径 | ComfyUI 官方模板默认 | 要记的要点 |
|---|---|---|---|
| 生成步数 | ≥50 效果最佳 | 25 步（T2I SFT）；edit 模板 30；color&depth 25 | 出图「夹生」第一步补到 50 步，别先改别的 |
| CFG | 默认 3.0，推荐 3.0–6.0 | 2.5；edit 模板 4 | 长提示词 3.0 足够；短提示词调高 |
| 采样器 | Euler（flow matching） | er_sde | 官方示例用 Euler + 50 步 |
| Shift | 5.0 | 5.0 | 一致 |
| SLG 跳层 | 标准 scale 3 / 二次采样 uncond skip，skip layer 推荐 22（22/24/26 都有效） | 标准；color&depth 模板 skip layer 24 | 关掉 SLG 画面非常真实，但细节会崩 |
| 分辨率 | 训练 1M / 1.5M / 2M 总像素；可外推 0.25M–4M | 1024×1024 系 | 宽高必须是 16 的正整数倍，否则直接报错 |
| 负面词 | 官方实测有效 5 项：`nsfw, worst quality, bad anatomy, watermark, jpeg artifact` | 同官方 | Python API 默认可留空；`guidance_scale=1.0` 时无负向分支，负面词失效 |
| 提示词长度 | 上限 4096 tokens | 同 | 文本编码器 Qwen3.5-9B，ComfyUI `CLIPLoader type=moss_image`；w4a8_gptq 7.34GB > 主干 5.41GB |
| 扩写 | 无 | 模板默认开 `enable_prompt_enhancer` | 要逐字控中文文案就设 false；扩写后的真 caption 在 Preview Any 节点可查 |

权重与版本：ComfyUI 原生支持需 0.42.0+（`Image Edit`、`Color&Depth` 模板需 0.43.0+，PR#17095；v0.41.3 无）。六个官方模板：T2I SFT / T2I Base / Layout-Guided SFT / Layout-Guided Base / Image Edit LoRA / Color&Depth Control。权重落位：`moss_image_sft_int8_convrot.safetensors` 5.41GB → `models/diffusion_models`；`qwen3.5_9b_w4a8_gptq.safetensors` 7.34GB → `models/text_encoders`；`flux2-vae_small.safetensors` 0.25GB → `models/vae`（合计约 13GB）。同 seed 不能复现 Diffusers 出图（原生调度不做训练网格对齐）。旧插件工作流迁移要整图导入，且 `ModelSamplingSD3` 换 `ModelSamplingAuraFlow` multiplier 1。

## 2. 文字渲染七条（逐字照用）

1. 写「成品画面」，不写「需求」。ComfyUI 官方口径：`Describe the finished image, not the request`。
   - 弱：`给我做一张夜市海报`
   - 强：`A vintage Chinese night market festival poster. Large bold title "夜市狂欢节" at the top with the English subtitle "Night Market Carnival" below it…`
2. 要渲染的文字一律进引号逐字给出，并保留原语言：英文描场景 + 中文写字。官方第一条示例就是纯中文长手写文字写在玻璃板上；第二条是冰箱便利贴三行手写「记得买牛奶和鸡蛋！/ 牛奶两盒，鸡蛋一打。/ 顺便带一袋面包。」（负面留空）。
3. 换行自己控制：模型自动换行不可靠，要分行就手写 `\n` 或直接换行。
4. 文字要有层级与像素：大标题 / 副标题 / 正文 / 页脚逐条说清位置与字号；小字塞不下就放大字号、删字，或把画布升到 2MP。
5. 收口多余文字：列完所有要出现的文字后补 `with no other text`（负向词管不了多余文字，正向收口才有效）。
6. 画质词位置：官方只在 Tag 串里把质量词放最前，自然语言描景不堆 `8K quality` 这类词。Tag 串顺序 `Quality → Score → Meta → Year → Character → Series → Artist → General`（例：`best quality, highres, <角色>, <系列>, <画师>, <一般标签>`）；带文字的图用自然语言更好。
7. 精确位置靠 Layout 框，不靠散文：官方与 ComfyUI 文档都认定 box 比文字描述位置可靠。

## 3. Layout 坐标系与合法字段

- 模型侧：`bbox_coord_space="abs_centralized"`、`bbox_format="yxyx"`（`y_min, x_min, y_max, x_max`），1024×1024 画布的坐标范围是 ±512，x 向右、y 向下。
- 草稿侧（人写）：`bbox_coord_space="abs"`、`bbox_format="xyxy"`，整数像素、左上原点；`width`/`height` 必须是 16 的倍数，且**不进编译产物**。
- 换算：`x' = x - W/2`，`y' = y - H/2`（例：1024×1024 上左上角 (0,0) → (-512,-512)；右下角 (1024,1024) → (512,512)）。官方选绝对坐标的理由是适配不同分辨率与长宽比。
- 字段白名单：`label` 只允许 `object` / `character` / `text`；`text` 字段放逐字可见文字（换行用 JSON 的 `\n`）。
- 禁止：`children` / `parent` / `id` / 百分比坐标 / 嵌套结构 / 自造字段 —— 编译器会拒绝未识别字段。
- 模型不应自行计算坐标：编译由官方 `skills/moss-image-prompt-enhancer/scripts/compile_prompt.py` 完成，生成时的画布尺寸必须与草稿一致。
- box 是位置标注，不是要画出来的边框；要边框得在描述里写。
- 需要框的情况：文字定位 / 海报 / 多面板 / 受控物体关系。纯氛围图用 caption 即可。
- 描述用英文（训练量最多，中文也支持）；`layout_json` 与坐标说明不得写进图像描述字段；显式极简需求保持极简。
- 写真实文案，禁止 `headline here` 这类占位。
- 在线画框备选：`moss-image-community/moss-image-layout-editor`（浏览器画框，输出与 `compile_prompt.py` 一致的提示词）。

## 4. 黑图（NaN）排查表

根因：FP16 残差流峰值约 62100（第 26/42 层），FP16 上限 65504，余量仅约 5%；残差流随像素数增长，CFG 与提示词几乎不影响。

| 画布 | 残差流峰值 | 结果 |
|---|---|---|
| 1024×1024 | ≈62100 | 安全 |
| 2048×2048 | ≈64100 | 可用 |
| 2560×2560 | 溢出 | 第 29/50 步出黑图 |

解法：去掉 `--fp16-unet` 走 bf16；或换 `KBlueLeaf/MOSS-Image-FP16-fixed`（权重内把残差流缩 1/16）、`MOSS-Image-heal`（流最大值 3083）。AMD gfx11 + `--bf16-vae` 全黑是 ComfyUI 的 bug（PR#17196 引入，issue #17317，commit fb3befd1 修复），N 卡无关。

## 5. 社区配套件（按需）

| 件 | 用途 |
|---|---|
| `MATLOWAI/MOSS-Image-SFT-DeBand` | 抑制 SFT 垂直色带，带 ComfyUI 预设；色带与细节有权衡 |
| `lodestones/MOSS-Image-SFT-8-steps-dmd` | 8 步 DMD 加速版 |
| `ComfyUI-Spectrum-MOSS` | 加速 |
| `mossimage.cpp` | 无 PyTorch 推理 |
| `KohakuMossTrainer` | 全参 + LyCORIS 训练，适配器最低 6GB 显存，Windows/Linux，NVIDIA SM70–SM120 + Intel Arc |
| `DiffSynth-Studio` / `ai-toolkit` | Base LoRA 训练（脚本参考 rank32 / lr1e-4 / 5 epoch / ≤1MP） |

训 LoRA 用 Base 权重，且必须冻结 Text Encoder。官方 caption 标注 prompt 提供 long / medium / short 三档，含 watermark 归一化 0–1000 框与 borders；标注模型推荐 Gemma 4 / Qwen3.5 27B / 35B-A3B 并开 thinking。

## 6. 与本机模板的三处冲突及处置

| 本机模板 | 官方口径 | 处置 |
|---|---|---|
| 负向固定 18 项含 `text`、`cartoon style` | 官方负面 5 项，不含 `text` / `cartoon` | 条件门禁：正向含可见文字时删 `text`；正向为动漫/卡通/插画风格时删 `cartoon style`（见 `references/negative-lexicon.md` 门禁节） |
| 正向固定 `high detail, 8K quality` | 质量词只放 Tag 串最前，自然语言描景不堆质量词 | 保留（源规范硬要求），在 warnings 里记一句「MOSS-Image 官方口径不堆质量词」；Tag 串模式下改按第 6 条顺序写 |
| 槽位式逗号串 | 连贯描述 + 文字逐字 + 位置层级 | 人物/场景/安全类需求继续用槽位串；带文字设计类改连贯描述并按第 2 条写文字 |
