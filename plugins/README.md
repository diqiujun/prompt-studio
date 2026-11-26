# 插件目录（plugins）

把这个文件夹里放的东西会**直接出现在软件界面里**。两种插件：

| 类型 | 你能得到什么 | 需要哪些文件 |
| --- | --- | --- |
| **模板插件**（只写规范，不执行代码） | 「提示词撰写」里多一张卡片，用你写的规范改写提示词 | `plugin.json` + `spec.md` |
| **代码插件**（可执行 Python） | 除了模板，还能注册**工具按钮**、**设置项**、**后端接口**，以及 `generate.after` **输出后处理钩子** | `plugin.json` + `plugin.py`（可再加 `spec.md`） |

放进去后到「设置 → 插件」点 **重新加载** 即可，不用重启软件。也可以在那里 **安装插件（zip）**、**启用/停用**、**删除**。
代码插件第一次加载需要点 **信任并加载** —— 插件代码和软件同权限运行，只放你信得过的。

自带两个示例：

- `sample_generic`：纯模板插件（一个 `plugin.json` + 一段 `spec.md`），抄它改就行。
- `sample_tools`：代码插件示例，演示工具按钮 / 设置项 / 接口 / 钩子四件事。

---

## 一、模板插件

最小形态（一个文件夹两个文件）：

```
plugins/我的插件/plugin.json
plugins/我的插件/spec.md
```

`plugin.json`：

```json
{
  "id": "my_prompt",
  "name": "我的提示词插件",
  "tagline": "一句话说明它干什么",
  "author": "你",
  "version": "1.0.0",
  "intro": "你是……引擎，正在按「我的插件」的规范改写用户的描述。",
  "spec": "spec.md",
  "expect_json": false,
  "min_images": 0,
  "max_images": 6,
  "params": [
    { "key": "style", "label": "风格", "type": "select", "options": ["写实", "电影感", "插画"], "default": "电影感" },
    { "key": "canvas", "label": "画幅（自由填写 WxH）", "type": "canvas", "default": "1024x1024" },
    { "key": "extra", "label": "补充要求", "type": "textarea", "placeholder": "可留空" }
  ],
  "examples": ["例：一段用户会输入的话，用来当输入框占位提示"]
}
```

`spec.md` 就是你的规范正文（写多长都行，会**原样**注入系统提示词）。

---

## 二、代码插件

`plugin.json` 里加 `"entry": "plugin.py"`，并写 `plugin.py`：

```python
def register(ctx):
    # 1) 工具按钮：出现在「提示词撰写」结果区上方，作用于当前结果文本
    def tidy(text, params):
        # params = {"settings": {...}, "params": {...}, "template": "h3_video", "images": [...]}
        return {"text": text.strip(), "note": "已整理"}

    ctx.tool("tidy", "整理文本", where="toolbar", hint="鼠标悬停提示")

    # 2) 后端接口：GET/POST /api/plugin/<插件id>/stats
    def stats(body, query):
        return {"ok": True, "chars": len((body or {}).get("text", ""))}

    ctx.route("stats", stats, methods=["GET", "POST"])

    # 3) 生成后处理：返回字符串 = 替换输出；返回 None = 不处理
    def after(payload):
        # payload = {"template", "content", "output", "json", "params", "settings"}
        return None

    ctx.on("generate.after", after)
```

`ctx` 提供的全部能力：

| 成员 | 说明 |
| --- | --- |
| `ctx.plugin_id` / `ctx.name` / `ctx.dir` | 插件 id、名字、目录 |
| `ctx.data_dir` | 这个插件自己的数据目录（`data/plugins/<id>/`，可写文件做缓存） |
| `ctx.settings` | 当前设置项的值（dict） |
| `ctx.get(key, default=None)` | 读一个设置项（等同 `ctx.settings.get`） |
| `ctx.log(msg)` | 写日志到 `data/plugins.log`（界面不显示，排错时看这个） |
| `ctx.tool(name, label, where="toolbar", hint="")` | 注册工具按钮，回调 `fn(text, params)` 返回 `str` 或 `{"text":…, "note":…}` |
| `ctx.route(path, fn, methods=("GET","POST"))` | 注册接口，回调 `fn(body, query)` 返回 dict（JSON） |
| `ctx.on("generate.after", fn)` | 生成后钩子，`fn(payload)` 返回字符串替换输出，返回 None 不处理 |

设置项（`plugin.json` 的 `settings` 数组，结构同 `params`，支持 `select` / `text` / `textarea` / `number` / `checkbox`）：

```json
"settings": [
  { "key": "strip_blank", "label": "去掉多余空行", "type": "checkbox", "default": true },
  { "key": "prefix", "label": "前缀", "type": "text", "default": "" }
]
```

界面里填好点「保存设置」，插件里 `ctx.get("strip_blank")` 就能读到。

---

## 三、运行时约定

- **参数**：界面里填的参数以「【生成参数】标签=值」附在用户消息前面。
- **参考图**：以「第 N 张 = `<imageN>` / `<Picture N>` 角色：…」列进系统提示词，并作为图片一起发给模型。
- **输出**：`expect_json: true` 时软件会尝试从模型输出里解析 JSON 并结构化展示。
- **停用**：只写进 `data/config.json` 的 `plugins_off`，**不会改动你的插件文件**。
- **信任**：写进 `data/config.json` 的 `plugin_trust`；取消信任后代码不再执行。
- **数据**：`data/plugin_settings`（设置值）、`data/plugins/<id>/`（插件自己的数据）、`data/plugins.log`（插件日志）。

---

## 四、排错

| 现象 | 原因 / 处理 |
| --- | --- |
| 设置页显示「出错」 | 看提示文字：缺 `plugin.json`、JSON 写错（逗号/引号）、代码插件既没 `spec.md` 也没 `entry` |
| 插件显示「未信任」 | 点「信任并加载」 |
| 代码插件「出错」 | 看 `data/plugins.log`，通常是 `register()` 里抛异常或函数名写错 |
| 界面里没有新卡片 | 点「重新加载」；或 `id` 与其它插件重复（重复会被拒绝） |
| 接口 404 | 路径以 `ctx.route("stats", …)` 声明的为准：`/api/plugin/<插件id>/stats` |
