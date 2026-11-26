# 负向词库（源 §5 §7 逐字）

> 来源：规范 §5 行 50–53、§7 行 69–82（§6 生成流程行 57–65、§8 质量门禁行 86–95）。

## 核心负向模板

```text
crash, accident, smoke, fire, explosion, wreckage, blood, horror, distorted figure, deformed hands, extra limbs, low resolution, blurry, overexposed, cartoon style, text, watermark, logo, {scene-specific negatives}.
```

## 通用负向词（必须保留，整串照抄）

```text
crash, accident, smoke, fire, explosion, wreckage, blood, horror, distorted figure, deformed hands, extra limbs, low resolution, blurry, overexposed, cartoon style, text, watermark, logo
```

18 项（源行 52 与行 72 两处完全一致），逐项都是质量门禁第 4 条的检查对象；不许因「本场景不涉及」而删项。

## 场景特定负向词（按场景追加）

| 场景 | 追加词 |
|---|---|
| 室内 | `messy cables, broken furniture, dark corners, cluttered background` |
| 户外 | `dangerous traffic, collapsed structures, heavy smoke, unsafe crowd` |
| 人物 | `twisted fingers, asymmetric eyes, bad anatomy, floating limbs` |
| 产品 | `deformed product, broken packaging, wrong text, duplicate object` |
| 建筑 | `leaning walls, cracked structure, unsafe scaffolding` |

场景可叠加（室内人物 → 室内组 + 人物组）。生成流程第 5 步给的推导示例：室内补「杂乱电线、破损家具、烟雾、明火」；户外补「危险交通、坍塌结构、浓烟」；产品补「变形产品、错误文字、破损包装」。

**组内可取舍（源示例口径，行 134）**：源示例是室内摄影工作室场景，室内组 4 项只取了 3 项 —— `messy cables, broken furniture, cluttered background`，**省略 `dark corners`**；人物组整组未追加。「追加场景特定 negatives」因此不要求整组全上：与正向内容（已声明补光灯、主体居中构图等）明显冗余的项可以省。通用段 18 项一项都不能少 —— 源示例共 23 项 = 通用 18 + 室内 3 + 道具变形 2，已逐项比对。

## 冲突检查（源 §7 注意事项）

场景负向词不能与正向主体冲突，例如正向需要「相机」时，负向不要写 `camera`。

操作口径：

- 负向词表里**不得出现**正向提示词中已声明的主体与必要道具的裸名词；
- 需要约束该道具时写成**变形 / 重复**类词（`deformed camera`、`duplicate tripod`），不写 `camera`、`tripod`；
- 检查方式：把正向提示词里出现的道具名词逐个在负向串里做字面检索，命中即改。

示例成品（见 `references/output-and-example.md`）里可见这条规则的实际执行：正向有相机与三脚架，负向串内 `camera` / `tripod` 只以 `deformed camera` / `duplicate tripod` 的形式出现，没有裸词项。

## MOSS-Image 条件门禁（2026-11-20 增补）

官方依据：MOSS-Image 官方负面 tag 只有 5 项 `nsfw, worst quality, bad anatomy, watermark, jpeg artifact`，不含 `text`、不含 `cartoon`；官方示例中玻璃板长文字那条只用 `worst quality, bad anatomy`，冰箱便利贴那条负面留空。故本技能的两项在 MOSS-Image 目标下属于自伤项：

| 触发条件 | 动作 | 理由 |
|---|---|---|
| 正向含要渲染的可见文字（引号逐字给出） | 负向串**删 `text`**；正向文字清单末尾补 `with no other text` | 负向 `text` 会封掉文字渲染，而文字渲染正是 MOSS-Image 主打能力（海报 / 信息图 / 带字插画 / 漫画分镜）；多余文字靠正向收口，负向管不住 |
| 正向目标风格为动漫 / 卡通 / 插画 / 海报设计 | 负向串**删 `cartoon style`** | 负向 `cartoon style` 会封掉动漫与插画风格 |

纪律：

1. 门禁只删这两项、只在触发时删，其余 16 项与 `watermark`、`logo` 一律保留，不得借门禁删其它项。
2. 触发时在 `warnings` 记一行「负向已删 X 项 + 原因」。
3. 门禁只作用于本技能产出的负向串，不修改源规范 `assets/source-moss-prompt-composer.txt` 的原文。
4. 质量门禁对应新增三条：正向有引号文字 → 负向无裸 `text` 且正向已补 `with no other text`；正向为动漫/插画 → 负向无 `cartoon style`；海报/信息图类 → 已给 `canvas_size` 与 `layout_json`（见 `references/layout-draft.md`）。
