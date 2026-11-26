"""提示词模板注册表：内置规范 + 拼装 system prompt。

规范正文直接内置本机已验证的官方/实测文档（templates/base/*.txt|md，逐字），
本模块只负责「角色与输出纪律前缀 + 按需注入规范组件 + 参数与参考图清单」。
"""
from __future__ import annotations

import json
import threading

import settings
import pluginlib

TPL_DIR = settings.resource_root() / "templates"
BASE_DIR = TPL_DIR / "base"

_cache: dict = {}
_local = threading.local()


def _specs() -> dict:
    """本轮生效的规范开关/替换/自定义规范状态。"""
    st = getattr(_local, "specs", None)
    if st is None:
        st = settings.load_specs()
        _local.specs = st
    return st


def _read(fname: str) -> str:
    """读内置规范正文；用户关闭则返回空串，用户写了替换文本则用用户的。"""
    ent = _specs()["files"].get(fname)
    if ent is not None:
        if not ent.get("enabled", True):
            return ""
        rep = (ent.get("replace") or "").strip()
        if rep:
            return rep
    return file_text(fname)


def file_text(fname: str) -> str:
    """内置规范原文（不受开关影响），供设置页查看。"""
    if fname in _cache:
        return _cache[fname]
    for p in (BASE_DIR / fname, TPL_DIR / fname):
        if p.exists():
            try:
                txt = p.read_text(encoding="utf-8").strip()
            except Exception:
                txt = ""
            _cache[fname] = txt
            return txt
    _cache[fname] = ""
    return ""


def effective_text(fname: str) -> str:
    """当前生效正文：用户替换文本优先，否则内置原文。"""
    ent = _specs()["files"].get(fname) or {}
    rep = (ent.get("replace") or "").strip()
    return rep if rep else file_text(fname)


# 每个模板注入了哪些内置规范组件（供设置页列出，用户可逐条启停/替换）
COMPONENTS = {
    "h3_video": [
        "h3_base.txt",
        "h3_ref.txt",
        "h3_negation_guard.md",
        "h3_reference_image_roles.md",
        "h3_micro_expression.md",
        "h3_writing_order.md",
        "h3_camera_and_lora.md",
    ],
    "qwen_i2i": ["qwen_image_2_1_i2i.txt"],
    "moss_t2i": [
        "moss_slots_and_defaults.md",
        "moss_template_positive.txt",
        "moss_template_negative.txt",
        "moss_negative_lexicon.md",
        "moss_template_output.txt",
        "moss_official_spec.md",
    ],
    "zt_t2i": ["z_image_turbo_skill.md"],
    "zi_i2i": [
        "z_image_i2i_skill.md",
        "z_image_i2i_strength_tiers.md",
        "z_image_i2i_patterns.md",
        "z_image_i2i_pitfalls.md",
    ],
    "tr_general": [],
    "tr_prompt": [],
}


def _extras_block(tid: str) -> str:
    """用户自定义规范：追加到该模板 system 末尾。"""
    blocks = []
    for e in _specs()["extra"]:
        if e.get("template") != tid or not e.get("enabled", True):
            continue
        txt = (e.get("text") or "").strip()
        if txt:
            blocks.append("【用户自定义规范：" + e["name"] + "】（优先级高于上方内置规范，冲突时以本节为准）\n" + txt)
    return "\n\n".join(blocks)



# --------------------------------------------------------------------------- 前缀

