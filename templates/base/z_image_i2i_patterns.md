# Z-Image 图生图逐字句式库

用途：组装时直接取句式，不要临场发明抽象形容词。所有英文串为社区逐字验证过的写法（来源：共绩算力 16 例、awesome-z-image-turbo 案例库、圆圈网转绘章节、MindCraft 正向化排除句）。

## 1. 核心三句公式（最高优先，逐字）

```text
keep the desk angle and daylight; replace mug with glass tumbler; add plant, shallow depth of field
```

= `保留项 ; 替换项 ; 新增项`。中强度 + 显式保留项 > 形容词堆砌。团队交付要存三件套：参考图 + 提示词 + 强度数字。

## 2. 风格转绘四型（正向只写目标风格，负向写不要留下的风格）

| 转换 | 正向逐字 |
|---|---|
| 照片 → 动漫 | `anime style, cel shading, clean lineart, vibrant, masterpiece` |
| 照片 → 油画 | `oil painting, thick brushstrokes, canvas texture, artstation` |
| 线稿 → 上色 | `anime color, flat color, shading, high quality illustration` |
| 日景 → 夜景 | `night scene, moonlight, dark sky, cinematic lighting` |

通用负向：`photo, realistic, 3d render, blurry, low quality, watermark`。
案例级写法（照片转吉卜力）：`anime screenshot, studio ghibli style, soft lighting, detailed eyes`，负向 `photo, realistic, nose, 3d`；脸仍太写实 → 加 LoRA 或略升 denoise。
整图风格声明句（文生图与转绘通用）：`Ghibli style illustration, ... , Studio Ghibli aesthetic, warm and nostalgic color palette, soft lighting, hand-painted texture, peaceful and dreamlike atmosphere, high quality, masterpiece`，负向 `realistic, photograph, 3d render, blurry, lowres, bad anatomy, extra fingers, watermark, text, worst quality`。

## 3. 洗图与二次洗模板

```text
正向：masterpiece, best quality, highly detailed, sharp focus, <一行原主题简述>
负向：low quality, blurry, jpeg artifacts, bad anatomy, watermark, text
```

原主题简述一行即可（`1girl, portrait, outdoor`），写太长会覆盖洗图效果。二次洗第二遍只用质量词。

## 4. 变换动词句族（Turbo 案例库范式——Turbo 无负向可用，指令全靠正向）

```text
Redraw this photo in Ghibli style
Turn this photo into a bobblehead: enlarge the head slightly, keep the face accurate and cartoonify the body. [Place it on a bookshelf]
Transform the characters in the scene into 3D chibi-style figures, while keeping the original scene layout and their clothing exactly the same.
Transform the person in the photo into a One Piece-themed anime-style action figure, presented inside a collectible figure box ... The box is shown in an isometric view. ... Next to the box, include a realistic, fully rendered version of the actual figure itself, outside the packaging.
Generate an anime-style figure photo placed on a desktop, presented from a casual, everyday snapshot perspective as if taken with a mobile phone. The figure model is based on the attached character photo, accurately reproducing the full body posture, facial expression, and clothing style of the person in the photo.
Create a finely crafted 3D-rendered collectible figure based on the subjects in the photo, displayed inside a pastel-toned presentation box. The lid is engraved with the words "FOREVER TOGETHER" ... Aspect ratio: 9:16
```

规律提炼：

- 变换动词开头（`Redraw / Turn ... into / Transform ... into / Create ... based on the subjects in the photo`）。
- 需要身份保真时**逐字要求复述参考图的身份要素**（full body posture, facial expression, clothing style）。
- 构图要保就在同一句里写 `while keeping the original scene layout and their clothing exactly the same`。
- 案例库多数条目自带 `Reference Image Required:` 说明要什么样的参考图（半身照/全身照/情侣照/要求露出姿态与服装）——写提示词时把这条要求一并交给用户。
- 混合精度（社区高分常用）：人物 `chibi 3D style` + 环境 `realistic and photorealistic`；服装与头饰用写实材质词逐件写（`red changpao and magua embroidered with golden dragon motifs`、`phoenix crown ... hanging tassels`），人物保持 Q 版。

## 5. 材质与形态转换模板（万能开头）

```text
Transform [X] into a soft 3D object with silk texture. The entire surface is wrapped in smooth flowing silk fabric, featuring surreal wrinkle details, soft highlights and shadows. ... Studio lighting, high-resolution rendering, centered composition.
```
负向排除原始材质防回退：`realistic flower`。

