# 发布到 GitHub 操作手册

这份手册描述怎么把 PromptStudio 的**源码**和**安装包**发到 GitHub。
仓库里只放源码（几 MB），二进制走 Releases；本机开发用的 `dist\`、`build\`、`models\`、`runtime\`、`data\`、`work\` 都不入库（见 `.gitignore`）。

---

## 0. 一次性准备

```powershell
# 装 Git（已装可跳过）
winget install --id Git.Git -e --source winget

# 让当前窗口认识 git
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
git --version

# 提交身份（只需一次，写进 ~/.gitconfig）
git config --global user.name  "minut"
git config --global user.email "你的GitHub邮箱"
git config --global core.autocrlf false      # 别让 git 改换行
git config --global core.quotepath false     # 中文文件名不转义
```

可选但推荐：装 GitHub CLI，后面建仓、发 Release 一条命令搞定。

```powershell
winget install --id GitHub.cli -e --source winget
gh auth login          # 选 GitHub.com → HTTPS → 浏览器登录
```

---

## 1. 初始化本地仓库（本机已可执行，不联网）

```powershell
cd E:\新建文件夹\prompt-studio

git init -b main
git add -A
git status --short        # 先看一眼：不该出现 dist/、build/、models/、runtime/、data/
git commit -m "PromptStudio 1.1：提示词工作室（多模型规范改写 + 本地模型 + ComfyUI 插件）"
```

查看这次提交到底收了什么：

```powershell
git ls-files | Measure-Object -Line           # 文件数（预期几百，不是上万）
git ls-files | Select-String -Pattern 'dist/|build/|models/|runtime/|data/'   # 必须为空
du -sh (git ls-files) 2>$null                 # 或用下面这条更准
(git ls-files | ForEach-Object { (Get-Item $_).Length } | Measure-Object -Sum).Sum / 1MB
```

---

## 2. 建远程仓库并推送

**方式 A：用 gh（推荐）**

```powershell
cd E:\新建文件夹\prompt-studio
gh repo create prompt-studio --public --source . --remote origin --push `
   --description "提示词工作室：把一句话改写成 H3 / Qwen Image / MOSS / Z-Image 规范提示词，内置本地模型与 ComfyUI 插件"
git push -u origin main
```

**方式 B：网页建仓 + 手动加 remote**

1. 打开 https://github.com/new ，仓库名 `prompt-studio`，选 **Public**，**不要**勾 "Add a README / .gitignore / license"（本地已有）。
2. 然后：

```powershell
cd E:\新建文件夹\prompt-studio
git remote add origin https://github.com/<你的用户名>/prompt-studio.git
git push -u origin main
```

> 第一次 push 会要凭据。Git for Windows 会弹浏览器让登录，或让你填 **Personal Access Token**（GitHub → Settings → Developer settings → Personal access tokens → Fine-grained，勾 `Contents: Read and write`）。密码认证早已停用，只能用 token。

---

## 3. 打版本标签

```powershell
git tag -a v1.1.0 -m "PromptStudio 1.1.0"
git push origin v1.1.0
```

版本号口径：`v主.次.修`；改界面/功能升次，只修 bug 升修。

---

## 4. 打包发布物（本机执行）

```powershell
python tools\release_pack.py
```

产出在 `dist\release\`：

| 文件 | 说明 |
|---|---|
| `PromptStudio-1.1-src.zip` | 源码包（不含 dist/build/models/runtime/data，几 MB） |
| `PromptStudio-Setup-1.1.exe` | 安装器（43.5 MB） |
| `PromptStudio-Setup-1.1.payload.zip.part1 … part4` | 安装数据分卷（每个 1.6 GB，GitHub 单文件上限 2 GB） |
| `SHA256SUMS.txt` | 上面所有文件的校验值 |
| `合并并安装.bat` | 用户侧脚本：把分卷合成完整 payload 再启动安装器 |

---

## 5. 发 Release 并上传

**方式 A：gh**

```powershell
gh release create v1.1.0 dist\release\* `
   --title "PromptStudio 1.1.0" `
   --notes-file docs\RELEASE_NOTES_1.1.0.md
```

**方式 B：网页**

仓库 → Releases → Draft a new release → 选 tag `v1.1.0` → 标题、说明 → 把 `dist\release\` 里的文件全部拖进 Attachments → Publish。

> 上传 4 个 1.6 GB 分卷大概要一段时间；中途断了就重传那一个文件。
> Release 说明可以直接用 `README.md` 的开头几节，或写一份变更清单。

---

## 6. 用户侧怎么用（写进 README / Release 说明）

1. 到 Releases 下载 **全部** `PromptStudio-Setup-1.1.*` 文件（1 个 exe + 4 个 part）到同一个文件夹。
2. 双击 `合并并安装.bat`（或手动：`copy /b part1+part2+part3+part4 payload.zip`）。
3. 双击 `PromptStudio-Setup-1.1.exe`，选安装目录，装完即可用。
4. 首次启动会检查运行环境：缺 CUDA/CPU 版 llama.cpp 会提示安装（内置 6 个预编译包，也可自行下载放入 `runtime\packs\`）。
5. 本地模型（.gguf）不随包分发，在「设置 → 本地模型」里指向你自己的文件即可。

---

## 7. 以后每次更新

```powershell
cd E:\新建文件夹\prompt-studio
python compile_check.py                # 语法自检
git add -A
git commit -m "修复：xxx"
git push
python tools\release_pack.py          # 重新打包
git tag -a v1.1.1 -m "PromptStudio 1.1.1"
git push origin v1.1.1
gh release create v1.1.1 dist\release\* --title "PromptStudio 1.1.1" --notes "…"
```

---

## 8. 不要提交的东西（本仓库已用 .gitignore 挡住）

- `dist\`（绿色版 + 安装包，25 GB）、`build\`（PyInstaller 中间件，6.6 GB）
- `models\`（.gguf，约 4 GB）、`runtime\`（预编译 llama.cpp，1.3 GB）
- `data\`（你的配置、历史、插件数据）、`work\`（临时工作区）
- `plugins\pose_gallery\`、`plugins\comfy_runner\`（自制插件，按决定不发布）
- `__pycache__`、`*.pyc`、`tools\*.exe`、`tmp_*.py`

如果哪天手滑把大文件 commit 了：`git rm --cached <路径>` 再 `git commit --amend`；已经 push 的话要用 `git filter-repo` 清历史，或者干脆删库重建（最省事）。

---

## 9. 许可证与商用

仓库根目录的 `LICENSE` 是**自定义非商业许可**：别人可以免费用、改、装插件、再分发，但**不能商用**（销售、付费分发、SaaS 收费、企业内部生产使用都要单独授权）。GitHub 会把它标成 "Other" —— 这是正常的，自定义许可都会这样。

需要开放的商业授权范围写进 `LICENSE` 第三节，或单独放 `COMMERCIAL.md`。