PREFIX = """你是运行在「提示词工作台」里的提示词引擎。输入 = 用户的口语化内容描述 + 生成参数 + 可选的参考图清单。
硬性输出纪律：
1. 直接产出成品提示词。不提问、不寒暄、不解释思路、不复述需求、不输出分析过程、不写"以下是"。
2. 缺失信息一律按下方规范里的默认值自动补全，直接写进成品，成品里不得出现"（默认）""建议补充"字样。
3. 用户明确写出的要求优先级最高，高于任何默认值；用户写了的槽位内容一律照用其原词。
4. 参考图只能按编号引用（<Subject N>/<Picture N>/<Video N>/<Audio N>/<imageN>），严禁编造文件名、路径或图片内容细节。本轮未提供图片时，输出里不得出现任何图片标签。
5. 画面描述一律正向陈述：禁止"不要/没有/无 + 动作或状态词"这类否定句（负向提示词字段除外），改写为可观察的正向状态。
6. 只输出下方规定的格式内容，格式之外零文字。
"""

PREFIX_TRANS = """你是运行在「提示词工作台」里的专业译者（中文↔英文，兼顾日/韩/法/西等语言的英中互译）。
硬性纪律：
1. 只输出译文，零解释、零注释、零"译文："前缀、零 markdown 代码围栏。
2. 忠实于原文的信息量：不增、不删、不概括、不评论；段落与换行结构与原文一致。
3. 数字、单位、专有名词、产品名、品牌名、代码、URL、占位符按规则处理（见下方细则），不擅自翻译品牌与代码。
4. 术语表（若给出）为最高优先，逐条强制采用。
"""

# 参考图角色卡（内置实测口径，精简模式用；完整模式追加官方 reference-image-roles 全文）
IMAGE_ROLES_BRIEF = """参考图角色分配（内置实测口径，必须遵守）：
- 人物身份/脸型/发型/服装图 → 内联进对应的 <Subject N> 定义里描述，不要让它独立成为构图锚。
- 场景图 → weak_reference：只借环境形制与光位氛围，不借构图与机位；须写明"仅作环境参照，构图与机位以本提示词的镜头描述为准"。
- 首帧图 → [Shot 1] 必须从首帧在 t=0 真实存在的元素起笔，不得凭空加入首帧里没有的东西。
- 尾帧图 → 末镜终态必须收敛到与尾帧一致的画面状态。
- 服装图/道具图 → 只借形制、材质与配色，不引入其背景与光照。
- 视频参考 → 只借运动规律与节奏；音频参考 → 只借音色与语速，台词文字以本提示词为准。
"""

# --------------------------------------------------------------------------- 输出格式

H3_OUT = """=== 输出格式（最高优先，覆盖上文任何交付格式要求）===
按下列四块输出，块名一字不改，格式之外零文字：
【模式判定】<T2VA|I2VA|FL2VA|L2VA|Ref2VA> + 一句话理由
【生成参数建议】每项一行：分辨率 / 时长(秒，≤8) / fps / steps / LoRA 首选（触发词+强度；无合适项就写"不挂 LoRA"）
【H3 提示词】
```text
subject_definitions:
（逐条 <Subject N>；无多主体时写 N/A）
summary:
（只讲剧情，不复述镜头句）
retention_analysis:
（每个参考主体 fully_preserved / weak_reference 及其保留范围）
detailed_description:
（[Shot N] 时间码 + 镜头句 + 动作 + 光影；台词按 (S1) 与 <d></d> 写法）
overall_soundscape:
（环境与动作声，对白不在此重复）
non_diegetic_music:
（不需要音乐写 N/A）
```
【提交前须知】不超过 3 条，第一条固定为否定式闸门自检结论
硬约束：六段齐全（允许 N/A 的段落写 N/A）；单段时长 ≤8 秒；只按编号引用参考图。"""

ZT_OUT = """=== 输出格式（最高优先）===
【参数建议】一行：尺寸(WxH) / steps / cfg / sampler
【提示词】
```text
（成品提示词，整段可直接复制，按规范的结构与权重语法写全）
```
【负向提示词】
```text
（负向词，逗号分隔）
```
【注意】不超过 3 条
格式之外零文字。"""

