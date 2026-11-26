# PromptStudio 提示词工作室

**发布者：minut　版本：1.1**

> 仓库：https://github.com/diqiujun/prompt-studio ｜ 下载安装包：[Releases](https://github.com/diqiujun/prompt-studio/releases)

一句话需求 → 自动改写成各类模型的规范提示词；内置官方规范全文，支持中英互译。
桌面程序，双击即用：原生窗口 + 内置本地模型（免 key、免联网也能跑），整个目录拷到别的 Windows 电脑上直接可用。

---

## 一、启动


**推荐（绿色安装）**：把整个 `dist\PromptStudio\` 目录拷到目标电脑任意位置，双击里面的 `PromptStudio.exe`。

- 先出现启动页，依次完成：启动内核 → 打开界面 → 加载本地模型（首次 10–40 秒，启动页上有进度）。
- 界面在原生窗口里（内嵌 Chromium 渲染），**不再弹浏览器**。关窗口即退出，程序会把自己拉起的本地模型一并关掉，不留后台进程。
- 状态栏常驻三段：本地模型状态（`● 运行中（pid xxxx）`/`○ 未启动`）、显卡与调参说明、实际端口。
- 想用浏览器打开也行，地址就是状态栏那个 `http://127.0.0.1:<端口>/`（端口被占用会自动往后顺延）。
- 菜单 **视图** 可刷新界面 / 缩放；**帮助** 可打开数据目录、本地模型日志。

首次启动会在 exe 同目录生成 `data\`：`config.json`（配置）、`history.json`（历史）、`llama.log`（本地模型日志）、`webprofile\`+`webcache\`（窗口缓存）、`run.log`（启动日志）。

> 只要 `llama\` 与 `models\` 两个目录跟着 exe 一起拷，换电脑不用装 Python、不用装 CUDA：
> 程序会按目标机器自动调参——8 GB 显存及以上全量放 GPU，4–8 GB 少放几层，没有 NVIDIA 卡就直接 CPU 跑（慢但能用）。

### 只有一个 exe 的形态（已废弃）
早期 `dist\PromptStudio.exe` 单文件版（约 48 MB、不含模型）已删除：它每次启动要把自身解包到临时目录，受限环境会报
`[PYI-xxxx:ERROR] Failed to create parent directory structure.`。现在要「单文件」请用安装包（见第十二节：`PromptStudio-Setup-1.1.exe` + 同目录 `payload.zip`）。

---

## 二、配置模型服务（设置页）


设置页 → 模型服务 → 填四项即可（预设可一键填入再改）：

| 字段 | 说明 | 举例 |
|---|---|---|
| 名称 | 自己起的名字 | DeepSeek |
| Base URL | OpenAI 兼容地址，末尾 `/v1` 可省 | `https://api.deepseek.com/v1` |
| 模型名 | 必须与 `/v1/models` 里的一字不差 | `deepseek-chat` |
| API Key | 云端必填；本地服务通常填 `local` 或留空 | `sk-xxxx` |
| max_tokens / temperature | 生成上限与温度 | 8000 / 0.6 |
| 额外参数 JSON | 原样并入请求，平台私有参数写这里 | `{"thinking":{"type":"disabled"}}` |
| 支持图片 | 该服务能否看图。**图生图类模板必须勾选**，否则上传的图不会发送 | ✓ |

内置预设：DeepSeek / LM Studio / Ollama / vLLM / OpenAI / 阿里 DashScope。本地模型（LM Studio `http://127.0.0.1:1234/v1`、Ollama `http://127.0.0.1:11434/v1`）可直接用预设，改模型名即可。

配置完点「测试连接」，绿了再「保存」→「设为当前」。可以保存多家，顶部下拉随时切换。

### 内置本地模型（免 key，开箱即用）

