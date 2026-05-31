# 企业售后工单系统 MVP

个人客户提交售后工单，内部客服处理并关闭的单体 Web 应用。

## 功能边界

### 已实现

- 三类用户（客户、客服、管理员）注册/登录/退出
- 管理员初始化（环境变量配置，首次启动自动创建）
- 问题分类管理（新增、编辑、启用/停用）
- 客服账号管理（创建，密码由管理员设定）
- 客户账号管理（启用/禁用，禁用后自动撤销会话）
- 客户建单（选择启用分类，标题+描述）
- 客户工单列表/详情/公开留言
- 内部工单列表（按单一状态筛选）/详情
- 工单分配/重新分配（仅管理员）
- 内部公开留言（仅负责人或管理员）
- 线性状态推进：待分配 → 处理中 → 已解决 → 已关闭
- 工单操作记录（创建、分配、状态变更）
- 角色导航与页面权限隔离
- 表单校验、错误/成功反馈、空状态、确认提示

### 不实现（MVP 范围外）

附件、外部通知、SLA、统计报表、高级搜索、多条件筛选、批量操作、导出、客户确认关闭/取消/退回/重开、自动关闭、密码找回、多因素认证、验证码、登录锁定、关系型数据库迁移、多实例并发写入。

## 快速开始

### 环境要求

- Python 3.10+
- 现代浏览器（Chrome / Edge）

### 安装

```bash
cd backend
pip install -e ".[dev]"
```

### 配置初始管理员

通过环境变量配置首个管理员账号：

```bash
# Windows PowerShell
$env:INITIAL_ADMIN_USERNAME="admin"
$env:INITIAL_ADMIN_EMAIL="admin@example.com"
$env:INITIAL_ADMIN_PASSWORD="your-secure-password"

# Linux / macOS
export INITIAL_ADMIN_USERNAME="admin"
export INITIAL_ADMIN_EMAIL="admin@example.com"
export INITIAL_ADMIN_PASSWORD="your-secure-password"
```

系统启动时，若尚无管理员账号，会自动创建。已有管理员后不会重复创建。

### 启动

```bash
cd backend
uvicorn app.main:app --reload
```

访问 http://localhost:8000 ，自动跳转登录页。

### 运行测试

```bash
cd backend
pytest                    # 全部测试
pytest tests/api/ -v      # API 集成测试
pytest tests/ -k test_login -v  # 指定测试函数
```

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | FastAPI（单进程） |
| 前端 | 原生 HTML / CSS / JavaScript 多页面应用 |
| 持久化 | JSON 文件（`backend/data/store.json`），原子写入 + 线程锁 |
| 认证 | 服务端会话，HttpOnly / SameSite=Lax Cookie，8 小时 TTL |
| 密码 | Argon2id 哈希 |
| 标识 | UUID v4；UTC ISO 8601 时间戳 |

## 架构分层

```
API 路由 → 应用服务 → 仓储协议 → JSON 存储适配器
```

业务服务面向 `JsonRepository` 协议工作，不直接操作文件，未来可替换为关系型数据库实现。

## 工单状态机

```
待分配 → 处理中 → 已解决 → 已关闭
```

仅支持线性推进，不支持跳级、回退、取消或重开。

## 运行限制

- **单进程写入**：仅支持一个应用进程操作数据文件，不启用多工作进程。
- **数据文件位置**：`backend/data/store.json`，不可由浏览器直接访问。
- **会话存储**：内存 + JSON 文件持久化，应用重启后可恢复。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `企业售后工单系统` | 应用名称 |
| `APP_ENV` | `local` | 运行环境 |
| `TICKET_DATA_FILE` | `backend/data/store.json` | 数据文件路径 |
| `SESSION_COOKIE_NAME` | `ticket_session` | 会话 Cookie 名 |
| `SESSION_COOKIE_SECURE` | `false` | 是否启用 Secure 标记（本地开发为 false） |
| `SESSION_TTL_HOURS` | `8` | 会话有效期（小时） |
| `INITIAL_ADMIN_USERNAME` | `""` | 初始管理员用户名 |
| `INITIAL_ADMIN_EMAIL` | `""` | 初始管理员邮箱 |
| `INITIAL_ADMIN_PASSWORD` | `""` | 初始管理员密码 |

## 目录概览

```
backend/
  pyproject.toml              # 项目依赖与测试配置
  app/
    main.py                   # FastAPI 应用入口
    config.py                 # 配置加载
    api/routes/               # 路由：auth, admin, categories, customer, internal
    services/                 # 业务用例编排
    domain/                   # 领域规则（枚举、状态机、模型工厂）
    repositories/             # 仓储协议 + JSON 适配器
    security/                 # 密码哈希、会话管理
    storage/                  # JSON 原子读写
  tests/                      # 单元、服务、API、存储测试

frontend/
  pages/                      # HTML 页面（公共、客户、内部、管理）
  assets/css/                 # 全局样式
  assets/js/                  # 共享 JavaScript 模块
```