ZI_OUT = """=== 输出格式（最高优先）===
【参数建议】一行：denoise(强度) / steps / cfg / 尺寸
【图生图提示词】
```text
（成品提示词，必须包含"保留项 / 替换项 / 新增项"三段句式，逐段写清）
```
【负向提示词】
```text
（负向词，逗号分隔）
```
【注意】不超过 3 条（含 denoise 取值理由）
格式之外零文字。"""

MOSS_OUT = """=== 输出格式（最高优先）===
只输出一个 JSON 对象，不要 markdown 围栏、不要任何解释，字段按下方模板逐字给全：
positive_prompt / negative_prompt / slots(12 个键) / scene_specific_negatives(数组) / canvas_size(width,height) / layout_json / sampling_profile(steps,cfg,sampler,shift,slg_skip_layer) / warnings(数组，无问题给空数组)
canvas_size 用给定的画幅参数；槽位内容用用户的语言，风格词与专有名词照抄英文。"""

QWEN_OUT = """严格按上述规范输出 JSON：{"rewritten_prompt": "...", "wh_ratio": "...", "ratio_follow": "..."}。
补充要求：rewritten_prompt 必须是单段连续文本（无换行）；不要在 rewritten_prompt 里出现任何分辨率或比例数字；不要输出 JSON 之外的任何文字（含 ```json 围栏）。"""

TR_OUT = """输出规则：只输出译文本身。"""

TR_PROMPT_OUT = """=== 提示词互译保护规则（最高优先，逐条强制）===
1. 字段名与结构名永不翻译、永不改写：subject_definitions / summary / retention_analysis / detailed_description / overall_soundscape / non_diegetic_music / positive_prompt / negative_prompt / wh_ratio / ratio_follow / rewritten_prompt。
2. 标签与占位符原样保留：<Subject 1>、<Picture 2>、<Video 1>、<Audio 1>、<image1>、[Shot 1]、(S1)(S2)、<d></d>、[reference generation]、fully_preserved、weak_reference、appears in。
3. <d></d> 内的台词文字：中→英时把台词正文译成英文并保留 </d> 结构，同时把语言标记 [Chinese] 改为 [English]（若原台词是中文）；英→中时反之。用户明确指定台词语言时以用户指定为准。
4. JSON 输入时：键名与结构不动，只译字符串值；rewritten_prompt 的值译完后仍保持单段无换行；wh_ratio / ratio_follow 的值原样保留。
5. 镜头术语用标准英文电影术语（push in / pull back / pan / tilt / track / crane / orbit / dolly zoom / handheld / aerial 等），中文侧用对应标准词（推镜/拉镜/摇镜/移镜/升降/环绕/希区柯克变焦/手持/航拍）。
6. 不增删内容、不重排段落、不改写句式风格，长度与信息量与原文一致。
只输出译文（与原文同结构）。"""

# --------------------------------------------------------------------------- builders


def _param_line(params: dict, keys: list, labels: dict) -> str:
    items = []
    for k in keys:
        v = params.get(k)
        if v in (None, "", False):
            continue
        items.append(f"{labels.get(k, k)}={v}")
    return "；".join(items)


def _image_block2(images: list) -> str:
    if not images:
        return ""
    lines = ["【参考图清单】本轮实际提供 %d 张，只能按编号引用，禁止编造图片里没有的东西：" % len(images)]
    for i, img in enumerate(images, 1):
        role = (img.get("role") or "参考图").strip()
        lines.append(f"第 {i} 张 = <image{i}> / <Picture {i}> = <Subject {i}> 角色：{role}")
    return "\n".join(lines)


def _feedback_line(params: dict) -> str:
    fb = (params.get("feedback") or "").strip()
    if not fb:
        return ""
    return "【上一版的问题 → 本次修改要求】" + fb + "\n上一版提示词全文见对话上文，按要求重做一版完整的成品（不要只改局部、不要解释改了什么）。"