程序自带一套 llama.cpp 托管：设置页 → **本地模型** 卡片里填三个模型文件路径（每个路径右边有「浏览…」，点开直接选目录 / 选 .gguf，也能把路径粘进去），程序会自己拉起 `llama-server`，并在「模型服务」里自动登记一家 `本机模型 · gemma-4-e2b（内置）`。
- **路径都归你选**：llama.cpp 目录、主模型、视觉投影、MTP 草稿四处都能点「浏览…」自己挑——换别的 llama.cpp 版本、换别的 gguf 模型都行；选完记得点「保存设置」再「启动本地模型」。

| 项 | 默认值 | 说明 |
|---|---|---|
| llama 目录 | `E:\llama` | 里面要有 `llama-server.exe` 及其 dll |
| 主模型 | `...\gemma-4-e2b\gemma-4-E2B-it-Q4_K_M.gguf` | 2.96 GB，文本 + 看图（思考型模型） |
| 视觉投影 | `...\gemma-4-e2b\mmproj-F16.gguf` | 940 MB，图生图模板必须靠它看图 |
| MTP 解码层 | `...\gemma-4-e2b\mtp-gemma-4-E2B-it.gguf` | 93 MB，投机解码草稿模型；**默认关闭**（见下） |
| 端口 / 上下文 / GPU 层 | `8910` / `32768` / `99` | 显存不够时把 GPU 层调小 |

- **自动启动**：勾着「启动程序时自动拉起本地模型」，打开 exe 就会加载；状态显示 `● 运行中 · 端口 8910 · pid xxxx`。
- **用时加载、生成完自动卸载（省显存）**：勾上这一项后程序启动时**不常驻**，第一次点「生成提示词」才拉起模型，生成结束立刻关掉、把显存还给系统（约 10 GB）；状态显示 `按需加载`。实测一次「加载＋生成＋卸载」约 8 秒，比常驻多 5–6 秒，但平时不占显存；自己手动点「启动」的服务程序不会替你关。
- **不用自动**：取消勾选，需要时点「启动」。首次加载约 5–20 秒（进度看 `data\llama.log`）。
- **退出即关**：程序退出时会把自己拉起的 llama-server 一起关掉；手动开的服务不会被误杀。
- **MTP 为什么默认关**：当前 llama.cpp 版本下用 `--spec-type draft-mtp` 加载这套组合会在加载完瞬间静默退出（日志停在 KV cache sharing 那行）。所以代码里做了「失败自动回退」——勾了 MTP 但起不来时会自动去掉 MTP 重试一次。
- **思考型模型**：gemma-4-e2b 会先输出 `reasoning_content`（英文思考），`content` 才是答案。程序已优先取 `content`；`max_tokens` 建议 ≥ 3000，给少了会被思考占满、返回空。
- 用本地模型时，图生图模板记得该 provider 的「支持图片」是勾上的（内置登记时已勾）。
- **H3 格式自动补齐**：本地 4B 模型偶尔会把台词写成「他开口说“都让开”」而漏掉 `<d>[Chinese] 都让开</d>`，或漏 `[Shot 1]` 时间码。程序在 h3_video 出稿后会自动自检一次，缺哪项就用低温再修一次格式（不改写内容），修完在输出下方的提示里写明「已自动补齐格式：…」。云端大模型基本不会触发。

---

## 三、撰写提示词（第一个标签页）


顶部选目标模型，下面填内容 → 「生成提示词」（Ctrl+Enter）。

**MiniMax H3 视频**（T2VA / I2VA / FL2VA / L2VA / Ref2VA）
- 模式选 auto 时程序按图片数量自动判定：0 图 T2VA、1 图 I2VA、2 图 FL2VA、≥3 图 Ref2VA。
- 「上一段结尾状态」用于链式续写：把上一段成片最后一帧的状态写成一句话填进去，本段开场就会接得上（程序会强制写独立成立、禁写「承接上一段」）。
- 内置规范包括：六段字段规范、否定式闸门、参考图片角色规则、微表情写法、运镜与 LoRA 规则、书写顺序。
- 输出含【模式判定】、六段字段、【生成参数建议】、【提交前须知】。

