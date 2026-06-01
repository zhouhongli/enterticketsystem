# Docker 部署问题记录

记录 Docker 容器化部署过程中遇到的所有问题与解决方案。

---

## 问题 1：Python 容器内 setuptools 缺失导致构建失败

**现象**：`docker compose build` 时报错，pip 安装依赖时提示找不到 setuptools。

**原因**：`python:3.10-slim` 镜像默认不包含 setuptools，而项目依赖安装需要。

**解决**：Dockerfile 中 RUN 命令增加 `pip install --no-cache-dir setuptools`。

---

## 问题 2：start.sh 行尾 CRLF 导致 bash 执行失败

**现象**：在 Ubuntu 服务器上执行 `./start.sh` 时报 `bad interpreter` 或 `command not found` 类错误。

**原因**：Windows 下编辑的 `.sh` 文件使用了 CRLF 行尾，Linux bash 将 `\r` 视为命令名的一部分。

**解决**：
- 服务器端临时修复：`sed -i 's/\r$//' start.sh`
- 永久修复：添加 `.gitattributes` 强制 `*.sh` 使用 LF 行尾：

```gitattributes
*.sh text eol=lf
Dockerfile text eol=lf
docker-compose* text eol=lf
.dockerignore text eol=lf
.env* text eol=lf
```

---

## 问题 3：Docker 镜像名称不符合预期

**现象**：镜像名变成了 `ftp-ticket-system_ticket-system` 之类，与预期不符。

**原因**：docker-compose.yml 未指定 `image` 字段时，Compose 默认使用 `<项目目录名>_<服务名>` 作为镜像名。项目最初目录名为 `ftp-ticket-system`。

**解决**：在 docker-compose.yml 中显式指定 `image: enterticketsystem:latest`。

---

## 问题 4：容器内首页 404

**现象**：部署后访问 `http://localhost:8000` 返回 404。

**原因**：`config.py` 中 `PROJECT_ROOT = BACKEND_ROOT.parent` 在容器内 `/app` 的父目录是根目录 `/`，而 `frontend/` 实际在 `/app/frontend/`，导致 `PROJECT_ROOT / "frontend"` 解析为 `/frontend`（不存在）。

本地开发时 `BACKEND_ROOT` 是 `.../backend`，`.parent` 才是项目根目录，所以本地正常。

**解决**：config.py 改为自动检测：

```python
_PROJECT_PARENT = BACKEND_ROOT.parent
PROJECT_ROOT = BACKEND_ROOT if (BACKEND_ROOT / "frontend").exists() else _PROJECT_PARENT
```

容器内 BACKEND_ROOT=`/app` 且 `/app/frontend` 存在 → PROJECT_ROOT=`/app`，正确。

---

## 问题 5：容器启动后预置数据为空

**现象**：容器启动成功，页面正常加载，但登录页看不到预置的测试用户，登录后也没有工单数据。

**原因**：`seed.py` 硬编码了 `DATA_FILE = "data/store.json"` 相对路径，而主程序通过环境变量 `TICKET_DATA_FILE=/app/data/store.json` 指定路径。seed 脚本写入的文件和主程序读取的文件不一致。

**解决**：seed.py 改为使用 `get_settings().data_file_path`，与主程序统一配置源：

```python
from app.config import get_settings

def seed() -> None:
    settings = get_settings()
    store = JsonFileStore(settings.data_file_path)
```

**重建容器注意**：需先删除旧 volume（`docker volume rm enterticketsystem_ticket-data`），否则 entrypoint 会检测到已有数据文件而跳过 seed。

---

## 问题 6：前端 CSS 和 JS 资源无法加载

**现象**：登录页面 HTML 能加载，但无样式（无边框、无按钮样式），点击登录按钮无响应，页面提示"网络连接失败"。

**原因**：同问题 4。config.py 中 PROJECT_ROOT 解析错误导致 `/assets` 静态文件挂载路径指向了不存在的目录，CSS 和 JS 文件全部 404。

**解决**：同问题 4 的 config.py 修复。重建容器后 `/assets` 正确挂载到 `/app/frontend/assets`。

---

## 完整重建流程

每次修复后需要完整重建：

```bash
docker compose down
docker volume rm enterticketsystem_ticket-data
docker compose build --no-cache
docker compose up -d
docker compose logs --tail=30
```

或使用一键脚本（需先手动删除 volume）：
```bash
docker volume rm enterticketsystem_ticket-data
./start.sh
```

---

## 预置测试账号

seed 脚本创建的默认账号（首次启动自动生成）：

| 用户名 | 邮箱 | 密码 | 角色 |
|--------|------|------|------|
| admin | admin@enterticket.com | Admin@12345 | 管理员 |
| 客服小王 | agent_a@enterticket.com | Agent@12345 | 客服 |
| 客服小李 | agent_b@enterticket.com | Agent@12345 | 客服 |
| 张三 | customer_x@enterticket.com | User@12345 | 客户 |
| 李四 | customer_y@enterticket.com | User@12345 | 客户 |

预置 5 个工单（硬件故障、软件问题、网络异常、退换货、审批流程），覆盖待分配、处理中、已解决、已关闭四种状态。