def build_h3(params: dict, images: list, fast: bool) -> dict:
    mode = (params.get("mode") or "auto").strip()
    has_img = bool(images)
    parts = [PREFIX, _read("h3_base.txt"), _read("h3_negation_guard.md")]
    if mode == "Ref2VA" or (mode == "auto" and len(images) >= 2):
        parts.append(_read("h3_ref.txt"))
    if has_img:
        parts.append(IMAGE_ROLES_BRIEF)
        if not fast:
            parts.append(_read("h3_reference_image_roles.md"))
    kind = (params.get("subject_kind") or "").strip()
    if (not fast) or kind in ("人物特写", "文戏对白", "打斗动作"):
        parts.append(_read("h3_micro_expression.md"))
    if not fast:
        parts.append(_read("h3_writing_order.md"))
        parts.append(_read("h3_camera_and_lora.md"))
    sys_txt = "\n\n".join([p for p in parts if p]) + "\n\n" + H3_OUT

    dur = params.get("duration") or 6
    labels = {
        "mode": "模式",
        "duration": "时长(秒)",
        "aspect": "画幅",
        "lang": "描述语言",
        "subject_kind": "题材类型",
        "resolution": "目标分辨率",
        "prev": "上一段结尾状态",
    }
    line = _param_line(params, ["mode", "duration", "aspect", "lang", "subject_kind", "resolution"], labels)
    user = "【内容描述】\n" + (params.get("content") or "")
    user += "\n\n【生成参数】" + (line or "全部按默认")
    user += "\n\n" + _image_block2(images)
    prev = (params.get("prev") or "").strip()
    if prev:
        user += "\n\n【上一段结尾状态（本段开场必须能独立成立，禁止写「承接上一段」）】" + prev
    user += "\n\n" + _feedback_line(params)
    return {"system": sys_txt, "user": user, "expect_json": False}


def build_qwen(params: dict, images: list, fast: bool) -> dict:
    sys_txt = PREFIX + "\n\n" + _read("qwen_image_2_1_i2i.txt") + "\n\n" + QWEN_OUT
    user = "【编辑指令】\n" + (params.get("content") or "")
    extra = []
    ratio = (params.get("ratio") or "").strip()
    if ratio:
        extra.append(f"用户指定输出比例={ratio}")
    role = (params.get("canvas_role") or "").strip()
    if role:
        extra.append("画布图指定=" + role)
    if extra:
        user += "\n\n【补充】" + "；".join(extra)
    user += "\n\n" + _image_block2(images)
    user += "\n\n" + _feedback_line(params)
    return {"system": sys_txt, "user": user, "expect_json": True}


def build_moss(params: dict, images: list, fast: bool) -> dict:
    parts = [
        PREFIX,
        _read("moss_slots_and_defaults.md"),
        _read("moss_template_positive.txt"),
        _read("moss_template_negative.txt"),
        _read("moss_negative_lexicon.md"),
        _read("moss_template_output.txt"),
    ]
    if not fast:
        parts.append(_read("moss_official_spec.md"))
    sys_txt = "\n\n".join([p for p in parts if p]) + "\n\n" + MOSS_OUT
    canvas = (params.get("canvas") or "1024x1024").strip()
    user = "【内容描述】\n" + (params.get("content") or "")
    extra = [f"画幅={canvas}"]
    if (params.get("style_pref") or "").strip():
        extra.append("风格偏好=" + params["style_pref"].strip())
    if (params.get("scene_tags") or "").strip():
        extra.append("场景关键词=" + params["scene_tags"].strip())
    if (params.get("lang") or "").strip():
        extra.append("槽位语言=" + params["lang"].strip())
    user += "\n\n【参数】" + "；".join(extra)
    user += "\n\n" + _image_block2(images)
    user += "\n\n" + _feedback_line(params)
    return {"system": sys_txt, "user": user, "expect_json": True}


