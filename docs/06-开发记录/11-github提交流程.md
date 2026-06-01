# Git + GitHub 提交方案说明

## 一、基本概念

### Git 是什么

Git 是一个**分布式版本控制系统**。它记录你项目中所有文件的每一次修改历史。

### 本地仓库 vs 远程仓库

| 概念 | 位置 | 说明 |
| --- | --- | --- |
| 本地仓库 | 你的电脑（`.git` 目录） | 存放所有代码的历史记录 |
| 远程仓库 | GitHub 服务器 | 本地仓库的网络副本，供他人查看和协作 |

### 为什么先在本地提交，再推送到远程

Git 是**先本地后远程**的工作方式：

```
你写的代码 → git add → git commit（存到本地 .git） → git push（上传到 GitHub）
```

不存在"直接提交到远程"这回事。所有提交首先存在本地，然后你选择性地推送到远程。

---

## 二、工作流程详解

### 第 1 步：初始化仓库（`git init`）

```bash
git init
```

**做了什么**：在项目根目录创建 `.git` 文件夹。

**`.git` 里存了什么**：
- **objects**：压缩后的文件快照（你的代码内容）
- **refs**：分支和标签指向哪个 commit
- **HEAD**：当前在哪个分支
- **config**：仓库级别的配置

**`.git` 里看不到源码是正常的**——源码以压缩编码的二进制格式存在 objects 中。你的原始代码仍然在项目目录中原封不动。

### 第 2 步：创建 .gitignore

**.gitignore 的作用**：告诉 git 哪些文件**不要**纳入版本管理。

```
.venv/              # Python 虚拟环境（几百MB，不同机器不同）
__pycache__/        # Python 运行缓存（自动生成）
backend/data/store.json  # 业务数据文件（不能公开）
backend/data/*.log  # 临时日志文件
.env                # 可能包含真实密码
```

**为什么排除这些**：

- 虚拟环境和缓存是**每次运行自动生成的**，不需要版本控制，换台电脑重新生成即可
- 数据文件和 `.env` 可能包含**敏感信息**，不应该公开

### 第 3 步：添加文件（`git add`）

```bash
git add -A
```

**做了什么**：把所有符合 `.gitignore` 规则的文件添加到**暂存区**（staging area）。

**暂存区是什么**：一个中间状态，标记"哪些文件要进入下一次提交"。

**结果**：245 个文件被标记，总共 28227 行代码。

### 第 4 步：提交（`git commit`）

```bash
git commit -m "提交说明"
```

**做了什么**：

1. 把暂存区中所有文件的内容压缩存入 `.git/objects`
2. 创建一个 commit 对象，包含：
   - 提交说明
   - 提交者信息（用户名、邮箱）
   - 时间戳
   - 父 commit（首次提交没有父）
   - 指向暂存区内容的树对象（tree）
3. 更新当前分支指针到这个新 commit

**结果**：commit `c457684` 创建成功，所有代码历史存入了本地 `.git` 数据库。

**此时代码只存在于你的电脑上**，GitHub 上什么都没有。

### 第 5 步：关联远程仓库（`git remote add`）

```bash
git remote add origin https://github.com/zhouhongli/enterticketsystem.git
```

**做了什么**：给远程仓库起一个别名 `origin`，后续可以用 `git push origin main` 推送。

**`origin` 只是别名**，你可以叫任何名字，但 `origin` 是惯例。

### 第 6 步：重命名分支（`git branch -M`）

```bash
git branch -M main
```

**做了什么**：把本地默认分支名从 `master` 改为 `main`，与 GitHub 的默认分支名一致。

### 第 7 步：推送（`git push`）

```bash
git push -u origin main
```

**做了什么**：

1. 读取本地 `main` 分支上的所有 commit
2. 通过 HTTPS 连接到 `github.com`
3. 进行身份认证（见下方认证原理）
4. 把所有 commit 上传到远程仓库
5. 远程仓库的 `main` 分支指向这些 commit
6. 本地记录跟踪关系（`-u` 参数），下次直接 `git push` 即可

**`-u` 的含义**：建立"上游"（upstream）跟踪关系。之后推送同一个远程分支时，只需 `git push`，不用重复写 `origin main`。

---

## 三、认证原理

### 为什么不需要手动输入 Token

