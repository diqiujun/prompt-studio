# PromptStudio（PM）插件格式规范 v1

> 本文件是插件作者手册。放在 `plugins\<你的插件>\` 里，程序扫描后即出现在界面中；
> 内置示例：`plugins\sample_generic`（模板插件）、`plugins\sample_tools`（代码插件）、
> `plugins\pose_gallery`（代码插件 + 自带界面面板）。

---

## 0. 三种形态，一套目录

| 形态 | 必备文件 | 能给软件带来什么 |
| --- | --- | --- |
| 模板插件 | `plugin.json` + `spec.md` | 「提示词撰写」页多一张模型卡：用户说话 → 按你的规范改写成提示词 |
| 代码插件 | `plugin.json` + `plugin.py` | 工具按钮、后端接口、生成后处理钩子 |
| 带界面插件 | 上面 + `web/panel.js`、`web/panel.css` + `web{}` 声明 | 在撰写页/设置页挂出你自己的面板（姿势库、素材库、批量工具…） |

三种可以叠加：一个插件既能出模板、又能加按钮、还能挂面板。

---

## 1. 目录结构

```
plugins/
└─ my_plugin/
   ├─ plugin.json          # 必需：插件清单
   ├─ spec.md              # 模板插件必需：规范正文（也可拆进 plugin.json 的 spec）
   ├─ plugin.py            # 代码插件必需：定义 register(ctx)
   ├─ web/
   │  ├─ panel.js          # 可选：面板脚本（用 window.PSPlugin 挂载）
   │  └─ panel.css         # 可选：面板样式
   └─ data/                # 可选：插件自带数据（图片、json…），随插件目录分发
      └─ index.json
```

约束：

- 目录名随意，但 `plugin.json` 的 `id` 唯一（重复会让该插件报错并跳过，不影响其它插件）。
- 所有相对路径都相对插件目录，**不允许** `..` 跳出插件目录（静态路由会做规范化校验）。
- 单个插件安装包 `plugins install` 上限 32 MB（zip）；随发行目录分发不受此限。

---

## 2. plugin.json 字段

```json
{
  "id": "my_plugin",
  "name": "我的插件",
  "tagline": "一句话说明",
  "description": "更长的说明（列表里展示）",
  "version": "1.0.0",
  "author": "minut",
  "intro": "你是……的提示词工程师，把用户的口语需求改写成……",

  "entry": "plugin.py",
  "spec": "规范正文…（也可用 spec_file 指向文件）",
  "spec_file": "spec.md",

  "min_images": 0,
  "max_images": 4,
  "expect_json": false,

  "params": [
    { "key": "style", "label": "风格", "type": "select",
      "options": ["电影感", "二次元"], "default": "电影感" },
    { "key": "shots", "label": "镜头数", "type": "number", "min": 1, "max": 8, "default": 1 },
    { "key": "canvas", "label": "画幅", "type": "canvas", "default": "1024x1024" }
  ],
  "examples": ["一句话示例", "另一句示例"],

  "settings": [
    { "key": "insert_text", "label": "同时插入描述", "type": "checkbox", "default": true },
    { "key": "prefix", "label": "前缀", "type": "text", "default": "" }
  ],

  "web": { "js": "web/panel.js", "css": "web/panel.css", "mount": "prompt", "title": "我的面板" },

  "enabled": true
}
```

字段说明：

- `id` 必填：字母/数字/下划线/短横线；内部模板 id 会变成 `plugin_<id>`。
- `name` 必填：界面显示名。
- `entry`：代码入口，默认 `plugin.py`；只有存在且被信任时才加载代码。
- `spec` / `spec_file`：模板插件写规范正文；两者都没有且没有 `plugin.py` 时该插件报错。
- `params[].type`：`select | number | text | textarea | canvas | checkbox`（未知类型按 text）。
  - `select` 需要 `options`；`number` 可用 `min`/`max`；`canvas` 生成「WxH」输入框（带建议值，用户可自由填）。
- `min_images` / `max_images`：参考图数量门槛（缺失会给出中文提示）。
- `expect_json`：期望模型输出 JSON（程序会用 extract_json 解析，结果在 `/api/generate` 的 `json` 键）。
- `settings`：面板/插件自己的设置项，值存在 `data\config.json` 的 `plugin_settings.<id>`。
- `web.mount`：`prompt`（撰写页，插在参考图下面）| `settings`（设置页）| `both` | `sidebar`（右侧工具栏：多个插件按页签切换，可折叠，Ctrl+Shift+B 开关，`?sbar=<插件id>` 直达）。
- `web.js` / `web.css`：相对路径，必须真实存在，否则 `web` 声明被忽略（面板不挂）。

---

## 3. 模板插件的注入方式

点模板卡 → 生成时系统提示词 = `intro` + 输出纪律 + `【插件规范】\n` + spec（有参考图时追加图片清单）；
用户消息 = `【生成参数】标签=值` + `【我的需求】\n内容`。

因此 spec 里要写「怎么产出提示词」（结构、顺序、语言、禁忌），不要写「你是谁」——那是 intro 的事。

---

## 4. 代码插件：register(ctx)

```python
def register(ctx):
    ctx.log("my_plugin 已加载")

    @ctx.tool("tidy", "整理文本", where="toolbar")
    def _tidy(text, params):
        # text：结果区或输入框里的文本；params：{"settings": {...}, "params": {...}, "template": "h3_video", "images": [...]}
        return {"text": text.strip(), "note": "已整理"}

    @ctx.route("stats", ["GET", "POST"])
    def _stats(body, query):
        return {"chars": len(str(body.get("text") or ""))}

    @ctx.on("generate.after")
    def _after(payload):
        # payload：{"template","content","output","json","params","settings"}
        if payload["settings"].get("append_note"):
            return payload["output"] + "\n\n（由插件整理）"
        return None
