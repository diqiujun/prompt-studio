# Z-Image 图生图参数口径 · 环境 · 失败模式

## 1. 官方参数口径（变体互斥，不可混档）

- **Z-Image-Turbo**（官方代码）：`height=width=1024`、`num_inference_steps=9`（实际 8 次 DiT 前向）、`guidance_scale=0.0`（官方注明 guidance should be 0 for Turbo）、`bfloat16`、seed 42。特性：SFT + RL + 蒸馏，8 NFE，关闭 CFG，写实能力最强，双语文字渲染，多样性低，**不可微调**。
- **Z-Image Base**（官方推荐档）：总像素 512×512 – 2048×2048 之间任意宽高比；`guidance_scale 3.0–5.0`；`num_inference_steps 28–50`；**强烈建议写负向提示词**；`cfg_normalization=False` → 通用风格化，`True` → 写实倾向。特性：SFT 无 RL，50 步，CFG 开启，高多样性，易微调。
- **Z-Image Edit**：Edit SFT，50 步，指令式编辑（改表情 / 变成雪天 / 增加气泡对话框 / 把所有「鹅」字改成「猫」）。**官方权重截至 2026-11-06 未公开** ⇒ 当前不可依赖；社区项目「Zen Image Edit」不是官方 Z-Image-Edit，勿混。
- 社区实测口径（ComfyUI）：Turbo = 8 步 / euler / simple / CFG 1 / 3–8 秒；Base = 28–40 步 / CFG 4.0–5.0 / 15–30 秒。Base 用 CFG 5 + 30 步约耗时 5 倍于 Turbo。
- 否定形（`no X`）需要 CFG≥1 才生效且推理时间翻倍 ⇒ Turbo 的实用做法是排除项正向化写进正向串。
- 采样器备选：`res_multistep` + 4 步出图细节偏糙，适合**快速验证提示词**；`dpmpp_2m_sde` 首步空 prompt 去噪可增随机性。

## 2. 权重与节点落位（ComfyUI）

| 文件 | 落位 | 备注 |
|---|---|---|
| `z_image_turbo_bf16.safetensors`（Base 为 `z_image_bf16.safetensors`） | `models/diffusion_models` | UNETLoader 加载 |
| `qwen_3_4b.safetensors` | `models/text_encoders` | CLIPLoader；社区有 `qwen_3_4b_fp8_mixed.safetensors` 版，其 `type` 配 `lumina2` |
| `ae.safetensors` | `models/vae` | = **Flux 1 VAE**；换 VAE 可改善细节（`UltraFlux-v1` 通用，动漫噪点减用社区 `Z-Image_Anime_VAE`） |
| `Z-Image-Turbo-Fun-Controlnet-Union`（含 .2.0/.2.1 与 8steps 版） | `models/model_patches` | ModelPatchLoader + ZImageFunControlnet 节点 |

显存与内存：模型 12GB + 文本编码器 8GB + VAE 0.3GB；RAM 32GB 足够。显存占用（ComfyUI 实测）：1024×1024 = 0.4GB，2048×2048 = 1.6GB。量化：fp8_scaled（RTX40 系省 >50%）、`nunchaku` int4/nvfp4（约 2 倍速度，**不可用 LoRA**）、`DFloat11`（省 30% 内存，速度可能降）。加速：SageAttention 15–25%，配 TorchCompile 合计约 30%。

## 3. 解像度与稳定边界

学习解像度 512–1536 是稳定区；超 1536 局部不稳、超 2K 近乎破绽（要 4MP 建议先出 1–2MP 再 upscale）。常用档位：1MP=1024×1024、1.5MP=1280×1280、2MP=1472×1472、4MP=2048×2048。图生图输入实用默认=**长边 1024**（太小细节糊，太大只多花带宽）。细节增强四法：步数提到 ≥9、提分辨率、加 `ModelSamplingAuraFlow` 的 shift、换更好的 VAE。

## 4. ComfyUI 图生图省时法与 denoise 语义

- 图生图的关键是 **KSampler 的 `denoise` 必须 < 1**（=1 等于完全重画，参考图只剩极弱影响）。
- 省时技巧：`steps = 目标步数 × denoise`。denoise=0.5 时把 steps 设 10，采样的正是 20 步运行的后半段 sigma 序列，模型评估次数减半。
- Turbo 提高步数会引入噪点；步数超默认值收益递减，只在出现条带时加。

## 5. 三大失败模式与修法（社区实测）

| 症状 | 根因 | 修法 |
|---|---|---|
| **风格漂移**（手与文字先崩） | 强度 >0.55 + 描述性长提示词，模型转去「渲染形容词」而非「重诠释源图」 | 降强度 + 砍形容词 + 提输入分辨率；跑偏时降 0.1 常恢复优雅，继续加词只会更糟 |
| **纹理膨胀**（麻点阴影、条带） | `grainy / gritty / distressed / filmic` 类词叠加 | 只选一个纹理家族、写短；出现条带才加步数 |
| **脸部恐怖谷**（同套图人脸互像表亲） | 强度偏高 + 换 seed | 锁 seed、强度压 0.35 以下、必要时做只针对脸的轻修 |
| 小特征读错（接口、缝线、倒角） | 强度 0.6–0.8 弱引导下参考图被当建议 | 文字里显式强调，或给更高分辨率参考图 |
| 复利偏置（风格固化） | 连续把上一张输出当下一张参考图 | 定期回到原始图或中性底图 |

定位方法 = **3×2 测试网格**：固定 seed / 采样器 / 分辨率 + 极短提示词，跑强度 0.22 / 0.34 / 0.48 × CFG 5 / 7 六格；选中格后只在格内改一个词；文件名标 `strength-CFG` 便于复现。约 12–15 分钟/概念。迭代纪律：一次只改一个变量；调参期锁 seed，定稿后放开；存档三件套=参考图 + 提示词 + 强度数字。

## 6. 手部与持物（已知薄弱点）

握持物、枪械类的手部易崩，社区实测「需要很多轮才能出一个好的」。约定：**握持物一律单独跑**，不要混在批量生成里；崩手先降强度，再调 guidance，最后才上局部重绘。

## 7. 训练口径（要给本模型训 LoRA 时）

- 训 LoRA 用 **Base**（`ai-toolkit`、`musubi-tuner`，VRAM 8GB 可行，4 步出图做验证）。
- 训 **Turbo 必须**套 `ostris/zimage_turbo_training_adapter`（差分学习只学概念、保蒸馏能力；追加学习越多画越劣）。去蒸后的 base 为 `ostris/Z-Image-De-Turbo`。
- 社区衍生模型：TwinFlow-Z-Image-Turbo（2 步）、NitroFusion2（1 步）、fullgreed（写实）、量化版 lightx2v / Kijai fp8_scaled / jayn7 GGUF。
- 提示词增强：可用 LLM 按结构化模板改写，或现成 PE 模型 `BennyDaBall/qwen3-4b-Z-Image-Engineer`。

## 8. 出图后的验收（接本机链路）

- 图生图产物先做**逐像素质检**：100% 放大检查身份、轮廓、文字、材质四项；记住新增的皮肤细节（毛孔）是模型合成，不是还原真实细节。
- 若产物进视频链路（定妆图/分镜图），出片后按用户级硬约束逐帧检查：抽帧密度 ≥8 fps、分两张图看，判据四项＝表情是否贯穿、背景是否稳定、人物是否漂移换脸、台词口型是否对得上；发现问题不询问直接返修。
- 未点名的生成参数不得擅自改动；单段生成时长 ≤8 秒。