**Qwen Image 2.1 图生图**（必须上传原图）
- 官方 PE 全文逐字内置，输出 JSON：`rewritten_prompt` / `wh_ratio` / `ratio_follow`。
- 多图时给每张图写角色（画布图·被编辑的底图 / 身份来源 / 服装参考 …），其中「画布图」指定写进参数。
- 比例参数留空即按官方规则自行判定；可写 `9:16`、`2:3`、`1920x1080`、`扩宽 20%`。

**moss-image 文生图**
- 输出 JSON：`positive_prompt` / `negative_prompt` / `slots` / `scene_specific_negatives` / `canvas_size` / `sampling_profile`。
- 通用负向词整串照抄不截断，场景特定负向词按场景关键词自动推导。

**Z-Image Turbo 文生图 / Z-Image 图生图**
- Turbo 原生中文七模块结构、权重语法、东方色名与材质术语库。
- 图生图：改造类型（洗图提质/风格转绘/局部修改/扩图/材质变换/人物转Q版手办…）+ 强度档位表内置，强制「保留项 + 替换项 + 新增项」句式。强度参数留空即自动选档。

**画幅**：moss / Z-Image 两个模板的画幅是自由填写，任意 `宽x高` 都能写（如 `1120x1472`），建议值在下拉里。Z-Image 图生图的输出尺寸留空即跟随原图。

**参考图**：拖拽 / 点击 / Ctrl+V 粘贴。每张图下面选角色。图会被压到长边 1568 以内再发送。
**@ 引用某张图**：传图后输入框里打 `@`，弹出图清单（↑↓ 选、Enter 插入、Esc 关闭），选中的会写成 `@图1`；生成时自动转成官方要求的 `<image1>` 引用。输入框下方也有「可 @ 引用」小标签，点一下即插入。模板不要图时，`@图N` 会原样保留、不会瞎写。
**界面外观**：右上角 `☾ 深色 / ☀ 浅色` 一键切换，选择记在本地，下次打开还是上次那套；滚动条、选中高亮、卡片阴影都跟着主题走，窗口顶部的「视图 / 帮助」菜单栏与底部状态栏（本地模型 · 显卡 · 地址）也随之换色（约 4 秒内自动跟随，无需重启）。
**快速模式**（顶部开关）：精简注入内容，省 token；需要完整规范时关掉。
**再改一版**：把上一版结果和修改意见一起喂回去迭代。

---

## 四、翻译（第二个标签页）


方向：中→英 / 英→中 / 自动 / 保留原文附译文。
语气：直译准确 / 自然口语 / 正式书面 / 本地化润色。
上下文：填这段的用途（如「视频脚本旁白」「商品详情页」）。
**术语表**：一行一条，如 `人元丹=Renshen Pill`，术语强制统一，译文照用。
「译文→原文」按钮把译文回填成原文再翻回去，用来核对。

**提示词翻译**模板：把中文提示词译成英文提示词（或反向），规则是画面内容翻译成英文，
而标签、占位符、字段名、镜头术语、时间码原样保留（如 `<Subject 1>`、`[Shot 2]`、`<d>[Chinese] 台词</d>` 里的标签不动，台词内容翻译）。

---

## 五、自定义模型（提示词撰写页「＋ 添加模型」）


内置模板之外，你可以让软件写任意模型的提示词（FLUX、SDXL、即梦、可灵……），不用改代码：

1. 打开「提示词撰写」，模板卡片末尾点「＋ 添加模型」；
2. 填 **模型名称**（如 `FLUX.1 文生图`）、一句话简介；
3. **规范正文**是核心：把你对这类模型写提示词的要求写清楚（语言、句式、顺序、光线写法、负面清单、禁止反问等）；
4. 参数可留空；需要的话每行一个：`标签|类型|默认值|选项1,选项2`（类型：select / number / text / textarea / canvas）；
5. 保存后它就和内置模板一样出现在列表里，选中它、用大白话说需求、点「生成提示词」；
6. 卡片右上角「编辑 / 删除」随时改；数据存在 `data\custom_templates.json`，不起作用就删这个文件。

