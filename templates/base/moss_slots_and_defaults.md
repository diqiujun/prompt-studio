# 槽位与默认值（源 §1–§3 逐字）

> 来源：`moss-image-prompt-composer` 规范（源全文在 `assets/source-moss-prompt-composer.txt`，共 137 行）：§1 行 3–11、§2 行 15–21、§3 行 25–41。

## 技能定位（源 §1）

把用户的自然语言图像需求，转换成符合 `moss-image` 模板的 **Positive Prompt + Negative Prompt**，并保证：

- 正向提示词严格覆盖模板槽位；
- 明确「安全 / 稳定状态」；
- 自动补充场景特定负向词；
- 对危险、事故、血腥、畸形等负向约束做质量门禁；
- 输出可直接用于图像生成的提示词与参数说明。

该 Skill 不直接生成图片，只生成 / 校验提示词。

## 触发条件（源 §2）

当用户提出以下需求时触发：

- 「按 moss-image 模板写提示词」
- 「生成正负提示词」
- 「把这个场景转成 image prompt」
- 「补全 negative prompt / 场景负向词」
- 提供主体、动作、场景、服装、表情等图像描述，要求结构化输出

## 输入槽位（源 §3 全表）

| 槽位 | 必填 | 说明 | 缺失处理 |
|---|---|---|---|
| `subject` | 是 | 主体，如人物、动物、产品 | 追问或使用保守默认「单人主体」 |
| `action/pose` | 是 | 动作 / 姿态 | 补「自然站立 / 稳定操作」 |
| `scene/location` | 是 | 室内 / 室外 / 具体地点 | 补「整洁安全的室内环境」 |
| `outfit` | 是 | 服装 / 装备 | 补「简洁合身服装」 |
| `expression/emotion` | 是 | 表情 / 情绪 | 补「平静、专注」 |
| `safe/stable state` | 是 | 安全稳定状态 | 必须显式写明，如「环境安全、设备稳定、无危险动作」 |
| `key visible details` | 是 | 道具 / 设备 / 环境元素 | 补 2–4 个低风险元素 |
| `composition/shot type` | 是 | 构图 / 景别 | 默认「中景，主体居中构图」 |
| `lighting` | 是 | 光照 | 默认「柔和自然光」 |
| `photography/art style` | 是 | 摄影 / 艺术风格 | 默认「写实摄影风格」 |
| `high detail, 8K quality` | 固定 | 质量词 | 保留 |
| `depth of field` | 是 | 景深 | 默认「浅景深」 |
| `color style` | 是 | 色彩风格 | 默认「自然低饱和」 |
| `scene-specific negatives` | 是 | 场景特定负向词 | 由 Skill 自动推导 |

槽位名与输出 JSON 的键名对应关系（正向模板用斜杠名，JSON 用下划线名）：`action/pose` → `action_pose`、`scene/location` → `scene_location`、`safe/stable state` → `safe_stable_state`、`key visible details` → `key_visible_details`、`composition/shot type` → `composition_shot_type`、`photography/art style` → `art_style`、`depth of field` → `depth_of_field`、`color style` → `color_style`。