def build_zt(params: dict, images: list, fast: bool) -> dict:
    sys_txt = PREFIX + "\n\n" + _read("z_image_turbo_skill.md") + "\n\n" + ZT_OUT
    user = "【内容描述】\n" + (params.get("content") or "")
    extra = []
    if (params.get("canvas") or "").strip():
        extra.append("画幅=" + params["canvas"].strip())
    if (params.get("style_pref") or "").strip():
        extra.append("风格偏好=" + params["style_pref"].strip())
    user += "\n\n【参数】" + ("；".join(extra) or "全部按默认")
    user += "\n\n" + _image_block2(images)
    user += "\n\n" + _feedback_line(params)
    return {"system": sys_txt, "user": user, "expect_json": False}


def build_zi(params: dict, images: list, fast: bool) -> dict:
    parts = [
        PREFIX,
        _read("z_image_i2i_skill.md"),
        _read("z_image_i2i_strength_tiers.md"),
        _read("z_image_i2i_patterns.md"),
    ]
    if not fast:
        parts.append(_read("z_image_i2i_pitfalls.md"))
    sys_txt = "\n\n".join([p for p in parts if p]) + "\n\n" + ZI_OUT
    user = "【改造要求】\n" + (params.get("content") or "")
    extra = []
    if (params.get("intent") or "").strip():
        extra.append("改造类型=" + params["intent"].strip())
    if (params.get("denoise_hint") or "").strip():
        extra.append("强度提示=" + params["denoise_hint"].strip())
    user += "\n\n【参数】" + ("；".join(extra) or "自行判定")
    user += "\n\n" + _image_block2(images)
    user += "\n\n" + _feedback_line(params)
    return {"system": sys_txt, "user": user, "expect_json": False}


def build_tr(params: dict, images: list, fast: bool) -> dict:
    direct = (params.get("direction") or "auto").strip()
    mapn = {
        "auto": "方向自动：原文是中文→译成英文；原文是外文→译成中文。",
        "zh2en": "方向固定：中文 → 英文。",
        "en2zh": "方向固定：英文 → 中文。",
        "zh2en_nl": "方向固定：中文 → 英文，要求地道自然、口语可读，像母语者写的，避免翻译腔。",
        "en2zh_nl": "方向固定：英文 → 中文，要求地道自然，符合中文表达习惯，避免翻译腔。",
    }
    rules = [
        "细则：",
        mapn.get(direct, mapn["auto"]),
        "文体跟随原文：正式对正式、口语对口语；专有名词与品牌名保留原文（首次出现可用括号给出通行译名）。",
        "数字、单位、日期、代码、URL、邮箱、占位符（如 {{var}}、%s、{var}）、Markdown 标记、HTML 标签一律原样保留。",
        "引号、书名号等标点按目标语言规范替换；英文句末不留中文标点，中文正文不使用英文标点。",
        "译文风格按下方「语域」要求执行。",
    ]
    sys_txt = PREFIX_TRANS + "\n".join(rules) + "\n" + TR_OUT
    user = ""
    gl = (params.get("glossary") or "").strip()
    if gl:
        user += "【术语表（逐条强制采用，出现即照译）】\n" + gl + "\n\n"
    register = (params.get("register") or "").strip()
    if register:
        user += "【语域】" + register + "\n\n"
    user += "【原文】\n" + (params.get("content") or "")
    return {"system": sys_txt, "user": user, "expect_json": False}


def build_tr_prompt(params: dict, images: list, fast: bool) -> dict:
    sys_txt = PREFIX_TRANS + TR_PROMPT_OUT
    direct = (params.get("direction") or "zh2en").strip()
    head = {
        "zh2en": "把下面的提示词译成英文（字段名与标签保持英文原样，描述内容译成英文）。",
        "en2zh": "把下面的提示词译成中文（字段名与标签保持英文原样，描述内容译成中文）。",
    }.get(direct, "中英互译下面这份提示词。")
    user = head + "\n\n【原文】\n" + (params.get("content") or "")
    return {"system": sys_txt, "user": user, "expect_json": False}