毛茸茸转换：`Transform a simple cat face icon into a soft, 3D fluffy object. The cat shape is fully covered in hyperrealistic fur with orange tabby pattern, soft shadows and ambient occlusion.` 负向排除 `flat, 2d`。

Emoji 食品化：`Transform the strawberry emoji into a creamy ice cream bar ... floating at a 45-degree angle in mid-air, rendered in a cute chibi-style 3D aesthetic. Solid pink gradient background with unified pastel color palette.`

双重曝光公式：`[动物/人物] silhouette + [风景] landscape`，并写风景如何从轮廓中延伸（`echo outward through the fabric of the figure`），背景保持单色（`stark monochrome background maintains razor-sharp contrast`）。

微缩与摄影感：`tilt-shift effect, isometric view`；第一人称俯视 `top-down photograph ... with the lid held open by two human hands`；3D 打印材质 `matte 3D-printed textures with visible layer lines`。

风格一致性强化：逐名词挂风格前缀（`LEGO buildings / LEGO minifigures / LEGO bricks / LEGO palm trees`），负向排除 `realistic, photograph`；水面写法 `translucent blue LEGO bricks`。

电商白底：`E-commerce product photography on pure white background ... Soft studio lighting from above, minimal shadows ... slightly angled to show both ear cups and the headband ... High-key lighting, centered composition with generous white space`；负向 `text, watermark, logo, cluttered background, harsh shadows, blurry, lowres, jpeg artifacts, worst quality`。

海报模板：`[城市] [国家] colourful summer vector art poster with big bold 'TOKYO' title at the top and smaller 'JAPAN' text below ... Retro travel poster aesthetic, warm sunset color palette ... vintage print texture`；地标逐名列出保识别度。

电影感人像（转绘目标风格用）：`soft Rembrandt lighting from the side illuminating her cheekbone and nose bridge ... extremely shallow depth of field with only the eye to nose tip in sharp focus ... Navy blue and warm brown as main color tones`；负向 `bright background, cartoon, anime, blurry, lowres, extra fingers, bad hands, watermark, text, logo, worst quality`。

## 6. 排除项正向化（Turbo 专用，写进正向串）

```text
no text, no watermark, no branding, no logos
plain background, simple clean backdrop, not cluttered
correct human anatomy, natural hands and fingers, no extra limbs
no motion blur, sharp focus, no grainy noise
```

## 7. 文字渲染四条（双语字是 Z-Image 强项）

1. 要渲染的文字用**英文双引号逐字包裹**（`big bold 'TOKYO' title`、`the words "FOREVER TOGETHER"`）。
2. 同一文字块不要中英混用。
3. 指定位置与字体样式（`at the top`、`in bold all-caps modern sans-serif pure black font`、`letters obscured by the frosted glass appear with a gentle Gaussian blur`）。
4. 末尾加抑制乱码的语句；转绘带原图文字的图时在负向里不要裸写 `text`（会连想要的字一起压掉）。

## 8. 口径类冷知识（写提示词时可用）

- 中国语角色名有效（芙宁娜 / 五条悟 / 雷姆 / 炭治郎）；英语角色与艺术家姓名多不识别。
- 颜文字直接做表情逐字有效：`a girl making this face "X.X"`。
- 六类必写项（决定画面质量）：位置关系 / 视线 / 感情 / 空气感 / 质感 / 動き。
- 多主体、多气泡、分区构图用 markdown 结构化写法（`# composition` / `## left` / `## middle` / `## right`）；散文式「画面右侧有个人」会被无视。
- 提示词结构公式：`[风格声明] + [主体描述] + [动作/状态] + [环境/背景] + [光影/氛围] + [技术参数/质量标签]`。
- 十大黄金法则摘要：① 第一句声明风格 ② 具体胜过笼统（`matte black finish with rose gold accents` 而非 `beautiful headphones`）③ 材质分层描述 ④ 光影是灵魂（`Rembrandt lighting / golden hour / Tyndall effect`）⑤ 控制构图（`isometric view / centered composition / top-down / 45-degree angle`）⑥ 善用对比（Q 版人物 + 写实环境、单色背景 + 彩色主体）⑦ 质量标签收尾（`high quality, masterpiece, 8k resolution, ultra-fine details`）⑧ 负向精准（做插画就排除 `realistic, photograph`）⑨ 留白（`generous white space, clean background, negative space`）⑩ 用 `[占位符]` 标记可替换部分，一套提示词适配多场景。