写作建议：规范正文写「可执行的要求」，别写「要好看」。例：
`英文单段长句，不分点；顺序 主体→动作→环境→光线→材质→构图→镜头→风格；光线写光位；末尾一行 negatives: 负面清单；不要反问用户。`

## 六、@ 引用参考图


上传图片后，输入框下方会列出「可 @ 引用」的图片；输入 `@` 会弹出带缩略图的列表，
↑↓ 选择、Enter 插入（写成 `@图1`），发送时会自动转成模型认识的 `<image1>`。

## 七、提示词规范管理（设置页底部）


界面上不再显示注入量/规范体积（按要求已去掉，普通用户看不到）。规范可以自己改：

- 每条内置规范组件都有开关：关掉就不注入这个模板的系统提示词。
- 「编辑替换」：把某条内置规范换成你自己的内容；「恢复内置」一键还原官方原文。
- 「＋ 添加自定义规范」：写一份你自己的规范，注入到该模板系统提示词的末尾，并声明「优先级高于上方内置规范，冲突时以本节为准」。
- 「全部恢复默认」清掉所有改动。

改动写进 `data\config.json` 的 `specs` 段，不碰 `templates\` 里的官方原文文件。

示例：把 `MOSS-Image 官方规范` 关掉、只留槽位表与模板；给 `MiniMax H3 视频` 加一条自己的「打斗密度：5 秒片段动作 3–5 个」自定义规范；把 `Z-Image 图生图 · 强度档位表` 替换成你自己的实测档位。

---

## 八、插件（把自己的提示词玩法塞进软件）


程序目录下有个 `plugins\` 文件夹。往里丢插件，界面的「提示词撰写」页就会多出一张模型卡片，点开即用——不用改代码、不用重装。

最小插件 = 一个文件夹 + 一份 `plugin.json` + 一份规范正文（`spec.md`）：

```
plugins\
  my_plugin\
    plugin.json
    spec.md
```

`plugin.json` 示例：

```json
{
  "id": "my_plugin",
  "name": "我的产品图提示词",
  "tagline": "一键出电商主图描述",
  "author": "我",
  "version": "1.0",
  "intro": "你是电商视觉提示词引擎，输出可直接投喂生图模型的单段描述。",
  "params": [
    { "key": "style", "label": "风格", "type": "select", "options": ["干净白底", "生活方式", "暗调质感"], "default": "干净白底" },
    { "key": "canvas", "label": "画幅（自由填写 WxH）", "type": "canvas", "default": "1024x1024" }
  ],
  "examples": ["一罐咖啡粉，木质台面，晨光斜打"],
  "enabled": true
}
```

- `spec.md` 是你的规范正文（写法要求、输出结构、负面清单都写这里），会整段注入系统提示词。
- `params` 支持 `select / number / text / textarea / canvas`，其中 `canvas` 是自由填 `WxH`。
- 参考图：模板需要图时按 `min_images / max_images` 校验，图片会以 `<image1>`、`<image2>` 编号发给模型，提示词里可以 `@图1` 引用（会自动换成 `<image1>`）。
- 设置页「插件」卡片里可以：**重新加载**（改完文件不用重启）、**安装插件 (zip)**、**打开插件文件夹**、逐条**启用/停用**、**删除**，改错了会在设置页红字报错且不影响其它插件。
- 发行目录里自带两个示例：`sample_generic`（模板插件）与 `sample_tools`（代码插件），照着改最快。

### 代码插件（能加按钮、设置项、后端接口）

除了模板插件，插件还可以带一个 `plugin.py`，在软件里注册**工具按钮**、**设置项**与**接口**——和 DSH 那种插件一个思路，只是规模更小：

```jsonc
{
  "id": "sample_tools", "name": "示例代码插件", "version": "1.0.0",
  "entry": "plugin.py",                       // 代码入口，默认就是这个
  "settings": [                               // 插件自己的设置项（界面自动生成表单）
    { "key": "strip_blank", "type": "checkbox", "label": "去掉多余空行", "default": true },
    { "key": "prefix", "type": "text", "label": "整理后的提示前缀" }
  ]
}
```

```python
# plugin.py —— 软件加载时调用 register(ctx)
def register(ctx):
    @ctx.tool("tidy", "整理文本", where="toolbar")        # 撰写页/结果区出现一个工具按钮
    def tidy(text, p):                                     # p = {settings, params, template, images}
        lines = [ln.rstrip() for ln in (text or "").splitlines()]
        out = "\n".join(lines)
        pre = p["settings"].get("prefix") or ""
        return {"text": (pre + "\n" + out) if pre else out, "note": "已整理"}

    @ctx.route("stats", ["GET", "POST"])                   # 挂到 /api/plugin/<id>/stats
    def stats(body, query):
        t = (body or {}).get("text") or ""
        return {"ok": True, "chars": len(t), "lines": len(t.splitlines())}

    @ctx.on("generate.after")                              # 生成出稿后改写结果
    def after(payload):
        if not ctx.get("append_note"):
            return None
        return payload["output"].rstrip() + "\n\n（由插件整理）"