def build_plugin(t: dict, params: dict, images: list, fast: bool) -> dict:
    """用户插件：开场角色句 + 输出纪律 + 插件自带规范。"""
    name = t.get("label") or "插件"
    intro = (t.get("_intro") or pluginlib.DEFAULT_INTRO.format(name=name)).strip()
    spec = (t.get("_spec") or "").strip()
    parts = [intro, pluginlib.OUTPUT_RULES, "【插件规范】\n" + spec]
    if images:
        parts.append(IMAGE_ROLES_BRIEF)
        parts.append(_image_block2(images))
    sys_txt = "\n\n".join(parts)

    lines = []
    kv = []
    for p in (t.get("params") or []):
        k = p.get("key")
        v = params.get(k)
        if v in (None, "", False):
            continue
        kv.append("%s=%s" % (p.get("label") or k, v))
    if kv:
        lines.append("【生成参数】" + "；".join(kv))
    fb = _feedback_line(params)
    if fb:
        lines.append(fb)
    lines.append("【我的需求】\n" + (params.get("content") or "").strip())
    return {"system": sys_txt, "user": "\n\n".join(lines), "expect_json": bool(t.get("expect_json"))}


# --------------------------------------------------------------------------- registry

TEMPLATES = [
    {
        "id": "h3_video",
        "group": "prompt",
        "label": "MiniMax H3 视频",
        "tagline": "T2VA / I2VA / FL2VA / L2VA / Ref2VA 六段式（含运镜、台词、微表情、LoRA 建议）",
        "min_images": 0,
        "max_images": 8,
        "need_roles": True,
        "builder": "build_h3",
        "params": [
            {
                "key": "mode",
                "label": "模式",
                "type": "select",
                "default": "auto",
                "options": ["auto", "T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"],
            },
            {"key": "duration", "label": "时长(秒)", "type": "number", "default": 6, "min": 1, "max": 8},
            {
                "key": "aspect",
                "label": "画幅",
                "type": "select",
                "default": "16:9",
                "options": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
            },
            {
                "key": "subject_kind",
                "label": "题材类型",
                "type": "select",
                "default": "通用",
                "options": ["通用", "文戏对白", "人物特写", "打斗动作", "场景空镜", "产品展示"],
            },
            {
                "key": "lang",
                "label": "描述语言",
                "type": "select",
                "default": "中文",
                "options": ["中文", "English"],
            },
            {"key": "resolution", "label": "目标分辨率", "type": "text", "default": "", "placeholder": "如 1280x720 / 704x1280，留空自动"},
            {"key": "prev", "label": "上一段结尾状态（链式续接）", "type": "text", "default": "", "placeholder": "留空表示独立镜头"},
        ],
    },
    {
        "id": "qwen_i2i",
        "group": "prompt",
        "label": "Qwen Image 2.1 图生图",
        "tagline": "官方 PE 逐字内置：改写编辑指令 + 输出比例判定，返回 JSON",
        "min_images": 1,
        "max_images": 6,
        "need_roles": True,
        "builder": "build_qwen",
        "params": [
            {"key": "ratio", "label": "输出比例", "type": "text", "default": "", "placeholder": "留空＝按原图；可写 9:16 / 2:3 / 1920x1080"},
            {"key": "canvas_role", "label": "画布图（多图的哪张是被编辑的底图）", "type": "text", "default": "", "placeholder": "如 第1张=画布，第2张=身份来源"},
        ],
    },
    {
        "id": "moss_t2i",
        "group": "prompt",
        "label": "moss-image 文生图",
        "tagline": "14 槽位正向模板 + 场景负向词自动推导，返回 JSON",
        "min_images": 0,
        "max_images": 4,
        "need_roles": True,
        "params": [
            {
                "key": "canvas",
                "label": "画幅（自由填写 WxH）",
                "type": "canvas",
                "default": "1024x1024",
                "suggestions": ["1024x1024", "1536x864", "864x1536", "1216x832", "1344x1024", "1024x1536", "832x1216"],
                "placeholder": "任意 WxH，如 1120x1472 / 1536x864",
            },
            {"key": "style_pref", "label": "风格偏好", "type": "text", "default": "", "placeholder": "如 3D 仙侠渲染 / 胶片写实 / 国风水墨"},
            {"key": "scene_tags", "label": "场景关键词（推导负向词）", "type": "text", "default": "", "placeholder": "如 古风室内, 雪夜, 产品静物, 带文字海报"},
            {"key": "lang", "label": "槽位语言", "type": "select", "default": "中文", "options": ["中文", "English"]},
        ],
        "builder": "build_moss",
    },
    {
        "id": "zt_t2i",
        "group": "prompt",
        "label": "Z-Image Turbo 文生图",
        "tagline": "原生中文七模块结构 + 权重语法 + 东方人像/古风意境术语库",
        "min_images": 0,
        "max_images": 3,
        "need_roles": False,
        "params": [
            {
                "key": "canvas",
                "label": "画幅（自由填写 WxH）",
                "type": "canvas",
                "default": "1024x1024",
                "suggestions": ["1024x1024", "1536x864", "864x1536", "1216x832", "1024x1536", "1440x1440"],
                "placeholder": "任意 WxH，如 1120x1472",
            },
            {"key": "style_pref", "label": "风格偏好", "type": "text", "default": "", "placeholder": "如 新中式时尚 / 吉卜力 / 油画 / 工笔仕女"},
        ],
        "builder": "build_zt",
    },
    {
        "id": "zi_i2i",
        "group": "prompt",
        "label": "Z-Image 图生图",
        "tagline": "强度档位表 + 保留项/替换项/新增项句式（洗图、转绘、局部重绘、扩图）",
        "min_images": 1,
        "max_images": 6,
        "need_roles": True,
        "params": [
            {
                "key": "intent",
                "label": "改造类型",
                "type": "select",
                "default": "洗图提质",
                "options": ["洗图提质", "局部修改", "换装换背景", "风格转绘", "材质变换", "扩图", "人物转Q版手办", "大改重画"],
            },
            {"key": "denoise_hint", "label": "强度提示", "type": "text", "default": "", "placeholder": "留空自动选档；可写 denoise≈0.3"},
            {
                "key": "canvas",
                "label": "输出尺寸（自由填写 WxH）",
                "type": "canvas",
                "default": "",
                "suggestions": ["1024x1024", "1536x864", "864x1536", "1216x832", "1024x1536"],
                "placeholder": "留空＝跟随原图；扩图/改比例时填目标尺寸",
            },
        ],
        "builder": "build_zi",
    },
    {
        "id": "tr_general",
        "group": "translate",
        "label": "通用翻译",
        "tagline": "中英互译（自动方向 / 固定方向 / 地道意译），支持术语表",
        "min_images": 0,
        "max_images": 0,
        "need_roles": False,
        "params": [
            {
                "key": "direction",
                "label": "方向",
                "type": "select",
                "default": "auto",
                "options": ["auto", "zh2en", "en2zh", "zh2en_nl", "en2zh_nl"],
                "labels": {
                    "auto": "自动判定",
                    "zh2en": "中 → 英",
                    "en2zh": "英 → 中",
                    "zh2en_nl": "中 → 英（地道自然）",
                    "en2zh_nl": "英 → 中（地道自然）",
                },
            },
            {
                "key": "register",
                "label": "语域",
                "type": "select",
                "default": "跟随原文",
                "options": ["跟随原文", "正式书面", "口语自然", "简洁口语（短视频文案）", "技术文档"],
            },
            {"key": "glossary", "label": "术语表（每行 原文=译文）", "type": "textarea", "default": "", "placeholder": "沈不违=Shen Buwei\n人元丹=Renyuan Pill"},
        ],
        "builder": "build_tr",
    },
    {
        "id": "tr_prompt",
        "group": "translate",
        "label": "提示词互译",
        "tagline": "H3 / Qwen / JSON 提示词中英互译，字段名与标签结构永不破坏",
        "min_images": 0,
        "max_images": 0,
        "need_roles": False,
        "params": [
            {
                "key": "direction",
                "label": "方向",
                "type": "select",
                "default": "zh2en",
                "options": ["zh2en", "en2zh"],
                "labels": {"zh2en": "提示词 中 → 英", "en2zh": "提示词 英 → 中"},
            },
        ],
        "builder": "build_tr_prompt",
    },
]


