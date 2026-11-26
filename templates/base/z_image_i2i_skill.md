---
name: z-image-img2img
description: 为 Z-Image（通义 Tongyi-MAI，6B 单流 S3-DiT）的图生图任务组装提示词与生成参数：风格转绘（照片转动漫/转吉卜力/转油画）、洗图（同构图重画一遍提质去瑕换模型味）、局部重绘、扩图、材质变换、人物转 Q 版手办、参考图引导换风格，核心是「强度（denoise/strength）决定改多少、提示词决定改什么」，并强制写「保留项 + 替换项 + 新增项」句式。当用户给一张图要求「转成某画风」「洗图」「提质」「换材质」「把这个人做成手办/Q 版」「保持构图只改光照」「系列图保持一致」「Z-Image 图生图怎么写」「denoise 设多少」时使用。本技能只做提示词与参数组装、失败模式预判，不直接生成图片；文生图写法与 MOSS 出图分别走文生图口径与 moss-image-prompt-composer。
---

# Z-Image 图生图提示词与参数组装

给 Z-Image 的图生图（img2img / 参考图引导）任务组装**正向提示词 + 负向提示词 + 生成参数 + 失败模式预判**。

一句话原理：**强度（strength / denoise）是主旋钮，提示词是调味料**。模型跑偏时先降强度，不要跟提示词搏斗。参考图会被模型整体继承——你文字没写的东西（顶光、木纹质感、机位、负空间）也会漏进输出，所以提示词必须显式声明**保留项**。

本技能**不生成图片**。生成执行走 ComfyUI 图生图链路（`dsh-comfyui-workflows`），出图后的逐帧/逐像素质检走 `minimax-h3-director` 的质检纪律。

## 触发条件

- 「Z-Image 图生图怎么写」「denoise 设多少」「强度设多少」
- 「把这张图转成动漫/吉卜力/油画/乐高/3D Q 版」「洗图」「提质」「去 AI 感」「换模型味」
- 「保持构图不变，只改材质/光照/配色」「把这个人做成手办/摇头娃娃/Q 版」「系列图要一致」
- 「用这张参考图换风格」「局部重绘」「扩图」

## 前置事实（写参数前必须知道的三条）

1. **模型变体先定，参数才有意义**。Turbo 与 Base 的参数口径互斥，不可混用一套档：

| 变体 | 步数 | CFG | 负向提示词 | 强度表现 | 备注 |
|---|---|---|---|---|---|
| Z-Image-Turbo | 8（ComfyUI 模板 8，官方代码 9 即 8 次 DiT 前向；改高步数会引入噪点） | 1（0 或 1，不得更高） | **完全忽略负向输入框**（否定形要生效需 CFG≥1 且推理时间翻倍） | 强度 0.15–0.45 主力，细节少 | 写实最强、多样性低、不可微调 |
| Z-Image Base | 25–50（社区实测 28–40） | 3.0–5.0（风格转绘常用 6–8） | **强烈建议写** | 强度 0.4–0.6 主力 | 高多样性、易微调、细节多 |
| Z-Image Edit | 50 | 同 Base | 写 | — | 指令式编辑（改表情/改天气/把「鹅」改「猫」）；**官方权重截至 2026-11-06 未公开**，当前不可依赖 |

⇒ 当前可走的图生图路线只有 **Turbo/Base 的 img2img（denoise<1）+ 局部重绘 + 扩图**。

2. **变体写进产物字段**（`model_variant`）。同一句提示词在两个变体上的表现完全不同。
3. **Z-Image 用 Flux 1 的 VAE（`ae.safetensors`）**，文本编码器为 qwen_3_4b；**与其它模型的 latent 不兼容**——从别的模型链路接图必须先 VAE 解码成像素图，再用 Z-Image 的 VAE 重编，提示词也要按 Z-Image 口径重写。

## 三种写法（先定写法，再定强度）

| 写法 | 目标 | 强度区间 | 提示词侧重 |
|---|---|---|---|
| **风格转绘** | 构图不变、换画风（照片→动漫、线稿→上色、日景→夜景） | 0.50–0.70 | **强风格词，少描述原图已有细节**；负向写「不要留下的风格」 |
| **洗图** | 同构图重画一遍，提质、去瑕、去 AI 感、换模型味、统一系列风格 | 0.45–0.65 | **强质量词 + 一行原主题简述**（写太长会覆盖洗图效果） |
| **重绘** | 大幅改内容，源图只当骨架 | 0.75–0.95 | 按新内容整段重写，接近文生图 |

细节档位与摩擦点见 `references/strength-tiers.md`。

## 核心句式（组装时按此顺序拼）

```text
[变换动词句] [保留项] ; [替换项] ; [新增项] [目标风格词 2–3 个] [材质/光照/色板一句] [构图控制词] [对冲源图光照的词] [质量与纯净度词]
```

逐字范例（最强的可复用骨架）：

```text
keep the desk angle and daylight; replace mug with glass tumbler; add plant, shallow depth of field
```

要点：

- **保留项必须写**，中强度 + 显式保留项胜过形容词堆砌。
- **风格词只写 2–3 个具体的**，超过就变噪音；**禁用抽象形容词**（✗ beautiful girl → ✓ a girl with flowing silver hair that catches the moonlight）。
- **纹理词只选一个家族**，`grainy, gritty, distressed, filmic` 叠加会出麻点阴影与条带。
- **混合精度是优质画面设计的杀手锏**：人物风格化 + 环境写实（人物 `chibi 3D style`，环境 `realistic and photorealistic`）。
- **源图带顶光就在提示词里对冲**：`soft side lighting, muted highlights`。
- Turbo 无负向可用 ⇒ 排除项一律**正向化**写进正向（`no text, no watermark, plain background, correct human anatomy, natural hands and fingers, no extra limbs, sharp focus`）。