```

- **信任门**：代码插件第一次不会自动执行，设置页点「信任并加载」后才运行；随时可以「取消信任」。判断依据存在 `data\config.json` 的 `plugin_trust`，**不会改动你的插件文件**。
- `ctx` 上可用的东西：`ctx.log(msg)`（写 `data\plugins.log`）、`ctx.get(key, default)`（读自己的设置）、`ctx.tool / ctx.route / ctx.on`（支持装饰器写法，也支持直接传函数）、`ctx.data_dir`（`data\plugins\<id>`，给你的插件存文件用）。
- 钩子目前支持 `generate.after`（payload：template / content / output / json / params / settings；返回字符串＝替换输出，返回 None＝不动）。
- 工具契约：`fn(text, params) -> str | {"text": ..., "note": ...}`；接口契约：`fn(body, query) -> dict`。

---

## 九、运行环境（自带 llama.cpp，按硬件自动适配）


程序自带 6 套 llama.cpp 预编译包（`runtime\packs\`，共约 1.04 GB），第一次启动时按你的机器自动挑一套解压到 `runtime\` 下：

| 你的机器 | 用哪个包 |
| --- | --- |
| NVIDIA，驱动支持 CUDA 13.x | `cuda-13.5-x64`（x64）／`cuda-13.5-arm64`（ARM） |
| NVIDIA，驱动只到 CUDA 12.x | `cuda-12.4-x64` |
| AMD 显卡（已装 ROCm） | `rocm-10.0-x64` |
| 没有独显／想稳一点 | `cpu-x64`／`cpu-arm64`（纯 CPU，慢但一定能跑） |

- 不用自己装 CUDA、也不用装 Python——包里就是编译好的 `llama-server.exe`。
- 设置页「运行环境」能看到检测结论（显卡型号 / 显存 / CUDA 版本 / 架构）、推荐包和已装包，也可以手动「重装」某一套。
- 换了显卡／换了机器：删掉 `runtime\` 下的包目录，重启程序会重新适配。
- 显存 8 GB 及以上可全量 GPU；4–8 GB 会自动少放层（也能跑）；没有 N 卡自动走 CPU。
- 只支持 Windows（x64 / ARM64）。Linux、macOS 不提供运行环境。
- 
## 十、常见问题


- **生成失败：HTTP 401 / 403**：Key 不对，或本地网关限流（governor）。稍等再试。
- **返回内容为空**：多半是模型名不存在、请求被拒、或服务要求流式返回。
- **图生图提示词质量差**：检查该模型服务是否勾选了「支持图片」。不勾选时程序只把图当编号占位，会明确告知模型不要臆想画面。
- **输出格式乱**：Qwen 与 moss 模板要求 JSON，程序会自动从围栏代码块里抽取；抽取失败时原文完整保留，可手工取用。
- **换电脑**：把 exe 所在目录整体拷走即可；`data\` 带着你的配置和历史。
- **本地模型生成完就不见了**：正常。设置页勾了「用时加载、生成完自动卸载」时，模型只在生成的那几秒活着，结束后显存就还给系统；把勾去掉就是常驻。
- **ComfyUI 插件认不出提示词在哪**：先在导入结果里看黄色提示；把「正向提示词」下拉改成 `1.timeline_data › segments[0].prompt` 这类复合节点路径再保存即可。
- **API Key 安全**：明文存在本机 `data\config.json`，界面只显示后 4 位，接口不返回明文。

## 十一、安装

两种形态，内容完全一样（程序 + 内置模型 + 6 套运行环境包，装完 6.07 GB / 7930 个文件）：

| 形态 | 位置 | 适合谁 |
| --- | --- | --- |
| 目录版（推荐） | `dist\PromptStudio-Setup-1.1\`（`PromptStudioSetup.exe` + `_internal\` + `payload.zip`） | 任何机器、任何路径都能跑；把整个文件夹拷给对方，双击 `PromptStudioSetup.exe` |
| 单文件版 | `dist\PromptStudio-Setup-1.1.exe`(45.6 MB) **＋** `dist\PromptStudio-Setup-1.1.payload.zip`(6.5 GB) | 想只发一个安装器时用；**两个文件必须放同一目录**（安装器会自动找同目录的 `*.payload.zip`），且**该目录路径不能含中文**（PyInstaller 解包器在中文路径下会报 `Could not create temporary directory!`） |

**安装位置可以自己选**：第一页「安装到」输入框直接改，或点「浏览…」选文件夹，或点下面的「常用：」快捷按钮一键跳到 C 盘用户目录 / D / E / F 盘。选中后下方会实时显示「安装包内容 / 需要空间 / 该磁盘可用」和目录校验结论：

- 目录不存在会自动创建；已经装过（目录里有 `PromptStudio.exe`）会提示「安装将覆盖（等于升级）」并要求确认。
- 路径不合法（没有盘符、含 `< > : " | ? *`、盘符不存在、是文件）或写不进去（典型是选到了 `C:\Program Files`）会红字提示并**禁用「开始安装」**，不会装到一半失败。
- 上次选过的目录会被记住（`%LOCALAPPDATA%\PromptStudio\setup_dir.txt`），下次打开默认就是它。