def user_templates() -> list:
    """用户自己添加的模型（存在 data\\custom_templates.json，界面里可增删改）。

    结构与「模板插件」一致，直接复用 build_plugin：开场角色句 + 输出纪律 + 你写的规范。
    """
    out = []
    try:
        items = settings.load_user_templates()
    except Exception:
        items = []
    for it in items:
        if not it.get("enabled", True):
            continue
        tid = it.get("id") or ("custom_" + str(abs(hash(it.get("name"))) % 10 ** 8))
        out.append({
            "id": tid,
            "group": "prompt",
            "label": it.get("name") or "自定义模型",
            "tagline": it.get("tagline") or "你自己的模型（自定义规范）",
            "min_images": int(it.get("min_images") or 0),
            "max_images": int(it.get("max_images") or 4),
            "need_roles": True,
            "builder": "build_plugin",
            "plugin": True,          # 走 build_plugin
            "custom": True,          # 前端据此显示「编辑 / 删除」
            "expect_json": bool(it.get("expect_json")),
            "params": it.get("params") or [],
            "examples": it.get("examples") or [],
            "_spec": it.get("spec") or "",
            "_intro": it.get("intro") or "",
        })
    return out


def all_templates() -> list:
    """内置模板 + 用户自定义模型 + 插件（插件目录每次现扫，丢进去即可用）。"""
    try:
        cfg = settings.load_config()
        plug = pluginlib.scan(cfg).get("templates") or []
    except Exception:
        plug = []
    try:
        mine = user_templates()
    except Exception:
        mine = []
    return list(TEMPLATES) + mine + plug