更多逐字句式（风格转绘四型、洗图模板、二次洗、变换动词句族、材质转换模板、双重曝光公式、LEGO/海报/电商模板、文字渲染四条、颜文字做表情）见 `references/prompt-patterns.md`。

## 生成流程（9 步，顺序执行）

1. **定任务类型**：风格转绘 / 洗图 / 重绘 / 局部重绘 / 扩图 / 材质变换 / 参考图引导换风格。
2. **定模型变体**：Turbo 还是 Base（按上面的互斥表；要细节与多样性选 Base，要快与写实选 Turbo）。
3. **审源图**（出参数前必做，写进 `source_prep`）：摆正、去杂物、校正曝光；长边定 1024（太小细节糊、太大只多花带宽）；要锚姿态就先铺一层只画轮廓与主褶的线稿（模型尊重线条，草图式源图比全阴影输入更能锚住姿态）；检查源图光照并在提示词里对冲。
4. **列三张清单**：保留项（构图/姿态/色板/光照/身份要素）、替换项、新增项。
5. **组装正向**：按核心句式顺序拼，长度控制 60–220 词。
6. **组装负向**（Base 才写）：按产品/人物/场景三组挑，外加「不要留下的风格」。Turbo 改成正向化排除句。
7. **定参数**：强度按写法区间给起点，steps/cfg 按变体档；ComfyUI 省时法 `steps = 目标步数 × denoise`。
8. **过质量门禁**（下面 13 条）。
9. **输出**：按输出格式给，含失败模式预判与测试网格。

## 质量门禁（逐条过）

1. 写法（转绘/洗图/重绘）是否明确，强度落在对应区间。
2. 变体是否写明；Turbo 是否没有把负向串当交付物。
3. **保留项是否显式写出**（这是第一判据）。
4. 风格词是否 ≤3 个且具体（无抽象形容词、无比喻）。
5. 纹理词是否只有一个家族。
6. 是否**没有**复述原图已有细节（转绘写法的要求）。
7. 洗图写法的原主题简述是否只有一行。
8. 负向词是否不含正向主体与必要道具；是否含「不要留下的风格」。
9. 源图光照是否已对冲。
10. 是否声明 seed 策略（调参期锁 seed，定稿后放开）。
11. 是否提醒「不要连续把上一张输出当下一张参考图」（风格固化）。
12. 是否给出存档三件套：参考图 + 提示词 + 强度数字。
13. 涉及人物身份保持时，是否写明「强度压 0.35 以下 + 锁 seed + 必要时做只针对脸的轻修」。

## 输出格式

```json
{
  "task_type": "style_transfer | wash | repaint | inpaint | outpaint | material_swap | reference_guided",
  "model_variant": "Z-Image-Turbo | Z-Image-Base",
  "strength_denoise": 0.55,
  "params": {"steps": 28, "cfg": 4.0, "sampler": "euler", "scheduler": "simple", "seed_policy": "lock", "vae": "ae.safetensors"},
  "positive_prompt": "...",
  "negative_prompt": "...（Turbo 时给 positive_purge 正向化排除句）",
  "keepers": ["desk angle", "daylight", "wood grain"],
  "replacements": ["mug -> glass tumbler"],
  "additions": ["plant", "shallow depth of field"],
  "source_prep": ["straighten", "de-clutter", "normalize exposure", "long edge 1024"],
  "failure_watch": ["style drift >0.55", "texture inflation", "face uncanny valley"],
  "test_grid": {"strengths": [0.22, 0.34, 0.48], "cfgs": [5, 7], "note": "固定 seed/采样器/分辨率 + 极短提示词，选中格后只改一个词，文件名标 strength-CFG"}
}
```

## 细则导航

| 需要 | 看 |
|---|---|
| 强度全曲线（Base 0.2–1.0 六段 + 摩擦点）、Turbo 实测四档与三用法实例、三种写法完整参数表、负向词三组逐字、ControlNet 强度掉画质两解法 | `references/strength-tiers.md` |
| 逐字句式库：转绘四型、洗图与二次洗模板、变换动词句族、混合精度、材质/毛茸茸/双重曝光/LEGO/海报/电商模板、十大黄金法则、文字渲染四条、角色名与颜文字口径 | `references/prompt-patterns.md` |
| 官方参数口径、权重落位、显存与解像度稳定边界、steps×denoise 省时法、三大失败模式修法、3×2 测试网格、Edit 权重状态、训 LoRA 口径 | `references/params-and-pitfalls.md` |

## 边界与分工

- 本技能只管**图生图的提示词与参数**；文生图（从零出图）的八段式与画面设计档位不在本技能范围。
- MOSS-Image 出图（含 Layout 排字与 FP16 画布上限）走 `moss-image-prompt-composer`，其细则争议以该技能的 `references/official-moss-spec.md` 为准，勿与本技能混用参数档。
- 短剧全链（剧本→分镜→资产→逐镜视频→打包）在 `short-drama-director`；单场戏调度与出片后逐帧质检在 `minimax-h3-director`（抽帧密度 ≥8 fps、分两张图、四项判据）。
- 生成执行与本机 ComfyUI 工作流选择在 `dsh-comfyui-workflows`。
- 未点名的生成参数不得擅自改动（用户级硬约束）；单段生成时长 ≤8 秒。