安装过程：选目录 → 勾选桌面快捷方式 / 开始菜单 / 装完启动 → 进度条 → 完成。安装器会写卸载信息到注册表，所以在「设置 → 应用」里能看到「提示词工作台 Prompt Studio」。

**静默安装**（批量部署、脚本调用）：

```bat
PromptStudioSetup.exe --silent --dir "D:\Tools\PromptStudio" --no-desktop --no-menu
```

`--no-desktop` 不建桌面快捷方式，`--no-menu` 不建开始菜单项，`--no-launch` 装完不启动。
装完目录里的 `卸载 PromptStudio.cmd` 可整体卸载（停进程 → 删快捷方式 → 删注册表项 → 删目录）。

重新构建安装包：`python build_installer.py --onedir`（目录版）或 `python build_installer.py`（单文件版），
前置条件是 `dist\PromptStudio\` 已由 `build_all.py` 生成；安装器本身不压缩（模型是高熵 gguf，deflate 只多花时间）。

**本仓库不包含**的两个自制插件：`plugins\pose_gallery`（姿势库）与 `plugins\comfy_runner`（ComfyUI 工作流）。要自己写插件，看 `plugins\PLUGIN_FORMAT.md`，或参考 `plugins\sample_generic`、`plugins\sample_tools`。