def template_ids() -> list:
    return [t["id"] for t in all_templates()]


def get_template(tid: str) -> dict | None:
    for t in all_templates():
        if t["id"] == tid:
            return t
    return None


def build(tid: str, params: dict, images: list, fast: bool) -> dict:
    t = get_template(tid)
    if not t:
        raise ValueError("未知模板：" + str(tid))
    _local.specs = settings.load_specs()
    try:
        if t.get("plugin"):
            out = build_plugin(t, params, images or [], bool(fast))
        else:
            fn = globals()[t["builder"]]
            out = fn(params, images or [], bool(fast))
        extras = _extras_block(tid)
        if extras:
            out["system"] = out["system"] + "\n\n" + extras
    finally:
        _local.specs = None
    out["template"] = tid
    out["label"] = t["label"]
    out["expect_json"] = bool(out.get("expect_json") or t.get("expect_json"))
    return out


def catalog() -> list:
    """给前端的模板定义（不含 builder 函数、不含插件规范正文）。"""
    out = []
    for t in all_templates():
        item = {k: v for k, v in t.items() if k != "builder" and not k.startswith("_")}
        out.append(item)
    return out


def template_stats() -> list:
    """内置规范文件清单与体积，给设置页展示。"""
    res = []
    for d in (TPL_DIR, BASE_DIR):
        if not d.exists():
            continue
        for p in sorted(d.glob("*")):
            if p.is_file():
                res.append({"name": p.name, "bytes": p.stat().st_size})
    return res