```

ctx 成员：

| 成员 | 说明 |
| --- | --- |
| `ctx.plugin_id` / `ctx.name` / `ctx.dir` | 插件身份与目录 |
| `ctx.data_dir` | `data/plugins/<id>/`，插件可写目录（自动创建） |
| `ctx.settings` | 当前设置值 dict |
| `ctx.get(key, default=None)` | 读设置 |
| `ctx.log(msg)` | 写 `data\plugins.log` |
| `ctx.tool(name, label, where="toolbar", hint="")` | 注册工具；`where` ∈ `toolbar`（结果区工具条）`result` `prompt` |
| `ctx.route(path, methods=("GET","POST"))` | 注册 HTTP 接口，实际路径 `/api/plugin/<id>/<path>` |
| `ctx.on("generate.after")` | 生成后钩子；返回字符串会替换输出，返回 `None` 表示不处理 |

工具返回值：字符串或 `{"text": "...", "note": "..."}`。
接口返回值：可 JSON 序列化的 dict（程序会包成 `{ok:true, ...}`）。
装饰器与直接调用两种写法都支持：`ctx.tool("tidy", "整理文本", fn)`。

---

## 5. 带界面插件：window.PSPlugin

`web/panel.js` 里用宿主 API 挂面板，不需要关心打包/框架：

```js
(function () {
  PSPlugin.addPanel({
    id: "my_panel",
    title: "我的面板",
    mount: "sidebar",             // prompt | settings | both | sidebar（右侧工具栏）
    render: function (el, api) {  // el：面板容器；api：宿主 API（即 PSPlugin）
      el.innerHTML = '<div class="pp-tools"><input class="inp" id="q"><button class="btn sm" id="go">搜索</button></div><div id="grid" class="pp-grid"></div>';
      async function load() {
        const d = await (await fetch("/api/plugin/my_plugin/list?q=" + encodeURIComponent(el.querySelector("#q").value))).json();
        el.querySelector("#grid").innerHTML = (d.items || []).map(function (it) {
          return '<button class="pp-item" data-img="' + it.thumb + '" data-zh="' + (it.zh || "") + '"><img loading="lazy" src="' + it.thumb + '"></button>';
        }).join("");
      }
      el.querySelector("#go").onclick = load;
      load();
    }
  });
})();
```

宿主 API（`PSPlugin` / `api`）：

| 方法 | 说明 |
| --- | --- |
| `addPanel({id,title,mount,render})` | 注册面板；`render(容器, api)` 在挂载时调用。`mount:"sidebar"` 时容器放进右侧工具栏，标题变成页签，宿主自动记住上次选中的页签（localStorage `ps-sbar-cur`）；面板自己的 `plugin.json` 里 `web.mount` 也应为 `sidebar` |
| `insertText(text)` | 插入到「内容描述」输入框光标处 |
| `insertImage(src, role)` | 把图片 URL / dataURL 加进参考图（自动按模板 max_images 校验），`role` 为角色名（见下） |
| `images()` | 当前参考图数组（`[{data_url, role}]`） |
| `template()` | 当前模板 id |
| `setting(key, def)` | 读本插件设置；写设置：`POST /api/plugins/settings {id, values:{...}}` |
| `toast(msg)` | 右下角提示 |

常用图片角色：`画布图·被编辑的底图`、`人物身份来源`、`风格参考`、`姿势参考（人体动态与构图）`、`姿势深度图（ControlNet Depth）`。

面板样式：用宿主 CSS 变量（`--bg2 --line --fg --fg2 --acc --chip` 等）即可自动跟随深浅色；
容器 class 为 `pp-panel`，写在 `web/panel.css` 里的规则会随插件注入。

静态资源路由：`/api/plugin-static/<id>/<相对路径>`（只允许插件目录内的文件，返回原字节）。

---

## 6. 安装、信任与停用

- 放目录：把插件目录拷进 `plugins\`，在「设置 → 插件」点 **重新加载**。
- 装 zip：设置页 **安装插件（zip）**，或 `POST /api/plugins/install`（multipart，字段 `file`）。
- 信任门：代码插件（有 `plugin.py`）默认 **未信任**，界面显示「信任并加载」；未信任时既不执行代码，也不注入它的面板。
- 停用：界面复选框（写 `data\config.json` 的 `plugins_off`，不改你的插件文件）。
- 卸载：界面「删除」或 `POST /api/plugins/delete {id}`。

状态取值：`template`（只有规范）、`loaded`（代码已加载）、`untrusted`（待信任）、
`disabled`（被停用）、`error`（见 `data\plugins.log`）。

---

## 7. 排错清单

| 现象 | 检查 |
| --- | --- |
| 插件列表里看不到 | `plugin.json` 是否存在且为合法 JSON；`id` 是否与别的插件重复 |
| 模板卡没出现 | 是否既无 `spec`/`spec_file` 又无 `plugin.py` |
| 面板没挂出 | `web.js` 路径是否存在；是否 **未信任**；`mount` 是否写对 |
| 工具按钮没出现 | 是否已信任；`register(ctx)` 是否抛异常（看 `data\plugins.log`） |
| 接口 404 | 路由名是否与 `ctx.route` 一致：`/api/plugin/<id>/<path>` |
| 图片 404 | 路径是否在插件目录内；静态路由前缀 `/api/plugin-static/<id>/` 是否漏写 |
| 改代码不生效 | 点「重新加载」（`POST /api/plugins/reload`）；模块已缓存，需 reload |

---

## 8. 打包与分发

- 随发行目录：`build_portable.py` 会把整个 `plugins\` 复制到 `dist\PromptStudio\plugins\`。
- 单独分发：把插件目录打成 zip（内含 `plugin.json` 与它的子文件，可在 zip 里再套一层目录），用户用「安装插件（zip）」导入。

---

## 9. 最小可运行示例

模板插件：

```
plugins/hello/
├─ plugin.json   {"id":"hello","name":"你好插件","intro":"你是提示词工程师","spec_file":"spec.md"}
└─ spec.md       写清「按什么结构产出提示词」
```

代码插件：

```
plugins/hello_tool/
├─ plugin.json   {"id":"hello_tool","name":"你好工具","entry":"plugin.py"}
└─ plugin.py     def register(ctx): ctx.tool("hi","打招呼", lambda text, p: "你好：" + text)
```

带界面插件：再补 `web/panel.js`（`PSPlugin.addPanel`）与 `web/panel.css`，并在 `plugin.json` 里写 `web{js,css,mount,title}`。