执行 `git push` 时，没有要求输入用户名或密码，是因为：

**Git Credential Manager（GCM）** 已经保存了 GitHub 的认证凭据。

### GCM 是什么

Windows 上 git 默认使用的凭据管理工具。它的工作流程：

```
git push → GCM 检查凭据 → 找到已保存的 Token → 自动附加到请求 → GitHub 验证通过
```

### 凭据保存在哪里

Windows **凭据管理器**（Credential Manager）：

1. 搜索并打开 "Credential Manager"
2. 选择 "Windows 凭据"
3. 找到 `git:https://github.com` 条目

里面保存的是一个 **OAuth 访问令牌**或 **Personal Access Token（PAT）**，格式类似 `gho_xxxxxxxx`。

### 它不是你的 GitHub 密码

GCM 保存的是**令牌（Token）**，不是你的登录密码。令牌是你在某个时刻授权 git 操作时生成的，具有特定的权限范围和过期时间。

### 如何查看和管理凭据

**Windows 端**：
- 打开凭据管理器 → Windows 凭据 → 找到 `git:https://github.com` → 查看或删除

**GitHub 端**：
- 打开 https://github.com/settings/tokens → 查看已生成的令牌
- 打开 https://github.com/settings/applications → 查看已授权的应用

**安全建议**：如果不确定凭据的有效期或权限，可以在 GitHub 设置中撤销，下次 git 操作时会重新授权。

---

## 四、当前状态

| 项目 | 状态 |
| --- | --- |
| 本地 git 仓库 | ✅ 已初始化，commit `c457684` |
| 本地文件 | ✅ 245 个文件已提交 |
| .gitignore | ✅ 已配置，排除敏感文件 |
| 远程关联 | ✅ `origin` → `https://github.com/zhouhongli/enterticketsystem.git` |
| GitHub 推送 | ✅ 245 个文件已上传 |
| 公开地址 | https://github.com/zhouhongli/enterticketsystem |

---

## 六、分支创建与推送

### 第 8 步：创建开发分支（`git checkout -b`）

```bash
git checkout -b dev
```

**做了什么**：

1. 基于当前分支（`main`）的最新 commit 创建一个新分支 `dev`
2. 自动切换到 `dev` 分支，后续所有 commit 都会在这个分支上

**分支是什么**：指向某个 commit 的指针。同一份代码可以有多个分支，每个分支独立演进。

**`dev` 分支的用途**：在 `dev` 上进行迭代开发，开发完成并测试通过后，合并回 `main`。

### 第 9 步：推送分支到远程（`git push -u`）

```bash
git push -u origin dev
```

**做了什么**：把本地 `dev` 分支上传到 GitHub，并建立跟踪关系。

**推送结果**：GitHub 上出现 `dev` 分支，地址：`https://github.com/zhouhongli/enterticketsystem/tree/dev`

### 实际执行记录

| 操作 | 结果 |
| --- | --- |
| `git checkout -b dev` | ✅ 切换到 dev 分支 |
| `git push -u origin dev`（第1次） | ❌ 网络超时 |
| `git push -u origin dev`（第2次） | ❌ 网络超时 |
| `git push -u origin dev`（第3次） | ✅ 成功，`[new branch] dev -> dev` |

---

## 七、当前状态

| 项目 | 状态 |
| --- | --- |
| 本地 git 仓库 | ✅ 已初始化 |
| 本地分支 | ✅ `main`（稳定版）+ `dev`（开发版） |
| 远程分支 | ✅ `origin/main` + `origin/dev` |
| 公开地址 | https://github.com/zhouhongli/enterticketsystem |

---

## 八、后续常用操作

| 操作 | 命令 | 说明 |
| --- | --- | --- |
| 查看修改 | `git status` | 查看哪些文件被修改了 |
| 添加修改 | `git add <文件>` | 把修改的文件加入暂存区 |
| 提交修改 | `git commit -m "说明"` | 创建新 commit |
| 推送到远程 | `git push` | 上传到 GitHub（已建立上游关系） |
| 拉取远程更新 | `git pull` | 从 GitHub 下载并合并最新代码 |
| 查看历史 | `git log --oneline` | 查看提交记录 |
| 添加远程 | `git remote add origin <URL>` | 关联远程仓库 |
| 查看远程 | `git remote -v` | 查看已配置的远程地址 |
